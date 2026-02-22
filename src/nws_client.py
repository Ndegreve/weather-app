"""NWS API client for fetching weather forecasts.

Implements the two-step NWS API flow:
1. /points/{lat},{lon} -> grid location metadata
2. /gridpoints/{office}/{x},{y}/forecast -> 12-hour period forecasts
3. /gridpoints/{office}/{x},{y}/forecast/hourly -> hourly forecasts

No API key is required. A User-Agent header is set per NWS guidelines.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from src import config


class NWSAPIError(Exception):
    """Raised when the NWS API returns an error or unexpected response."""


class NWSPointNotFoundError(NWSAPIError):
    """Raised when the requested coordinates are not covered by NWS."""


@dataclass(frozen=True)
class ForecastPeriod:
    """A single forecast time period from the NWS API.

    Attributes:
        name: Period label (e.g., "Today", "Tonight", "Tuesday").
        temperature: Temperature value.
        temperature_unit: Temperature unit ("F" or "C").
        wind_speed: Wind speed description (e.g., "10 to 15 mph").
        wind_direction: Cardinal wind direction (e.g., "NW").
        short_forecast: Brief summary (e.g., "Partly Cloudy").
        detailed_forecast: Full narrative text.
        is_daytime: Whether this is a daytime period.
        start_time: ISO 8601 start time for the period.
        icon_url: NWS weather icon URL.
    """

    name: str
    temperature: int
    temperature_unit: str
    wind_speed: str
    wind_direction: str
    short_forecast: str
    detailed_forecast: str
    is_daytime: bool
    start_time: str = ""
    icon_url: str = ""


@dataclass(frozen=True)
class HourlyPeriod:
    """A single hourly forecast period from the NWS API.

    Attributes:
        start_time: ISO 8601 start time.
        temperature: Temperature value.
        temperature_unit: Temperature unit ("F" or "C").
        wind_speed: Wind speed description.
        wind_direction: Cardinal wind direction.
        short_forecast: Brief summary (e.g., "Sunny").
        icon_url: NWS weather icon URL.
        is_daytime: Whether this is a daytime hour.
    """

    start_time: str
    temperature: int
    temperature_unit: str
    wind_speed: str
    wind_direction: str
    short_forecast: str
    icon_url: str = ""
    is_daytime: bool = True


@dataclass(frozen=True)
class Forecast:
    """Complete forecast response from the NWS.

    Attributes:
        location_name: Human-readable location from the /points response.
        generated_at: ISO 8601 timestamp of when the forecast was generated.
        periods: List of 12-hour forecast periods (typically 14 periods / 7 days).
        hourly_periods: List of hourly forecast periods (up to 156 hours).
    """

    location_name: str
    generated_at: str
    periods: list[ForecastPeriod] = field(default_factory=list)
    hourly_periods: list[HourlyPeriod] = field(default_factory=list)


def _create_client() -> httpx.Client:
    """Create an httpx client configured for the NWS API."""
    return httpx.Client(
        base_url=config.NWS_API_BASE_URL,
        headers={
            "User-Agent": config.NWS_USER_AGENT,
            "Accept": "application/geo+json",
        },
        timeout=config.NWS_REQUEST_TIMEOUT,
    )


def _request_with_retry(client: httpx.Client, url: str, max_retries: int = 1) -> dict:
    """Make a GET request with simple retry logic for server errors.

    Args:
        client: The httpx client to use.
        url: URL or path to request.
        max_retries: Number of retries for 5xx errors.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        NWSPointNotFoundError: On 404 responses.
        NWSAPIError: On other HTTP errors, timeouts, or invalid JSON.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.get(url)
        except httpx.TimeoutException:
            raise NWSAPIError("Request to NWS timed out. Please try again.")
        except httpx.HTTPError as exc:
            raise NWSAPIError(f"HTTP error communicating with NWS: {exc}")

        if response.status_code == 404:
            raise NWSPointNotFoundError(
                "The National Weather Service does not have data for this location. "
                "Try a nearby city."
            )

        if response.status_code >= 500:
            last_error = NWSAPIError(
                f"NWS server error (HTTP {response.status_code}). "
                "The service may be temporarily unavailable."
            )
            if attempt < max_retries:
                time.sleep(5)
                continue
            raise last_error

        if response.status_code != 200:
            raise NWSAPIError(
                f"Unexpected response from NWS (HTTP {response.status_code})."
            )

        try:
            return response.json()
        except ValueError:
            raise NWSAPIError("Received invalid JSON from NWS.")

    raise last_error  # pragma: no cover


