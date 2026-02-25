"""Tests for the nws_extended module — extended NWS weather data."""

from __future__ import annotations

import pytest

from src.nws_extended import (
    CurrentConditions,
    ExtendedData,
    SunData,
    celsius_to_fahrenheit,
    kmh_to_mph,
    meters_to_miles,
    pa_to_mbar,
    _extract_value,
    _parse_hourly_precip,
    _parse_observation,
)


# ---------------------------------------------------------------------------
# Unit conversion tests
# ---------------------------------------------------------------------------

class TestUnitConversions:
    """Test temperature, pressure, distance, and speed conversions."""

    def test_celsius_to_fahrenheit_freezing(self):
        assert celsius_to_fahrenheit(0.0) == 32

    def test_celsius_to_fahrenheit_boiling(self):
        assert celsius_to_fahrenheit(100.0) == 212

    def test_celsius_to_fahrenheit_negative(self):
        assert celsius_to_fahrenheit(-40.0) == -40

    def test_celsius_to_fahrenheit_none(self):
        assert celsius_to_fahrenheit(None) is None

    def test_pa_to_mbar(self):
        assert pa_to_mbar(101325.0) == 1013.2

    def test_pa_to_mbar_none(self):
        assert pa_to_mbar(None) is None

    def test_meters_to_miles(self):
        assert meters_to_miles(1609.34) == 1.0

    def test_meters_to_miles_none(self):
        assert meters_to_miles(None) is None

    def test_kmh_to_mph(self):
        result = kmh_to_mph(100.0)
        assert result == pytest.approx(62.1, abs=0.2)

    def test_kmh_to_mph_none(self):
        assert kmh_to_mph(None) is None


# ---------------------------------------------------------------------------
# Observation parsing tests
# ---------------------------------------------------------------------------

class TestParseObservation:
    """Test parsing of NWS observation station responses."""

    def _make_obs(self, **overrides) -> dict:
        """Create a sample observation response."""
        props = {
            "temperature": {"value": 20.0, "unitCode": "wmoUnit:degC"},
            "dewpoint": {"value": 10.0, "unitCode": "wmoUnit:degC"},
            "relativeHumidity": {"value": 52.3, "unitCode": "wmoUnit:percent"},
            "windSpeed": {"value": 16.0, "unitCode": "wmoUnit:km_h-1"},
            "windDirection": {"value": 225, "unitCode": "wmoUnit:degree_(angle)"},
            "barometricPressure": {"value": 101500, "unitCode": "wmoUnit:Pa"},
            "visibility": {"value": 16093, "unitCode": "wmoUnit:m"},
            "windChill": {"value": 18.0, "unitCode": "wmoUnit:degC"},
            "heatIndex": {"value": None, "unitCode": "wmoUnit:degC"},
            "textDescription": "Partly Cloudy",
        }
        props.update(overrides)
        return {"properties": props}

    def test_parses_temperature(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.temperature_f == 68  # 20C = 68F

    def test_parses_humidity(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.humidity == 52.3

    def test_parses_wind_speed(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.wind_speed_mph is not None
        assert result.wind_speed_mph == pytest.approx(9.9, abs=0.2)

    def test_parses_wind_direction_degrees(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.wind_direction == "SW"

    def test_parses_pressure(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.pressure_mbar == 1015.0

    def test_parses_visibility(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.visibility_miles == 10.0

    def test_parses_feels_like_windchill(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.feels_like_f == 64  # 18C = 64.4 -> 64

    def test_parses_feels_like_heatindex_fallback(self):
        obs = self._make_obs(
            windChill={"value": None},
            heatIndex={"value": 35.0},
        )
        result = _parse_observation(obs)
        assert result.feels_like_f == 95  # 35C = 95F

    def test_parses_description(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.description == "Partly Cloudy"

    def test_handles_missing_values(self):
        obs = {"properties": {
            "temperature": {"value": None},
            "textDescription": "Fair",
        }}
        result = _parse_observation(obs)
        assert result.temperature_f is None
        assert result.description == "Fair"

    def test_parses_dewpoint(self):
        obs = self._make_obs()
        result = _parse_observation(obs)
        assert result.dewpoint_f == 50  # 10C = 50F


# ---------------------------------------------------------------------------
# Hourly precipitation parsing tests
# ---------------------------------------------------------------------------

class TestParseHourlyPrecip:
    """Test parsing of hourly precipitation probability data."""

    def test_parses_precip_values(self):
        data = {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-02-25T10:00:00-05:00",
                        "probabilityOfPrecipitation": {"value": 40},
                    },
                    {
                        "startTime": "2026-02-25T11:00:00-05:00",
                        "probabilityOfPrecipitation": {"value": 0},
                    },
                ]
            }
        }
        result = _parse_hourly_precip(data)
        assert result["2026-02-25T10:00:00-05:00"] == 40
        assert result["2026-02-25T11:00:00-05:00"] == 0

    def test_handles_none_precip(self):
        data = {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-02-25T10:00:00-05:00",
                        "probabilityOfPrecipitation": {"value": None},
                    },
                ]
            }
        }
        result = _parse_hourly_precip(data)
        assert len(result) == 0

    def test_handles_empty_data(self):
        result = _parse_hourly_precip({})
        assert result == {}

    def test_handles_missing_periods(self):
        result = _parse_hourly_precip({"properties": {}})
        assert result == {}


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestDataclasses:
    """Test dataclass construction and defaults."""

    def test_current_conditions_defaults(self):
        cc = CurrentConditions()
        assert cc.temperature_f is None
        assert cc.humidity is None
        assert cc.wind_direction == ""
        assert cc.description == ""

    def test_extended_data_defaults(self):
        ed = ExtendedData()
        assert ed.current is None
        assert ed.sun is None
        assert ed.hourly_precip is None

    def test_sun_data_defaults(self):
        sd = SunData()
        assert sd.sunrise == ""
        assert sd.sunset == ""

    def test_current_conditions_frozen(self):
        cc = CurrentConditions(temperature_f=72)
        with pytest.raises(AttributeError):
            cc.temperature_f = 80  # type: ignore


# ---------------------------------------------------------------------------
# Extract value helper tests
# ---------------------------------------------------------------------------

class TestExtractValue:
    """Test the _extract_value helper function."""

    def test_extracts_numeric(self):
        obs = {"temperature": {"value": 20.5}}
        assert _extract_value(obs, "temperature") == 20.5

    def test_returns_none_for_missing_key(self):
        assert _extract_value({}, "temperature") is None

    def test_returns_none_for_none_value(self):
        obs = {"temperature": {"value": None}}
        assert _extract_value(obs, "temperature") is None

    def test_returns_none_for_non_dict(self):
        obs = {"temperature": "not a dict"}
        assert _extract_value(obs, "temperature") is None
