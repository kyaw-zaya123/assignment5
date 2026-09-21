"""Major Myanmar cities and towns for map display."""

from __future__ import annotations

import csv
from pathlib import Path

from app.core.config import get_settings
from app.weather.weather_client import get_weather_client

# name, latitude, longitude, region/state
MYANMAR_CITIES: list[dict] = [
    {"name": "Yangon", "lat": 16.8409, "lon": 96.1735, "region": "Yangon"},
    {"name": "Mandalay", "lat": 21.9588, "lon": 96.0891, "region": "Mandalay"},
    {"name": "Naypyidaw", "lat": 19.7633, "lon": 96.0785, "region": "Naypyidaw"},
    {"name": "Mawlamyine", "lat": 16.4542, "lon": 97.6445, "region": "Mon"},
    {"name": "Bago", "lat": 17.3352, "lon": 96.4814, "region": "Bago"},
    {"name": "Pathein", "lat": 16.7792, "lon": 94.7321, "region": "Ayeyarwady"},
    {"name": "Monywa", "lat": 22.1086, "lon": 95.1358, "region": "Sagaing"},
    {"name": "Meiktila", "lat": 20.8778, "lon": 95.8583, "region": "Mandalay"},
    {"name": "Myingyan", "lat": 21.4600, "lon": 95.3883, "region": "Mandalay"},
    {"name": "Taunggyi", "lat": 20.7892, "lon": 97.0378, "region": "Shan"},
    {"name": "Lashio", "lat": 22.9350, "lon": 97.7497, "region": "Shan"},
    {"name": "Kengtung", "lat": 21.2917, "lon": 99.6050, "region": "Shan"},
    {"name": "Tachileik", "lat": 20.4492, "lon": 99.8808, "region": "Shan"},
    {"name": "Muse", "lat": 23.9780, "lon": 97.9040, "region": "Shan"},
    {"name": "Myawaddy", "lat": 16.6897, "lon": 98.5089, "region": "Kayin"},
    {"name": "Hpa-an", "lat": 16.8906, "lon": 97.6333, "region": "Kayin"},
    {"name": "Dawei", "lat": 14.0828, "lon": 98.1935, "region": "Tanintharyi"},
    {"name": "Myeik", "lat": 12.4397, "lon": 98.6003, "region": "Tanintharyi"},
    {"name": "Kawthaung", "lat": 9.9822, "lon": 98.5503, "region": "Tanintharyi"},
    {"name": "Sittwe", "lat": 20.1462, "lon": 92.8984, "region": "Rakhine"},
    {"name": "Thandwe", "lat": 18.4608, "lon": 94.3689, "region": "Rakhine"},
    {"name": "Kyaukpyu", "lat": 19.4264, "lon": 93.5447, "region": "Rakhine"},
    {"name": "Magway", "lat": 20.1496, "lon": 94.9321, "region": "Magway"},
    {"name": "Pakokku", "lat": 21.3342, "lon": 95.0897, "region": "Magway"},
    {"name": "Pyay", "lat": 18.8246, "lon": 95.2156, "region": "Bago"},
    {"name": "Taungoo", "lat": 18.9429, "lon": 96.4341, "region": "Bago"},
    {"name": "Pyin Oo Lwin", "lat": 22.0347, "lon": 96.4570, "region": "Mandalay"},
    {"name": "Sagaing", "lat": 21.8822, "lon": 95.9792, "region": "Sagaing"},
    {"name": "Shwebo", "lat": 22.5690, "lon": 95.6982, "region": "Sagaing"},
    {"name": "Kalay", "lat": 23.1881, "lon": 94.0544, "region": "Sagaing"},
    {"name": "Tamu", "lat": 24.2153, "lon": 94.3100, "region": "Sagaing"},
    {"name": "Hakha", "lat": 22.6445, "lon": 93.6045, "region": "Chin"},
    {"name": "Falam", "lat": 22.9130, "lon": 93.6778, "region": "Chin"},
    {"name": "Mindat", "lat": 21.3667, "lon": 93.9833, "region": "Chin"},
    {"name": "Loikaw", "lat": 19.6742, "lon": 97.2099, "region": "Kayah"},
    {"name": "Hpapun", "lat": 18.0667, "lon": 97.4333, "region": "Kayin"},
    {"name": "Thaton", "lat": 16.9186, "lon": 97.3708, "region": "Mon"},
    {"name": "Ye", "lat": 15.2483, "lon": 97.8564, "region": "Mon"},
    {"name": "Hinthada", "lat": 17.6494, "lon": 95.4572, "region": "Ayeyarwady"},
    {"name": "Bogale", "lat": 16.2942, "lon": 95.3975, "region": "Ayeyarwady"},
    {"name": "Labutta", "lat": 16.1450, "lon": 94.7592, "region": "Ayeyarwady"},
    {"name": "Myitkyina", "lat": 25.3834, "lon": 97.3950, "region": "Kachin"},
    {"name": "Bhamo", "lat": 24.2526, "lon": 97.2336, "region": "Kachin"},
    {"name": "Putao", "lat": 27.3296, "lon": 97.4269, "region": "Kachin"},
    {"name": "Mohnyin", "lat": 24.7833, "lon": 96.3667, "region": "Kachin"},
    {"name": "Namhkam", "lat": 23.8300, "lon": 97.6830, "region": "Shan"},
    {"name": "Hopang", "lat": 23.4167, "lon": 98.7667, "region": "Shan"},
    {"name": "Hsipaw", "lat": 22.6167, "lon": 97.3000, "region": "Shan"},
    {"name": "Kalaw", "lat": 20.6333, "lon": 96.5667, "region": "Shan"},
    {"name": "Nyaungshwe", "lat": 20.6606, "lon": 96.9342, "region": "Shan"},
    {"name": "Chauk", "lat": 20.8992, "lon": 94.8217, "region": "Magway"},
    {"name": "Yenangyaung", "lat": 20.4600, "lon": 94.8742, "region": "Magway"},
    {"name": "Thanlyin", "lat": 16.7619, "lon": 96.2525, "region": "Yangon"},
    {"name": "Twante", "lat": 16.7100, "lon": 95.9333, "region": "Yangon"},
    {"name": "Hlegu", "lat": 17.0969, "lon": 96.2200, "region": "Yangon"},
    {"name": "Bago East", "lat": 17.3360, "lon": 96.4900, "region": "Bago"},
    {"name": "Thayet", "lat": 19.3200, "lon": 95.1800, "region": "Magway"},
    {"name": "Minbu", "lat": 20.1800, "lon": 94.8800, "region": "Magway"},
    {"name": "Kanpetlet", "lat": 21.2000, "lon": 94.0500, "region": "Chin"},
    {"name": "Paletwa", "lat": 21.3000, "lon": 92.8500, "region": "Chin"},
]


