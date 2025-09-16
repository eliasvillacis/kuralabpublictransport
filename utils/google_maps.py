# utils/google_maps.py
from typing import Dict, Any, Optional, Union
import os, requests, ipaddress
from utils.logger import get_logger

# Try to load environment variables if not already loaded
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, assume env vars are set

logger = get_logger(__name__)

GOOGLE_CLOUD_API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY")
if not GOOGLE_CLOUD_API_KEY:
    logger.warning("GOOGLE_CLOUD_API_KEY not found - Google Maps features will be disabled")
    GOOGLE_CLOUD_API_KEY = None

def geocode_place(q: str) -> Optional[Dict[str, Any]]:
    """
    Convert a place name or address into coordinates using Google Maps Geocoding API.
    Also includes detailed location information like city, region, etc.
    """
    if not GOOGLE_CLOUD_API_KEY:
        logger.error("Google Cloud API key not available for geocoding")
        return None
        
    url = ("https://maps.googleapis.com/maps/api/geocode/json"
           f"?address={requests.utils.quote(q)}&key={GOOGLE_CLOUD_API_KEY}")
    headers = {
        "X-Goog-Api-Key": GOOGLE_CLOUD_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        j = r.json()
        
        if j.get("results"):
            loc = j["results"][0]["geometry"]["location"]
            # Include full location details
            result = {
                "lat": loc["lat"],
                "lon": loc["lng"],
                "source": "explicit",
                "query": q
            }
            
            # Get address components
            if "address_components" in j["results"][0]:
                components = j["results"][0]["address_components"]
                address = {}
                for comp in components:
                    types = comp.get("types", [])
                    if "sublocality" in types or "neighborhood" in types:
                        address["neighborhood"] = comp["long_name"]
                    elif "locality" in types:
                        address["city"] = comp["long_name"]
                    elif "administrative_area_level_1" in types:
                        address["region"] = comp["long_name"]
                    elif "country" in types:
                        address["country"] = comp["long_name"]
                
                # Build location label
                location_parts = []
                if address.get("neighborhood"):
                    location_parts.append(address["neighborhood"])
                if address.get("city"):
                    location_parts.append(address["city"])
                if address.get("region"):
                    location_parts.append(address["region"])
                if address.get("country"):
                    location_parts.append(address["country"])
                
                result.update({
                    "neighborhood": address.get("neighborhood"),
                    "city": address.get("city"),
                    "region": address.get("region"),
                    "country": address.get("country"),
                    "label": ", ".join(location_parts)
                })
            
            return result
            
        logger.error(f"Geocoding failed: {j.get('error_message', 'No results')}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to geocode location: {e}")
        if hasattr(e, 'response'):
            logger.error(f"Response: {e.response.text}")
        return None

def get_location_from_source(source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get location from various sources (IP, phone, etc) using Google Maps APIs.
    Args:
        source: Dict with either "ip" or "phone_number"
    Returns:
        Dict with location info or None
    """
    if not GOOGLE_CLOUD_API_KEY:
        logger.error("Google Cloud API key not available for location services")
        return None
        
    try:
        # Handle phone number
        if "phone_number" in source:
            phone = source["phone_number"]
            # Fall back to default location
            return None
            
        # Handle IP address
        if "ip" in source:
            ip = source["ip"]
            ipaddress.ip_address(ip)  # validate IP format
            
            url = f"https://www.googleapis.com/geolocation/v1/geolocate?key={GOOGLE_CLOUD_API_KEY}"
            headers = {
                "X-Goog-Api-Key": GOOGLE_CLOUD_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            data = {
                "considerIp": True,
                "wifiAccessPoints": []  # Empty since we're using IP only
            }
            
            r = requests.post(url, headers=headers, json=data, timeout=10)
            r.raise_for_status()
            j = r.json()
        
        if "location" in j:
            location = {
                "lat": j["location"]["lat"],
                "lon": j["location"]["lng"],
                "accuracy": j.get("accuracy")
            }

            # Try to get detailed address info using reverse geocoding
            reverse_url = (
                f"https://maps.googleapis.com/maps/api/geocode/json"
                f"?latlng={location['lat']},{location['lon']}"
                f"&result_type=street_address|sublocality|locality|neighborhood"
                f"&key={GOOGLE_CLOUD_API_KEY}"
            )
            rev = requests.get(reverse_url, headers=headers, timeout=10)
            rev.raise_for_status()
            rev_data = rev.json()
            
            # Extract address components with more detail
            address = {}
            if rev_data.get("results"):
                components = rev_data["results"][0]["address_components"]
                for comp in components:
                    types = comp.get("types", [])
                    if "sublocality" in types or "neighborhood" in types:
                        address["neighborhood"] = comp["long_name"]
                    elif "locality" in types:
                        address["city"] = comp["long_name"]
                    elif "administrative_area_level_1" in types:
                        address["region"] = comp["long_name"]
                    elif "country" in types:
                        address["country"] = comp["long_name"]
            
            # Build location parts
            location_parts = []
            if address.get("neighborhood"):
                location_parts.append(address["neighborhood"])
            if address.get("city"):
                location_parts.append(address["city"])
            if address.get("region"):
                location_parts.append(address["region"])
            if address.get("country"):
                location_parts.append(address["country"])

            # Add address components to location data
            location.update({
                "neighborhood": address.get("neighborhood"),
                "city": address.get("city"),
                "region": address.get("region"),
                "country": address.get("country"),
                "label": ", ".join(location_parts),  # e.g. "Upper East Side, New York City, New York, USA"
                "source": "phone" if "phone_number" in source else "ip"
            })
            
            return location
        
        logger.error("Geolocation response missing location data")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get location: {e}")
        if hasattr(e, 'response'):
            logger.error(f"Response: {e.response.text}")
        return None