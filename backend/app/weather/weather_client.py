"""Weather provider abstraction."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class WeatherSnapshot:
    temperature: float | None
    rainfall: float | None
    humidity: float | None
    condition: str
    storm: bool
    flood_risk: str  # low | medium | high
    provider: str
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WeatherClient(ABC):
    @abstractmethod
    def get_by_coords(self, latitude: float, longitude: float) -> WeatherSnapshot:
        raise NotImplementedError


class StubWeatherClient(WeatherClient):
    """Deterministic offline weather for Myanmar corridor demos."""

    def get_by_coords(self, latitude: float, longitude: float) -> WeatherSnapshot:
        # Heavy rain near Myawaddy corridor (~16.68N, 98.5E)
        near_myawaddy = abs(latitude - 16.68) < 1.2 and abs(longitude - 98.5) < 1.5
        if near_myawaddy:
            return WeatherSnapshot(
                temperature=27.5,
                rainfall=42.0,
                humidity=91.0,
                condition="heavy_rain",
                storm=True,
                flood_risk="high",
                provider="stub",
            )
        return WeatherSnapshot(
            temperature=31.0,
            rainfall=2.0,
            humidity=68.0,
            condition="partly_cloudy",
            storm=False,
            flood_risk="low",
            provider="stub",
        )


class OpenWeatherClient(WeatherClient):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: dict[tuple[float, float], WeatherSnapshot] = {}

    def get_by_coords(self, latitude: float, longitude: float) -> WeatherSnapshot:
        if not self.settings.openweather_api_key:
            logger.warning("OPENWEATHER_API_KEY missing; falling back to stub")
            return StubWeatherClient().get_by_coords(latitude, longitude)

        cache_key = (round(latitude, 2), round(longitude, 2))
        hit = self._cache.get(cache_key)
        if hit is not None:
            return hit

        url = f"{self.settings.openweather_base_url}/weather"
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.settings.openweather_api_key,
            "units": "metric",
        }
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        rain = float((data.get("rain") or {}).get("1h") or 0.0)
        weather = (data.get("weather") or [{}])[0]
        main = data.get("main") or {}
        condition = str(weather.get("main") or "unknown").lower()
        storm = condition in {"thunderstorm", "squall"}
        if rain >= 30 or storm:
            flood = "high"
        elif rain >= 10:
            flood = "medium"
        else:
            flood = "low"
        snap = WeatherSnapshot(
            temperature=main.get("temp"),
            rainfall=rain,
            humidity=main.get("humidity"),
            condition=condition,
            storm=storm,
            flood_risk=flood,
            provider="openweather",
            raw=data,
        )
        self._cache[cache_key] = snap
        return snap


_weather_client: WeatherClient | None = None


def get_weather_client(settings: Settings | None = None) -> WeatherClient:
    """Process-wide client so OpenWeather responses stay cached across requests."""
    global _weather_client
    settings = settings or get_settings()
    if _weather_client is None:
        if settings.weather_provider == "openweather":
            _weather_client = OpenWeatherClient(settings)
        else:
            _weather_client = StubWeatherClient()
    return _weather_client
