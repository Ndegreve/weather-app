"""Centralized configuration loaded from environment variables.

All settings are read from environment variables with sensible defaults.
Also checks Streamlit secrets (st.secrets) for Streamlit Cloud deployments.
This ensures the app works in any cloud environment without hardcoded paths.
"""

import os


def get_anthropic_api_key() -> str:
    """Get the Anthropic API key lazily so st.secrets is ready.

    Must be called at runtime (not import time) because Streamlit
    Cloud only makes st.secrets available after the app starts.
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "ANTHROPIC_API_KEY" in st.secrets:
            return str(st.secrets["ANTHROPIC_API_KEY"])
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _get_int(key: str, default: int) -> int:
    """Read an integer environment variable with a default."""
    return int(os.environ.get(key, str(default)))


# NWS API
NWS_API_BASE_URL: str = os.environ.get("NWS_API_BASE_URL", "https://api.weather.gov")
NWS_USER_AGENT: str = os.environ.get(
    "NWS_USER_AGENT", "(weather-app, weather-app@example.com)"
)
NWS_REQUEST_TIMEOUT: int = _get_int("NWS_REQUEST_TIMEOUT", 15)

# Geocoding (Nominatim)
NOMINATIM_USER_AGENT: str = os.environ.get(
    "NOMINATIM_USER_AGENT", "us-weather-forecast-app"
)
NOMINATIM_TIMEOUT: int = _get_int("NOMINATIM_TIMEOUT", 10)

# Anthropic API — model and tokens from env vars, key is lazy via function
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
CHAT_MAX_TOKENS: int = _get_int("CHAT_MAX_TOKENS", 1024)