def _parse_periods(data: dict) -> list[ForecastPeriod]:
    """Parse forecast periods from the NWS API response."""
    try:
        raw_periods = data["properties"]["periods"]
    except (KeyError, TypeError):
        raise NWSAPIError("Unexpected forecast response format from NWS.")

    periods = []
    for p in raw_periods:
        periods.append(
            ForecastPeriod(
                name=p.get("name", ""),
                temperature=p.get("temperature", 0),
                temperature_unit=p.get("temperatureUnit", "F"),
                wind_speed=p.get("windSpeed", ""),
                wind_direction=p.get("windDirection", ""),
                short_forecast=p.get("shortForecast", ""),
                detailed_forecast=p.get("detailedForecast", ""),
                is_daytime=p.get("isDaytime", True),
                start_time=p.get("startTime", ""),
                icon_url=p.get("icon", ""),
            )
        )
    return periods


def _parse_hourly_periods(data: dict) -> list[HourlyPeriod]:
    """Parse hourly forecast periods from the NWS API response."""
    try:
        raw_periods = data["properties"]["periods"]
    except (KeyError, TypeError):
        raise NWSAPIError("Unexpected hourly forecast response format from NWS.")

    periods = []
    for p in raw_periods:
        periods.append(
            HourlyPeriod(
                start_time=p.get("startTime", ""),
                temperature=p.get("temperature", 0),
                temperature_unit=p.get("temperatureUnit", "F"),
                wind_speed=p.get("windSpeed", ""),
                wind_direction=p.get("windDirection", ""),
                short_forecast=p.get("shortForecast", ""),
                icon_url=p.get("icon", ""),
                is_daytime=p.get("isDaytime", True),
            )
        )
    return periods


def get_forecast(latitude: float, longitude: float) -> Forecast:
    """Fetch the NWS forecast for the given coordinates.

    Makes three API calls:
    1. GET /points/{lat},{lon} to resolve the grid location.
    2. GET the forecast URL for 12-hour periods.
    3. GET the hourly forecast URL for hourly data.

    Args:
        latitude: Decimal latitude (will be rounded to 4 places).
        longitude: Decimal longitude (will be rounded to 4 places).

    Returns:
        Forecast containing both standard and hourly periods.

    Raises:
        NWSAPIError: On API communication errors.
        NWSPointNotFoundError: If the coordinates are not covered by NWS.
    """
    lat = round(latitude, 4)
    lon = round(longitude, 4)

    client = _create_client()
    try:
        # Step 1: Resolve grid location
        points_data = _request_with_retry(client, f"/points/{lat},{lon}")

        try:
            props = points_data["properties"]
            forecast_url = props["forecast"]
            hourly_url = props["forecastHourly"]
            location_name = (
                f"{props.get('relativeLocation', {}).get('properties', {}).get('city', '')}, "
                f"{props.get('relativeLocation', {}).get('properties', {}).get('state', '')}"
            )
        except (KeyError, TypeError):
            raise NWSAPIError("Unexpected response format from NWS /points endpoint.")

        # Step 2: Fetch standard forecast (12-hour periods)
        forecast_data = _request_with_retry(client, forecast_url)
        periods = _parse_periods(forecast_data)
        generated_at = (
            forecast_data.get("properties", {}).get("generatedAt", "")
        )

        # Step 3: Fetch hourly forecast
        try:
            hourly_data = _request_with_retry(client, hourly_url)
            hourly_periods = _parse_hourly_periods(hourly_data)
        except NWSAPIError:
            # Hourly forecast is optional — don't fail the whole request
            hourly_periods = []

        return Forecast(
            location_name=location_name,
            generated_at=generated_at,
            periods=periods,
            hourly_periods=hourly_periods,
        )
    finally:
        client.close()
