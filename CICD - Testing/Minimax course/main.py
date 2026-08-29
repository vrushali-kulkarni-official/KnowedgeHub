"""Weather lookup skill — example implementation.

Replace the body with your real API call.
"""
from __future__ import annotations

from typing import Any


def run(inputs: dict[str, Any]) -> dict[str, Any]:
    """Look up the weather for a city.

    Args:
        inputs: Must contain 'city'. Optionally 'units' (celsius/fahrenheit).

    Returns:
        {"temperature": float, "conditions": str} on success.
        {"error": str} on failure.
    """
    city = inputs.get("city")
    if not city:
        return {"error": "city is required"}
    units = inputs.get("units", "celsius")
    if units not in {"celsius", "fahrenheit"}:
        return {"error": "units must be 'celsius' or 'fahrenheit'"}

    # In production, call the real OpenWeatherMap API.
    # For this example, return a deterministic stub.
    return {
        "temperature": 22.0 if units == "celsius" else 71.6,
        "conditions": "sunny",
    }
