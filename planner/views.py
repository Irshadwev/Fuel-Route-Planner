
import requests

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status


GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_ROUTING_URL = "https://api.geoapify.com/v1/routing"


def geocode_location(location):
    """Convert a US address or place name into coordinates."""

    response = requests.get(
        GEOAPIFY_GEOCODE_URL,
        params={
            "text": location,
            "filter": "countrycode:us",
            "format": "json",
            "apiKey": settings.GEOAPIFY_API_KEY,
        },
        timeout=15,
    )
    response.raise_for_status()

    results = response.json().get("results", [])

    if not results:
        return None

    result = results[0]
    return {
        "latitude": result["lat"],
        "longitude": result["lon"],
        "formatted_address": result.get("formatted", location),
    }


@api_view(["POST"])
def plan_route(request):
    """Return a driving route between two US locations."""

    start = request.data.get("start")
    destination = request.data.get("destination")

    if not isinstance(start, str) or not start.strip():
        return Response(
            {"error": "A valid start location is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(destination, str) or not destination.strip():
        return Response(
            {"error": "A valid destination is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        start_location = geocode_location(start.strip())
        destination_location = geocode_location(destination.strip())

        if not start_location or not destination_location:
            return Response(
                {"error": "Could not find one or both US locations."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Geoapify expects latitude,longitude for each waypoint.
        waypoints = (
            f"{start_location['latitude']},{start_location['longitude']}"
            f"|{destination_location['latitude']},"
            f"{destination_location['longitude']}"
        )

        response = requests.get(
            GEOAPIFY_ROUTING_URL,
            params={
                "waypoints": waypoints,
                "mode": "drive",
                "apiKey": settings.GEOAPIFY_API_KEY,
            },
            timeout=20,
        )
        response.raise_for_status()
        route_data = response.json()

        features = route_data.get("features", [])
        if not features:
            return Response(
                {"error": "No driving route was found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        route = features[0]
        properties = route["properties"]

        distance_miles = properties["distance"] / 1609.344

        return Response(
            {
                "start": start_location,
                "destination": destination_location,
                "route": {
                    "distance_miles": round(distance_miles, 2),
                    "duration_seconds": round(properties["time"], 2),
                    "geometry": route["geometry"],
                },
                "fuel_stops": [],
                "estimated_fuel_cost": None,
                "message": (
                    "Route calculated successfully. "
                    "Fuel-stop recommendations are not implemented yet."
                ),
            },
            status=status.HTTP_200_OK,
        )

    except requests.Timeout:
        return Response(
            {"error": "The mapping service took too long to respond."},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    except requests.RequestException:
        return Response(
            {"error": "Could not communicate with the mapping service."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
