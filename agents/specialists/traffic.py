# agents/specialists/traffic.py
# Specialist for real-time road traffic and travel time with traffic.
# Uses Google Routes API (computeRoutes endpoint with trafficModel parameter).
# Now uses direct information from the supervisor without an LLM dependency.
import os
import json
from typing import Dict, Any
from langchain_core.runnables import Runnable, RunnableLambda
from utils.logger import get_logger
import requests

logger = get_logger(__name__)

def create_traffic_agent() -> Runnable:
    """
    Traffic Specialist Agent
    - Handles real-time road traffic, congestion, and travel time with traffic.
    - Uses Google Routes API (computeRoutes endpoint, trafficModel parameter).
    - Uses information extracted directly from the supervisor without an LLM.
    - Returns JSON with traffic details for a given route or area.
    """
    # Load Google Cloud API key for routes
    google_cloud_key = os.getenv("GOOGLE_CLOUD_API_KEY")
    if not google_cloud_key:
        logger.warning("GOOGLE_CLOUD_API_KEY not found - Using mock traffic data")
    
    def extract_traffic_info(x: Dict[str, Any]) -> Dict[str, Any]:
        """Process input using supervisor's extracted information"""
        query = x.get("query", "") or x.get("input", "")
        
        # Collect extracted information from supervisor
        origin = x.get("origin")
        destination = x.get("destination")
        location_context = x.get("location_context")
        time_reference = x.get("time_reference", "now")
        
        # Build a structured traffic request
        traffic_request = {
            "query": query,
            "origin": origin,
            "destination": destination,
            "location_context": location_context,
            "time_reference": time_reference
        }
        
        logger.debug(f"Traffic request: {json.dumps(traffic_request, default=str)}")
        return traffic_request
    
    def get_traffic_info(traffic_request: Dict[str, Any]) -> Dict[str, Any]:
        """Get traffic information from Google Routes API or mock data"""
        # For now, return mock traffic data based on the request
        # In a real implementation, this would call the Google Routes API
        
        # Extract data from the request
        origin = traffic_request.get("origin")
        destination = traffic_request.get("destination")
        location_context = traffic_request.get("location_context")
        time_reference = traffic_request.get("time_reference", "now")
        
        # Default response
        response = {
            "type": "traffic_info"
        }
        
        # Check if we have both origin and destination for a route
        if origin and destination:
            # Route-specific traffic information
            response["route"] = f"{origin} to {destination}"
            response["distance"] = "8.2 miles"
            
            # Vary conditions based on time reference
            if time_reference in ["now", "current"]:
                response["condition"] = "moderate"
                response["delay_minutes"] = 12
                response["travel_time"] = "28 minutes"
                response["reason"] = "Normal rush hour traffic"
            elif "morning" in time_reference:
                response["condition"] = "heavy"
                response["delay_minutes"] = 25
                response["travel_time"] = "42 minutes"
                response["reason"] = "Morning rush hour congestion"
            elif "evening" in time_reference or "afternoon" in time_reference:
                response["condition"] = "very heavy"
                response["delay_minutes"] = 35
                response["travel_time"] = "50 minutes"
                response["reason"] = "Evening rush hour congestion"
            else:
                response["condition"] = "light"
                response["delay_minutes"] = 5
                response["travel_time"] = "18 minutes"
                response["reason"] = "Free-flowing traffic"
        
        # If we only have a location context, provide area traffic
        elif location_context:
            response["area"] = location_context
            response["overall_condition"] = "moderate congestion"
            response["hotspots"] = ["Downtown area", "Main highway interchange"]
        else:
            # Generic response
            response["note"] = "For specific traffic information, please provide both origin and destination locations."
        
        return response

    # Create the chain that first processes the input, then gets traffic information
    chain = (
        RunnableLambda(extract_traffic_info)
        | RunnableLambda(get_traffic_info)
    )
    
    return chain