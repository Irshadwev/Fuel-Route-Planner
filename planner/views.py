import requests
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .services.optimiser import MPG, MAX_RANGE_MILES, optimise_fuel_stops
from .services.routing import geocode_location, get_route
from .services.stations import get_stations_along_route


def public_station(station):
    """The fields of one station that we show in the API response."""
    return {
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
    }


@api_view(["POST"])
def plan_route(request):
    start = request.data.get("start")
    destination = request.data.get("destination")

    if not isinstance(start, str) or not start.strip():
        return Response(
            {"error": "'start' is required and must be a non-empty string."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(destination, str) or not destination.strip():
        return Response(
            {"error": "'destination' is required and must be a non-empty string."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        start_coords = geocode_location(start.strip())
        end_coords = geocode_location(destination.strip())
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
    except requests.RequestException:
        return Response(
            {"error": "A map service request failed. Please try again."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    route_miles = route["distance_miles"]
    stations = get_stations_along_route(route["geometry"])
    plan = optimise_fuel_stops(stations, route_miles)

    if plan is None:
        return Response(
            {
                "error": (
                    "Could not build a fuel plan: no station near the start, "
                    "or stations cannot connect this route within the "
                    "500-mile range."
                ),
                "route_distance_miles": round(route_miles, 2),
                "stations_found": len(stations),
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return Response({
        "start": start.strip(),
        "destination": destination.strip(),
        "route_distance_miles": round(route_miles, 2),
        "duration_seconds": route["duration_seconds"],
        "fuel_economy_mpg": MPG,
        "maximum_range_miles": MAX_RANGE_MILES,
        "route_geometry": route["geometry"],
        "initial_fill": public_station(plan["initial_fill"]),
        "initial_fill_assumption": (
            "The car starts with a full tank bought at the cheapest "
            "station near the start."
        ),
        "fuel_stops": [public_station(s) for s in plan["stops"]],
        "estimated_gallons": round(route_miles / MPG, 2),
        "estimated_fuel_cost": plan["estimated_fuel_cost"],
        "stations_considered": len(stations),
    })
