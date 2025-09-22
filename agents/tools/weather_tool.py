import os
import logging
import requests
import time
from langchain_core.tools import tool
from utils.api_logger import log_api_call

logger = logging.getLogger(__name__)

# Real Google Weather API call
def get_current_weather(lat: float, lng: float, units: str = "IMPERIAL") -> dict:
    # Use the canonical GOOGLE_API_KEY environment variable
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Missing Google Cloud API key. Set GOOGLE_API_KEY in your environment.")
    logger.debug("Using Google API key from GOOGLE_API_KEY")
    logger.info(f"Calling Google Weather API for lat={lat}, lng={lng}")
    
    url = (
        f"https://weather.googleapis.com/v1/currentConditions:lookup"
        f"?key={api_key}"
        f"&location.latitude={lat}"
        f"&location.longitude={lng}"
        f"&unitsSystem={units.upper()}"
    )
    headers = {
        "X-Goog-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    logger.debug(f"API URL: {url}")
    logger.debug(f"API Headers: {headers}")
    
    start = time.time()
    r = requests.get(url, headers=headers, timeout=20)
    elapsed_ms = int((time.time() - start) * 1000)
    try:
        response_bytes = len(r.content) if r.content is not None else None
    except Exception:
        response_bytes = None

    logger.debug(f"API Response Status: {r.status_code}")
    logger.debug(f"API Response Headers: {dict(r.headers)}")
    logger.debug(f"API Response Body: {r.text[:500]}...")  # First 500 chars

    # Ensure we raise for HTTP errors first
    r.raise_for_status()
    response_data = r.json()
    logger.debug(f"Parsed API Response: {response_data}")

    # Best-effort API call logging. Do not let logging failures break the tool.
    try:
        log_api_call(
            tool_name="weather_tool",
            provider="google",
            endpoint="currentConditions:lookup",
            status=r.status_code,
            elapsed_ms=elapsed_ms,
            response_bytes=response_bytes,
            params={"lat": lat, "lng": lng, "units": units},
            estimated_cost=None,
        )
    except Exception:
        logger.debug("api_logger.log_api_call failed but continuing")

    return response_data

@tool("Weather")
def weather_current(lat: float, lng: float, units: str = "IMPERIAL") -> dict:
    """Return dict with currentConditions; raises on error."""
    data = get_current_weather(lat, lng, units)
    # Build a WorldState-compatible patch
    # Google Weather API returns data at root level
    conditions = data.get("weatherCondition", {})
    temp = data.get("temperature", {})
    temp_value = temp.get("degrees") if units.upper() == "IMPERIAL" else temp.get("degreesCelsius")
    weather_patch = {
        "context": {
            "lastWeather": {
                "lat": lat,
                "lng": lng,
                "units": units,
                "summary": conditions.get("description", {}).get("text", ""),
                "temp": temp_value,
                "feels_like": temp.get("heatIndex") or temp_value,
                "humidity": data.get("relativeHumidity"),
                "wind_speed": data.get("wind", {}).get("speed", {}).get("value"),
                "raw": data
            }
        }
    }
    return weather_patch
