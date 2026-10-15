import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
HEADERS = {"User-Agent": "FuelRoutePlannerAssessment/1.0"}
METERS_PER_MILE = 1609.344
TIMEOUT = 15


def geocode_location(location):
    """Convert a US place name like 'New York, NY' into (latitude, longitude).
    Return None if the place is not found."""
    response = requests.get(
        NOMINATIM_URL,
        params={
            "q": location,
            "countrycodes": "us",
            "format": "json",
            "limit": 1,
        },
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    results = response.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def get_route(start_coords, end_coords):
    """Ask OSRM one time for the driving route between two pins.
    Return distance, duration and the route geometry (the map line)."""
    start_lat, start_lon = start_coords
    end_lat, end_lon = end_coords

    # Careful: OSRM wants longitude first, then latitude.
    url = f"{OSRM_URL}/{start_lon},{start_lat};{end_lon},{end_lat}"
    response = requests.get(
        url,
        params={"overview": "full", "geometries": "geojson"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    routes = response.json().get("routes", [])
    if not routes:
        return None

    route = routes[0]
    return {
        "distance_miles": route["distance"] / METERS_PER_MILE,
        "duration_seconds": route["duration"],
        "geometry": route["geometry"],  # the route map (GeoJSON line)
    }
