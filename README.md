# Fuel Route Planner

A Django REST API for planning a cost-effective driving trip between two US
locations. It returns a GeoJSON route map, the fuel purchases required to
complete the trip, and the total fuel cost.

## Assessment requirements covered

- **US start and finish:** Nominatim geocoding is restricted to, and verifies,
  the United States.
- **Route map:** `map_geojson` is a ready-to-render GeoJSON FeatureCollection
  containing the OSRM route line and selected fuel-stop markers.
- **Cost-effective fuel stops:** the optimiser carries fuel already bought in
  the tank and buys only enough to reach the first cheaper reachable station;
  otherwise it fills up to the 500-mile range.
- **Vehicle assumptions:** 500-mile maximum range, 10 MPG, and a 50-gallon
  effective tank capacity.
- **Price source:** `dataset/fuel-prices.csv` is loaded into the local
  database once with `python manage.py load_stations`.
- **Low external API use:** a cold request makes two parallel Nominatim
  geocoding calls and one OSRM route call. Geocodes, routes, and complete
  plans are cached, so a repeated request makes no external map calls.

## API

**POST** `/api/plan-route/`

```json
{
  "start": "New York, NY",
  "destination": "Chicago, IL"
}
```

Important response fields:

```json
{
  "route_distance_miles": 790.57,
  "fuel_economy_mpg": 10,
  "maximum_range_miles": 500,
  "map_geojson": { "type": "FeatureCollection", "features": ["route and stop markers"] },
  "initial_fill": {
    "name": "Example station",
    "price_per_gallon": 3.099,
    "route_mile": 0.0,
    "gallons_purchased": 50.0,
    "fuel_cost": 154.95
  },
  "fuel_stops": [
    {
      "name": "Later station",
      "route_mile": 386.47,
      "gallons_purchased": 29.06,
      "fuel_cost": 94.13
    }
  ],
  "estimated_gallons": 79.06,
  "estimated_fuel_cost": 249.08
}
```

`gallons_purchased` and `fuel_cost` make the total transparent. The API
assumes the vehicle begins empty and uses the cheapest supplied station within
25 route miles of the start as the initial fill location.

Errors are returned as JSON: `400` for invalid inputs, `422` when a US
location, route, or valid 500-mile fuel plan cannot be found, and `502` when a
free map service is unavailable.

## Short implementation notes

1. **Routing:** Nominatim finds US coordinates and OSRM supplies one driving
   route. The full OSRM GeoJSON geometry is returned to the client.
2. **Accurate route mile:** each point on the route line is calibrated to the
   road mileage that OSRM reports. The 500-mile range check therefore uses
   driving miles, not straight-line miles.
3. **Fast station lookup:** the route is split into short segments and indexed
   in a small geographic grid. Each local station is compared only with nearby
   route segments.
4. **Fuel optimisation:** fuel left in the tank is carried to the next stop.
   This avoids the common error of charging every leg as if the tank became
   empty at each station.
5. **Map output:** `map_geojson` can be passed directly to Leaflet, MapLibre,
   or any other GeoJSON-capable map UI.

## Fuel-location data note

The supplied price CSV has station name/address/city/state but no coordinates.
The loader geocodes each unique US city once and labels every returned station
with `"location_source": "city_centroid"`. This is transparent in the API:
the price and route-mile calculations are sound, while the displayed pin is an
approximation until a source with exact station coordinates is provided.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py load_stations
python manage.py runserver
```

Run the verification suite:

```powershell
python manage.py check
python manage.py test planner -v 2
```

## Example map

New York to Chicago route with selected fuel stops:

![Route Map](https://github.com/Irshadwev/Fuel-Route-Planner/blob/main/Map.png)
