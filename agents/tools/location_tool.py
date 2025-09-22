import os
import logging
import requests
import time
from typing import Optional
from langchain_core.tools import tool
from utils.api_logger import log_api_call

logger = logging.getLogger(__name__)

# Geocode tool: address or place name to lat/lng
@tool("Geocode")
def geocode_place(address: Optional[str] = None, cityHint: Optional[str] = None, slot: str = 'origin') -> dict:
    """Return a dict with 'lat', 'lng' and 'formatted_address'.

    Args:
        address: free-text address or place name. If None, 'cityHint' will be used if provided.
        cityHint: optional city hint to disambiguate.
        slot: which slot to populate ('origin' or 'destination')
    """
    logger.info(f"Geocode tool called with address={address}, cityHint={cityHint}")
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set")
        raise ValueError("Missing Google API key. Set GOOGLE_API_KEY in your environment.")

    query = address or cityHint
    if not query:
        raise ValueError("geocode_place requires 'address' or 'cityHint'")

    try:
        # Prefer googlemaps client if available
        try:
            import googlemaps
            logger.debug(f"Using googlemaps client for geocoding: {query}")
            gm = googlemaps.Client(key=api_key)
            res = gm.geocode(query)
            logger.debug(f"Google Maps API response received, {len(res)} results")
        except Exception as e:
            logger.debug(f"Google Maps client failed ({e}), falling back to direct API call")
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {"address": query, "key": api_key}
            logger.debug(f"Making direct geocoding API call to: {url}")
            logger.debug(f"API Parameters: {params}")
            start = time.time()
            r = requests.get(url, params=params, timeout=20)
            elapsed_ms = int((time.time() - start) * 1000)
            try:
                response_bytes = len(r.content) if r.content is not None else None
            except Exception:
                response_bytes = None
            logger.debug(f"Geocoding API Response Status: {r.status_code}")
            logger.debug(f"Geocoding API Response: {r.text[:500]}...")
            r.raise_for_status()
            res = r.json().get("results", [])
            logger.debug(f"Parsed {len(res)} geocoding results")
            try:
                log_api_call(
                    tool_name="location_tool_geocode",
                    provider="google",
                    endpoint="geocode/json",
                    status=r.status_code,
                    elapsed_ms=elapsed_ms,
                    response_bytes=response_bytes,
                    params={"address": query},
                    estimated_cost=None,
                )
            except Exception:
                logger.debug("api_logger.log_api_call failed but continuing")

        if not res:
            raise ValueError(f"No geocoding results found for: {query}")

        first = res[0]
        loc = first.get("geometry", {}).get("location", {})
        lat = loc.get("lat")
        lng = loc.get("lng")
        formatted_address = first.get("formatted_address")
        # Return a WorldState-compatible patch
        return {
            "slots": {
                slot: {
                    "lat": lat,
                    "lng": lng,
                    "name": formatted_address or query
                }
            },
            "raw": first
        }
    except Exception as e:
        logger.exception("Geocode request failed")
        raise

