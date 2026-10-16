# Fuel Route Planner

A Django REST API that plans the cheapest way to drive between two US
locations: it returns the route map, the optimal (cheapest) fuel stops
along the route, and the total fuel cost.

- Vehicle range: **500 miles** maximum between fuel stops
- Fuel economy: **10 miles per gallon**
- Fuel prices: the supplied dataset (`dataset/fuel-prices.csv`, 8,151 records)

## API

**POST** `/api/plan-route/`

Request:
```json
{"start": "New York, NY", "destination": "Chicago, IL"}
```

Response (shortened):
```json
{
  "start": "New York, NY",
  "destination": "Chicago, IL",
  "route_distance_miles": 790.57,
  "route_geometry": {"type": "LineString", "coordinates": ["..."]},
  "initial_fill": {"name": "7-ELEVEN #40084", "city": "Palisades Park",
                   "state": "NJ", "price_per_gallon": 3.099, "route_mile": 0.0},
  "fuel_stops": [
    {"name": "ACI TRUCK STOP", "city": "Columbia", "state": "NJ",
     "price_per_gallon": 3.079, "route_mile": 65.81},
    {"name": "MR FUEL #732", "city": "Girard", "state": "OH",
     "price_per_gallon": 3.239, "route_mile": 386.47}
  ],
  "estimated_gallons": 79.06,
  "estimated_fuel_cost": 250.01,
  "stations_considered": 139
}
```

Errors: `400` if start/destination is missing or empty, `422` if a
location or route cannot be found or no valid fuel plan exists,
`502` if a map service fails.

## Example Map
New York → Chicago route with the fuel stops selected by the API:
Fuel-Route-Planner

![Route Map](https://github.com/Irshadwev/Fuel-Route-Planner/Map.png)




## Setup

```
python -m venv .venv
.venv\Scripts\activate        (Windows)
pip install -r requirements.txt
python manage.py migrate
python manage.py load_stations   (one-time: loads the dataset, see below)
python manage.py runserver
```

Run the tests with: `python manage.py test planner`

## How it works

1. **Stations are prepared once, not per request.** The CSV has no
   coordinates, and its addresses are highway-exit descriptions
   (e.g. "I-44, EXIT 283 & US-69") that geocoders cannot resolve
   (verified: full-address lookup failed on 5 of 6 samples, city lookup
   succeeded on 6 of 6). So `load_stations` geocodes each **city + state
   once** with Nominatim (4,275 cities instead of 8,151 stations),
   caches every result in `dataset/geocode_cache.json`, and stores the
   stations in the database. Re-running the command is fast because of
   the cache, and it retries automatically on network errors.
   A station's location is therefore its city location — an
   approximation that is accurate enough to place it on the route.

2. **One routing call per request.** The start and destination are
   geocoded with Nominatim, then a single OSRM call returns the route
   geometry and distance. Both services are free and need no API key.

3. **Stations near the route.** Route geometry has thousands of
   points, so every 20th point is used as a checkpoint. Stations within
   10 miles of a checkpoint are kept, each with its trip position
   (`route_mile`), using haversine distances.

4. **Cheapest stops by dynamic programming.** Starting from the
   cheapest station near the start (the initial full tank), the
   optimiser works backwards from the destination and keeps, for every
   station, the cheapest way to finish the trip — never driving more
   than 500 miles on one tank. Cost of a leg = miles / 10 MPG x price
   at the station where the leg starts.

## Project structure

```
config/                          settings and root URLs
planner/
  models.py                      FuelStation model
  views.py                       thin API view (validation + response)
  urls.py
  services/
    routing.py                   Nominatim geocoding + one OSRM route call
    stations.py                  stations within 10 miles of the route
    optimiser.py                 cheapest-stop selection (dynamic programming)
  management/commands/
    load_stations.py             one-time dataset loader with geocode cache
  tests.py                       unit tests + API tests with mocked map services
dataset/fuel-prices.csv          supplied fuel price dataset
```

## Contributing
Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

Feel free to reach out with questions or suggestions!