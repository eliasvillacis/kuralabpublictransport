import os
import logging
import requests
import time
import math
from typing import Optional, List, Dict, Any

from langchain_core.tools import tool
from utils.api_logger import log_api_call

# --- Constants ---
logger = logging.getLogger(__name__)
GOOGLE_PLACES_API_BASE_URL = "https://places.googleapis.com/v1"
RADIUS_METERS_DEFAULT = 1500
RADIUS_METERS_MAX = 50000
MAX_RESULTS_DEFAULT = 5
EARTH_RADIUS_METERS = 6371000.0

# In-memory cache to avoid redundant API calls for place details
_DETAILS_CACHE: Dict[str, Dict[str, Any]] = {}

# --- Helper Functions ---

def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Calculates the distance between two lat/lon coordinates in meters using the Haversine formula."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return int(EARTH_RADIUS_METERS * c)

def _normalize_place_item(item: dict, near: Optional[dict]) -> dict:
    """Transforms a raw Google Places API (New) result into a standardized dictionary."""
    loc = item.get("location", {})
    lat, lng = loc.get("latitude"), loc.get("longitude")
    
    distance = None
    if near and lat is not None and lng is not None:
        try:
            distance = _haversine_meters(float(near["lat"]), float(near["lng"]), float(lat), float(lng))
        except (ValueError, TypeError, KeyError):
            # Ignore if location data is malformed
            distance = None

    types = item.get("types", [])
    rating = item.get("rating")
    business_status = item.get("businessStatus")
    is_open = business_status == "OPERATIONAL"  # Simplified assumption

    # Build a quick summary string like "Restaurant · ★4.5 · Open now"
    quick_summary_parts = []
    if types:
        quick_summary_parts.append(types[0].replace("_", " ").title())
    if rating is not None:
        quick_summary_parts.append(f"★{rating}")
    if is_open:
        quick_summary_parts.append("Open now")
    elif business_status == "CLOSED_PERMANENTLY":
        quick_summary_parts.append("Permanently closed")

    return {
        "placeId": item.get("id"),
        "name": item.get("displayName", {}).get("text"),
        "types": types,
        "rating": rating,
        "userRatingsTotal": item.get("userRatingCount", 0),
        "priceLevel": item.get("priceLevel"),
        "isOpenNow": is_open,
        "address": item.get("formattedAddress"),
        "location": {"lat": lat, "lng": lng} if lat is not None else None,
        "distanceMeters": distance,
        "quickSummary": " · ".join(quick_summary_parts),
        "raw": item,
    }

# --- LangChain Tools ---

