"""Tests for the NWS API client module."""

import httpx
import pytest
import respx

from src.nws_client import (
    Forecast,
    ForecastPeriod,
    HourlyPeriod,
    NWSAPIError,
    NWSPointNotFoundError,
    get_forecast,
)


NWS_BASE = "https://api.weather.gov"


class TestGetForecastSuccess:
    """Test successful forecast retrieval."""

    @respx.mock
    def test_returns_forecast_with_periods(
        self, points_response, forecast_response, hourly_response
    ):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json=forecast_response))
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast/hourly"
        ).mock(return_value=httpx.Response(200, json=hourly_response))

        result = get_forecast(39.7392, -104.9903)

        assert isinstance(result, Forecast)
        assert len(result.periods) == 2
        assert len(result.hourly_periods) == 3

    @respx.mock
    def test_parses_period_fields(
        self, points_response, forecast_response, hourly_response
    ):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json=forecast_response))
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast/hourly"
        ).mock(return_value=httpx.Response(200, json=hourly_response))

        result = get_forecast(39.7392, -104.9903)
        today = result.periods[0]

        assert isinstance(today, ForecastPeriod)
        assert today.name == "Today"
        assert today.temperature == 45
        assert today.temperature_unit == "F"
        assert today.wind_speed == "10 to 15 mph"
        assert today.wind_direction == "NW"
        assert today.short_forecast == "Partly Cloudy"
        assert "high near 45" in today.detailed_forecast
        assert today.is_daytime is True

    @respx.mock
    def test_parses_hourly_fields(
        self, points_response, forecast_response, hourly_response
    ):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json=forecast_response))
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast/hourly"
        ).mock(return_value=httpx.Response(200, json=hourly_response))

        result = get_forecast(39.7392, -104.9903)
        hour = result.hourly_periods[0]

        assert isinstance(hour, HourlyPeriod)
        assert hour.temperature == 38
        assert hour.short_forecast == "Partly Cloudy"

    @respx.mock
    def test_location_name_from_points(
        self, points_response, forecast_response, hourly_response
    ):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json=forecast_response))
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast/hourly"
        ).mock(return_value=httpx.Response(200, json=hourly_response))

        result = get_forecast(39.7392, -104.9903)

        assert result.location_name == "Denver, CO"

    @respx.mock
    def test_generated_at_timestamp(
        self, points_response, forecast_response, hourly_response
    ):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json=forecast_response))
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast/hourly"
        ).mock(return_value=httpx.Response(200, json=hourly_response))

        result = get_forecast(39.7392, -104.9903)

        assert result.generated_at == "2026-02-22T12:00:00+00:00"

    @respx.mock
    def test_rounds_coordinates_to_four_decimals(
        self, points_response, forecast_response, hourly_response
    ):
        route = respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json=forecast_response))
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast/hourly"
        ).mock(return_value=httpx.Response(200, json=hourly_response))

        get_forecast(39.73921234, -104.99031234)

        assert route.called

    @respx.mock
    def test_hourly_failure_does_not_break_forecast(
        self, points_response, forecast_response
    ):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json=forecast_response))
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast/hourly"
        ).mock(return_value=httpx.Response(500, json={}))

        result = get_forecast(39.7392, -104.9903)

        assert len(result.periods) == 2
        assert result.hourly_periods == []


class TestGetForecastErrors:
    """Test error handling in forecast retrieval."""

    @respx.mock
    def test_point_not_found_raises_error(self):
        respx.get(f"{NWS_BASE}/points/0.0,0.0").mock(
            return_value=httpx.Response(404, json={})
        )

        with pytest.raises(NWSPointNotFoundError, match="does not have data"):
            get_forecast(0.0, 0.0)

    @respx.mock
    def test_server_error_raises_after_retry(self):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(500, json={})
        )

        with pytest.raises(NWSAPIError, match="server error"):
            get_forecast(39.7392, -104.9903)

    @respx.mock
    def test_timeout_raises_error(self):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        with pytest.raises(NWSAPIError, match="timed out"):
            get_forecast(39.7392, -104.9903)

    @respx.mock
    def test_invalid_json_raises_error(self):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})
        )

        with pytest.raises(NWSAPIError, match="invalid JSON"):
            get_forecast(39.7392, -104.9903)

    @respx.mock
    def test_missing_properties_raises_error(self):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json={"type": "Feature"})
        )

        with pytest.raises(NWSAPIError, match="Unexpected response"):
            get_forecast(39.7392, -104.9903)

    @respx.mock
    def test_missing_forecast_periods_raises_error(self, points_response):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(200, json=points_response)
        )
        respx.get(
            f"{NWS_BASE}/gridpoints/BOU/62,60/forecast"
        ).mock(return_value=httpx.Response(200, json={"properties": {}}))

        with pytest.raises(NWSAPIError, match="Unexpected forecast"):
            get_forecast(39.7392, -104.9903)

    @respx.mock
    def test_unexpected_status_code_raises_error(self):
        respx.get(f"{NWS_BASE}/points/39.7392,-104.9903").mock(
            return_value=httpx.Response(403, json={})
        )

        with pytest.raises(NWSAPIError, match="Unexpected response"):
            get_forecast(39.7392, -104.9903)
