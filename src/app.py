"""Streamlit app for US weather forecasts with conversational Q&A.

Run with: streamlit run src/app.py

Features:
- Enter any US location (city/state or zip code)
- Visual hourly forecast for the current day (icons + temps)
- 7-day forecast with hi/lo temps and weather icons
- Detailed text forecast per period
- Chat interface to ask questions about the weather
- Dynamic background that reflects current conditions
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from src import config
from src.chat import ChatError, ask_weather_question
from src.geocoding import GeocodingError, GeoLocation, NonUSLocationError, geocode_location
from src.nws_client import Forecast, ForecastPeriod, HourlyPeriod, NWSAPIError, NWSPointNotFoundError, get_forecast


# ---------------------------------------------------------------------------
# Weather condition -> emoji mapping
# ---------------------------------------------------------------------------

_CONDITION_ICONS = {
    "sunny": "\u2600\ufe0f",
    "clear": "\u2600\ufe0f",
    "mostly sunny": "\U0001f324\ufe0f",
    "mostly clear": "\U0001f319",
    "partly sunny": "\u26c5",
    "partly cloudy": "\u26c5",
    "mostly cloudy": "\U0001f325\ufe0f",
    "cloudy": "\u2601\ufe0f",
    "overcast": "\u2601\ufe0f",
    "fog": "\U0001f32b\ufe0f",
    "haze": "\U0001f32b\ufe0f",
    "rain": "\U0001f327\ufe0f",
    "light rain": "\U0001f326\ufe0f",
    "heavy rain": "\U0001f327\ufe0f",
    "showers": "\U0001f327\ufe0f",
    "rain showers": "\U0001f327\ufe0f",
    "chance rain showers": "\U0001f326\ufe0f",
    "slight chance rain showers": "\U0001f326\ufe0f",
    "scattered showers": "\U0001f326\ufe0f",
    "thunderstorm": "\u26c8\ufe0f",
    "thunderstorms": "\u26c8\ufe0f",
    "chance thunderstorms": "\u26c8\ufe0f",
    "snow": "\U0001f328\ufe0f",
    "light snow": "\U0001f328\ufe0f",
    "heavy snow": "\u2744\ufe0f",
    "blizzard": "\u2744\ufe0f",
    "sleet": "\U0001f328\ufe0f",
    "freezing rain": "\U0001f328\ufe0f",
    "ice": "\U0001f9ca",
    "windy": "\U0001f32c\ufe0f",
    "breezy": "\U0001f32c\ufe0f",
    "hot": "\U0001f525",
    "cold": "\U0001f976",
}


def _get_weather_icon(short_forecast: str) -> str:
    """Map a short forecast string to a weather emoji."""
    lower = short_forecast.lower().strip()
    # Try exact match first
    if lower in _CONDITION_ICONS:
        return _CONDITION_ICONS[lower]
    # Try substring match
    for key, icon in _CONDITION_ICONS.items():
        if key in lower:
            return icon
    # Fallback
    return "\U0001f321\ufe0f"


# ---------------------------------------------------------------------------
# Dynamic background CSS based on weather conditions
# ---------------------------------------------------------------------------

_WEATHER_THEMES = {
    "sunny": {
        "bg": "linear-gradient(180deg, #87CEEB 0%, #E0F4FF 50%, #FFF8E7 100%)",
        "text": "#1a1a2e",
        "card_bg": "rgba(255, 255, 255, 0.85)",
    },
    "clear": {
        "bg": "linear-gradient(180deg, #1a1a4e 0%, #2d3a8c 50%, #4a6fa5 100%)",
        "text": "#e8e8f0",
        "card_bg": "rgba(30, 30, 80, 0.75)",
    },
    "cloudy": {
        "bg": "linear-gradient(180deg, #8e9eab 0%, #b8c6d4 50%, #d4dde6 100%)",
        "text": "#2c3e50",
        "card_bg": "rgba(255, 255, 255, 0.80)",
    },
    "rain": {
        "bg": "linear-gradient(180deg, #4a5568 0%, #6b7b8d 50%, #8899a6 100%)",
        "text": "#ecf0f1",
        "card_bg": "rgba(40, 50, 60, 0.80)",
    },
    "snow": {
        "bg": "linear-gradient(180deg, #ccd5db 0%, #e8edf2 50%, #f5f7fa 100%)",
        "text": "#2c3e50",
        "card_bg": "rgba(255, 255, 255, 0.90)",
    },
    "thunderstorm": {
        "bg": "linear-gradient(180deg, #1a1a2e 0%, #2d2d44 50%, #434360 100%)",
        "text": "#e8e8f0",
        "card_bg": "rgba(30, 30, 50, 0.85)",
    },
    "fog": {
        "bg": "linear-gradient(180deg, #a8b5c2 0%, #c4cdd5 50%, #dee4ea 100%)",
        "text": "#3a4a5c",
        "card_bg": "rgba(255, 255, 255, 0.75)",
    },
    "default": {
        "bg": "linear-gradient(180deg, #667eea 0%, #764ba2 100%)",
        "text": "#ffffff",
        "card_bg": "rgba(255, 255, 255, 0.15)",
    },
}


def _detect_weather_theme(short_forecast: str, is_daytime: bool) -> dict:
    """Pick a background theme based on the current weather condition."""
    lower = short_forecast.lower()

    if any(w in lower for w in ("thunderstorm", "thunder")):
        return _WEATHER_THEMES["thunderstorm"]
    if any(w in lower for w in ("snow", "blizzard", "sleet", "ice", "freezing")):
        return _WEATHER_THEMES["snow"]
    if any(w in lower for w in ("rain", "shower", "drizzle")):
        return _WEATHER_THEMES["rain"]
    if any(w in lower for w in ("fog", "haze", "mist")):
        return _WEATHER_THEMES["fog"]
    if any(w in lower for w in ("cloudy", "overcast")):
        return _WEATHER_THEMES["cloudy"]
    if any(w in lower for w in ("sunny", "clear")):
        if is_daytime:
            return _WEATHER_THEMES["sunny"]
        return _WEATHER_THEMES["clear"]

    return _WEATHER_THEMES["default"]


def _apply_theme(theme: dict) -> None:
    """Inject CSS to style the page background and text."""
    st.markdown(
        f"""
        <style>
        .stApp {{
            background: {theme["bg"]};
            color: {theme["text"]};
        }}
        .stApp [data-testid="stHeader"] {{
            background: transparent;
        }}
        .weather-card {{
            background: {theme["card_bg"]};
            border-radius: 12px;
            padding: 16px;
            margin: 4px;
            text-align: center;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
        }}
        .weather-card h3 {{
            margin: 0 0 4px 0;
            font-size: 0.9rem;
        }}
        .weather-icon {{
            font-size: 2rem;
            margin: 4px 0;
        }}
        .weather-temp {{
            font-size: 1.4rem;
            font-weight: bold;
        }}
        .weather-temp-range {{
            font-size: 0.85rem;
            opacity: 0.8;
        }}
        .weather-desc {{
            font-size: 0.8rem;
            opacity: 0.9;
        }}
        .hourly-scroll {{
            display: flex;
            overflow-x: auto;
            gap: 8px;
            padding: 8px 0;
        }}
        .hourly-scroll .weather-card {{
            min-width: 80px;
            flex-shrink: 0;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Cached data-fetching helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_geocode(query: str) -> dict:
    """Geocode a location (cached for 1 hour). Returns a dict for cacheability."""
    loc = geocode_location(query)
    return {"lat": loc.latitude, "lon": loc.longitude, "name": loc.display_name}


@st.cache_data(ttl=900, show_spinner=False)
def _cached_forecast(lat: float, lon: float) -> Forecast:
    """Fetch the NWS forecast (cached for 15 minutes)."""
    return get_forecast(lat, lon)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _parse_hour(start_time: str) -> str:
    """Extract a short hour label from an ISO 8601 timestamp."""
    try:
        dt = datetime.fromisoformat(start_time)
        return dt.strftime("%-I%p").lower()
    except (ValueError, TypeError):
        return ""


def _render_hourly_forecast(forecast: Forecast) -> None:
    """Render the hourly forecast as a horizontally scrollable row."""
    if not forecast.hourly_periods:
        return

    # Show first 24 hours
    hours = forecast.hourly_periods[:24]
    st.subheader("Hourly Forecast")

    cards_html = ""
    for h in hours:
        icon = _get_weather_icon(h.short_forecast)
        hour_label = _parse_hour(h.start_time)
        cards_html += f"""
        <div class="weather-card">
            <h3>{hour_label}</h3>
            <div class="weather-icon">{icon}</div>
            <div class="weather-temp">{h.temperature}\u00b0{h.temperature_unit}</div>
            <div class="weather-desc">{h.short_forecast}</div>
        </div>
        """

    st.markdown(
        f'<div class="hourly-scroll">{cards_html}</div>',
        unsafe_allow_html=True,
    )


def _render_daily_forecast(forecast: Forecast) -> None:
    """Render the 7-day forecast as cards with hi/lo temps and icons."""
    if not forecast.periods:
        return

    st.subheader("7-Day Forecast")

    # Group periods into day/night pairs to show hi/lo
    days: list[dict] = []
    i = 0
    while i < len(forecast.periods):
        p = forecast.periods[i]
        day_info: dict = {
            "name": p.name.replace(" Night", "").replace("This Afternoon", "Today"),
            "short": p.short_forecast,
            "detailed": p.detailed_forecast,
        }

        if p.is_daytime:
            day_info["high"] = p.temperature
            day_info["unit"] = p.temperature_unit
            # Check if next period is the night counterpart
            if i + 1 < len(forecast.periods) and not forecast.periods[i + 1].is_daytime:
                day_info["low"] = forecast.periods[i + 1].temperature
                day_info["night_detailed"] = forecast.periods[i + 1].detailed_forecast
                i += 2
            else:
                day_info["low"] = None
                i += 1
        else:
            day_info["high"] = None
            day_info["low"] = p.temperature
            day_info["unit"] = p.temperature_unit
            i += 1

        days.append(day_info)

    # Render as columns (max 4 per row for readability)
    row_size = 4
    for row_start in range(0, len(days), row_size):
        row = days[row_start : row_start + row_size]
        cols = st.columns(len(row))
        for col, day in zip(cols, row):
            icon = _get_weather_icon(day["short"])
            temp_display = ""
            if day.get("high") is not None and day.get("low") is not None:
                temp_display = (
                    f'<div class="weather-temp">{day["high"]}\u00b0</div>'
                    f'<div class="weather-temp-range">Lo: {day["low"]}\u00b0</div>'
                )
            elif day.get("high") is not None:
                temp_display = f'<div class="weather-temp">{day["high"]}\u00b0</div>'
            elif day.get("low") is not None:
                temp_display = f'<div class="weather-temp">{day["low"]}\u00b0</div>'

            col.markdown(
                f"""
                <div class="weather-card">
                    <h3>{day["name"]}</h3>
                    <div class="weather-icon">{icon}</div>
                    {temp_display}
                    <div class="weather-desc">{day["short"]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Expandable detailed forecasts
    with st.expander("Detailed Forecasts"):
        for day in days:
            st.markdown(f"**{day['name']}**: {day['detailed']}")
            if day.get("night_detailed"):
                night_name = day["name"] + " Night"
                st.markdown(f"**{night_name}**: {day['night_detailed']}")


def _render_chat(forecast: Forecast, location: GeoLocation) -> None:
    """Render the conversational weather Q&A chat interface."""
    st.subheader("Ask About the Weather")

    if not config.ANTHROPIC_API_KEY:
        st.warning(
            "Set the ANTHROPIC_API_KEY environment variable to enable the chat feature."
        )
        return

    # Initialize chat history in session state
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display existing messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("e.g., Will it rain tonight? Can I go for a run?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    answer = ask_weather_question(
                        question=prompt,
                        forecast=forecast,
                        location=location,
                        chat_history=st.session_state.messages[:-1],
                    )
                    st.markdown(answer)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer}
                    )
                except ChatError as exc:
                    st.error(f"Could not get a response: {exc}")


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main():
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="US Weather Forecast",
        page_icon="\u26c5",
        layout="wide",
    )

    st.title("\u26c5 US Weather Forecast")
    st.caption("Powered by the National Weather Service (NOAA/NWS)")

    location_input = st.text_input(
        "Enter a US location",
        placeholder="e.g., Denver, CO  or  90210",
        key="location_input",
    )

    if not location_input:
        st.info("Enter a city and state or zip code above to get started.")
        return

    # --- Geocode ---
    with st.spinner("Finding location..."):
        try:
            loc_data = _cached_geocode(location_input)
        except NonUSLocationError:
            st.error(
                "This app only supports US locations. "
                "The National Weather Service only covers US territories."
            )
            return
        except GeocodingError as exc:
            st.error(str(exc))
            return

    location = GeoLocation(
        latitude=loc_data["lat"],
        longitude=loc_data["lon"],
        display_name=loc_data["name"],
    )
    st.markdown(f"**{location.display_name}**")

    # --- Fetch forecast ---
    with st.spinner("Fetching forecast from NWS..."):
        try:
            forecast = _cached_forecast(location.latitude, location.longitude)
        except NWSPointNotFoundError:
            st.error(
                "The NWS does not have forecast data for this location. "
                "Try a nearby city."
            )
            return
        except NWSAPIError as exc:
            st.error(str(exc))
            return

    # --- Apply dynamic background ---
    if forecast.periods:
        current = forecast.periods[0]
        theme = _detect_weather_theme(current.short_forecast, current.is_daytime)
    else:
        theme = _WEATHER_THEMES["default"]
    _apply_theme(theme)

    # --- Visual dashboard ---
    _render_hourly_forecast(forecast)
    _render_daily_forecast(forecast)

    st.divider()

    # --- Chat Q&A ---
    _render_chat(forecast, location)


if __name__ == "__main__":
    main()
