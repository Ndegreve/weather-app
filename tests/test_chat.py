"""Tests for the chat Q&A module."""

from unittest.mock import MagicMock, patch

import pytest

from src.chat import ChatError, ask_weather_question, _build_forecast_context, _build_hourly_context
from src.geocoding import GeoLocation
from src.nws_client import Forecast, ForecastPeriod, HourlyPeriod


@pytest.fixture()
def sample_location():
    return GeoLocation(
        latitude=39.7392,
        longitude=-104.9903,
        display_name="Denver, Denver County, Colorado, USA",
    )


@pytest.fixture()
def sample_forecast():
    return Forecast(
        location_name="Denver, CO",
        generated_at="2026-02-22T12:00:00+00:00",
        periods=[
            ForecastPeriod(
                name="Today",
                temperature=45,
                temperature_unit="F",
                wind_speed="10 to 15 mph",
                wind_direction="NW",
                short_forecast="Partly Cloudy",
                detailed_forecast="Partly cloudy, with a high near 45.",
                is_daytime=True,
                start_time="2026-02-22T06:00:00-07:00",
            ),
            ForecastPeriod(
                name="Tonight",
                temperature=28,
                temperature_unit="F",
                wind_speed="5 mph",
                wind_direction="S",
                short_forecast="Mostly Clear",
                detailed_forecast="Mostly clear, with a low around 28.",
                is_daytime=False,
                start_time="2026-02-22T18:00:00-07:00",
            ),
        ],
        hourly_periods=[
            HourlyPeriod(
                start_time="2026-02-22T10:00:00-07:00",
                temperature=38,
                temperature_unit="F",
                wind_speed="10 mph",
                wind_direction="NW",
                short_forecast="Partly Cloudy",
            ),
        ],
    )


class TestAskWeatherQuestion:
    """Test the ask_weather_question function."""

    @patch("src.chat.config")
    @patch("src.chat.anthropic.Anthropic")
    def test_returns_response_text(
        self, mock_anthropic_cls, mock_config, sample_location, sample_forecast
    ):
        mock_config.ANTHROPIC_API_KEY = "sk-test"
        mock_config.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
        mock_config.CHAT_MAX_TOKENS = 1024

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="It will be partly cloudy today.")]
        mock_client.messages.create.return_value = mock_response

        result = ask_weather_question(
            "What's the weather like today?",
            sample_forecast,
            sample_location,
        )

        assert result == "It will be partly cloudy today."

    @patch("src.chat.config")
    @patch("src.chat.anthropic.Anthropic")
    def test_includes_forecast_in_system_prompt(
        self, mock_anthropic_cls, mock_config, sample_location, sample_forecast
    ):
        mock_config.ANTHROPIC_API_KEY = "sk-test"
        mock_config.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
        mock_config.CHAT_MAX_TOKENS = 1024

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="answer")]
        mock_client.messages.create.return_value = mock_response

        ask_weather_question("test?", sample_forecast, sample_location)

        call_kwargs = mock_client.messages.create.call_args
        system_text = call_kwargs.kwargs["system"]
        assert "Partly cloudy" in system_text
        assert "Denver" in system_text

    @patch("src.chat.config")
    @patch("src.chat.anthropic.Anthropic")
    def test_passes_chat_history(
        self, mock_anthropic_cls, mock_config, sample_location, sample_forecast
    ):
        mock_config.ANTHROPIC_API_KEY = "sk-test"
        mock_config.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
        mock_config.CHAT_MAX_TOKENS = 1024

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="follow-up answer")]
        mock_client.messages.create.return_value = mock_response

        history = [
            {"role": "user", "content": "Will it rain?"},
            {"role": "assistant", "content": "No rain expected."},
        ]

        ask_weather_question(
            "What about tomorrow?",
            sample_forecast,
            sample_location,
            chat_history=history,
        )

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 3  # 2 history + 1 new
        assert messages[0]["content"] == "Will it rain?"
        assert messages[2]["content"] == "What about tomorrow?"

    @patch("src.chat.config")
    def test_missing_api_key_raises_error(
        self, mock_config, sample_location, sample_forecast
    ):
        mock_config.ANTHROPIC_API_KEY = ""

        with pytest.raises(ChatError, match="ANTHROPIC_API_KEY is not set"):
            ask_weather_question("test?", sample_forecast, sample_location)

    @patch("src.chat.config")
    @patch("src.chat.anthropic.Anthropic")
    def test_api_error_raises_chat_error(
        self, mock_anthropic_cls, mock_config, sample_location, sample_forecast
    ):
        mock_config.ANTHROPIC_API_KEY = "sk-test"
        mock_config.ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
        mock_config.CHAT_MAX_TOKENS = 1024

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API down")

        # The function catches anthropic.APIError specifically, but a generic
        # Exception won't be caught — let's test with a proper mock
        import anthropic as anthropic_mod

        mock_client.messages.create.side_effect = anthropic_mod.APIConnectionError(
            request=MagicMock()
        )

        with pytest.raises(ChatError, match="chat request failed"):
            ask_weather_question("test?", sample_forecast, sample_location)


class TestBuildForecastContext:
    """Test forecast context formatting."""

    def test_formats_periods(self, sample_forecast):
        text = _build_forecast_context(sample_forecast)
        assert "Today:" in text
        assert "Tonight:" in text
        assert "45F" in text

    def test_empty_periods(self):
        forecast = Forecast(location_name="Test", generated_at="", periods=[])
        text = _build_forecast_context(forecast)
        assert text == ""


class TestBuildHourlyContext:
    """Test hourly context formatting."""

    def test_formats_hourly_periods(self, sample_forecast):
        text = _build_hourly_context(sample_forecast)
        assert "Partly Cloudy" in text
        assert "38F" in text

    def test_empty_hourly_periods(self):
        forecast = Forecast(location_name="Test", generated_at="")
        text = _build_hourly_context(forecast)
        assert text == "Hourly data not available."

    def test_caps_at_max_hours(self):
        periods = [
            HourlyPeriod(
                start_time=f"2026-02-22T{i:02d}:00:00-07:00",
                temperature=40 + i,
                temperature_unit="F",
                wind_speed="5 mph",
                wind_direction="N",
                short_forecast="Clear",
            )
            for i in range(60)
        ]
        forecast = Forecast(
            location_name="Test",
            generated_at="",
            hourly_periods=periods,
        )
        text = _build_hourly_context(forecast, max_hours=24)
        assert text.count("\n") == 23  # 24 lines, 23 newlines