# Geolocate tool: get user's current location using Google Geolocation API
@tool("Geolocate")
def geolocate_user() -> dict:
    """Return a dict with 'lat', 'lng', 'accuracy', and raw Google response. Uses Google Geolocation API."""
    logger.info("Geolocate tool called")
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set")
        raise ValueError("Missing Google API key. Set GOOGLE_API_KEY in your environment.")
    url = f"https://www.googleapis.com/geolocation/v1/geolocate?key={api_key}"
    logger.debug(f"Making geolocation API call to: {url}")
    try:
        # For CLI, we don't have wifi/cell data, so send an empty POST body (Google will use IP fallback)
        logger.debug("Sending empty POST body for IP-based geolocation")
        start = time.time()
        r = requests.post(url, json={}, timeout=15)
        elapsed_ms = int((time.time() - start) * 1000)
        logger.debug(f"Geolocation API Response Status: {r.status_code}")
        logger.debug(f"Geolocation API Response: {r.text}")
        r.raise_for_status()
        data = r.json()
        logger.debug(f"Parsed geolocation response: {data}")
        try:
            response_bytes = len(r.content) if r.content is not None else None
        except Exception:
            response_bytes = None
        try:
            log_api_call(
                tool_name="location_tool_geolocate",
                provider="google",
                endpoint="geolocate",
                status=r.status_code,
                elapsed_ms=elapsed_ms,
                response_bytes=response_bytes,
                params=None,
                estimated_cost=None,
            )
        except Exception:
            logger.debug("api_logger.log_api_call failed but continuing")
        loc = data.get("location", {})
        lat = loc.get("lat")
        lng = loc.get("lng")
        if lat is None or lng is None:
            raise ValueError("Unable to determine location from IP geolocation. The API did not return valid coordinates.")
        accuracy = data.get("accuracy")
        # Return a WorldState-compatible patch
        return {
            "slots": {
                "origin": {
                    "lat": lat,
                    "lng": lng,
                    "name": "Current Location"
                }
            },
            "context": {
                "accuracy": accuracy,
                "accuracy_note": f"IP-based location (±{accuracy/1609:.1f} miles accuracy). Note: IP geolocation may show your network's location rather than your physical location. For precise location, use GPS or WiFi-based services."
            },
            "raw": data
        }
    except Exception as e:
        logger.exception("Geolocate via Google API failed")
        raise

# Reverse geocode tool: lat/lng to human-readable address
@tool("ReverseGeocode")
def reverse_geocode(lat: float, lng: float) -> dict:
    """Return a dict with human-readable address from coordinates.

    Args:
        lat: latitude
        lng: longitude
    """
    logger.info(f"Reverse geocode tool called with lat={lat}, lng={lng}")
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set")
        raise ValueError("Missing Google API key. Set GOOGLE_API_KEY in your environment.")

    try:
        # Prefer googlemaps client if available
        try:
            import googlemaps
            logger.debug(f"Using googlemaps client for reverse geocoding: {lat}, {lng}")
            gm = googlemaps.Client(key=api_key)
            res = gm.reverse_geocode((lat, lng))
            logger.debug(f"Google Maps reverse geocoding response received, {len(res)} results")
        except Exception as e:
            logger.debug(f"Google Maps client failed ({e}), falling back to direct API call")
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                "latlng": f"{lat},{lng}",
                "key": api_key
            }
            logger.debug(f"Making direct reverse geocoding API call to: {url}")
            logger.debug(f"API Parameters: {params}")
            start = time.time()
            r = requests.get(url, params=params, timeout=20)
            elapsed_ms = int((time.time() - start) * 1000)
            try:
                response_bytes = len(r.content) if r.content is not None else None
            except Exception:
                response_bytes = None
            logger.debug(f"Reverse geocoding API Response Status: {r.status_code}")
            logger.debug(f"Reverse geocoding API Response: {r.text[:500]}...")
            r.raise_for_status()
            res = r.json().get("results", [])
            logger.debug(f"Parsed {len(res)} reverse geocoding results")
            try:
                log_api_call(
                    tool_name="location_tool_reverse_geocode",
                    provider="google",
                    endpoint="geocode/json",
                    status=r.status_code,
                    elapsed_ms=elapsed_ms,
                    response_bytes=response_bytes,
                    params={"latlng": f"{lat},{lng}"},
                    estimated_cost=None,
                )
            except Exception:
                logger.debug("api_logger.log_api_call failed but continuing")

        if not res:
            raise ValueError(f"No reverse geocoding results found for coordinates: {lat}, {lng}")

        first = res[0]
        formatted_address = first.get("formatted_address")

        # Extract useful address components
        address_components = first.get("address_components", [])
        components = {}
        for component in address_components:
            types = component.get("types", [])
            if "locality" in types:  # City
                components["city"] = component.get("long_name")
            elif "administrative_area_level_1" in types:  # State/Province
                components["state"] = component.get("short_name")
            elif "country" in types:  # Country
                components["country"] = component.get("long_name")

        # Return a WorldState-compatible patch
        return {
            "context": {
                "reverse_geocode_result": {
                    "formatted_address": formatted_address,
                    "address_components": components,
                    "coordinates": {"lat": lat, "lng": lng}
                }
            },
            "raw": first
        }
    except Exception as e:
        logger.exception("Reverse geocode request failed")
        raise
