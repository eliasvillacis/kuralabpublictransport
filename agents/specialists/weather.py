# agents/specialists/weather.py
# Specialist for weather hazards and travel-impacting conditions.
# Uses Google Weather API for real-time and forecast weather data.
# Uses direct information from the supervisor without an LLM dependency.

import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from langchain.schema.runnable import Runnable, RunnableLambda

from utils.google_maps import geocode_place, get_location_from_source
from utils.logger import get_logger
import requests

logger = get_logger(__name__)

# ----------------------------
# Google Weather API helpers
# ----------------------------

def google_weather_now(lat: float, lon: float, units: str = "IMPERIAL") -> Dict[str, Any]:
    """
    Get current weather conditions from Google Maps Weather API.
    Returns the inner `currentConditions` object when present.
    """
    api_key = os.getenv("GOOGLE_CLOUD_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_CLOUD_API_KEY")

    url = (
        f"https://weather.googleapis.com/v1/currentConditions:lookup"
        f"?key={api_key}"
        f"&location.latitude={lat}"
        f"&location.longitude={lon}"
        f"&unitsSystem={units.upper()}"
    )
    headers = {
        "X-Goog-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    logger.debug(f"Fetching weather data for coordinates ({lat}, {lon})")
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    # unwrap if present
    return data.get("currentConditions", data)


def google_weather_hourly(lat: float, lon: float, hours: int = 24, units: str = "IMPERIAL") -> List[Dict[str, Any]]:
    """
    Get hourly weather forecast from Google Maps Weather API.
    Returns list of normalized hourly dicts.
    """
    api_key = os.getenv("GOOGLE_CLOUD_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_CLOUD_API_KEY")

    url = (
        f"https://weather.googleapis.com/v1/forecast/hours:lookup"
        f"?key={api_key}"
        f"&location.latitude={lat}"
        f"&location.longitude={lon}"
        f"&hours={min(hours, 240)}"
        f"&unitsSystem={units.upper()}"
    )

    headers = {
        "X-Goog-Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()

    if "forecastHours" not in data:
        logger.error("No forecast data in response")
        return []

    forecasts: List[Dict[str, Any]] = []
    for hour in data["forecastHours"]:
        start_time = datetime.fromisoformat(hour["interval"]["startTime"].replace("Z", "+00:00"))

        fc: Dict[str, Any] = {
            "time": start_time.isoformat(),
            "conditions": hour["weatherCondition"]["description"]["text"],
            "icon": hour["weatherCondition"].get("iconBaseUri"),
            "temperature": {
                "value": hour["temperature"]["degrees"],
                "unit": hour["temperature"]["unit"],
            },
            "feels_like": {
                "value": hour["feelsLikeTemperature"]["degrees"],
                "unit": hour["feelsLikeTemperature"]["unit"],
            },
            "humidity": hour.get("relativeHumidity"),
            "precipitation": {
                "probability": hour["precipitation"]["probability"]["percent"],
                "type": hour["precipitation"]["probability"]["type"].lower(),
            },
            "wind": {
                "speed": {
                    "value": hour["wind"]["speed"]["value"],
                    "unit": hour["wind"]["speed"]["unit"],
                },
                "direction": hour["wind"]["direction"]["cardinal"],
            },
            "cloud_cover": hour.get("cloudCover"),
            "is_daytime": hour.get("isDaytime"),
        }

        if "uvIndex" in hour:
            fc["uv_index"] = hour["uvIndex"]
        if "thunderstormProbability" in hour:
            fc["thunderstorm_probability"] = hour["thunderstormProbability"]

        forecasts.append(fc)

    return forecasts


def format_hourly_forecast(forecasts: List[Dict[str, Any]], hours: Optional[int] = None) -> str:
    """
    Format hourly forecast data into a human-readable string.
    """
    if not forecasts:
        return "No forecast data available."

    if hours:
        forecasts = forecasts[:hours]

    lines = []
    for f in forecasts:
        time = datetime.fromisoformat(f["time"]).strftime("%I %p").lstrip("0")
        temp = f"{f['temperature']['value']}°{f['temperature']['unit'][0]}"
        feels = f"{f['feels_like']['value']}°{f['feels_like']['unit'][0]}"
        temp_str = temp if temp == feels else f"{temp} (feels like {feels})"

        precip = ""
        if f["precipitation"]["probability"] > 0:
            precip = f", {f['precipitation']['probability']}% chance of {f['precipitation']['type']}"

        wind = ""
        if f["wind"]["speed"]["value"] > 5:
            wind = f", {f['wind']['direction']} wind {f['wind']['speed']['value']} {f['wind']['speed']['unit']}"

        line = f"{time}: {f['conditions']}, {temp_str}{precip}{wind}"
        lines.append(line)

    return "\n".join(lines)


def _normalize_weather(payload: Dict[str, Any], label: Optional[str]) -> Dict[str, Any]:
    """
    Normalize the current-conditions payload (handles top-level or nested `currentConditions`).
    """
    if not payload:
        return {
            "location": label or "Unknown",
            "conditions": "Unknown",
            "temperature_fahrenheit": None,
            "wind_mph": None,
            "humidity_percent": None,
            "source": "Google Maps Platform Weather",
        }

    # unwrap if caller passed the full response by mistake
    if "currentConditions" in payload and isinstance(payload["currentConditions"], dict):
        payload = payload["currentConditions"]

    try:
        # Description
        desc = "Unknown"
        condition = payload.get("weatherCondition", {})
        if isinstance(condition, dict):
            desc_obj = condition.get("description", {})
            if isinstance(desc_obj, dict):
                desc = desc_obj.get("text", "Unknown")

        # Temperature -> Fahrenheit
        temp_f = None
        temp = payload.get("temperature", {})
        if isinstance(temp, dict):
            degrees = temp.get("degrees")
            unit = (temp.get("unit") or "").upper()
            if degrees is not None:
                if unit == "CELSIUS":
                    temp_f = round((degrees * 9 / 5) + 32, 1)
                elif unit == "FAHRENHEIT":
                    temp_f = round(degrees, 1)

        # Wind mph + direction
        wind_mph = None
        wind_dir = None
        wind = payload.get("wind", {})
        if isinstance(wind, dict):
            speed = wind.get("speed", {})
            if isinstance(speed, dict):
                sv = speed.get("value")
                su = (speed.get("unit") or "").upper()
                if sv is not None:
                    if su == "KILOMETERS_PER_HOUR":
                        wind_mph = round(sv * 0.621371, 1)
                    elif su == "MILES_PER_HOUR":
                        wind_mph = round(sv, 1)
            direction = wind.get("direction", {})
            if isinstance(direction, dict):
                wind_dir = (direction.get("cardinal") or "").replace("_", " ").title() or None

        humidity = payload.get("relativeHumidity")

        result: Dict[str, Any] = {
            "location": label or "Unknown",
            "conditions": desc,
            "temperature_fahrenheit": temp_f,
            "wind_mph": wind_mph,
            "humidity_percent": humidity,
            "source": "Google Maps Platform Weather",
        }
        if wind_dir:
            result["wind_direction"] = wind_dir

        return result

    except Exception as e:
        logger.error(f"Error parsing weather data: {e}")
        logger.debug(f"Raw payload keys: {list(payload.keys())}")
        raise


# ----------------------------
# Agent
# ----------------------------

def create_weather_agent() -> Runnable:
    # No need for LLM initialization since we'll use the supervisor's extracted data
    
    # Time reference mapping for forecast types
    TIME_REFERENCE_MAPPING = {
        "now": {"type": "current"},
        "current": {"type": "current"},
        "today": {"type": "current"},
        "tomorrow": {"type": "hourly", "hours": 24},
        "morning": {"type": "hourly", "hours": 12},
        "afternoon": {"type": "hourly", "hours": 12},
        "evening": {"type": "hourly", "hours": 12},
        "night": {"type": "hourly", "hours": 12},
        "weekend": {"type": "daily"},
        "week": {"type": "daily"},
        "later": {"type": "hourly", "hours": 6},
        "tonight": {"type": "hourly", "hours": 6}
    }
    
    # We'll now use the supervisor's extracted information directly
    # No need for hybrid parsing anymore
    def extract_weather_info(x: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract weather information from the supervisor's data.
        
        This function is part of the LLM-free specialist design pattern:
        - It processes structured data already extracted by the supervisor's LLM
        - No LLM calls are made in this specialist
        - Data is directly prepared for API calls without language understanding
        
        This replaces the previous hybrid parsing approach (rule-based + LLM fallback)
        with direct use of supervisor-extracted information, making the specialist
        more efficient and removing duplicate LLM processing.
        
        Args:
            x: Dictionary containing supervisor-extracted information including
               location_context, origin, destination, time_reference, etc.
               
        Returns:
            Dictionary with structured weather intent information
        """
        intent = {}
        
        # Extract location from supervisor-provided info
        if x.get("location_context"):
            intent["place"] = x["location_context"]
        elif x.get("origin"):
            intent["place"] = x["origin"]
        elif x.get("destination"):
            intent["place"] = x["destination"]
            
        # Extract time reference
        if x.get("time_reference"):
            intent["time_reference"] = x["time_reference"]
            # Set forecast type based on time reference
            time_ref = x["time_reference"].lower() if x.get("time_reference") else ""
            
            if time_ref in TIME_REFERENCE_MAPPING:
                forecast_info = TIME_REFERENCE_MAPPING[time_ref]
                intent["type"] = forecast_info["type"]
                if "hours" in forecast_info:
                    intent["hours"] = forecast_info["hours"]
            else:
                # Default to current if time reference isn't recognized
                intent["type"] = "current"
                
        # Use intent from supervisor if available
        if x.get("intent"):
            if "weather" in x["intent"].lower():
                if "rain" in x["intent"].lower():
                    intent["weather_condition"] = "rain"
                elif "snow" in x["intent"].lower():
                    intent["weather_condition"] = "snow"
                    
        return intent


    def _exec(x: Dict[str, Any]) -> Dict[str, Any]:
        logger.debug(f"Weather agent received last_location: {x.get('last_location')}")
        query = x.get("query", x.get("input", "")) or ""
        
        # Get the intent directly from the supervisor's extracted information
        # This replaces the hybrid parser with direct use of LLM-extracted data
        intent = extract_weather_info(x)
        
        # If we didn't get enough information, use basic defaults
        if not intent.get("type"):
            intent["type"] = "current"  # Default to current weather
            
        if not intent.get("time_reference"):
            intent["time_reference"] = "now"
            
        logger.debug(f"LLM-derived intent: {intent}")

        label: Optional[str] = None
        lat: Optional[float] = None
        lon: Optional[float] = None
        accuracy: Optional[float] = None
        source: Optional[str] = None

        # Location resolution priority:
        # 1) explicit coords in intent (from parser)
        # 2) place string -> geocode (from parser)
        # 3) last_location from session context
        # 4) client IP geolocation (fallback)
        # 5) hard default (never should happen with new default_location)
        
        # 1) explicit coords in intent
        if "lat" in intent and "lon" in intent:
            lat, lon = float(intent["lat"]), float(intent["lon"])
            label = intent.get("label") or None
            accuracy = 0
            source = "explicit_intent"
            logger.debug(f"Using explicit coordinates from intent: ({lat}, {lon})")

        # 2) place string -> geocode (but never for generic phrases or time references)
        elif "place" in intent and intent["place"] and intent["place"].strip().lower() not in {
            "temperature", "weather", "forecast", "here", "current location", "my location", "location",
            "now", "today", "tomorrow", "morning", "afternoon", "evening", "night", "weekend",
            "and morning", "and afternoon", "and evening", "and night", "and tomorrow",
            "this morning", "this afternoon", "this evening", "this weekend", "next week"
        }:
            geo = geocode_place(intent["place"])
            if geo:
                lat, lon = geo["lat"], geo["lon"]
                label = geo.get("label") or intent["place"]
                accuracy = geo.get("accuracy")
                source = "geocoded_place"
                logger.debug(f"Using geocoded place '{intent['place']}': {label} ({lat}, {lon})")
            else:
                logger.info(f"No geocode result for '{intent['place']}'. Using last_location.")

        # 3) last_location from session - should always be available now
        if (lat is None or lon is None) and x.get("last_location") and all(k in x["last_location"] for k in ("lat", "lon")):
            lat = x["last_location"]["lat"]
            lon = x["last_location"]["lon"]
            label = x["last_location"].get("label")
            accuracy = x["last_location"].get("accuracy")
            source = x["last_location"].get("source", "last_location")
            logger.debug(f"Using last_location: {label} ({lat}, {lon})")

        # 4) IP geolocation fallback - should rarely be needed now
        if (lat is None or lon is None) and x.get("client_ip"):
            try:
                geo = get_location_from_source({"ip": x["client_ip"]})
                if geo:
                    lat, lon = geo["lat"], geo["lon"]
                    label = geo.get("label")
                    accuracy = geo.get("accuracy")
                    source = "ip_geolocation"
                    logger.debug(f"Using IP geolocation: {label} ({lat}, {lon})")
            except Exception as e:
                logger.warning(f"IP geolocation failed: {e}")

        # 5) hard default - this should now be very rare with the default_location
        if lat is None or lon is None:
            lat, lon = 40.7128, -74.0060  # NYC instead of Anchorage
            label = "New York City, NY, USA"
            accuracy = None
            source = "hard_default"
            logger.warning(f"Using hard-coded default location: {label}")

        # current conditions
        try:
            cur = google_weather_now(lat, lon)
            result = _normalize_weather(cur, label)
        except Exception as e:
            logger.error(f"Error fetching/normalizing current weather: {e}")
            result = {
                "location": label or "Unknown",
                "conditions": "Unavailable",
                "temperature_fahrenheit": None,
                "wind_mph": None,
                "humidity_percent": None,
                "source": "Google Maps Platform Weather",
            }

        # hourly, if requested
        forecast_type = None
        try:
            if intent.get("type") == "hourly":
                hours = min(int(intent.get("hours", 24)), 240)
                forecasts = google_weather_hourly(lat, lon, hours=hours)
                if forecasts:
                    result["forecast"] = format_hourly_forecast(forecasts, hours)
                    forecast_type = "hourly"
        except Exception as e:
            logger.error(f"Error getting {forecast_type or 'hourly'} forecast: {e}")
            result[f"{forecast_type or 'hourly'}_forecast"] = f"{(forecast_type or 'Hourly').capitalize()} forecast unavailable"

        # attach session metadata
        result_metadata = {
            "lat": lat, 
            "lon": lon, 
            "label": label or "", 
            "accuracy": accuracy,
            "source": source
        }

        class WithMeta(dict):
            pass

        out = WithMeta(result)
        out.metadata = {"weather_location": result_metadata}
        return out

    return RunnableLambda(_exec)