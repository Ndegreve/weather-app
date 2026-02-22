"""Tests for the geocoding module."""

from unittest.mock import MagicMock, patch

import pytest
from geopy.exc import GeocoderServiceError, GeocoderTimedOut

from src.geocoding import (
    GeocodingError,
    GeoLocation,
    NonUSLocationError,
    geocode_location,
)


def _make_geopy_location(lat, lon, address):
    """Create a mock geopy Location object."""
    loc = MagicMock()
    loc.latitude = lat
    loc.longitude = lon
    loc.address = address
    return loc


class TestGeocodeLocationSuccess:
    """Test successful geocoding scenarios."""

    @patch("src.geocoding.Nominatim")
    def test_city_state_returns_location(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.return_value = _make_geopy_location(
            39.7392, -104.9903, "Denver, Denver County, Colorado, USA"
        )

        result = geocode_location("Denver, CO")

        assert isinstance(result, GeoLocation)
        assert result.latitude == 39.7392
        assert result.longitude == -104.9903
        assert "Denver" in result.display_name

    @patch("src.geocoding.Nominatim")
    def test_zip_code_returns_location(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.return_value = _make_geopy_location(
            34.0901, -118.4065, "Beverly Hills, California 90210, USA"
        )

        result = geocode_location("90210")

        assert isinstance(result, GeoLocation)
        assert result.latitude == 34.0901
        assert result.longitude == -118.4065

    @patch("src.geocoding.Nominatim")
    def test_alaska_location_accepted(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.return_value = _make_geopy_location(
            61.2181, -149.9003, "Anchorage, Alaska, USA"
        )

        result = geocode_location("Anchorage, AK")

        assert result.latitude == 61.2181

    @patch("src.geocoding.Nominatim")
    def test_hawaii_location_accepted(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.return_value = _make_geopy_location(
            21.3069, -157.8583, "Honolulu, Hawaii, USA"
        )

        result = geocode_location("Honolulu, HI")

        assert result.latitude == 21.3069

    @patch("src.geocoding.Nominatim")
    def test_strips_whitespace(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.return_value = _make_geopy_location(
            39.7392, -104.9903, "Denver, Colorado, USA"
        )

        geocode_location("  Denver, CO  ")

        mock_geocoder.geocode.assert_called_once_with(
            "Denver, CO", country_codes="us", exactly_one=True
        )


class TestGeocodeLocationErrors:
    """Test error handling in geocoding."""

    def test_empty_string_raises_error(self):
        with pytest.raises(GeocodingError, match="Please enter a location"):
            geocode_location("")

    def test_whitespace_only_raises_error(self):
        with pytest.raises(GeocodingError, match="Please enter a location"):
            geocode_location("   ")

    @patch("src.geocoding.Nominatim")
    def test_not_found_raises_error(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.return_value = None

        with pytest.raises(GeocodingError, match="Could not find"):
            geocode_location("xyznotarealplace123")

    @patch("src.geocoding.Nominatim")
    def test_non_us_location_raises_error(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.return_value = _make_geopy_location(
            51.5074, -0.1278, "London, England"
        )

        with pytest.raises(NonUSLocationError, match="only supports US"):
            geocode_location("London, England")

    @patch("src.geocoding.Nominatim")
    def test_timeout_raises_geocoding_error(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.side_effect = GeocoderTimedOut("timeout")

        with pytest.raises(GeocodingError, match="timed out"):
            geocode_location("Denver, CO")

    @patch("src.geocoding.Nominatim")
    def test_service_error_raises_geocoding_error(self, mock_nominatim_cls):
        mock_geocoder = MagicMock()
        mock_nominatim_cls.return_value = mock_geocoder
        mock_geocoder.geocode.side_effect = GeocoderServiceError("service down")

        with pytest.raises(GeocodingError, match="unavailable"):
            geocode_location("Denver, CO")


class TestGeoLocationDataclass:
    """Test the GeoLocation dataclass."""

    def test_frozen(self):
        loc = GeoLocation(latitude=39.0, longitude=-104.0, display_name="Test")
        with pytest.raises(AttributeError):
            loc.latitude = 40.0

    def test_equality(self):
        a = GeoLocation(latitude=39.0, longitude=-104.0, display_name="A")
        b = GeoLocation(latitude=39.0, longitude=-104.0, display_name="A")
        assert a == b
