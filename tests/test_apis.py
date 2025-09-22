#!/usr/bin/env python3
"""
Test script to verify Google API integrations for geolocation and weather.
This isolates tool functionality from the LLM/agent flow.
"""

import os
import sys
import logging

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Loaded .env from {dotenv_path}")
except ImportError:
    print("python-dotenv not installed. Install with: pip install python-dotenv")
    print("Or set environment variables manually.")

# Add the project root to path (parent of tests directory)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.tools.location_tool import geolocate_user, geocode_place
from agents.tools.weather_tool import weather_current

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_env_vars():
    """Check if required environment variables are set."""
    google_key = os.environ.get("GOOGLE_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    print("Environment Variables:")
    print(f"GOOGLE_API_KEY: {'Set' if google_key else 'NOT SET'}")
    print(f"GEMINI_API_KEY: {'Set' if gemini_key else 'NOT SET'}")
    print()
    
    if not google_key:
        print("ERROR: GOOGLE_API_KEY is required for Google APIs (Geolocation, Geocoding, Weather)")
        return False
    return True

def test_geolocate():
    """Test the geolocate_user tool."""
    print("Testing Geolocate User...")
    try:
        result = geolocate_user.invoke({})
        print(f"Geolocate Result: {result}")
        if isinstance(result, dict) and result.get("slots", {}).get("origin", {}).get("lat"):
            print("✅ Geolocate successful - got coordinates")
            return result["slots"]["origin"]
        else:
            print("❌ Geolocate failed - no coordinates returned")
            return None
    except Exception as e:
        print(f"❌ Geolocate error: {e}")
        return None

def test_geocode():
    """Test the geocode_place tool."""
    print("\nTesting Geocode Place...")
    try:
        result = geocode_place("Miami, FL")
        print(f"Geocode Result: {result}")
        if isinstance(result, dict) and result.get("slots", {}).get("origin", {}).get("lat"):
            print("✅ Geocode successful - got coordinates")
            return result["slots"]["origin"]
        else:
            print("❌ Geocode failed - no coordinates returned")
            return None
    except Exception as e:
        print(f"❌ Geocode error: {e}")
        return None

def test_weather():
    """Test the weather_current tool."""
    # Use a hardcoded location for testing
    location = {"lat": 40.7128, "lng": -74.0060, "name": "New York, NY"}
    
    print(f"\nTesting Weather for {location.get('name', 'location')}...")
    try:
        result = weather_current.invoke({"lat": location["lat"], "lng": location["lng"], "units": "imperial"})
        print(f"Weather Result: {result}")
        if isinstance(result, dict) and result.get("context", {}).get("lastWeather"):
            print("✅ Weather successful - got weather data")
        else:
            print("❌ Weather failed - no weather data returned")
    except Exception as e:
        print(f"❌ Weather error: {e}")
    try:
        result = weather_current.invoke({"lat": location["lat"], "lng": location["lng"], "units": "imperial"})
        print(f"Weather Result: {result}")
        if isinstance(result, dict) and result.get("context", {}).get("lastWeather"):
            print("✅ Weather successful - got weather data")
        else:
            print("❌ Weather failed - no weather data returned")
    except Exception as e:
        print(f"❌ Weather error: {e}")

def main():
    print("=== Google API Integration Test ===\n")
    
    if not test_env_vars():
        return
    
    # Test geolocation
    location = test_geolocate()
    
    # Test geocoding
    geocode_location = test_geocode()
    
    # Use geocode location if geolocate failed
    test_location = location or geocode_location
    
    # Test weather
    test_weather(test_location)
    
    print("\n=== Test Complete ===")
    print("Check your GCP dashboard for API calls after running this test.")
    print("If APIs are called but return errors, check API key permissions and billing.")

if __name__ == "__main__":
    main()