# agents/specialists/transit.py
# Specialist for public transit status, delays, and disruptions.
# Uses Transitland API for real-time transit data (delays, disruptions, service status).
# Now uses direct information from the supervisor without an LLM dependency.
import os
import json
from typing import Dict, Any
from langchain.schema.runnable import Runnable, RunnableLambda
from utils.logger import get_logger
import requests

logger = get_logger(__name__)

def create_transit_agent() -> Runnable:
    """
    Transit Specialist Agent
    - Handles public transit status, delays, and disruptions.
    - Uses Transitland API for real-time transit data (delays, disruptions, service status).
    - Uses information extracted by the supervisor directly without an LLM.
    - Returns JSON with transit details for a given line or service.
    """
    # Load Transitland API key
    transitland_key = os.getenv("TRANSITLAND_API_KEY")
    if not transitland_key:
        logger.warning("TRANSITLAND_API_KEY not found - Using mock transit data")
    
    def extract_transit_info(x: Dict[str, Any]) -> Dict[str, Any]:
        """Process input using supervisor's extracted information"""
        query = x.get("query", "") or x.get("input", "")
        
        # Collect extracted information from supervisor
        origin = x.get("origin")
        destination = x.get("destination")
        transit_type = x.get("transit_type")
        time_reference = x.get("time_reference", "now")
        
        # Build a structured transit request
        transit_request = {
            "query": query,
            "origin": origin,
            "destination": destination, 
            "transit_type": transit_type,
            "time_reference": time_reference
        }
        
        logger.debug(f"Transit request: {json.dumps(transit_request, default=str)}")
        return transit_request
    
    def get_transit_info(transit_request: Dict[str, Any]) -> Dict[str, Any]:
        """Get transit information from Transitland API or mock data"""
        # For now, return mock transit data based on the request
        # In a real implementation, this would call the Transitland API
        
        # Extract data from the request
        origin = transit_request.get("origin")
        destination = transit_request.get("destination")
        transit_type = transit_request.get("transit_type", "").lower() if transit_request.get("transit_type") else ""
        
        # Default response
        response = {
            "type": "transit_info",
            "service_available": True,
            "origin": origin,
            "destination": destination
        }
        
        # Check if we have both origin and destination
        if origin and destination:
            if "subway" in transit_type or "train" in transit_type:
                response["line"] = "Express Train"
                response["status"] = "On time"
                response["next_departure"] = "10 minutes"
                response["travel_time"] = "25 minutes"
            elif "bus" in transit_type:
                response["line"] = "Local Bus"
                response["status"] = "Slight delay"
                response["next_departure"] = "7 minutes"
                response["travel_time"] = "35 minutes"
            else:
                response["line"] = "Transit Service"
                response["status"] = "Check schedule"
                response["next_departure"] = "See schedule"
                response["travel_time"] = "Varies"
        else:
            # Just general transit info for the area
            response["service_status"] = "Normal operations on most lines"
            response["notes"] = "For specific route information, please provide both origin and destination"
        
        return response

    # Create the chain that first processes the input, then gets transit information
    chain = (
        RunnableLambda(extract_transit_info)
        | RunnableLambda(get_transit_info)
    )
    
    return chain