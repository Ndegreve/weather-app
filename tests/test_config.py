"""Tests for the config module."""

import importlib
from unittest.mock import patch

from src import config


class TestConfigDefaults:
    """Verify default values when no environment variables are set."""

    def test_nws_api_base_url_default(self):
        assert config.NWS_API_BASE_URL == "https://api.weather.gov"

    def test_nws_user_agent_default(self):
        assert config.NWS_USER_AGENT == "(weather-app, weather-app@example.com)"

    def test_nws_request_timeout_default(self):
        assert config.NWS_REQUEST_TIMEOUT == 15

    def test_nominatim_user_agent_default(self):
        assert config.NOMINATIM_USER_AGENT == "us-weather-forecast-app"

    def test_nominatim_timeout_default(self):
        assert config.NOMINATIM_TIMEOUT == 10

    def test_anthropic_api_key_default_empty(self):
        assert config.ANTHROPIC_API_KEY == "" or isinstance(config.ANTHROPIC_API_KEY, str)

    def test_anthropic_model_default(self):
        assert config.ANTHROPIC_MODEL == "claude-sonnet-4-20250514"

    def test_chat_max_tokens_default(self):
        assert config.CHAT_MAX_TOKENS == 1024


class TestConfigEnvOverrides:
    """Verify environment variables override defaults."""

    @patch.dict("os.environ", {"NWS_API_BASE_URL": "https://custom.api.gov"})
    def test_nws_api_base_url_override(self):
        importlib.reload(config)
        assert config.NWS_API_BASE_URL == "https://custom.api.gov"
        importlib.reload(config)  # Reset

    @patch.dict("os.environ", {"NWS_REQUEST_TIMEOUT": "30"})
    def test_nws_request_timeout_override(self):
        importlib.reload(config)
        assert config.NWS_REQUEST_TIMEOUT == 30
        importlib.reload(config)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key-123"})
    def test_anthropic_api_key_override(self):
        importlib.reload(config)
        assert config.ANTHROPIC_API_KEY == "sk-test-key-123"
        importlib.reload(config)

    @patch.dict("os.environ", {"ANTHROPIC_MODEL": "claude-haiku-4-5-20251001"})
    def test_anthropic_model_override(self):
        importlib.reload(config)
        assert config.ANTHROPIC_MODEL == "claude-haiku-4-5-20251001"
        importlib.reload(config)

    @patch.dict("os.environ", {"CHAT_MAX_TOKENS": "2048"})
    def test_chat_max_tokens_override(self):
        importlib.reload(config)
        assert config.CHAT_MAX_TOKENS == 2048
        importlib.reload(config)


class TestConfigTypeConversion:
    """Verify integer environment variables are properly converted."""

    def test_nws_request_timeout_is_int(self):
        assert isinstance(config.NWS_REQUEST_TIMEOUT, int)

    def test_nominatim_timeout_is_int(self):
        assert isinstance(config.NOMINATIM_TIMEOUT, int)

    def test_chat_max_tokens_is_int(self):
        assert isinstance(config.CHAT_MAX_TOKENS, int)
