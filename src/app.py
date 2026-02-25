"""Apple Weather-style Streamlit app for US weather forecasts.

Run with: streamlit run src/app.py

Replicates the Apple Weather layout with glassmorphism cards,
dynamic gradient backgrounds, temperature-colored bars, and
weather detail cards. Includes AI-powered Q&A via Claude.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from src import config
from src.chat import ChatError, ask_weather_question
from src.geocoding import GeocodingError, GeoLocation, NonUSLocationError, geocode_location
from src.nws_client import Forecast, NWSAPIError, NWSPointNotFoundError, get_forecast
from src.nws_extended import ExtendedData, get_extended_data


# ---------------------------------------------------------------------------
# Weather condition -> emoji mapping
# ---------------------------------------------------------------------------

_CONDITION_ICONS: dict[str, str] = {
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
# Dynamic gradient backgrounds
# ---------------------------------------------------------------------------

_WEATHER_GRADIENTS: dict[str, str] = {
    "clear_day": "linear-gradient(180deg, #1e88e5 0%, #42a5f5 40%, #64b5f6 100%)",
    "clear_night": "linear-gradient(180deg, #0d1b2a 0%, #1b2838 50%, #1a2744 100%)",
    "cloudy_day": "linear-gradient(180deg, #546e7a 0%, #78909c 50%, #90a4ae 100%)",
    "cloudy_night": "linear-gradient(180deg, #263238 0%, #37474f 50%, #455a64 100%)",
    "rain": "linear-gradient(180deg, #37474f 0%, #455a64 50%, #546e7a 100%)",
    "snow": "linear-gradient(180deg, #546e7a 0%, #78909c 50%, #90a4ae 100%)",
    "storm": "linear-gradient(180deg, #1a1a2e 0%, #2d2d44 50%, #1a1a2e 100%)",
    "fog": "linear-gradient(180deg, #607d8b 0%, #78909c 50%, #90a4ae 100%)",
    "default": "linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
}


def _get_gradient(short_forecast: str, is_daytime: bool) -> str:
    """Choose a background gradient based on weather conditions and time."""
    lower = short_forecast.lower()
    if any(w in lower for w in ("thunderstorm", "thunder")):
        return _WEATHER_GRADIENTS["storm"]
    if any(w in lower for w in ("rain", "shower", "drizzle")):
        return _WEATHER_GRADIENTS["rain"]
    if any(w in lower for w in ("snow", "blizzard", "sleet", "ice", "freezing")):
        return _WEATHER_GRADIENTS["snow"]
    if any(w in lower for w in ("fog", "haze", "mist")):
        return _WEATHER_GRADIENTS["fog"]
    if any(w in lower for w in ("cloudy", "overcast", "mostly cloudy")):
        return _WEATHER_GRADIENTS["cloudy_night"] if not is_daytime else _WEATHER_GRADIENTS["cloudy_day"]
    if any(w in lower for w in ("sunny", "clear", "mostly sunny", "mostly clear")):
        return _WEATHER_GRADIENTS["clear_night"] if not is_daytime else _WEATHER_GRADIENTS["clear_day"]
    return _WEATHER_GRADIENTS["default"]


# ---------------------------------------------------------------------------
# Temperature color mapping (Apple Weather style)
# ---------------------------------------------------------------------------

def _temp_to_color(temp_f: int) -> str:
    """Map a temperature (F) to an Apple Weather-style color.

    Returns a CSS color string.
    """
    if temp_f <= 10:
        return "#4a148c"  # deep purple — frigid
    if temp_f <= 32:
        return "#5c6bc0"  # indigo — freezing
    if temp_f <= 50:
        return "#42a5f5"  # blue — cold
    if temp_f <= 65:
        return "#26c6da"  # cyan — cool
    if temp_f <= 75:
        return "#66bb6a"  # green — comfortable
    if temp_f <= 85:
        return "#ffca28"  # amber — warm
    if temp_f <= 95:
        return "#ff7043"  # deep orange — hot
    return "#ef5350"  # red — extreme heat


def _compute_temp_bars(days: list[dict]) -> list[dict]:
    """Compute temperature bar positions and color gradients.

    Each day's bar is positioned relative to the overall min/max
    across all days, matching Apple Weather's visualization.
    """
    all_lows = [d["low"] for d in days if d.get("low") is not None]
    all_highs = [d["high"] for d in days if d.get("high") is not None]

    if not all_lows or not all_highs:
        return days

    global_min = min(all_lows)
    global_max = max(all_highs)
    spread = max(global_max - global_min, 1)

    for day in days:
        lo = day.get("low") if day.get("low") is not None else global_min
        hi = day.get("high") if day.get("high") is not None else global_max

        day["bar_left_pct"] = ((lo - global_min) / spread) * 100
        day["bar_width_pct"] = max(((hi - lo) / spread) * 100, 3)
        day["bar_color_lo"] = _temp_to_color(lo)
        day["bar_color_hi"] = _temp_to_color(hi)

    return days


# ---------------------------------------------------------------------------
# CSS injection — Apple Weather glassmorphism
# ---------------------------------------------------------------------------

def _inject_css(gradient: str) -> None:
    """Inject Apple Weather-style CSS with glassmorphism and dynamic gradient."""
    st.markdown(f"""
    <style>
    /* ===== PAGE BACKGROUND ===== */
    .stApp {{
        background: {gradient} !important;
    }}

    /* Hide Streamlit chrome for cleaner look */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    .block-container {{
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
        max-width: 600px !important;
    }}

    /* ===== GLASS CARD ===== */
    .glass-card {{
        background: rgba(255, 255, 255, 0.08);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        padding: 16px;
        margin-bottom: 14px;
    }}

    /* ===== SECTION LABEL ===== */
    .section-label {{
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: rgba(255, 255, 255, 0.55);
        margin-bottom: 10px;
        font-weight: 600;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }}

    /* ===== CURRENT CONDITIONS HEADER ===== */
    .wx-header {{
        text-align: center;
        padding: 10px 0 16px 0;
    }}
    .wx-location {{
        font-size: 1.4rem;
        color: rgba(255, 255, 255, 0.95);
        font-weight: 500;
        margin-bottom: 2px;
    }}
    .wx-temp {{
        font-size: 5rem;
        font-weight: 200;
        color: #ffffff;
        line-height: 1.05;
        margin: 0;
    }}
    .wx-condition {{
        font-size: 1.1rem;
        color: rgba(255, 255, 255, 0.8);
        margin: 4px 0;
    }}
    .wx-hilo {{
        font-size: 1rem;
        color: rgba(255, 255, 255, 0.7);
    }}

    /* ===== HOURLY SCROLL ===== */
    .hourly-row {{
        display: flex;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        gap: 0;
        padding: 4px 0;
        scrollbar-width: none;
    }}
    .hourly-row::-webkit-scrollbar {{ display: none; }}

    .hourly-item {{
        flex: 0 0 62px;
        text-align: center;
        padding: 6px 2px;
    }}
    .hourly-item .h-time {{
        font-size: 0.78rem;
        font-weight: 600;
        color: rgba(255,255,255,0.85);
        margin-bottom: 6px;
    }}
    .hourly-item .h-precip {{
        font-size: 0.7rem;
        color: #64b5f6;
        font-weight: 600;
        margin-bottom: 2px;
        min-height: 14px;
    }}
    .hourly-item .h-icon {{
        font-size: 1.3rem;
        margin-bottom: 6px;
    }}
    .hourly-item .h-temp {{
        font-size: 0.9rem;
        font-weight: 600;
        color: #ffffff;
    }}

    /* ===== DAILY FORECAST ===== */
    .daily-row {{
        display: flex;
        align-items: center;
        padding: 10px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .daily-row:last-child {{ border-bottom: none; }}
    .daily-row .d-name {{
        flex: 0 0 55px;
        font-weight: 600;
        font-size: 0.9rem;
        color: #ffffff;
    }}
    .daily-row .d-icon {{
        flex: 0 0 35px;
        font-size: 1.2rem;
        text-align: center;
    }}
    .daily-row .d-lo {{
        flex: 0 0 32px;
        text-align: right;
        font-size: 0.85rem;
        color: rgba(255,255,255,0.5);
        font-weight: 500;
    }}
    .daily-row .d-bar-track {{
        flex: 1;
        height: 5px;
        border-radius: 3px;
        background: rgba(255, 255, 255, 0.12);
        margin: 0 8px;
        position: relative;
        overflow: hidden;
    }}
    .daily-row .d-bar-fill {{
        position: absolute;
        top: 0;
        height: 100%;
        border-radius: 3px;
    }}
    .daily-row .d-hi {{
        flex: 0 0 32px;
        text-align: left;
        font-size: 0.9rem;
        font-weight: 600;
        color: #ffffff;
    }}

    /* ===== DETAIL CARDS ===== */
    .detail-card {{
        background: rgba(255, 255, 255, 0.08);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        padding: 14px;
        min-height: 130px;
    }}
    .detail-label {{
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: rgba(255, 255, 255, 0.5);
        margin-bottom: 8px;
        font-weight: 600;
    }}
    .detail-value {{
        font-size: 1.8rem;
        font-weight: 400;
        color: #ffffff;
        margin-bottom: 4px;
        line-height: 1.1;
    }}
    .detail-note {{
        font-size: 0.78rem;
        color: rgba(255, 255, 255, 0.55);
        line-height: 1.3;
    }}

    /* ===== CHAT BUBBLES ===== */
    .chat-user {{
        background: rgba(33, 150, 243, 0.25);
        backdrop-filter: blur(10px);
        border-radius: 16px 16px 4px 16px;
        padding: 10px 14px;
        margin: 6px 0;
        color: #ffffff;
        font-size: 0.9rem;
    }}
    .chat-assistant {{
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 16px 16px 16px 4px;
        padding: 10px 14px;
        margin: 6px 0;
        color: rgba(255,255,255,0.9);
        font-size: 0.9rem;
    }}

    /* ===== STREAMLIT OVERRIDES ===== */
    .stMarkdown, .stMarkdown p, .stMarkdown li,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
        color: #ffffff !important;
    }}
    .stTextInput > div > div > input {{
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
        border-radius: 12px !important;
    }}
    .stTextInput label {{
        color: rgba(255,255,255,0.7) !important;
    }}

    /* Tab styling — Apple-style dot navigation */
    .stTabs [data-baseweb="tab-list"] {{
        justify-content: center;
        gap: 8px;
        background: transparent !important;
        border-bottom: none !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-size: 0.8rem !important;
        padding: 6px 14px !important;
        border-radius: 20px !important;
        background: rgba(255,255,255,0.1) !important;
        color: rgba(255,255,255,0.7) !important;
        border: none !important;
    }}
    .stTabs [aria-selected="true"] {{
        background: rgba(255,255,255,0.25) !important;
        color: #ffffff !important;
    }}

    /* Button styling */
    .stButton > button[kind="primary"] {{
        background: rgba(255,255,255,0.15) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        color: #ffffff !important;
        border-radius: 12px !important;
    }}

    /* Expander styling */
    .streamlit-expanderHeader {{
        color: rgba(255,255,255,0.7) !important;
    }}

    /* Warning/info boxes */
    .stAlert {{
        background: rgba(255,255,255,0.08) !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 12px !important;
    }}
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


