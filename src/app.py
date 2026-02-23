"""Streamlit app for US weather forecasts — Apple Weather style.

Run with: streamlit run src/app.py

Layout (top to bottom):
1. Location name + current temp
2. Written forecast description
3. Chat box to ask questions
4. Horizontally scrollable hourly forecast
5. 7-day forecast list
6. Saved location tabs
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
# Global CSS
# ---------------------------------------------------------------------------

def _inject_css() -> None:
    """Inject CSS for dark-themed layout and weather sections.

    Dark background (#1a1a2e) with light text for high readability.
    Tile backgrounds use a lighter shade (#1e2d4d) for depth.
    """
    st.markdown("""
    <style>
    /* ===== HIGH CONTRAST LIGHT TEXT ON DARK ===== */
    .stMarkdown, .stMarkdown p, .stMarkdown li,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
    .stCaption, [data-testid="stCaptionContainer"],
    .stAlert p, .stAlert div {
        color: #f0f0f0 !important;
    }

    /* Forecast description text */
    .forecast-text {
        color: #e8e8e8 !important;
        font-size: 1rem;
        line-height: 1.6;
    }

    /* Chat message styling — dark-friendly */
    .chat-user {
        background: #1e3a5f;
        border-radius: 12px;
        padding: 10px 14px;
        margin: 6px 0;
        color: #e8e8e8;
        font-size: 0.95rem;
    }
    .chat-assistant {
        background: #1a3d2e;
        border-radius: 12px;
        padding: 10px 14px;
        margin: 6px 0;
        color: #e8e8e8;
        font-size: 0.95rem;
    }

    /* ===== HOURLY SCROLL ===== */
    .hourly-row {
        display: flex;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        gap: 0;
        padding: 12px 0;
        scrollbar-width: none;
    }
    .hourly-row::-webkit-scrollbar { display: none; }

    .hourly-item {
        flex: 0 0 65px;
        text-align: center;
        padding: 8px 4px;
    }
    .hourly-item .h-time {
        font-size: 0.8rem;
        font-weight: 600;
        color: #a0aec0;
        margin-bottom: 6px;
    }
    .hourly-item .h-icon {
        font-size: 1.4rem;
        margin-bottom: 4px;
    }
    .hourly-item .h-temp {
        font-size: 0.95rem;
        font-weight: 700;
        color: #f0f0f0;
    }

    /* ===== DAILY FORECAST ===== */
    .daily-row {
        display: flex;
        align-items: center;
        padding: 10px 0;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .daily-row .d-name {
        flex: 0 0 90px;
        font-weight: 600;
        font-size: 0.95rem;
        color: #f0f0f0;
    }
    .daily-row .d-icon {
        flex: 0 0 40px;
        font-size: 1.3rem;
        text-align: center;
    }
    .daily-row .d-lo {
        flex: 0 0 40px;
        text-align: right;
        font-size: 0.85rem;
        color: #8899aa;
    }
    .daily-row .d-bar {
        flex: 1;
        height: 5px;
        border-radius: 3px;
        background: linear-gradient(90deg, #4a90d9, #f0c040);
        margin: 0 8px;
    }
    .daily-row .d-hi {
        flex: 0 0 40px;
        text-align: left;
        font-size: 0.95rem;
        font-weight: 600;
        color: #f0f0f0;
    }

    /* ===== SECTION CARDS ===== */
    .weather-section {
        background: #1e2d4d;
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 12px;
    }
    .weather-section-title {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #8899aa;
        margin-bottom: 8px;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)


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
    if name.lower() not in [loc.lower() for loc in st.session_state.saved_locations]:
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
    """Geocode a location (cached for 1 hour)."""
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
    """Extract a short hour label like '3pm' from an ISO timestamp."""
    try:
        dt = datetime.fromisoformat(start_time)
        return dt.strftime("%-I%p").lower()
    except (ValueError, TypeError):
        return ""


def _render_header(forecast: Forecast, location: GeoLocation) -> None:
    """Render the big location name + current temp + conditions with high contrast."""
    if not forecast.periods:
        st.markdown(f"### {location.display_name}")
        return

    current = forecast.periods[0]
    icon = _get_weather_icon(current.short_forecast)
    display = forecast.location_name if forecast.location_name else location.display_name

    st.markdown(
        f'<h3 style="color:#f0f0f0;margin-bottom:0">{display}</h3>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="color:#ffffff;font-size:2.5rem;font-weight:700;margin:4px 0">'
        f'{icon} {current.temperature}\u00b0{current.temperature_unit}</div>'
        f'<div style="color:#d0d0d0;font-size:1.1rem;font-weight:600;margin-bottom:12px">'
        f'{current.short_forecast}</div>',
        unsafe_allow_html=True,
    )


def _render_written_forecast(forecast: Forecast) -> None:
    """Render written text forecast for the next 24 hours with high contrast."""
    if not forecast.periods:
        return

    st.markdown('<div class="weather-section">', unsafe_allow_html=True)
    st.markdown('<div class="weather-section-title">Forecast</div>', unsafe_allow_html=True)

    for p in forecast.periods[:3]:
        icon = _get_weather_icon(p.short_forecast)
        st.markdown(
            f'<div class="forecast-text"><strong>{icon} {p.name}</strong> — {p.detailed_forecast}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)


def _make_chat_callback(input_key: str):
    """Create a chat submission callback for a specific input key.

    Returns a closure that reads the question from the given session
    state key, calls the Claude API, and stores the response.
    """
    def _on_submit():
        question = st.session_state.get(input_key, "").strip()
        if not question:
            return

        tab_key = st.session_state.get("active_tab_key", "search")
        forecast = st.session_state.get("active_forecast")
        location = st.session_state.get("active_location")

        if not forecast or not location:
            return

        history_key = f"messages_{tab_key}"
        if history_key not in st.session_state:
            st.session_state[history_key] = []

        st.session_state[history_key].append({"role": "user", "content": question})

        try:
            answer = ask_weather_question(
                question=question,
                forecast=forecast,
                location=location,
                chat_history=st.session_state[history_key][:-1],
            )
            st.session_state[history_key].append(
                {"role": "assistant", "content": answer}
            )
        except ChatError as exc:
            st.session_state[history_key].append(
                {"role": "assistant", "content": f"Sorry, something went wrong: {exc}"}
            )

        # Clear the input for next question
        st.session_state[input_key] = ""

    return _on_submit


def _render_chat(forecast: Forecast, location: GeoLocation, tab_key: str) -> None:
    """Render the weather chat section with history and input.

    Uses a visible labeled text_input with an Ask button beside it.
    The label and button make it obvious this is tappable on mobile.
    """
    history_key = f"messages_{tab_key}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    # Store active context for the callback
    st.session_state["active_tab_key"] = tab_key
    st.session_state["active_forecast"] = forecast
    st.session_state["active_location"] = location

    api_key = config.get_anthropic_api_key()

    # Always show the chat section — with or without API key
    st.markdown(
        '<div class="weather-section">'
        '<div class="weather-section-title">\U0001f4ac Weather Q&A</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not api_key:
        st.warning(
            "Chat is not enabled. Add ANTHROPIC_API_KEY in "
            "Streamlit app Settings \u2192 Secrets to ask questions."
        )
        return

    # Show chat history
    if st.session_state[history_key]:
        for msg in st.session_state[history_key]:
            if msg["role"] == "user":
                st.markdown(
                    f'<div class="chat-user"><strong>You:</strong> {msg["content"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="chat-assistant"><strong>Weather AI:</strong> {msg["content"]}</div>',
                    unsafe_allow_html=True,
                )

    # Input: full-width text field with visible label
    input_key = f"chat_input_{tab_key}"
    st.text_input(
        "\U0001f4ac Ask a question about the weather",
        key=input_key,
        placeholder="Will it rain? Should I bring a jacket?",
        on_change=_make_chat_callback(input_key),
    )
    if st.button("Ask \u2192", key=f"chat_btn_{tab_key}", type="primary", use_container_width=True):
        _make_chat_callback(input_key)()
        st.rerun()


def _render_hourly_forecast(forecast: Forecast) -> None:
    """Render a horizontally scrollable hourly strip (like Apple Weather)."""
    if not forecast.hourly_periods:
        return

    hours = forecast.hourly_periods[:24]

    items_html = ""
    for h in hours:
        icon = _get_weather_icon(h.short_forecast)
        hour_label = _parse_hour(h.start_time)
        items_html += (
            f'<div class="hourly-item">'
            f'<div class="h-time">{hour_label}</div>'
            f'<div class="h-icon">{icon}</div>'
            f'<div class="h-temp">{h.temperature}\u00b0</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="weather-section">'
        f'<div class="weather-section-title">Hourly Forecast</div>'
        f'<div class="hourly-row">{items_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_daily_forecast(forecast: Forecast) -> None:
    """Render the multi-day forecast as a vertical list (like Apple Weather)."""
    if not forecast.periods:
        return

    days: list[dict] = []
    i = 0
    while i < len(forecast.periods):
        p = forecast.periods[i]
        day_info: dict = {
            "name": p.name.replace("This Afternoon", "Today"),
            "short": p.short_forecast,
            "detailed": p.detailed_forecast,
        }

        if p.is_daytime:
            day_info["high"] = p.temperature
            if i + 1 < len(forecast.periods) and not forecast.periods[i + 1].is_daytime:
                day_info["low"] = forecast.periods[i + 1].temperature
                day_info["night_detailed"] = forecast.periods[i + 1].detailed_forecast
                i += 2
            else:
                day_info["low"] = None
                i += 1
        else:
            day_info["name"] = p.name
            day_info["high"] = None
            day_info["low"] = p.temperature
            i += 1

        days.append(day_info)

    rows_html = ""
    for day in days:
        icon = _get_weather_icon(day["short"])
        hi = f'{day["high"]}\u00b0' if day.get("high") is not None else "--"
        lo = f'{day["low"]}\u00b0' if day.get("low") is not None else "--"

        rows_html += (
            f'<div class="daily-row">'
            f'<div class="d-name">{day["name"]}</div>'
            f'<div class="d-icon">{icon}</div>'
            f'<div class="d-lo">{lo}</div>'
            f'<div class="d-bar"></div>'
            f'<div class="d-hi">{hi}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="weather-section">'
        f'<div class="weather-section-title">7-Day Forecast</div>'
        f'{rows_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Detailed Forecasts"):
        for day in days:
            st.markdown(f"**{day['name']}**: {day['detailed']}")
            if day.get("night_detailed"):
                st.markdown(f"**{day['name']} Night**: {day['night_detailed']}")


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

    with st.spinner("Fetching forecast from NWS..."):
        try:
            forecast = _cached_forecast(location.latitude, location.longitude)
        except NWSPointNotFoundError:
            st.error("The NWS does not have forecast data for this location. Try a nearby city.")
            return
        except NWSAPIError as exc:
            st.error(str(exc))
            return

    # Layout (top to bottom):
    _render_header(forecast, location)
    _render_written_forecast(forecast)
    _render_chat(forecast, location, tab_key)
    _render_hourly_forecast(forecast)
    _render_daily_forecast(forecast)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="US Weather Forecast",
        page_icon="\u26c5",
        layout="centered",
    )

    _inject_css()
    _init_saved_locations()

    # --- Sidebar: manage locations ---
    with st.sidebar:
        st.header("Manage Locations")

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

        if st.session_state.saved_locations:
            for loc_name in st.session_state.saved_locations:
                col1, col2 = st.columns([3, 1])
                col1.write(loc_name)
                if col2.button("X", key=f"remove_{loc_name}"):
                    _remove_location(loc_name)
                    st.rerun()
        else:
            st.caption("No saved locations yet.")

    # --- Build tab list ---
    tab_names = []
    tab_queries = []

    if st.session_state.home_location:
        tab_names.append("Home")
        tab_queries.append(st.session_state.home_location)

    for loc_name in st.session_state.saved_locations:
        if st.session_state.home_location and loc_name.lower() == st.session_state.home_location.lower():
            continue
        tab_names.append(loc_name)
        tab_queries.append(loc_name)

    tab_names.append("Search")
    tab_queries.append(None)

    # --- Render ---
    if len(tab_names) == 1:
        st.info("Use the sidebar (\u00bb) to set a Home location, or search below.")
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
