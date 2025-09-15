from typing import Dict, Any, Optional
import requests
import ipaddress
import os

#Runs GET requests for a given url and return the response.
def fetch_and_parse_url(url: str) -> str:
  """A helper function to run GET requests for a given url and return the response."""
  response = requests.get(url)
  response.raise_for_status()
  try:
    return response.json()
  except Exception:
    return response.content
  

#Gathers information of a given IP Address, such as latitude & longitude.
def get_location() -> Dict[str, Any]:
  """Gathers location data based on a given IPv4 address.

  """
  # For the purpose of demonstration, we'll preconfigure our own IP Address.
  # In production system, you would have a mechanism that collect's the user's IP
  # address and passes it to this tool as input.
  ip = os.getenv("IP_ADDRESS")
  if not ip:
    raise ValueError("Cannot run Getlocation Tool - Missing IP_ADDRESS")

  try:
    ipaddress.ip_address(ip)
  except ValueError:
    raise ValueError("Invalid IPv4 address format.")

  url = f"http://ip-api.com/json/{ip}"
  location_response = fetch_and_parse_url(url)
  return location_response

#retrieve local weather based on lat/lon
def local_weather(lat: float, lon: float) -> Dict[str, Any]:
  """Retrieves the local weather based on the given location.

  Args:
    lat: The latitude of the location.
    lon: The longitude of the location.
  Returns:
    A dictionary of metadata about the weather.

  """
  api_key = os.getenv("GOOGLE_GENAI_API_KEY")
  if not api_key:
    raise ValueError("Cannot run Weather Tool - Missing ")

  url = f"https://weather.googleapis.com/v1/currentConditions:lookup?key={api_key}&location.latitude={lat}&location.longitude={lon}"
  weather_response = fetch_and_parse_url(url)
  return weather_response

