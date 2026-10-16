from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .models import FuelStation
from .services.optimiser import optimise_fuel_stops
from .services.routing import geocode_location
from .services.stations import build_route_segments, get_stations_along_route, haversine_miles


def make_station(station_id, price, route_mile):
    return {
        "station_id": station_id,
        "name": f"Station {station_id}",
        "address": "Test Address",
        "city": "Test City",
        "state": "TX",
        "price": price,
        "latitude": 35.0,
        "longitude": -95.0,
        "route_mile": route_mile,
        "distance_from_route_miles": 1.0,
        "location_source": "test",
    }


class HaversineTests(SimpleTestCase):
    def test_same_point_is_zero(self):
        point = (-95.0, 35.0)
        self.assertAlmostEqual(haversine_miles(point, point), 0, places=5)

    def test_distance_is_positive(self):
        self.assertGreater(haversine_miles((-95.0, 35.0), (-94.0, 35.0)), 0)


class OptimiserTests(SimpleTestCase):
    def test_short_trip_needs_no_extra_stop(self):
        result = optimise_fuel_stops([make_station("1", 3.00, 0.0)], 100)
        self.assertIsNotNone(result)
        self.assertEqual(result["stops"], [])
        self.assertAlmostEqual(result["estimated_gallons"], 10.0)
        self.assertAlmostEqual(result["estimated_fuel_cost"], 30.00)

    def test_long_trip_picks_cheaper_reachable_station(self):
        stations = [make_station("1", 4.00, 0.0), make_station("2", 3.00, 400.0)]
        result = optimise_fuel_stops(stations, 700)
        self.assertEqual([s["station_id"] for s in result["stops"]], ["2"])
        self.assertAlmostEqual(result["estimated_fuel_cost"], 250.00)
        self.assertAlmostEqual(result["initial_fill"]["gallons_purchased"], 40.0)
        self.assertAlmostEqual(result["stops"][0]["gallons_purchased"], 30.0)

    def test_carries_cheaper_fuel_past_an_expensive_station(self):
        stations = [make_station("1", 2.00, 0.0), make_station("2", 4.00, 400.0)]
        result = optimise_fuel_stops(stations, 700)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["initial_fill"]["gallons_purchased"], 50.0)
        self.assertAlmostEqual(result["stops"][0]["gallons_purchased"], 20.0)
        self.assertAlmostEqual(result["estimated_fuel_cost"], 180.00)

    def test_uses_first_cheaper_station_and_skips_expensive_one(self):
        stations = [
            make_station("1", 4.00, 0.0),
            make_station("2", 5.00, 100.0),
            make_station("3", 2.00, 400.0),
        ]
        result = optimise_fuel_stops(stations, 700)
        self.assertEqual([s["station_id"] for s in result["stops"]], ["3"])
        self.assertAlmostEqual(result["estimated_fuel_cost"], 220.00)

    def test_gap_over_maximum_range_returns_none(self):
        stations = [make_station("1", 3.00, 0.0), make_station("2", 3.00, 501.0)]
        self.assertIsNone(optimise_fuel_stops(stations, 800))

    def test_no_station_near_start_returns_none(self):
        self.assertIsNone(optimise_fuel_stops([make_station("9", 3.00, 100.0)], 200))


class StationProjectionTests(TestCase):
    def setUp(self):
        FuelStation.objects.create(
            station_id="route-station",
            name="Route Station",
            address="I-70 Exit 1",
            city="Test City",
            state="KS",
            price=3.0,
            latitude=40.0,
            longitude=-99.5,
        )
        FuelStation.objects.create(
            station_id="canadian-station",
            name="Not Eligible",
            address="Test",
            city="Test City",
            state="ON",
            price=1.0,
            latitude=40.0,
            longitude=-99.5,
        )

    def test_segment_positions_end_at_osrm_road_distance(self):
        geometry = {"type": "LineString", "coordinates": [[-100.0, 40.0], [-99.0, 40.0]]}
        segments = build_route_segments(geometry, 100.0)
        self.assertAlmostEqual(
            segments[-1][2] + segments[-1][3], 100.0, places=6
        )

    def test_station_position_is_scaled_to_osrm_road_miles(self):
        geometry = {"type": "LineString", "coordinates": [[-100.0, 40.0], [-99.0, 40.0]]}
        stations = get_stations_along_route(geometry, 100.0)
        self.assertEqual([station["station_id"] for station in stations], ["route-station"])
        self.assertAlmostEqual(stations[0]["route_mile"], 50.0, delta=0.5)


class RoutingCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("planner.services.routing.requests.get")
    def test_non_us_geocode_result_is_rejected_and_cached(self, mock_get):
        response = Mock()
        response.json.return_value = [{
            "lat": "43.0", "lon": "-79.0", "address": {"country_code": "ca"},
        }]
        mock_get.return_value = response

        self.assertIsNone(geocode_location("Toronto"))
        self.assertIsNone(geocode_location("Toronto"))
        self.assertEqual(mock_get.call_count, 1)


class PlanRouteApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_missing_start_is_400(self):
        response = self.client.post(
            "/api/plan-route/", {"destination": "Chicago, IL"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_too_long_location_is_400(self):
        response = self.client.post(
            "/api/plan-route/", {"start": "x" * 201, "destination": "Chicago, IL"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("planner.views.get_stations_along_route")
    @patch("planner.views.get_route")
    @patch("planner.views.geocode_location")
    def test_successful_plan_returns_geojson_map_and_purchases(
        self, mock_geocode, mock_route, mock_stations
    ):
        mock_geocode.side_effect = [(40.7, -74.0), (41.8, -87.6)]
        mock_route.return_value = {
            "distance_miles": 100.0,
            "duration_seconds": 6000,
            "geometry": {"type": "LineString", "coordinates": [[-74.0, 40.7], [-87.6, 41.8]]},
        }
        mock_stations.return_value = [make_station("1", 3.00, 0.0)]

        response = self.client.post(
            "/api/plan-route/",
            {"start": "New York, NY", "destination": "Chicago, IL"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["route_distance_miles"], 100.0)
        self.assertEqual(response.data["estimated_fuel_cost"], 30.0)
        self.assertEqual(response.data["initial_fill"]["gallons_purchased"], 10.0)
        self.assertEqual(response.data["map_geojson"]["type"], "FeatureCollection")
        self.assertEqual(len(response.data["map_geojson"]["features"]), 2)

    @patch("planner.views.get_stations_along_route")
    @patch("planner.views.get_route")
    @patch("planner.views.geocode_location")
    def test_completed_plan_is_cached(self, mock_geocode, mock_route, mock_stations):
        mock_geocode.side_effect = [(35.0, -90.0), (36.0, -91.0)]
        mock_route.return_value = {
            "distance_miles": 100.0,
            "duration_seconds": 6000,
            "geometry": {"type": "LineString", "coordinates": [[-90.0, 35.0], [-91.0, 36.0]]},
        }
        mock_stations.return_value = [make_station("1", 3.00, 0.0)]
        payload = {"start": "Memphis, TN", "destination": "Little Rock, AR"}

        first = self.client.post("/api/plan-route/", payload, format="json")
        second = self.client.post("/api/plan-route/", payload, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mock_geocode.call_count, 2)
        mock_route.assert_called_once()
        mock_stations.assert_called_once()
