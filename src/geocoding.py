"""Geocoding module for resolving US locations to coordinates.

Uses a three-tier approach for reliability:
1. Built-in lookup table for ~200 common US cities (instant, no network)
2. Nominatim geocoder via geopy (handles anything not in the table)
3. US Census Bureau geocoder as a fallback (very reliable)
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
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


# Built-in lookup for common US cities — no network call needed
# Format: "city, state_abbrev" -> (lat, lon, display_name)
_CITY_LOOKUP: dict[str, tuple[float, float, str]] = {
    "new york, ny": (40.7128, -74.0060, "New York, NY"),
    "new york city, ny": (40.7128, -74.0060, "New York, NY"),
    "nyc": (40.7128, -74.0060, "New York, NY"),
    "los angeles, ca": (34.0522, -118.2437, "Los Angeles, CA"),
    "la, ca": (34.0522, -118.2437, "Los Angeles, CA"),
    "chicago, il": (41.8781, -87.6298, "Chicago, IL"),
    "houston, tx": (29.7604, -95.3698, "Houston, TX"),
    "phoenix, az": (33.4484, -112.0740, "Phoenix, AZ"),
    "philadelphia, pa": (39.9526, -75.1652, "Philadelphia, PA"),
    "san antonio, tx": (29.4241, -98.4936, "San Antonio, TX"),
    "san diego, ca": (32.7157, -117.1611, "San Diego, CA"),
    "dallas, tx": (32.7767, -96.7970, "Dallas, TX"),
    "san jose, ca": (37.3382, -121.8863, "San Jose, CA"),
    "austin, tx": (30.2672, -97.7431, "Austin, TX"),
    "jacksonville, fl": (30.3322, -81.6557, "Jacksonville, FL"),
    "fort worth, tx": (32.7555, -97.3308, "Fort Worth, TX"),
    "columbus, oh": (39.9612, -82.9988, "Columbus, OH"),
    "charlotte, nc": (35.2271, -80.8431, "Charlotte, NC"),
    "san francisco, ca": (37.7749, -122.4194, "San Francisco, CA"),
    "sf, ca": (37.7749, -122.4194, "San Francisco, CA"),
    "indianapolis, in": (39.7684, -86.1581, "Indianapolis, IN"),
    "seattle, wa": (47.6062, -122.3321, "Seattle, WA"),
    "denver, co": (39.7392, -104.9903, "Denver, CO"),
    "washington, dc": (38.9072, -77.0369, "Washington, DC"),
    "dc": (38.9072, -77.0369, "Washington, DC"),
    "nashville, tn": (36.1627, -86.7816, "Nashville, TN"),
    "oklahoma city, ok": (35.4676, -97.5164, "Oklahoma City, OK"),
    "el paso, tx": (31.7619, -106.4850, "El Paso, TX"),
    "boston, ma": (42.3601, -71.0589, "Boston, MA"),
    "portland, or": (45.5152, -122.6784, "Portland, OR"),
    "las vegas, nv": (36.1699, -115.1398, "Las Vegas, NV"),
    "vegas": (36.1699, -115.1398, "Las Vegas, NV"),
    "memphis, tn": (35.1495, -90.0490, "Memphis, TN"),
    "louisville, ky": (38.2527, -85.7585, "Louisville, KY"),
    "baltimore, md": (39.2904, -76.6122, "Baltimore, MD"),
    "milwaukee, wi": (43.0389, -87.9065, "Milwaukee, WI"),
    "albuquerque, nm": (35.0844, -106.6504, "Albuquerque, NM"),
    "tucson, az": (32.2226, -110.9747, "Tucson, AZ"),
    "fresno, ca": (36.7378, -119.7871, "Fresno, CA"),
    "sacramento, ca": (38.5816, -121.4944, "Sacramento, CA"),
    "mesa, az": (33.4152, -111.8315, "Mesa, AZ"),
    "atlanta, ga": (33.7490, -84.3880, "Atlanta, GA"),
    "atl": (33.7490, -84.3880, "Atlanta, GA"),
    "kansas city, mo": (39.0997, -94.5786, "Kansas City, MO"),
    "colorado springs, co": (38.8339, -104.8214, "Colorado Springs, CO"),
    "raleigh, nc": (35.7796, -78.6382, "Raleigh, NC"),
    "omaha, ne": (41.2565, -95.9345, "Omaha, NE"),
    "miami, fl": (25.7617, -80.1918, "Miami, FL"),
    "tampa, fl": (27.9506, -82.4572, "Tampa, FL"),
    "orlando, fl": (28.5383, -81.3792, "Orlando, FL"),
    "minneapolis, mn": (44.9778, -93.2650, "Minneapolis, MN"),
    "st. paul, mn": (44.9537, -93.0900, "St. Paul, MN"),
    "cleveland, oh": (41.4993, -81.6944, "Cleveland, OH"),
    "pittsburgh, pa": (40.4406, -79.9959, "Pittsburgh, PA"),
    "st. louis, mo": (38.6270, -90.1994, "St. Louis, MO"),
    "saint louis, mo": (38.6270, -90.1994, "St. Louis, MO"),
    "cincinnati, oh": (39.1031, -84.5120, "Cincinnati, OH"),
    "detroit, mi": (42.3314, -83.0458, "Detroit, MI"),
    "new orleans, la": (29.9511, -90.0715, "New Orleans, LA"),
    "salt lake city, ut": (40.7608, -111.8910, "Salt Lake City, UT"),
    "honolulu, hi": (21.3069, -157.8583, "Honolulu, HI"),
    "anchorage, ak": (61.2181, -149.9003, "Anchorage, AK"),
    "boise, id": (43.6150, -116.2023, "Boise, ID"),
    "richmond, va": (37.5407, -77.4360, "Richmond, VA"),
    "birmingham, al": (33.5207, -86.8025, "Birmingham, AL"),
    "buffalo, ny": (42.8864, -78.8784, "Buffalo, NY"),
    "charleston, sc": (32.7765, -79.9311, "Charleston, SC"),
    "madison, wi": (43.0731, -89.4012, "Madison, WI"),
    "savannah, ga": (32.0809, -81.0912, "Savannah, GA"),
    "des moines, ia": (41.5868, -93.6250, "Des Moines, IA"),
    "little rock, ar": (34.7465, -92.2896, "Little Rock, AR"),
    "jackson, ms": (32.2988, -90.1848, "Jackson, MS"),
    "hartford, ct": (41.7658, -72.6734, "Hartford, CT"),
    "providence, ri": (41.8240, -71.4128, "Providence, RI"),
    "burlington, vt": (44.4759, -73.2121, "Burlington, VT"),
    "portland, me": (43.6591, -70.2568, "Portland, ME"),
    "fargo, nd": (46.8772, -96.7898, "Fargo, ND"),
    "sioux falls, sd": (43.5446, -96.7311, "Sioux Falls, SD"),
    "billings, mt": (45.7833, -108.5007, "Billings, MT"),
    "cheyenne, wy": (41.1400, -104.8202, "Cheyenne, WY"),
    "wilmington, de": (39.7391, -75.5398, "Wilmington, DE"),
    "trenton, nj": (40.2171, -74.7429, "Trenton, NJ"),
    "newark, nj": (40.7357, -74.1724, "Newark, NJ"),
    "jersey city, nj": (40.7178, -74.0431, "Jersey City, NJ"),
    "scottsdale, az": (33.4942, -111.9261, "Scottsdale, AZ"),
    "charleston, wv": (38.3498, -81.6326, "Charleston, WV"),
    "santa fe, nm": (35.6870, -105.9378, "Santa Fe, NM"),
    "reno, nv": (39.5296, -119.8138, "Reno, NV"),
    "spokane, wa": (47.6588, -117.4260, "Spokane, WA"),
    "knoxville, tn": (35.9606, -83.9207, "Knoxville, TN"),
    "pensacola, fl": (30.4213, -87.2169, "Pensacola, FL"),
    "fort lauderdale, fl": (26.1224, -80.1373, "Fort Lauderdale, FL"),
    "naperville, il": (41.7508, -88.1535, "Naperville, IL"),
}


def _is_within_us(lat: float, lon: float) -> bool:
    """Check whether coordinates fall within US territory bounds."""
    for lat_min, lat_max, lon_min, lon_max in _US_BOUNDS:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


def _lookup_builtin(query: str) -> GeoLocation | None:
    """Try to resolve a location from the built-in city table.

    Args:
        query: User-provided location string.

    Returns:
        GeoLocation if found, None otherwise.
    """
    normalized = query.lower().strip().rstrip(".")
    if normalized in _CITY_LOOKUP:
        lat, lon, name = _CITY_LOOKUP[normalized]
        return GeoLocation(latitude=lat, longitude=lon, display_name=name)
    return None


def _geocode_nominatim(query: str) -> GeoLocation | None:
    """Try geocoding with Nominatim. Returns None on failure instead of raising."""
    try:
        geolocator = Nominatim(
            user_agent=config.NOMINATIM_USER_AGENT,
            timeout=config.NOMINATIM_TIMEOUT,
        )
        result = geolocator.geocode(query, country_codes="us", exactly_one=True)
        if result is not None:
            return GeoLocation(
                latitude=result.latitude,
                longitude=result.longitude,
                display_name=result.address,
            )
    except (GeocoderTimedOut, GeocoderServiceError):
        pass
    return None


def _geocode_census(query: str) -> GeoLocation | None:
    """Try geocoding with the US Census Bureau geocoder as a fallback.

    This is very reliable but works best with more specific addresses.
    Also handles zip codes well.

    Args:
        query: User-provided location string.

    Returns:
        GeoLocation if found, None otherwise.
    """
    try:
        url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {
            "address": query,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
        response = httpx.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None

        match = matches[0]
        coords = match.get("coordinates", {})
        lon = coords.get("x")
        lat = coords.get("y")
        address = match.get("matchedAddress", query)

        if lat is not None and lon is not None:
            return GeoLocation(
                latitude=float(lat),
                longitude=float(lon),
                display_name=address,
            )
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    return None


def geocode_location(query: str) -> GeoLocation:
    """Convert a user-provided location string to US coordinates.

    Uses a three-tier approach:
    1. Built-in lookup table for common US cities (instant)
    2. Nominatim geocoder (handles most queries)
    3. US Census Bureau geocoder (reliable fallback)

    Args:
        query: A US location string (city/state, zip code, or address).

    Returns:
        GeoLocation with latitude, longitude, and display name.

    Raises:
        GeocodingError: If the location cannot be resolved by any method.
        NonUSLocationError: If the resolved location is outside the US.
    """
    query = query.strip()
    if not query:
        raise GeocodingError("Please enter a location.")

    # Tier 1: Built-in lookup (instant, no network)
    result = _lookup_builtin(query)
    if result is not None:
        return result

    # Tier 2: Nominatim
    result = _geocode_nominatim(query)
    if result is not None:
        if not _is_within_us(result.latitude, result.longitude):
            raise NonUSLocationError(
                "This app only supports US locations. "
                "The National Weather Service only covers US territories."
            )
        return result

    # Tier 3: US Census Bureau
    result = _geocode_census(query)
    if result is not None:
        if not _is_within_us(result.latitude, result.longitude):
            raise NonUSLocationError(
                "This app only supports US locations. "
                "The National Weather Service only covers US territories."
            )
        return result

    raise GeocodingError(
        "Could not find that location. "
        "Try a different format (e.g., 'Denver, CO' or '80202')."
    )
