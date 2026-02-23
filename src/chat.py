"""Conversational weather Q&A powered by the Anthropic Claude API.

Takes the NWS forecast data as context and answers user questions
about the weather in natural language (e.g., "What time will the
storm arrive?", "Can I go for a run before the rain?").
"""

from __future__ import annotations

import anthropic

from src import config
from src.geocoding import GeoLocation
from src.nws_client import Forecast


class ChatError(Exception):
    """Raised when the chat API call fails."""


_SYSTEM_PROMPT = """\
You are a helpful weather assistant. You answer questions about the weather
based on official National Weather Service (NWS) forecast data provided below.

Rules:
- Base your answers ONLY on the forecast data provided. Do not make up weather information.
- Be specific about times, temperatures, and conditions when the data supports it.
- If the forecast data does not contain enough information to answer a question, say so honestly.
- Keep answers concise and conversational.
- When discussing timing (e.g., "when will the storm arrive"), reference the forecast period names and times.
- For activity-related questions (e.g., "can I mow the lawn"), consider temperature, precipitation, and wind.

Location: {location_name}
Coordinates: {lat}, {lon}

--- STANDARD FORECAST (12-hour periods) ---
{standard_forecast}

--- HOURLY FORECAST (next 24+ hours) ---
{hourly_forecast}
"""


def _build_forecast_context(forecast: Forecast) -> str:
    """Format the standard forecast periods as readable text."""
    lines = []
    for p in forecast.periods:
        lines.append(
            f"{p.name}: {p.detailed_forecast} "
            f"(Temp: {p.temperature}{p.temperature_unit}, "
            f"Wind: {p.wind_speed} {p.wind_direction})"
        )
    return "\n".join(lines)


def _build_hourly_context(forecast: Forecast, max_hours: int = 48) -> str:
    """Format the hourly forecast as readable text (capped to avoid token bloat)."""
    lines = []
    for p in forecast.hourly_periods[:max_hours]:
        lines.append(
            f"{p.start_time}: {p.short_forecast}, "
            f"{p.temperature}{p.temperature_unit}, "
            f"Wind {p.wind_speed} {p.wind_direction}"
        )
    return "\n".join(lines) if lines else "Hourly data not available."


def ask_weather_question(
    question: str,
    forecast: Forecast,
    location: GeoLocation,
    chat_history: list[dict] | None = None,
) -> str:
    """Ask a natural-language question about the weather forecast.

    Args:
        question: The user's question (e.g., "Will it rain tonight?").
        forecast: The current NWS forecast data.
        location: The resolved location for context.
        chat_history: Optional list of prior messages as
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}].

    Returns:
        Claude's text response.

    Raises:
        ChatError: If the API key is missing or the API call fails.
    """
    api_key = config.get_anthropic_api_key()
    if not api_key:
        raise ChatError(
            "ANTHROPIC_API_KEY is not set. "
            "Please set it in your environment to use the chat feature."
        )

    system = _SYSTEM_PROMPT.format(
        location_name=location.display_name,
        lat=location.latitude,
        lon=location.longitude,
        standard_forecast=_build_forecast_context(forecast),
        hourly_forecast=_build_hourly_context(forecast),
    )

    messages = []
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": question})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=config.CHAT_MAX_TOKENS,
            system=system,
            messages=messages,
        )
        return response.content[0].text
    except anthropic.APIError as exc:
        raise ChatError(f"Weather chat request failed: {exc}")
