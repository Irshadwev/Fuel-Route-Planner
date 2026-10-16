"""Cached, US-only geocoding and one-call OSRM routing."""

import hashlib

import requests
from django.core.cache import cache

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
HEADERS = {"User-Agent": "FuelRoutePlannerAssessment/1.0 (assessment project)"}
METERS_PER_MILE = 1609.344
TIMEOUT = (3.05, 8)
GEOCODE_CACHE_SECONDS = 7 * 24 * 60 * 60
ROUTE_CACHE_SECONDS = 24 * 60 * 60


class RoutingServiceError(Exception):
    """The public geocoder or router could not provide a usable response."""


def _cache_key(prefix, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"fuel-route:{prefix}:{digest}"


def _normalise_location(location):
    """Give equivalent user input one cache key without changing its meaning."""
    return " ".join(location.strip().casefold().split())


def geocode_location(location):
    """Return a US location as ``(latitude, longitude)``, or ``None``.

    Results (including a not-found result) are cached. A cache hit eliminates
    an otherwise unnecessary Nominatim request on repeated API calls.
    """
    normalised = _normalise_location(location)
    key = _cache_key("geocode", normalised)
    cached = cache.get(key)
    if cached is not None:
        return tuple(cached["coordinates"]) if cached["found"] else None

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": location,
                "countrycodes": "us",
                "addressdetails": 1,
                "format": "jsonv2",
                "limit": 1,
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingServiceError("US geocoding failed") from exc

    if not isinstance(results, list):
        raise RoutingServiceError("Geocoder returned an invalid response")

    if not results:
        cache.set(key, {"found": False}, GEOCODE_CACHE_SECONDS)
        return None

    result = results[0]
    country_code = result.get("address", {}).get("country_code", "").casefold()
    if country_code != "us":
        cache.set(key, {"found": False}, GEOCODE_CACHE_SECONDS)
        return None

    try:
        coordinates = (float(result["lat"]), float(result["lon"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RoutingServiceError("Geocoder returned invalid coordinates") from exc

    cache.set(key, {"found": True, "coordinates": coordinates}, GEOCODE_CACHE_SECONDS)
    return coordinates


def get_route(start_coords, end_coords):
    """Get a driving route and GeoJSON line with exactly one OSRM request.

    OSRM's reported driving distance is authoritative. Station projection later
    maps each point on this shape to that road distance, rather than treating
    a straight-line distance as a driving distance.
    """
    start_lat, start_lon = start_coords
    end_lat, end_lon = end_coords
    cache_value = f"{start_lat:.6f},{start_lon:.6f};{end_lat:.6f},{end_lon:.6f}"
    key = _cache_key("route", cache_value)
    cached = cache.get(key)
    if cached is not None:
        return cached

    url = f"{OSRM_URL}/{start_lon},{start_lat};{end_lon},{end_lat}"
    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OSRM response must be an object")
        routes = payload.get("routes", [])
    except (requests.RequestException, ValueError) as exc:
        raise RoutingServiceError("Driving route lookup failed") from exc

    if not routes:
        return None

    route = routes[0]
    geometry = route.get("geometry")
    try:
        coordinates = geometry["coordinates"]
        distance_miles = float(route["distance"]) / METERS_PER_MILE
        duration_seconds = float(route["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RoutingServiceError("Router returned an invalid route") from exc

    if len(coordinates) < 2 or distance_miles <= 0:
        return None

    result = {
        "distance_miles": distance_miles,
        "duration_seconds": duration_seconds,
        "geometry": geometry,
    }
    cache.set(key, result, ROUTE_CACHE_SECONDS)
    return result
