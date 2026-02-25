"""Extended NWS data: current observations, sunrise/sunset, precipitation.

Companion to nws_client.py — fetches supplemental data from NWS endpoints
that the base client does not use. All data is best-effort: if any call
fails, the corresponding field is None and the UI simply omits that card.

No API key required. Uses the same NWS User-Agent header.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src import config


class ExtendedDataError(Exception):
    """Raised when extended data fetching fails (non-critical)."""


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def celsius_to_fahrenheit(celsius: float | None) -> int | None:
    """Convert Celsius to Fahrenheit, rounding to nearest integer."""
    if celsius is None:
        return None
    return round(celsius * 9 / 5 + 32)


def pa_to_mbar(pascals: float | None) -> float | None:
    """Convert Pascals to millibars (hPa)."""
    if pascals is None:
        return None
    return round(pascals / 100, 1)


def meters_to_miles(meters: float | None) -> float | None:
    """Convert meters to miles."""
    if meters is None:
        return None
    return round(meters / 1609.34, 1)


def kmh_to_mph(kmh: float | None) -> float | None:
    """Convert km/h to mph."""
    if kmh is None:
        return None
    return round(kmh / 1.609, 1)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrentConditions:
    """Current weather observations from the nearest NWS station.

    Attributes:
        temperature_f: Current temperature in Fahrenheit.
        feels_like_f: Wind chill or heat index in Fahrenheit.
        humidity: Relative humidity percentage.
        wind_speed_mph: Wind speed in mph.
        wind_direction: Cardinal direction (e.g., "NW").
        pressure_mbar: Barometric pressure in millibars.
        visibility_miles: Visibility in miles.
        description: Text description (e.g., "Mostly Cloudy").
        dewpoint_f: Dewpoint temperature in Fahrenheit.
    """

    temperature_f: int | None = None
    feels_like_f: int | None = None
    humidity: float | None = None
    wind_speed_mph: float | None = None
    wind_direction: str = ""
    pressure_mbar: float | None = None
    visibility_miles: float | None = None
    description: str = ""
    dewpoint_f: int | None = None


@dataclass(frozen=True)
class SunData:
    """Sunrise and sunset times for the forecast location.

    Attributes:
        sunrise: Formatted time string (e.g., "6:42 AM").
        sunset: Formatted time string (e.g., "5:31 PM").
        sunrise_iso: Raw ISO 8601 string from NWS.
        sunset_iso: Raw ISO 8601 string from NWS.
    """

    sunrise: str = ""
    sunset: str = ""
    sunrise_iso: str = ""
    sunset_iso: str = ""


@dataclass(frozen=True)
class ExtendedData:
    """All supplemental weather data (best-effort, fields may be None).

    Attributes:
        current: Current conditions from observation station.
        sun: Sunrise/sunset data.
        hourly_precip: Mapping of ISO start_time to precipitation chance (0-100).
    """

    current: CurrentConditions | None = None
    sun: SunData | None = None
    hourly_precip: dict | None = None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _create_client() -> httpx.Client:
    """Create an httpx client for NWS API requests."""
    return httpx.Client(
        base_url=config.NWS_API_BASE_URL,
        headers={
            "User-Agent": config.NWS_USER_AGENT,
            "Accept": "application/geo+json",
        },
        timeout=config.NWS_REQUEST_TIMEOUT,
    )


def _safe_get(client: httpx.Client, url: str) -> dict | None:
    """Make a GET request, returning None on any failure."""
    try:
        response = client.get(url)
        if response.status_code == 200:
            return response.json()
    except (httpx.HTTPError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def _extract_value(obs: dict, key: str) -> float | None:
    """Safely extract a numeric value from an NWS observation property."""
    prop = obs.get(key)
    if prop is None:
        return None
    val = prop.get("value") if isinstance(prop, dict) else None
    return val


def _parse_observation(data: dict) -> CurrentConditions:
    """Parse an observation station response into CurrentConditions."""
    props = data.get("properties", {})

    temp_c = _extract_value(props, "temperature")
    dewpoint_c = _extract_value(props, "dewpoint")
    humidity = _extract_value(props, "relativeHumidity")
    wind_speed_kmh = _extract_value(props, "windSpeed")
    pressure_pa = _extract_value(props, "barometricPressure")
    visibility_m = _extract_value(props, "visibility")

    # Feels like: use windChill if available, else heatIndex
    feels_c = _extract_value(props, "windChill")
    if feels_c is None:
        feels_c = _extract_value(props, "heatIndex")

    wind_dir = props.get("windDirection", {})
    if isinstance(wind_dir, dict):
        wind_dir = str(wind_dir.get("value", "")) if wind_dir.get("value") else ""
    else:
        wind_dir = ""

    # Wind direction from NWS can be degrees — convert to cardinal
    try:
        degrees = float(wind_dir)
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                       "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        idx = round(degrees / 22.5) % 16
        wind_dir = directions[idx]
    except (ValueError, TypeError):
        pass

    description = props.get("textDescription", "")

    return CurrentConditions(
        temperature_f=celsius_to_fahrenheit(temp_c),
        feels_like_f=celsius_to_fahrenheit(feels_c),
        humidity=round(humidity, 1) if humidity is not None else None,
        wind_speed_mph=kmh_to_mph(wind_speed_kmh),
        wind_direction=wind_dir,
        pressure_mbar=pa_to_mbar(pressure_pa),
        visibility_miles=meters_to_miles(visibility_m),
        description=description,
        dewpoint_f=celsius_to_fahrenheit(dewpoint_c),
    )


def _parse_sun_data(points_data: dict) -> SunData | None:
    """Extract sunrise/sunset from the /points response or gridpoint data.

    NWS doesn't directly provide sunrise/sunset in a simple way.
    We approximate from the forecast periods — the first daytime period
    starts near sunrise, and the first nighttime period starts near sunset.

    For a more accurate approach, we use the USNO API as a fallback.
    """
    # NWS doesn't reliably expose sunrise/sunset.
    # We'll compute from the forecast periods in the app layer instead.
    return None


def _parse_hourly_precip(hourly_data: dict) -> dict[str, int]:
    """Extract precipitation probability from hourly forecast JSON.

    Returns a mapping of ISO start_time to precipitation chance (0-100).
    """
    result: dict[str, int] = {}
    try:
        periods = hourly_data["properties"]["periods"]
        for p in periods:
            start = p.get("startTime", "")
            precip = p.get("probabilityOfPrecipitation", {})
            chance = precip.get("value") if isinstance(precip, dict) else None
            if start and chance is not None:
                result[start] = int(chance)
    except (KeyError, TypeError):
        pass
    return result


def _parse_hourly_humidity(hourly_data: dict) -> dict[str, float]:
    """Extract relative humidity from hourly forecast JSON.

    Returns a mapping of ISO start_time to humidity percentage.
    """
    result: dict[str, float] = {}
    try:
        periods = hourly_data["properties"]["periods"]
        for p in periods:
            start = p.get("startTime", "")
            hum = p.get("relativeHumidity", {})
            value = hum.get("value") if isinstance(hum, dict) else None
            if start and value is not None:
                result[start] = float(value)
    except (KeyError, TypeError):
        pass
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_extended_data(
    latitude: float,
    longitude: float,
    points_data: dict | None = None,
) -> ExtendedData:
    """Fetch supplemental weather data for a location.

    All data is best-effort. Individual failures result in None fields
    rather than raising exceptions.

    Args:
        latitude: Decimal latitude.
        longitude: Decimal longitude.
        points_data: Optional pre-fetched /points response (to avoid duplicate call).

    Returns:
        ExtendedData with whatever data was successfully fetched.
    """
    lat = round(latitude, 4)
    lon = round(longitude, 4)

    current: CurrentConditions | None = None
    sun: SunData | None = None
    hourly_precip: dict | None = None

    client = _create_client()
    try:
        # Get points data if not provided
        if points_data is None:
            points_data = _safe_get(client, f"/points/{lat},{lon}")

        if points_data:
            props = points_data.get("properties", {})

            # Fetch current conditions from nearest observation station
            stations_url = props.get("observationStations")
            if stations_url:
                stations_data = _safe_get(client, stations_url)
                if stations_data:
                    features = stations_data.get("features", [])
                    if features:
                        station_id = features[0].get("properties", {}).get(
                            "stationIdentifier", ""
                        )
                        if station_id:
                            obs_url = f"/stations/{station_id}/observations/latest"
                            obs_data = _safe_get(client, obs_url)
                            if obs_data:
                                current = _parse_observation(obs_data)

            # Fetch hourly precipitation data
            hourly_url = props.get("forecastHourly")
            if hourly_url:
                hourly_data = _safe_get(client, hourly_url)
                if hourly_data:
                    hourly_precip = _parse_hourly_precip(hourly_data)

    finally:
        client.close()

    return ExtendedData(
        current=current,
        sun=sun,
        hourly_precip=hourly_precip,
    )
