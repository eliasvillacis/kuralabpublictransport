# agents/specialists/maps.py
# Specialist for geolocation, directions, and place search.
# Uses Google Geocoding API, Places API, Maps Static API, and Geolocation API.
# For routing with traffic, see the Traffic agent (uses Google Routes API).
# Now uses direct information from the supervisor without an LLM dependency.
from langchain.schema.runnable import Runnable, RunnableLambda
import os
import json
from typing import Dict, Any, Optional
from utils.google_maps import get_location_from_source, geocode_place
from utils.logger import get_logger

logger = get_logger(__name__)

def create_maps_agent() -> Runnable:
    """
    Maps Specialist Agent.
    Handles geolocation, address lookup, and place search.
    Uses Google Geocoding API, Places API, Maps Static API, and Geolocation API.
    For routing and traffic, refer to the Traffic agent (Routes API).
    Uses direct information from the supervisor without an LLM dependency.
    """
    # Load Google Maps API key
    google_maps_key = os.getenv("GOOGLE_CLOUD_API_KEY")
    if not google_maps_key:
        logger.warning("GOOGLE_CLOUD_API_KEY not found - Some Maps features may be unavailable")
    
    def extract_maps_info(x: Dict[str, Any]) -> Dict[str, Any]:
        """Process input using supervisor's extracted information"""
        query = x.get("query", "") or x.get("input", "")
        
        # Collect extracted information from supervisor
        origin = x.get("origin")
        destination = x.get("destination")
        location_context = x.get("location_context")
        
        # Try to geocode locations
        origin_coords = None
        destination_coords = None
        location_coords = None
        
        if origin:
            origin_geo = geocode_place(origin)
            if origin_geo:
                origin_coords = {"lat": origin_geo["lat"], "lng": origin_geo["lon"], "label": origin_geo.get("label", origin)}
                
        if destination:
            dest_geo = geocode_place(destination)
            if dest_geo:
                destination_coords = {"lat": dest_geo["lat"], "lng": dest_geo["lon"], "label": dest_geo.get("label", destination)}
                
        if location_context:
            loc_geo = geocode_place(location_context)
            if loc_geo:
                location_coords = {"lat": loc_geo["lat"], "lng": loc_geo["lon"], "label": loc_geo.get("label", location_context)}

        # Combine all location information for context
        location_info = {
            "query": query,
            "origin": origin_coords,
            "destination": destination_coords,
            "location_context": location_coords,
            "raw_origin": origin,
            "raw_destination": destination,
            "raw_location_context": location_context,
        }
        
        logger.debug(f"Maps specialist processed input: {json.dumps(location_info, default=str)}")
        return location_info

    def get_location(x: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # First try to use supervisor-extracted locations
        if x.get("origin") and isinstance(x["origin"], dict) and "lat" in x["origin"] and "lng" in x["origin"]:
            return {"lat": x["origin"]["lat"], "lon": x["origin"]["lng"], "label": x["origin"].get("label", "Origin")}
            
        if x.get("location_context") and isinstance(x["location_context"], dict) and "lat" in x["location_context"] and "lng" in x["location_context"]:
            return {"lat": x["location_context"]["lat"], "lon": x["location_context"]["lng"], "label": x["location_context"].get("label", "Location")}
            
        # Fall back to previous methods
        if x.get("last_location") and all(k in x["last_location"] for k in ("lat", "lon")):
            return x["last_location"]
            
        # Try IP geolocation if available
        if x.get("client_ip"):
            try:
                return get_location_from_source({"ip": x["client_ip"]})
            except Exception as e:
                logger.warning(f"IP geolocation failed: {e}")
        return None

    def generate_response(x: Dict[str, Any]) -> Dict[str, Any]:
        processed_info = extract_maps_info(x)
        
        # If we have specific locations from the query, use those
        if processed_info.get("origin") or processed_info.get("destination") or processed_info.get("location_context"):
            # Handle different maps queries based on available information
            if processed_info.get("destination") and processed_info.get("origin"):
                return {
                    "type": "directions",
                    "origin": processed_info["origin"],
                    "destination": processed_info["destination"],
                    "query": processed_info["query"]
                }
            elif processed_info.get("location_context"):
                return {
                    "type": "place_info",
                    "location": processed_info["location_context"],
                    "query": processed_info["query"]
                }
            elif processed_info.get("origin"):
                return {
                    "type": "place_info",
                    "location": processed_info["origin"],
                    "query": processed_info["query"]
                }
            elif processed_info.get("destination"):
                return {
                    "type": "place_info", 
                    "location": processed_info["destination"],
                    "query": processed_info["query"]
                }
        
        # Fall back to current location if no specific places in query
        location = get_location(processed_info)
        if not location:
            return {
                "type": "error",
                "message": "Could not determine your location. Please specify a location in your query."
            }
        return {
            "type": "location",
            "latitude": location["lat"],
            "longitude": location["lon"],
            "address": location.get("label", "Unknown Location"),
            "accuracy": location.get("accuracy"),
            "query": processed_info["query"]
        }

    # Build the full agent chain
    maps_chain = (
        RunnableLambda(extract_maps_info)
        | RunnableLambda(generate_response)
    )
    
    return maps_chain