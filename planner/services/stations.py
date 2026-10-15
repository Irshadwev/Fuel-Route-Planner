import math

from planner.models import FuelStation

MAX_DISTANCE_FROM_ROUTE_MILES = 10
CHECKPOINT_EVERY = 20  # route points are very close together; use every 20th


def haversine_miles(point_a, point_b):
    """Return the distance in miles between two (longitude, latitude) points."""
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


def get_stations_along_route(geometry, max_distance_miles=MAX_DISTANCE_FROM_ROUTE_MILES):
    """Return the database stations that are close to the route,
    each with its position on the trip (route_mile)."""
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) < 2:
        return []

    # Checkpoints along the route, with the trip distance at each one.
    checkpoints = coordinates[::CHECKPOINT_EVERY]
    if checkpoints[-1] != coordinates[-1]:
        checkpoints.append(coordinates[-1])

    cumulative = [0.0]
    for index in range(1, len(checkpoints)):
        cumulative.append(
            cumulative[-1] + haversine_miles(checkpoints[index - 1], checkpoints[index])
        )

    # A quick box around the whole route, so far-away stations are
    # skipped without any distance maths. (0.2 degrees is about 14 miles.)
    lons = [point[0] for point in checkpoints]
    lats = [point[1] for point in checkpoints]
    pad = 0.2
    min_lon, max_lon = min(lons) - pad, max(lons) + pad
    min_lat, max_lat = min(lats) - pad, max(lats) + pad

    stations = []
    for station in FuelStation.objects.all():
        if not (min_lon <= station.longitude <= max_lon
                and min_lat <= station.latitude <= max_lat):
            continue

        point = (station.longitude, station.latitude)
        best_index = min(
            range(len(checkpoints)),
            key=lambda i: haversine_miles(point, checkpoints[i]),
        )
        distance = haversine_miles(point, checkpoints[best_index])
        if distance > max_distance_miles:
            continue

        stations.append({
            "station_id": station.station_id,
            "name": station.name,
            "address": station.address,
            "city": station.city,
            "state": station.state,
            "price": station.price,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "route_mile": cumulative[best_index],
            "distance_from_route_miles": round(distance, 2),
        })

    stations.sort(key=lambda item: item["route_mile"])
    return stations