# Sparse set shown as weather badges on the live map (avoid 60-city clutter)
MAP_BADGE_CITIES = {
    "Yangon",
    "Mandalay",
    "Naypyidaw",
    "Bago",
    "Taungoo",
    "Mawlamyine",
    "Hpa-an",
    "Myawaddy",
    "Muse",
    "Lashio",
    "Tachileik",
    "Dawei",
    "Sittwe",
    "Meiktila",
    "Pyay",
}


def list_map_cities() -> list[dict]:
    """Map no longer pins hardcoded cities — OSM labels + click-anywhere weather.

    Kept for API compatibility; returns empty so the live map stays uncluttered.
    Border gates come from DB separately.
    """
    return []


def _load_reference_cities() -> list[dict]:
    csv_path = Path(__file__).resolve().parents[3] / "geocoding_reference.csv"
    if not csv_path.exists():
        return []

    cities: list[dict] = []
    seen: set[tuple[str, float, float]] = set()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            city_name = (row.get("city") or "").strip()
            if not city_name:
                continue
            try:
                lat = float(row.get("city_latitude") or 0)
                lon = float(row.get("city_longitude") or 0)
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            key = (city_name, round(lat, 5), round(lon, 5))
            if key in seen:
                continue
            seen.add(key)
            cities.append(
                {
                    "name": city_name,
                    "lat": lat,
                    "lon": lon,
                    "region": (row.get("state") or row.get("district") or "Myanmar").strip(),
                }
            )

    return cities


def list_cities() -> list[dict]:
    """Full city catalog for pickers — no live weather (keeps API fast)."""
    cities: list[dict] = []
    seen: set[tuple[str, float, float]] = set()

    for c in MYANMAR_CITIES + _load_reference_cities():
        key = (c["name"], round(float(c["lat"]), 5), round(float(c["lon"]), 5))
        if key in seen:
            continue
        seen.add(key)
        cities.append(
            {
                "name": c["name"],
                "latitude": c["lat"],
                "longitude": c["lon"],
                "region": c.get("region", "Myanmar"),
            }
        )
    return cities
