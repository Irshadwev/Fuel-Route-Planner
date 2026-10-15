from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from .services.optimiser import optimise_fuel_stops
from .services.stations import haversine_miles


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
    }


class HaversineTests(SimpleTestCase):
    def test_same_point_is_zero(self):
        point = (-95.0, 35.0)
        self.assertAlmostEqual(haversine_miles(point, point), 0, places=5)

    def test_distance_is_positive(self):
        self.assertGreater(haversine_miles((-95.0, 35.0), (-94.0, 35.0)), 0)


class OptimiserTests(SimpleTestCase):
    def test_short_trip_needs_no_extra_stop(self):
        stations = [make_station("1", 3.00, 0.0)]
        result = optimise_fuel_stops(stations, 100)
        self.assertIsNotNone(result)
        self.assertEqual(result["stops"], [])
        self.assertAlmostEqual(result["estimated_fuel_cost"], 30.00)

    def test_long_trip_picks_cheaper_reachable_station(self):
        stations = [
            make_station("1", 4.00, 0.0),
            make_station("2", 3.00, 400.0),
        ]
        result = optimise_fuel_stops(stations, 700)
        self.assertEqual([s["station_id"] for s in result["stops"]], ["2"])
        self.assertAlmostEqual(result["estimated_fuel_cost"], 250.00)

    def test_no_station_near_start_returns_none(self):
        stations = [make_station("9", 3.00, 100.0)]
        self.assertIsNone(optimise_fuel_stops(stations, 200))


class PlanRouteApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_missing_start_is_400(self):
        response = self.client.post(
            "/api/plan-route/", {"destination": "Chicago, IL"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    @patch("planner.views.get_stations_along_route")
    @patch("planner.views.get_route")
    @patch("planner.views.geocode_location")
    def test_successful_plan(self, mock_geocode, mock_route, mock_stations):
        mock_geocode.side_effect = [(40.7, -74.0), (41.8, -87.6)]
        mock_route.return_value = {
            "distance_miles": 100.0,
            "duration_seconds": 6000,
            "geometry": {"type": "LineString", "coordinates": []},
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
