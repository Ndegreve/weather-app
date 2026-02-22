"""Geocoding module for resolving US locations to coordinates.

Uses the Nominatim geocoder (OpenStreetMap) via geopy to convert
user-provided location strings (city/state, zip codes) into
latitude/longitude coordinates for the NWS API.
"""

from dataclasses import dataclass

from geopy.exc import GeocoderServiceError, GeocoderTimedOut
from geopy.geocoders import Nominatim

from src import config


class GeocodingError(Exception):
    """Raised when a location cannot be resolved to coordinates."""


class NonUSLocationError(GeocodingError):
    """Raised when the resolved location is outside the United States."""


@dataclass(frozen=True)
class GeoLocation:
    """A resolved geographic location with coordinates.

    Attributes:
        latitude: Decimal latitude.
        longitude: Decimal longitude.
        display_name: Human-readable location name from the geocoder.
    """

    latitude: float
    longitude: float
    display_name: str


# Bounding boxes for US territories (lat_min, lat_max, lon_min, lon_max)
_US_BOUNDS = [
    (24.5, 49.5, -125.0, -66.5),   # Continental US
    (51.0, 71.5, -180.0, -130.0),   # Alaska
    (18.0, 23.0, -161.0, -154.0),   # Hawaii
    (17.5, 18.6, -67.3, -65.5),     # Puerto Rico
    (17.6, 18.5, -65.1, -64.5),     # US Virgin Islands
    (13.2, 20.6, 144.5, 146.1),     # Guam / Northern Mariana Islands
    (-14.6, -14.1, -171.2, -170.5), # American Samoa
]


def _is_within_us(lat: float, lon: float) -> bool:
    """Check whether coordinates fall within US territory bounds."""
    for lat_min, lat_max, lon_min, lon_max in _US_BOUNDS:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


def geocode_location(query: str) -> GeoLocation:
    """Convert a user-provided location string to US coordinates.

    Accepts city/state names (e.g., "Denver, CO"), zip codes (e.g., "90210"),
    or full addresses.

    Args:
        query: A US location string.

    Returns:
        GeoLocation with latitude, longitude, and display name.

    Raises:
        GeocodingError: If the location cannot be resolved or a service error occurs.
        NonUSLocationError: If the resolved location is outside the US.
    """
    query = query.strip()
    if not query:
        raise GeocodingError("Please enter a location.")

    geolocator = Nominatim(
        user_agent=config.NOMINATIM_USER_AGENT,
        timeout=config.NOMINATIM_TIMEOUT,
    )

    try:
        result = geolocator.geocode(query, country_codes="us", exactly_one=True)
    except GeocoderTimedOut:
        raise GeocodingError(
            "The geocoding service timed out. Please try again."
        )
    except GeocoderServiceError as exc:
        raise GeocodingError(
            f"The geocoding service is unavailable: {exc}"
        )

    if result is None:
        raise GeocodingError(
            "Could not find that location. "
            "Try a different format (e.g., 'Denver, CO' or '80202')."
        )

    lat, lon = result.latitude, result.longitude

    if not _is_within_us(lat, lon):
        raise NonUSLocationError(
            "This app only supports US locations. "
            "The National Weather Service only covers US territories."
        )

    return GeoLocation(
        latitude=lat,
        longitude=lon,
        display_name=result.address,
    )
