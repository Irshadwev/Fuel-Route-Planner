import math

MPG = 10
MAX_RANGE_MILES = 500


def optimise_fuel_stops(stations, route_miles):
    """
    Pick the cheapest sequence of fuel stops for the trip.

    Rules:
    - The car starts with a full tank bought at the cheapest station
      near the start (within the first 25 route miles).
    - The car can never drive more than 500 miles between stops.
    - Every leg costs (leg miles / MPG) x price at the leg's start station.

    Return None if no valid plan exists.
    """
    if not stations:
        return None

    # The starting station: cheapest one in the first 25 miles.
    start_candidates = [s for s in stations if s["route_mile"] <= 25]
    if not start_candidates:
        return None
    start_station = min(start_candidates, key=lambda s: s["price"])
    start_station = {**start_station, "route_mile": 0.0}

    # Stations in the middle of the trip. If two stations are at the
    # same position (same city), keep only the cheaper one.
    by_position = {}
    for station in stations:
        if 0.1 < station["route_mile"] < route_miles:
            key = round(station["route_mile"], 2)
            if key not in by_position or station["price"] < by_position[key]["price"]:
                by_position[key] = station
    nodes = [start_station] + sorted(
        by_position.values(), key=lambda s: s["route_mile"]
    )
    destination_index = len(nodes)

    # Dynamic programming, working backwards from the destination:
    # best[i] = the cheapest cost to finish the trip from station i.
    best = [float("inf")] * (len(nodes) + 1)
    next_node = [None] * (len(nodes) + 1)
    best[destination_index] = 0.0

    for i in range(len(nodes) - 1, -1, -1):
        current_position = nodes[i]["route_mile"]
        for j in range(i + 1, destination_index + 1):
            next_position = (
                route_miles if j == destination_index else nodes[j]["route_mile"]
            )
            leg_miles = next_position - current_position
            if leg_miles > MAX_RANGE_MILES:
                break
            segment_cost = (leg_miles / MPG) * nodes[i]["price"]
            total_cost = segment_cost + best[j]
            if total_cost < best[i]:
                best[i] = total_cost
                next_node[i] = j

    if not math.isfinite(best[0]):
        return None

    # Walk forward from the start, collecting the chosen stops.
    stops = []
    index = 0
    while index != destination_index:
        index = next_node[index]
        if index is None:
            return None
        if index != destination_index:
            stops.append(nodes[index])

    return {
        "initial_fill": start_station,
        "stops": stops,
        "estimated_fuel_cost": round(best[0], 2),
    }