@tool("PlacesSearch")
def places_search(
    query: Optional[str] = None,
    near: Optional[dict] = None,
    radiusMeters: int = RADIUS_METERS_DEFAULT,
    type: Optional[str] = None,
    openNow: Optional[bool] = None,
    minRating: Optional[float] = None,
    priceLevels: Optional[List[int]] = None,
    maxResults: int = MAX_RESULTS_DEFAULT,
    rankBy: Optional[str] = None
) -> dict:
    """
    Search for places using Google Places Text Search (if query is provided) or Nearby Search.
    
    If `near` is not provided, this tool will return a MISSING_INFO status to request the user's location.
    """
    logger.info(f"PlacesSearch called with: query='{query}', type='{type}', near={near}")
    
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set for PlacesSearch")
        raise ValueError("Missing Google API key. Set GOOGLE_API_KEY in your environment.")

    if not near:
        return {
            "status": "MISSING_INFO",
            "hints": {"need": "origin"},
            "context": {"places": {"results": [], "query": query, "near": None}}
        }

    # --- Parameter Sanitization ---
    try:
        max_results = max(1, int(maxResults or MAX_RESULTS_DEFAULT))
        radius = min(int(radiusMeters or RADIUS_METERS_DEFAULT), RADIUS_METERS_MAX)
    except (ValueError, TypeError):
        max_results = MAX_RESULTS_DEFAULT
        radius = RADIUS_METERS_DEFAULT

    use_text_search = bool(query and str(query).strip())
    if use_text_search:
        api_endpoint = f"{GOOGLE_PLACES_API_BASE_URL}/places:searchText"
        request_body = {
            "textQuery": query,
            "maxResultCount": max_results
        }
        if near.get("lat") is not None and near.get("lng") is not None:
            request_body["locationBias"] = {
                "circle": {
                    "center": {"latitude": near["lat"], "longitude": near["lng"]},
                    "radius": radius
                }
            }
    else: # Nearby Search
        api_endpoint = f"{GOOGLE_PLACES_API_BASE_URL}/places:searchNearby"
        request_body = {
            "maxResultCount": max_results,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": near["lat"], "longitude": near["lng"]},
                    "radius": radius
                }
            }
        }
        if type:
            request_body["includedTypes"] = [str(type).split("|")[0]]

    # --- API Call and Response Handling ---
    try:
        start_time = time.time()
        headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.priceLevel,places.businessStatus,places.types,places.id"}
        response = requests.post(api_endpoint, json=request_body, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Log the API call details
        log_api_call(
            tool_name="places_search", provider="google",
            endpoint=api_endpoint.replace("https://", ""),
            status=response.status_code,
            elapsed_ms=int((time.time() - start_time) * 1000),
            response_bytes=len(response.content),
            params={"body": request_body}
        )

        raw_results = data.get("places", [])

        # --- Post-filtering and Sorting ---
        normalized = [_normalize_place_item(item, near) for item in raw_results]

        # Apply client-side filters for criteria the API doesn't support directly
        filtered = []
        for place in normalized:
            try:
                if openNow and not place.get("isOpenNow"):
                    continue
                if minRating is not None and (place.get("rating") or 0) < float(minRating):
                    continue
                if priceLevels and place.get("priceLevel") not in priceLevels:
                    continue
                filtered.append(place)
            except (ValueError, TypeError):
                continue # Skip items with malformed data

        # Sort by distance if requested, placing items without distance at the end
        if rankBy and rankBy.lower() == "distance":
            filtered.sort(key=lambda p: p.get("distanceMeters") if p.get("distanceMeters") is not None else float('inf'))

        final_results = filtered[:max_results]
        
        return {
            "status": "OK",
            "context": {
                "places": {
                    "results": final_results, "query": query, "near": near
                }
            }
        }

    except requests.exceptions.RequestException as e:
        logger.exception(f"Places API request failed: {e}")
        return {"status": "ERROR", "error": str(e), "context": {"places": {"results": [], "query": query, "near": near}}}

    except requests.exceptions.RequestException as e:
        logger.exception(f"Places API request failed: {e}")
        return {"status": "ERROR", "error": str(e), "context": {"places": {"results": [], "query": query, "near": near}}}


@tool("PlaceDetails")
def place_details(placeId: str, fields: Optional[List[str]] = None) -> dict:
    """Fetch detailed information for a single placeId. Uses an in-memory cache to avoid repeated calls."""
    logger.info(f"PlaceDetails called for {placeId}")
    
    if not placeId:
        raise ValueError("placeId is required for PlaceDetails")

    # Return cached value if available
    if placeId in _DETAILS_CACHE:
        logger.debug(f"PlaceDetails cache hit for {placeId}")
        return {"status": "OK", "context": {"placeDetails": _DETAILS_CACHE[placeId]}, "cached": True}

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set for PlaceDetails")
        raise ValueError("Missing Google API key. Set GOOGLE_API_KEY in your environment.")

    # --- API Call ---
    api_endpoint = f"{GOOGLE_PLACES_API_BASE_URL}/places/{placeId}"
    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": "displayName,formattedAddress,internationalPhoneNumber,website,rating,userRatingCount,openingHours,geometry,id"}
    
    try:
        start_time = time.time()
        response = requests.get(api_endpoint, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        log_api_call(
            tool_name="place_details", provider="google",
            endpoint=f"places.googleapis.com/v1/places/{placeId}", status=response.status_code,
            elapsed_ms=int((time.time() - start_time) * 1000),
            response_bytes=len(response.content), params={"fields": fields or []}
        )

        # Normalize a subset of useful fields
        normalized_detail = {
            "placeId": data.get("id"),
            "name": data.get("displayName", {}).get("text"),
            "formatted_address": data.get("formattedAddress"),
            "international_phone_number": data.get("internationalPhoneNumber"),
            "website": data.get("website"),
            "rating": data.get("rating"),
            "userRatingsTotal": data.get("userRatingCount"),
            "opening_hours": data.get("openingHours"),
            "geometry": data.get("geometry"),
            "raw": data,
        }
        
        # Cache the successful result
        _DETAILS_CACHE[placeId] = normalized_detail
        
        return {"status": "OK", "context": {"placeDetails": normalized_detail}}

    except requests.exceptions.RequestException as e:
        logger.exception(f"Place Details request failed: {e}")
        return {"status": "ERROR", "error": str(e), "context": {"placeDetails": None}}