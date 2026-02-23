"""Centralized configuration loaded from environment variables.

All settings are read from environment variables with sensible defaults.
Also checks Streamlit secrets (st.secrets) for Streamlit Cloud deployments.
This ensures the app works in any cloud environment without hardcoded paths.
"""

import os


def _get_secret(key: str, default: str = "") -> str:
    """Read a config value from Streamlit secrets or environment variables.

    Streamlit Cloud stores secrets in st.secrets, not os.environ.
    This function checks both, with st.secrets taking priority.
    """
    # Try Streamlit secrets first (for Streamlit Cloud)
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass

    # Fall back to environment variable
    return os.environ.get(key, default)


def _get_int(key: str, default: int) -> int:
    """Read an integer config value with a default."""
    return int(_get_secret(key, str(default)))


# NWS API
NWS_API_BASE_URL: str = _get_secret("NWS_API_BASE_URL", "https://api.weather.gov")
NWS_USER_AGENT: str = _get_secret(
    "NWS_USER_AGENT", "(weather-app, weather-app@example.com)"
)
NWS_REQUEST_TIMEOUT: int = _get_int("NWS_REQUEST_TIMEOUT", 15)

# Geocoding (Nominatim)
NOMINATIM_USER_AGENT: str = _get_secret(
    "NOMINATIM_USER_AGENT", "us-weather-forecast-app"
)
NOMINATIM_TIMEOUT: int = _get_int("NOMINATIM_TIMEOUT", 10)

# Anthropic API
ANTHROPIC_API_KEY: str = _get_secret("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = _get_secret("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
CHAT_MAX_TOKENS: int = _get_int("CHAT_MAX_TOKENS", 1024)
