"""Find the supplied fuel stations near an OSRM route efficiently."""

from collections import defaultdict
import math

from planner.models import FuelStation
from planner.services.us import US_STATE_CODES

MAX_DISTANCE_FROM_ROUTE_MILES = 10
GRID_DEGREES = 0.25
GRID_NEIGHBOUR_CELLS = 2
MAX_SEGMENT_MILES = 2
MILES_PER_LATITUDE_DEGREE = 69.172


def haversine_miles(point_a, point_b):
    """Return the great-circle distance between two ``(longitude, latitude)`` points."""
    lon1, lat1 = point_a
    lon2, lat2 = point_b

    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlat = lat2 - lat1
    dlon = math.radians(lon2 - lon1)
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(value)))


def build_route_segments(geometry, route_miles):
    """Split the route line into short segments with *road-mile* positions.

    OSRM reports driving distance, whereas a GeoJSON line is measured as
    straight-line geometry. We preserve the geometry's position along the
    route but scale it to OSRM's authoritative distance. This prevents the
    old code's Haversine route-mile values from disagreeing with the 500-mile
    range rule.
    """
    coordinates = geometry.get("coordinates", []) if geometry else []
    if len(coordinates) < 2 or route_miles <= 0:
        return []

    raw_segments = []
    geometry_miles = 0.0
    for first, second in zip(coordinates, coordinates[1:]):
        try:
            start = (float(first[0]), float(first[1]))
            end = (float(second[0]), float(second[1]))
        except (IndexError, TypeError, ValueError):
            continue
        line_miles = haversine_miles(start, end)
        if line_miles:
            raw_segments.append((start, end, line_miles))
            geometry_miles += line_miles

    if not raw_segments or geometry_miles <= 0:
        return []

    road_per_geometry_mile = route_miles / geometry_miles
    route_position = 0.0
    segments = []
    for start, end, line_miles in raw_segments:
        road_miles = line_miles * road_per_geometry_mile
        pieces = max(1, math.ceil(line_miles / MAX_SEGMENT_MILES))
        for piece in range(pieces):
            start_fraction = piece / pieces
            end_fraction = (piece + 1) / pieces
            part_start = _interpolate(start, end, start_fraction)
            part_end = _interpolate(start, end, end_fraction)
            part_miles = road_miles / pieces
            segments.append((part_start, part_end, route_position, part_miles))
            route_position += part_miles

    # Avoid an accumulated floating-point error at the destination.
    if segments:
        start, end, position, _ = segments[-1]
        segments[-1] = (start, end, position, route_miles - position)
    return segments


def _interpolate(start, end, fraction):
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )


def _grid_key(point):
    lon, lat = point
    return math.floor(lon / GRID_DEGREES), math.floor(lat / GRID_DEGREES)


def _grid_keys_for_segment(start, end):
    """Cells within one grid cell of a short segment.

    Two neighbouring cells cover the 10-mile radius even at Alaska's northern
    latitudes, where one degree of longitude is relatively short. This avoids
    a station-by-route-point full scan.
    """
    start_lon_cell, start_lat_cell = _grid_key(start)
    end_lon_cell, end_lat_cell = _grid_key(end)
    for lon_cell in range(min(start_lon_cell, end_lon_cell) - GRID_NEIGHBOUR_CELLS,
                          max(start_lon_cell, end_lon_cell) + GRID_NEIGHBOUR_CELLS + 1):
        for lat_cell in range(min(start_lat_cell, end_lat_cell) - GRID_NEIGHBOUR_CELLS,
                              max(start_lat_cell, end_lat_cell) + GRID_NEIGHBOUR_CELLS + 1):
            yield lon_cell, lat_cell


def _project_onto_segment(point, start, end):
    """Return ``(fraction_along_segment, distance_miles)`` for a short segment."""
    lon, lat = point
    start_lon, start_lat = start
    end_lon, end_lat = end
    longitude_scale = MILES_PER_LATITUDE_DEGREE * math.cos(
        math.radians((start_lat + end_lat + lat) / 3)
    )
    x = (lon - start_lon) * longitude_scale
    y = (lat - start_lat) * MILES_PER_LATITUDE_DEGREE
    dx = (end_lon - start_lon) * longitude_scale
    dy = (end_lat - start_lat) * MILES_PER_LATITUDE_DEGREE
    length_squared = dx * dx + dy * dy
    fraction = 0.0 if length_squared == 0 else (x * dx + y * dy) / length_squared
    fraction = max(0.0, min(1.0, fraction))
    closest = _interpolate(start, end, fraction)
    return fraction, haversine_miles(point, closest)


def get_stations_along_route(
    geometry, route_miles, max_distance_miles=MAX_DISTANCE_FROM_ROUTE_MILES
):
    """Return US stations close to the route with an accurate road-mile position.

    The route is indexed into small geographic cells. Each station is compared
    only to adjacent short route segments, not to every coordinate in a long
    cross-country route.
    """
    segments = build_route_segments(geometry, route_miles)
    if not segments:
        return []

    segments_by_cell = defaultdict(list)
    for index, (start, end, _, _) in enumerate(segments):
        for cell in _grid_keys_for_segment(start, end):
            segments_by_cell[cell].append(index)

    station_fields = (
        "station_id", "name", "address", "city", "state", "price",
        "latitude", "longitude", "location_source",
    )
    station_rows = FuelStation.objects.filter(state__in=US_STATE_CODES).values(*station_fields)
    stations = []
    for station in station_rows.iterator():
        point = (station["longitude"], station["latitude"])
        nearby_segment_indexes = segments_by_cell.get(_grid_key(point), [])
        if not nearby_segment_indexes:
            continue

        best_distance = float("inf")
        best_route_mile = None
        for index in nearby_segment_indexes:
            start, end, segment_start_mile, segment_miles = segments[index]
            fraction, distance = _project_onto_segment(point, start, end)
            if distance < best_distance:
                best_distance = distance
                best_route_mile = segment_start_mile + fraction * segment_miles

        if best_distance > max_distance_miles:
            continue

        stations.append({
            **station,
            "route_mile": best_route_mile,
            "distance_from_route_miles": round(best_distance, 2),
        })

    stations.sort(key=lambda item: item["route_mile"])
    return stations
