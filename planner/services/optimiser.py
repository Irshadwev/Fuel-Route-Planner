"""Cost-optimal fuel purchasing for stations ordered along one route."""

MPG = 10
MAX_RANGE_MILES = 500
TANK_CAPACITY_GALLONS = MAX_RANGE_MILES / MPG
INITIAL_STATION_WINDOW_MILES = 25
POSITION_PRECISION_MILES = 0.01
EPSILON = 1e-8


def optimise_fuel_stops(stations, route_miles):
    """Choose fuel purchases that minimise the total price paid.

    The driver starts empty at the cheapest supplied station near the origin.
    At each station, the standard optimal policy is used: buy just enough to
    reach the first cheaper reachable station; if none exists, fill only as
    much as needed to reach the destination or the 500-mile tank capacity.
    Fuel already in the tank is carried forward, which is essential for true
    price optimisation and was not modelled by the original leg-cost DP.

    Returns ``None`` when the station data cannot make the route with a
    500-mile maximum range.
    """
    if route_miles <= 0 or not stations:
        return None

    start_candidates = [
        station for station in stations
        if station["route_mile"] <= INITIAL_STATION_WINDOW_MILES
    ]
    if not start_candidates:
        return None

    initial_fill = min(start_candidates, key=lambda station: station["price"])
    initial_fill = {**initial_fill, "route_mile": 0.0}
    nodes = [initial_fill] + _deduplicated_route_stations(stations, route_miles)
    destination_index = len(nodes)

    fuel_in_tank = 0.0
    total_gallons = 0.0
    total_cost = 0.0
    purchases = []

    for index, station in enumerate(nodes):
        station_mile = station["route_mile"]
        distance_to_destination = route_miles - station_mile
        if distance_to_destination < -EPSILON:
            return None

        next_mile = (
            route_miles if index + 1 == destination_index
            else nodes[index + 1]["route_mile"]
        )
        distance_to_next = next_mile - station_mile
        if distance_to_next > MAX_RANGE_MILES + EPSILON:
            return None
        if distance_to_next < -EPSILON:
            return None

        target_gallons = _target_fuel_gallons(
            index, nodes, route_miles, station_mile
        )
        if target_gallons > TANK_CAPACITY_GALLONS + EPSILON:
            return None

        gallons_to_buy = max(0.0, target_gallons - fuel_in_tank)
        if gallons_to_buy > EPSILON:
            purchase_cost = gallons_to_buy * station["price"]
            purchase = {
                **station,
                "gallons_purchased": gallons_to_buy,
                "fuel_cost": purchase_cost,
            }
            purchases.append(purchase)
            fuel_in_tank += gallons_to_buy
            total_gallons += gallons_to_buy
            total_cost += purchase_cost

        fuel_required_for_next = distance_to_next / MPG
        if fuel_in_tank + EPSILON < fuel_required_for_next:
            return None
        fuel_in_tank = max(0.0, fuel_in_tank - fuel_required_for_next)

    if not purchases:
        return None

    return {
        "initial_fill": purchases[0],
        "stops": purchases[1:],
        "estimated_gallons": total_gallons,
        "estimated_fuel_cost": round(total_cost, 2),
    }


def _deduplicated_route_stations(stations, route_miles):
    """Keep only the cheapest option at each effectively identical position."""
    by_position = {}
    for station in stations:
        route_mile = station["route_mile"]
        if not (INITIAL_STATION_WINDOW_MILES < route_mile < route_miles):
            continue
        key = round(route_mile / POSITION_PRECISION_MILES)
        current = by_position.get(key)
        if current is None or station["price"] < current["price"]:
            by_position[key] = station
    return sorted(by_position.values(), key=lambda station: station["route_mile"])


def _target_fuel_gallons(index, nodes, route_miles, station_mile):
    """Fuel level to hold after leaving this station under the greedy optimum."""
    distance_to_destination = route_miles - station_mile
    if distance_to_destination <= MAX_RANGE_MILES:
        return distance_to_destination / MPG

    current_price = nodes[index]["price"]
    for later_station in nodes[index + 1:]:
        distance = later_station["route_mile"] - station_mile
        if distance > MAX_RANGE_MILES:
            break
        if later_station["price"] < current_price:
            return distance / MPG
    return TANK_CAPACITY_GALLONS
