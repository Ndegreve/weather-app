"""Streamlit app for US weather forecasts with conversational Q&A.

Run with: streamlit run src/app.py

Features:
- Home location + saved locations as tabs across the top
- Written text forecast for the next 24 hours
- Hourly temperature display
- 7-day forecast with hi/lo temps
- Chat interface to ask questions about the weather
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from src import config
from src.chat import ChatError, ask_weather_question
from src.geocoding import GeocodingError, GeoLocation, NonUSLocationError, geocode_location
from src.nws_client import Forecast, NWSAPIError, NWSPointNotFoundError, get_forecast


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
    if lower in _CONDITION_ICONS:
        return _CONDITION_ICONS[lower]
    for key, icon in _CONDITION_ICONS.items():
        if key in lower:
            return icon
    return "\U0001f321\ufe0f"


# ---------------------------------------------------------------------------
# Saved locations management
# ---------------------------------------------------------------------------

def _init_saved_locations() -> None:
    """Initialize saved locations in session state if not present."""
    if "saved_locations" not in st.session_state:
        st.session_state.saved_locations = []
    if "home_location" not in st.session_state:
        st.session_state.home_location = None


def _add_location(name: str) -> None:
    """Add a location to saved locations (if not already there)."""
    name = name.strip()
    if not name:
        return
    existing = [loc for loc in st.session_state.saved_locations]
    if name.lower() not in [loc.lower() for loc in existing]:
        st.session_state.saved_locations.append(name)


def _remove_location(name: str) -> None:
    """Remove a location from saved locations."""
    st.session_state.saved_locations = [
        loc for loc in st.session_state.saved_locations
        if loc.lower() != name.lower()
    ]


def _set_home(name: str) -> None:
    """Set the home location."""
    st.session_state.home_location = name.strip()


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


def _render_written_forecast(forecast: Forecast) -> None:
    """Render a written text forecast for the next 24 hours (today + tonight)."""
    if not forecast.periods:
        return

    st.subheader("Current Forecast")

    for p in forecast.periods[:3]:
        icon = _get_weather_icon(p.short_forecast)
        st.markdown(f"**{icon} {p.name}** \u2014 {p.detailed_forecast}")


def _render_hourly_forecast(forecast: Forecast) -> None:
    """Render the hourly forecast using native Streamlit columns."""
    if not forecast.hourly_periods:
        return

    st.subheader("Hourly Forecast")

    hours = forecast.hourly_periods[:12]
    cols = st.columns(len(hours))

    for col, h in zip(cols, hours):
        icon = _get_weather_icon(h.short_forecast)
        hour_label = _parse_hour(h.start_time)
        col.markdown(
            f"**{hour_label}**\n\n"
            f"{icon}\n\n"
            f"**{h.temperature}\u00b0**"
        )

    next_hours = forecast.hourly_periods[12:24]
    if next_hours:
        with st.expander("Next 12 hours"):
            cols2 = st.columns(len(next_hours))
            for col, h in zip(cols2, next_hours):
                icon = _get_weather_icon(h.short_forecast)
                hour_label = _parse_hour(h.start_time)
                col.markdown(
                    f"**{hour_label}**\n\n"
                    f"{icon}\n\n"
                    f"**{h.temperature}\u00b0**"
                )


def _render_daily_forecast(forecast: Forecast) -> None:
    """Render the 7-day forecast using native Streamlit columns."""
    if not forecast.periods:
        return

    st.subheader("7-Day Forecast")

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

    row_size = 4
    for row_start in range(0, len(days), row_size):
        row = days[row_start : row_start + row_size]
        cols = st.columns(len(row))
        for col, day in zip(cols, row):
            icon = _get_weather_icon(day["short"])
            temp_text = ""
            if day.get("high") is not None and day.get("low") is not None:
                temp_text = f"**{day['high']}\u00b0** / {day['low']}\u00b0"
            elif day.get("high") is not None:
                temp_text = f"**{day['high']}\u00b0**"
            elif day.get("low") is not None:
                temp_text = f"**{day['low']}\u00b0**"

            col.markdown(
                f"**{day['name']}**\n\n"
                f"{icon}\n\n"
                f"{temp_text}\n\n"
                f"{day['short']}"
            )

    with st.expander("Detailed Forecasts"):
        for day in days:
            st.markdown(f"**{day['name']}**: {day['detailed']}")
            if day.get("night_detailed"):
                night_name = day["name"] + " Night"
                st.markdown(f"**{night_name}**: {day['night_detailed']}")


def _render_chat(forecast: Forecast, location: GeoLocation, tab_key: str) -> None:
    """Render the conversational weather Q&A chat interface."""
    st.subheader("Ask About the Weather")

    if not config.ANTHROPIC_API_KEY:
        st.warning(
            "Set the ANTHROPIC_API_KEY environment variable to enable the chat feature."
        )
        return

    # Per-location chat history
    history_key = f"messages_{tab_key}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    for msg in st.session_state[history_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input(
        "e.g., Will it rain tonight? Can I go for a run?",
        key=f"chat_{tab_key}",
    ):
        st.session_state[history_key].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    answer = ask_weather_question(
                        question=prompt,
                        forecast=forecast,
                        location=location,
                        chat_history=st.session_state[history_key][:-1],
                    )
                    st.markdown(answer)
                    st.session_state[history_key].append(
                        {"role": "assistant", "content": answer}
                    )
                except ChatError as exc:
                    st.error(f"Could not get a response: {exc}")


def _render_location_forecast(location_query: str, tab_key: str) -> None:
    """Fetch and render the full forecast for a single location."""
    with st.spinner("Finding location..."):
        try:
            loc_data = _cached_geocode(location_query)
        except NonUSLocationError:
            st.error("This app only supports US locations.")
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

    _render_written_forecast(forecast)
    st.divider()
    _render_hourly_forecast(forecast)
    st.divider()
    _render_daily_forecast(forecast)
    st.divider()
    _render_chat(forecast, location, tab_key)


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

    _init_saved_locations()

    st.title("\u26c5 US Weather Forecast")
    st.caption("Powered by the National Weather Service (NOAA/NWS)")

    # --- Sidebar: manage locations ---
    with st.sidebar:
        st.header("Manage Locations")

        # Set home location
        st.subheader("Home Location")
        home_input = st.text_input(
            "Set your home city",
            value=st.session_state.home_location or "",
            placeholder="e.g., Denver, CO",
            key="home_input",
        )
        if st.button("Set as Home", key="set_home_btn"):
            if home_input.strip():
                _set_home(home_input)
                st.rerun()

        if st.session_state.home_location:
            st.success(f"Home: {st.session_state.home_location}")

        # Add saved locations
        st.subheader("Saved Locations")
        new_location = st.text_input(
            "Add a location",
            placeholder="e.g., Miami, FL",
            key="new_location_input",
        )
        if st.button("Add Location", key="add_loc_btn"):
            if new_location.strip():
                _add_location(new_location)
                st.rerun()

        # List saved locations with remove buttons
        if st.session_state.saved_locations:
            for loc_name in st.session_state.saved_locations:
                col1, col2 = st.columns([3, 1])
                col1.write(loc_name)
                if col2.button("X", key=f"remove_{loc_name}"):
                    _remove_location(loc_name)
                    st.rerun()
        else:
            st.caption("No saved locations yet.")

    # --- Build the tab list ---
    tab_names = []
    tab_queries = []

    if st.session_state.home_location:
        tab_names.append(f"Home")
        tab_queries.append(st.session_state.home_location)

    for loc_name in st.session_state.saved_locations:
        # Don't duplicate if same as home
        if st.session_state.home_location and loc_name.lower() == st.session_state.home_location.lower():
            continue
        tab_names.append(loc_name)
        tab_queries.append(loc_name)

    # Always add a "Search" tab at the end
    tab_names.append("Search")
    tab_queries.append(None)

    # --- Render tabs ---
    if len(tab_names) == 1:
        # Only the Search tab — no saved locations yet
        st.info(
            "Use the sidebar to set a Home location and add saved locations. "
            "Or search for a location below."
        )
        location_input = st.text_input(
            "Search for a US location",
            placeholder="e.g., Denver, CO  or  90210",
            key="search_input",
        )
        if location_input:
            _render_location_forecast(location_input, "search")
    else:
        tabs = st.tabs(tab_names)

        for i, tab in enumerate(tabs):
            with tab:
                query = tab_queries[i]
                if query is None:
                    # This is the Search tab
                    location_input = st.text_input(
                        "Search for a US location",
                        placeholder="e.g., Denver, CO  or  90210",
                        key="search_input",
                    )
                    if location_input:
                        _render_location_forecast(location_input, "search")
                else:
                    tab_key = query.lower().replace(" ", "_").replace(",", "")
                    _render_location_forecast(query, tab_key)


if __name__ == "__main__":
    main()
