"""City weather payloads should be available for map rendering."""

from __future__ import annotations


def test_cities_include_weather_data(client):
    r = client.get("/api/cities")
    assert r.status_code == 200, r.text
    cities = r.json()
    assert isinstance(cities, list)
    assert len(cities) >= 10

    sample = next((c for c in cities if c["name"] == "Yangon"), None)
    assert sample is not None
    assert "weather" in sample
    assert sample["weather"]["provider"] in {"stub", "openweather"}
    assert "condition" in sample["weather"]
