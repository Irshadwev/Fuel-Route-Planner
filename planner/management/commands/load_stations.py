import csv
import json
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from planner.models import FuelStation

CSV_PATH = Path(settings.BASE_DIR) / "dataset" / "fuel-prices.csv"
CACHE_PATH = Path(settings.BASE_DIR) / "dataset" / "geocode_cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "FuelRoutePlannerAssessment/1.0"}


def geocode_city(city, state, cache):
    """Get the map pin for one city. Save every answer in the cache
    file, so we never ask the map service the same city twice.
    If the network fails, try again 3 times. If it still fails,
    return None but do NOT save the failure in the cache, so the
    next run will try this city again."""
    key = f"{city}, {state}"
    if key in cache:
        return cache[key]

    for attempt in range(3):
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={"q": f"{city}, {state}, USA", "format": "json", "limit": 1},
                headers=HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            results = response.json()
            if results:
                cache[key] = [float(results[0]["lat"]), float(results[0]["lon"])]
            else:
                cache[key] = None
            CACHE_PATH.write_text(json.dumps(cache))  # save progress every time
            time.sleep(1.1)  # Nominatim rule: maximum 1 request per second
            return cache[key]
        except requests.RequestException:
            print(f"Network problem for {key}, trying again ({attempt + 1}/3)...")
            time.sleep(5)

    return None



class Command(BaseCommand):
    help = "Load fuel stations from the CSV and geocode each city once."

    def handle(self, *args, **options):
        if CACHE_PATH.exists():
            cache = json.loads(CACHE_PATH.read_text())
        else:
            cache = {}

        rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig")))
        seen_ids = set()
        saved = 0
        skipped = 0

        for row in rows:
            station_id = row["OPIS Truckstop ID"].strip()
            if station_id in seen_ids:  # same station listed twice in CSV
                continue
            seen_ids.add(station_id)

            try:
                price = float(row["Retail Price"])
            except ValueError:
                skipped += 1
                continue

            city = row["City"].strip()
            state = row["State"].strip()
            coords = geocode_city(city, state, cache)
            if coords is None:
                skipped += 1
                continue

            FuelStation.objects.update_or_create(
                station_id=station_id,
                defaults={
                    "name": row["Truckstop Name"].strip(),
                    "address": row["Address"].strip(),
                    "city": city,
                    "state": state,
                    "price": price,
                    "latitude": coords[0],
                    "longitude": coords[1],
                },
            )
            saved += 1
            if saved % 100 == 0:
                self.stdout.write(f"Saved {saved} stations...")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Saved: {saved}, Skipped: {skipped}"
        ))
