"""Public API view for creating a cost-effective US fuel plan."""

from concurrent.futures import ThreadPoolExecutor
import hashlib

from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .services.optimiser import MPG, MAX_RANGE_MILES, optimise_fuel_stops
from .services.routing import RoutingServiceError, geocode_location, get_route
from .services.stations import get_stations_along_route

PLAN_CACHE_SECONDS = 30 * 60
MAX_LOCATION_LENGTH = 200


def public_station(station):
    """Return a client-safe station and, when present, its fuel purchase."""
    data = {
        "station_id": station["station_id"],
        "name": station["name"],
        "address": station["address"],
        "city": station["city"],
        "state": station["state"],
        "price_per_gallon": round(station["price"], 3),
        "latitude": station["latitude"],
        "longitude": station["longitude"],
        "route_mile": round(station["route_mile"], 2),
        "distance_from_route_miles": station["distance_from_route_miles"],
        "location_source": station.get("location_source", "city_centroid"),
    }
    if "gallons_purchased" in station:
        data["gallons_purchased"] = round(station["gallons_purchased"], 2)
        data["fuel_cost"] = round(station["fuel_cost"], 2)
    return data


def plan_cache_key(start, destination):
    normalised = f"{' '.join(start.casefold().split())}|{' '.join(destination.casefold().split())}"
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
    return f"fuel-route:plan:{digest}"


def build_map_geojson(route_geometry, initial_fill, fuel_stops):
    """Return a display-ready GeoJSON route plus the selected fuel markers."""
    features = [{
        "type": "Feature",
        "properties": {"kind": "route"},
        "geometry": route_geometry,
    }]
    for label, station in [("initial_fill", initial_fill), *( ("fuel_stop", stop) for stop in fuel_stops )]:
        features.append({
            "type": "Feature",
            "properties": {
                "kind": label,
                "name": station["name"],
                "price_per_gallon": station["price_per_gallon"],
                "route_mile": station["route_mile"],
                "gallons_purchased": station.get("gallons_purchased", 0),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [station["longitude"], station["latitude"]],
            },
        })
    return {"type": "FeatureCollection", "features": features}


@api_view(["POST"])
def plan_route(request):
    """Plan a valid 500-mile-range fuel journey between two US locations."""
    start = request.data.get("start")
    destination = request.data.get("destination")

    for field_name, value in (("start", start), ("destination", destination)):
        if not isinstance(value, str) or not value.strip():
            return Response(
                {"error": f"'{field_name}' is required and must be a non-empty string."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(value.strip()) > MAX_LOCATION_LENGTH:
            return Response(
                {"error": f"'{field_name}' must be {MAX_LOCATION_LENGTH} characters or fewer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    start = start.strip()
    destination = destination.strip()
    cached_plan = cache.get(plan_cache_key(start, destination))
    if cached_plan is not None:
        return Response(cached_plan)

    try:
        # These independent Nominatim lookups overlap, keeping a cold request
        # fast while still making only the permitted two geocoding calls.
        with ThreadPoolExecutor(max_workers=2) as executor:
            start_future = executor.submit(geocode_location, start)
            destination_future = executor.submit(geocode_location, destination)
            start_coords = start_future.result()
            end_coords = destination_future.result()
        if not start_coords or not end_coords:
            return Response(
                {"error": "Could not locate one or both locations in the USA."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        route = get_route(start_coords, end_coords)
        if not route:
            return Response(
                {"error": "No driving route was found."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
    except RoutingServiceError:
        return Response(
            {"error": "A map service request failed. Please try again."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    route_miles = route["distance_miles"]
    stations = get_stations_along_route(route["geometry"], route_miles)
    plan = optimise_fuel_stops(stations, route_miles)
    if plan is None:
        return Response(
            {
                "error": (
                    "Could not build a fuel plan: no station near the start, "
                    "or a station gap exceeds the 500-mile range."
                ),
                "route_distance_miles": round(route_miles, 2),
                "stations_found": len(stations),
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    initial_fill = public_station(plan["initial_fill"])
    fuel_stops = [public_station(station) for station in plan["stops"]]
    response_data = {
        "start": start,
        "destination": destination,
        "route_distance_miles": round(route_miles, 2),
        "duration_seconds": round(route["duration_seconds"]),
        "fuel_economy_mpg": MPG,
        "maximum_range_miles": MAX_RANGE_MILES,
        "route_geometry": route["geometry"],
        "map_geojson": build_map_geojson(route["geometry"], initial_fill, fuel_stops),
        "initial_fill": initial_fill,
        "initial_fill_assumption": (
            "The vehicle begins empty and buys fuel at the cheapest supplied "
            "station within 25 route miles of the start."
        ),
        "fuel_stops": fuel_stops,
        "estimated_gallons": round(plan["estimated_gallons"], 2),
        "estimated_fuel_cost": plan["estimated_fuel_cost"],
        "stations_considered": len(stations),
        "station_location_note": (
            "The supplied price data has city/state but no station coordinates; "
            "pins marked city_centroid are an approximate station location."
        ),
    }
    cache.set(plan_cache_key(start, destination), response_data, PLAN_CACHE_SECONDS)
    return Response(response_data)
