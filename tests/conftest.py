"""Shared test fixtures for NWS API response data."""

import pytest


@pytest.fixture()
def points_response():
    """Sample NWS /points response for Denver, CO."""
    return {
        "properties": {
            "gridId": "BOU",
            "gridX": 62,
            "gridY": 60,
            "forecast": "https://api.weather.gov/gridpoints/BOU/62,60/forecast",
            "forecastHourly": "https://api.weather.gov/gridpoints/BOU/62,60/forecast/hourly",
            "relativeLocation": {
                "properties": {
                    "city": "Denver",
                    "state": "CO",
                }
            },
        }
    }


@pytest.fixture()
def forecast_response():
    """Sample NWS forecast response with two periods."""
    return {
        "properties": {
            "generatedAt": "2026-02-22T12:00:00+00:00",
            "periods": [
                {
                    "number": 1,
                    "name": "Today",
                    "startTime": "2026-02-22T06:00:00-07:00",
                    "temperature": 45,
                    "temperatureUnit": "F",
                    "windSpeed": "10 to 15 mph",
                    "windDirection": "NW",
                    "shortForecast": "Partly Cloudy",
                    "detailedForecast": (
                        "Partly cloudy, with a high near 45. "
                        "Northwest wind 10 to 15 mph."
                    ),
                    "isDaytime": True,
                    "icon": "https://api.weather.gov/icons/land/day/sct",
                },
                {
                    "number": 2,
                    "name": "Tonight",
                    "startTime": "2026-02-22T18:00:00-07:00",
                    "temperature": 28,
                    "temperatureUnit": "F",
                    "windSpeed": "5 mph",
                    "windDirection": "S",
                    "shortForecast": "Mostly Clear",
                    "detailedForecast": (
                        "Mostly clear, with a low around 28. "
                        "South wind around 5 mph."
                    ),
                    "isDaytime": False,
                    "icon": "https://api.weather.gov/icons/land/night/few",
                },
            ],
        }
    }


@pytest.fixture()
def hourly_response():
    """Sample NWS hourly forecast response with three periods."""
    return {
        "properties": {
            "periods": [
                {
                    "startTime": "2026-02-22T10:00:00-07:00",
                    "temperature": 38,
                    "temperatureUnit": "F",
                    "windSpeed": "10 mph",
                    "windDirection": "NW",
                    "shortForecast": "Partly Cloudy",
                    "isDaytime": True,
                    "icon": "https://api.weather.gov/icons/land/day/sct",
                },
                {
                    "startTime": "2026-02-22T11:00:00-07:00",
                    "temperature": 40,
                    "temperatureUnit": "F",
                    "windSpeed": "12 mph",
                    "windDirection": "NW",
                    "shortForecast": "Sunny",
                    "isDaytime": True,
                    "icon": "https://api.weather.gov/icons/land/day/skc",
                },
                {
                    "startTime": "2026-02-22T12:00:00-07:00",
                    "temperature": 42,
                    "temperatureUnit": "F",
                    "windSpeed": "12 mph",
                    "windDirection": "NW",
                    "shortForecast": "Sunny",
                    "isDaytime": True,
                    "icon": "https://api.weather.gov/icons/land/day/skc",
                },
            ]
        }
    }