@st.cache_data(ttl=600, show_spinner=False)
def _cached_extended(lat: float, lon: float) -> ExtendedData:
    """Fetch extended weather data (cached for 10 minutes)."""
    try:
        return get_extended_data(lat, lon)
    except Exception:
        return ExtendedData()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _parse_hour(start_time: str) -> str:
    """Extract a short hour label like '3PM' from an ISO timestamp."""
    try:
        dt = datetime.fromisoformat(start_time)
        return dt.strftime("%-I%p")
    except (ValueError, TypeError):
        return ""


def _get_day_abbrev(name: str) -> str:
    """Convert a period name to a short day abbreviation."""
    name = name.replace("This Afternoon", "Today")
    if name in ("Today", "Tonight"):
        return name[:3]
    # NWS names like "Tuesday", "Wednesday Night" etc.
    return name[:3]


# ---------------------------------------------------------------------------
# Render: Current conditions header
# ---------------------------------------------------------------------------

def _render_header(
    forecast: Forecast,
    location: GeoLocation,
    extended: ExtendedData,
) -> None:
    """Render the Apple Weather-style centered current conditions."""
    if not forecast.periods:
        st.markdown(f"### {location.display_name}")
        return

    current_period = forecast.periods[0]
    display = forecast.location_name if forecast.location_name else location.display_name

    # Use observation station temp if available, otherwise forecast
    if extended.current and extended.current.temperature_f is not None:
        temp = extended.current.temperature_f
    else:
        temp = current_period.temperature

    condition = (
        extended.current.description
        if extended.current and extended.current.description
        else current_period.short_forecast
    )

    # Get H/L from forecast periods
    hi = current_period.temperature if current_period.is_daytime else None
    lo = None
    if len(forecast.periods) > 1:
        if current_period.is_daytime and not forecast.periods[1].is_daytime:
            lo = forecast.periods[1].temperature
        elif not current_period.is_daytime:
            lo = current_period.temperature
            if len(forecast.periods) > 1 and forecast.periods[1].is_daytime:
                hi = forecast.periods[1].temperature

    hilo_parts = []
    if hi is not None:
        hilo_parts.append(f"H:{hi}\u00b0")
    if lo is not None:
        hilo_parts.append(f"L:{lo}\u00b0")
    hilo = "  ".join(hilo_parts)

    st.markdown(
        f'<div class="wx-header">'
        f'<div class="wx-location">{display}</div>'
        f'<div class="wx-temp">{temp}\u00b0</div>'
        f'<div class="wx-condition">{condition}</div>'
        f'<div class="wx-hilo">{hilo}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Render: Hourly forecast strip
# ---------------------------------------------------------------------------

def _render_hourly(forecast: Forecast, extended: ExtendedData) -> None:
    """Render the horizontally scrollable hourly forecast strip."""
    if not forecast.hourly_periods:
        return

    hours = forecast.hourly_periods[:24]
    precip = extended.hourly_precip or {}

    items = ""
    for i, h in enumerate(hours):
        label = "Now" if i == 0 else _parse_hour(h.start_time)
        icon = _get_weather_icon(h.short_forecast)

        # Show precipitation chance if > 0%
        chance = precip.get(h.start_time, 0)
        precip_html = (
            f'<div class="h-precip">{chance}%</div>'
            if chance and chance > 0 else '<div class="h-precip"></div>'
        )

        items += (
            f'<div class="hourly-item">'
            f'<div class="h-time">{label}</div>'
            f'{precip_html}'
            f'<div class="h-icon">{icon}</div>'
            f'<div class="h-temp">{h.temperature}\u00b0</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="glass-card">'
        f'<div class="section-label">\U0001f552 HOURLY FORECAST</div>'
        f'<div class="hourly-row">{items}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Render: 10-day forecast with temperature bars
# ---------------------------------------------------------------------------

def _extract_daily_pairs(forecast: Forecast) -> list[dict]:
    """Extract day/night period pairs from forecast periods."""
    days: list[dict] = []
    i = 0
    while i < len(forecast.periods):
        p = forecast.periods[i]
        day_info: dict = {
            "name": _get_day_abbrev(p.name),
            "full_name": p.name.replace("This Afternoon", "Today"),
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
            day_info["full_name"] = p.name
            day_info["high"] = None
            day_info["low"] = p.temperature
            i += 1

        days.append(day_info)

    return days


def _render_daily(forecast: Forecast) -> None:
    """Render the multi-day forecast with Apple-style colored temp bars."""
    if not forecast.periods:
        return

    days = _extract_daily_pairs(forecast)
    days = _compute_temp_bars(days)

    rows = ""
    for day in days:
        icon = _get_weather_icon(day["short"])
        hi = f'{day["high"]}\u00b0' if day.get("high") is not None else "--"
        lo = f'{day["low"]}\u00b0' if day.get("low") is not None else "--"

        bar_left = day.get("bar_left_pct", 0)
        bar_width = day.get("bar_width_pct", 50)
        color_lo = day.get("bar_color_lo", "rgba(255,255,255,0.3)")
        color_hi = day.get("bar_color_hi", "rgba(255,255,255,0.3)")

        rows += (
            f'<div class="daily-row">'
            f'<div class="d-name">{day["name"]}</div>'
            f'<div class="d-icon">{icon}</div>'
            f'<div class="d-lo">{lo}</div>'
            f'<div class="d-bar-track">'
            f'<div class="d-bar-fill" style="left:{bar_left:.1f}%;width:{bar_width:.1f}%;'
            f'background:linear-gradient(90deg,{color_lo},{color_hi});">'
            f'</div></div>'
            f'<div class="d-hi">{hi}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="glass-card">'
        f'<div class="section-label">\U0001f4c5 7-DAY FORECAST</div>'
        f'{rows}'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Detailed Forecasts"):
        for day in days:
            st.markdown(f"**{day['full_name']}**: {day['detailed']}")
            if day.get("night_detailed"):
                st.markdown(f"**{day['full_name']} Night**: {day['night_detailed']}")


# ---------------------------------------------------------------------------
# Render: Weather detail cards (2-column grid)
# ---------------------------------------------------------------------------

def _render_detail_cards(
    forecast: Forecast,
    extended: ExtendedData,
) -> None:
    """Render Apple Weather-style detail cards in a 2-column grid."""
    current = extended.current
    if not current:
        return

    # Build cards list: (emoji, label, value, note)
    cards: list[tuple[str, str, str, str]] = []

    # Feels Like
    if current.feels_like_f is not None:
        feels = current.feels_like_f
        actual = current.temperature_f or feels
        if abs(feels - actual) <= 3:
            note = "Similar to the actual temperature."
        elif feels < actual:
            note = "Wind is making it feel colder."
        else:
            note = "Humidity is making it feel warmer."
        cards.append(("\U0001f321\ufe0f", "FEELS LIKE", f"{feels}\u00b0", note))

    # Wind
    if current.wind_speed_mph is not None:
        wind_val = f"{current.wind_speed_mph:.0f} mph"
        wind_note = f"Direction: {current.wind_direction}" if current.wind_direction else ""
        cards.append(("\U0001f32c\ufe0f", "WIND", wind_val, wind_note))

    # Humidity
    if current.humidity is not None:
        hum_note = ""
        if current.dewpoint_f is not None:
            hum_note = f"Dew point: {current.dewpoint_f}\u00b0"
        cards.append(("\U0001f4a7", "HUMIDITY", f"{current.humidity:.0f}%", hum_note))

    # Visibility
    if current.visibility_miles is not None:
        vis = current.visibility_miles
        vis_note = "Clear conditions." if vis >= 10 else "Reduced visibility."
        cards.append(("\U0001f441\ufe0f", "VISIBILITY", f"{vis:.0f} mi", vis_note))

    # Pressure
    if current.pressure_mbar is not None:
        # Convert mbar to inHg for US users
        inhg = round(current.pressure_mbar * 0.02953, 2)
        cards.append(("\u2b07\ufe0f", "PRESSURE", f"{inhg} inHg", f"{current.pressure_mbar:.0f} mbar"))

    if not cards:
        return

    # Render in 2-column grid
    for i in range(0, len(cards), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            idx = i + j
            if idx < len(cards):
                emoji, label, value, note = cards[idx]
                col.markdown(
                    f'<div class="detail-card">'
                    f'<div class="detail-label">{emoji} {label}</div>'
                    f'<div class="detail-value">{value}</div>'
                    f'<div class="detail-note">{note}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# Render: Chat Q&A
# ---------------------------------------------------------------------------

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

        st.session_state[input_key] = ""

    return _on_submit


def _render_chat(forecast: Forecast, location: GeoLocation, tab_key: str) -> None:
    """Render the weather chat section in a glass card."""
    history_key = f"messages_{tab_key}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    st.session_state["active_tab_key"] = tab_key
    st.session_state["active_forecast"] = forecast
    st.session_state["active_location"] = location

    api_key = config.get_anthropic_api_key()

    st.markdown(
        '<div class="glass-card">'
        '<div class="section-label">\U0001f4ac ASK ABOUT THE WEATHER</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not api_key:
        st.warning(
            "Chat is not enabled. Add ANTHROPIC_API_KEY in "
            "Streamlit app Settings \u2192 Secrets to ask questions."
        )
        return

    # Chat history
    if st.session_state[history_key]:
        for msg in st.session_state[history_key]:
            if msg["role"] == "user":
                st.markdown(
                    f'<div class="chat-user"><strong>You:</strong> {msg["content"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="chat-assistant"><strong>AI:</strong> {msg["content"]}</div>',
                    unsafe_allow_html=True,
                )

    # Input
    input_key = f"chat_input_{tab_key}"
    st.text_input(
        "Ask a question",
        key=input_key,
        placeholder="Will it rain? Should I bring a jacket?",
        on_change=_make_chat_callback(input_key),
    )
    if st.button("Ask \u2192", key=f"chat_btn_{tab_key}", type="primary", use_container_width=True):
        _make_chat_callback(input_key)()
        st.rerun()


# ---------------------------------------------------------------------------
# Render: Full location forecast
# ---------------------------------------------------------------------------

def _render_location_forecast(location_query: str, tab_key: str) -> None:
    """Fetch and render the full Apple Weather-style forecast."""
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

    with st.spinner("Fetching forecast..."):
        try:
            forecast = _cached_forecast(location.latitude, location.longitude)
        except NWSPointNotFoundError:
            st.error("NWS does not have data for this location. Try a nearby city.")
            return
        except NWSAPIError as exc:
            st.error(str(exc))
            return

    # Fetch extended data (best-effort, won't crash)
    extended = _cached_extended(location.latitude, location.longitude)

    # Set dynamic background gradient
    if forecast.periods:
        gradient = _get_gradient(
            forecast.periods[0].short_forecast,
            forecast.periods[0].is_daytime,
        )
    else:
        gradient = _WEATHER_GRADIENTS["default"]
    _inject_css(gradient)

    # Render all sections (Apple Weather order)
    _render_header(forecast, location, extended)
    _render_hourly(forecast, extended)
    _render_daily(forecast)
    _render_detail_cards(forecast, extended)
    _render_chat(forecast, location, tab_key)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="Weather",
        page_icon="\U0001f326\ufe0f",
        layout="centered",
    )

    # Inject default CSS (will be overridden per-location)
    _inject_css(_WEATHER_GRADIENTS["default"])
    _init_saved_locations()

    # --- Sidebar: manage locations ---
    with st.sidebar:
        st.markdown("### \U0001f30d Locations")

        st.text_input(
            "\U0001f3e0 Home Location",
            value=st.session_state.home_location or "",
            placeholder="e.g., Denver, CO",
            key="home_input",
        )
        if st.button("Set as Home", key="set_home_btn", use_container_width=True):
            val = st.session_state.get("home_input", "").strip()
            if val:
                _set_home(val)
                st.rerun()

        if st.session_state.home_location:
            st.success(f"\U0001f3e0 {st.session_state.home_location}")

        st.markdown("---")
        st.text_input(
            "Add a saved location",
            placeholder="e.g., Miami, FL",
            key="new_location_input",
        )
        if st.button("Add Location", key="add_loc_btn", use_container_width=True):
            val = st.session_state.get("new_location_input", "").strip()
            if val:
                _add_location(val)
                st.rerun()

        if st.session_state.saved_locations:
            for loc_name in st.session_state.saved_locations:
                col1, col2 = st.columns([4, 1])
                col1.write(f"\U0001f4cd {loc_name}")
                if col2.button("\u2715", key=f"rm_{loc_name}"):
                    _remove_location(loc_name)
                    st.rerun()
        else:
            st.caption("No saved locations yet.")

    # --- Build tab list ---
    tab_names: list[str] = []
    tab_queries: list[str | None] = []

    if st.session_state.home_location:
        tab_names.append("\U0001f3e0 Home")
        tab_queries.append(st.session_state.home_location)

    for loc_name in st.session_state.saved_locations:
        if (
            st.session_state.home_location
            and loc_name.lower() == st.session_state.home_location.lower()
        ):
            continue
        tab_names.append(loc_name)
        tab_queries.append(loc_name)

    tab_names.append("\U0001f50d Search")
    tab_queries.append(None)

    # --- Render ---
    if len(tab_names) == 1:
        st.markdown(
            '<div style="text-align:center;color:rgba(255,255,255,0.6);padding:20px 0;">'
            'Use the sidebar (\u00bb) to add your home location, or search below.'
            '</div>',
            unsafe_allow_html=True,
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
