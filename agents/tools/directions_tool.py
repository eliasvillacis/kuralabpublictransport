import os
import logging
import requests
import time
from typing import Optional, List
from langchain_core.tools import tool
from utils.api_logger import log_api_call

logger = logging.getLogger(__name__)

def get_directions(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float,
                  mode: str = "transit", departure_time: Optional[str] = None) -> dict:
    """
    Get directions using Google Maps Directions API.

    Args:
        origin_lat: Origin latitude
        origin_lng: Origin longitude
        dest_lat: Destination latitude
        dest_lng: Destination longitude
        mode: Travel mode ("transit" or "walking")
        departure_time: ISO 8601 datetime string for departure time
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Missing Google Cloud API key. Set GOOGLE_API_KEY in your environment.")

    # Use the correct Google Maps Directions API endpoint
    url = "https://maps.googleapis.com/maps/api/directions/json"

    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{dest_lat},{dest_lng}",
        "mode": mode.lower(),  # "transit" or "walking"
        "key": api_key,
        "alternatives": "true"  # Get multiple route options
    }

    if departure_time:
        params["departure_time"] = departure_time
    else:
        # Default to now for transit
        import time
        params["departure_time"] = str(int(time.time()))

    # Log API call
    # Note: status will be logged after the request completes
    # log_api_call("directions", url, params)

    try:
        response = requests.get(url, params=params, timeout=10)

        # Log API call with status
        log_api_call("directions", "google", "maps/api/directions/json", response.status_code, params=params)
        response.raise_for_status()

        data = response.json()

        if data.get("status") != "OK":
            raise ValueError(f"Directions API error: {data.get('status')} - {data.get('error_message', 'Unknown error')}")

        return data

    except requests.exceptions.RequestException as e:
        logger.error(f"Directions API request failed: {e}")
        raise

@tool("TransitDirections")
def transit_directions(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float,
                      departure_time: Optional[str] = None) -> dict:
    """
    Get public transit directions between two points.

    Args:
        origin_lat: Origin latitude
        origin_lng: Origin longitude
        dest_lat: Destination latitude
        dest_lng: Destination longitude
        departure_time: Optional ISO 8601 datetime string for departure time
    """
    logger.info(f"Getting transit directions from ({origin_lat}, {origin_lng}) to ({dest_lat}, {dest_lng})")

    try:
        data = get_directions(origin_lat, origin_lng, dest_lat, dest_lng, "transit", departure_time)

        # Extract route information
        routes = data.get("routes", [])
        if not routes:
            # No transit routes found - attempt walking fallback automatically
            logger.info("No transit routes found, attempting walking fallback")
            try:
                walk_data = get_directions(origin_lat, origin_lng, dest_lat, dest_lng, "walking", departure_time)
                walk_routes = walk_data.get("routes", [])
                if walk_routes:
                    # Build walking directions summary similar to transit format but mark as fallback
                    route = walk_routes[0]
                    legs = route.get("legs", [])
                    directions = {
                        "origin": {"lat": origin_lat, "lng": origin_lng},
                        "destination": {"lat": dest_lat, "lng": dest_lng},
                        "mode": "walking",
                        "total_duration": legs[0].get("duration", {}).get("text", "Unknown") if legs else "Unknown",
                        "total_distance": legs[0].get("distance", {}).get("text", "Unknown") if legs else "Unknown",
                        "legs": []
                    }
                    for leg in legs:
                        leg_info = {
                            "start_address": leg.get("start_address", ""),
                            "end_address": leg.get("end_address", ""),
                            "duration": leg.get("duration", {}).get("text", "Unknown"),
                            "distance": leg.get("distance", {}).get("text", "Unknown"),
                            "steps": []
                        }
                        for step in leg.get("steps", []):
                            step_info = {
                                "travel_mode": step.get("travel_mode", "UNKNOWN"),
                                "duration": step.get("duration", {}).get("text", "Unknown"),
                                "distance": step.get("distance", {}).get("text", "Unknown"),
                                "instructions": step.get("html_instructions", "").replace("<b>", "").replace("</b>", "").replace("<div>", "").replace("</div>", ""),
                                "maneuver": ""
                            }
                            leg_info["steps"].append(step_info)
                        directions["legs"].append(leg_info)

                    return {
                        "context": {
                            "transit_directions": {
                                "mode": "walking_fallback",
                                "note": "No transit routes found; returning walking directions as fallback",
                                "directions": directions
                            }
                        }
                    }
            except Exception:
                # If walking fallback also fails, return an error patch
                logger.exception("Walking fallback failed after transit not found")
                return {
                    "context": {
                        "transit_directions": {
                            "error": "No transit routes found and walking fallback failed",
                            "origin": {"lat": origin_lat, "lng": origin_lng},
                            "destination": {"lat": dest_lat, "lng": dest_lng}
                        }
                    }
                }

        # Take the first (best) route
        route = routes[0]
        legs = route.get("legs", [])

        # Build directions summary
        directions = {
            "origin": {"lat": origin_lat, "lng": origin_lng},
            "destination": {"lat": dest_lat, "lng": dest_lng},
            "mode": "transit",
            "total_duration": legs[0].get("duration", {}).get("text", "Unknown") if legs else "Unknown",
            "total_distance": legs[0].get("distance", {}).get("text", "Unknown") if legs else "Unknown",
            "legs": []
        }

        # Process each leg
        for leg in legs:
            leg_info = {
                "start_address": leg.get("start_address", ""),
                "end_address": leg.get("end_address", ""),
                "duration": leg.get("duration", {}).get("text", "Unknown"),
                "distance": leg.get("distance", {}).get("text", "Unknown"),
                "steps": []
            }

            # Process steps
            steps = leg.get("steps", [])
            for step in steps:
                step_info = {
                    "travel_mode": step.get("travel_mode", "UNKNOWN"),
                    "duration": step.get("duration", {}).get("text", "Unknown"),
                    "distance": step.get("distance", {}).get("text", "Unknown"),
                    "instructions": step.get("html_instructions", "").replace("<b>", "").replace("</b>", "").replace("<div>", "").replace("</div>", ""),
                    "maneuver": ""
                }

                # Add transit details if available
                transit_details = step.get("transit_details", {})
                if transit_details:
                    step_info["transit"] = {
                        "line_name": transit_details.get("line", {}).get("name", ""),
                        "vehicle_type": transit_details.get("line", {}).get("vehicle", {}).get("type", ""),
                        "headsign": transit_details.get("headsign", ""),
                        "num_stops": transit_details.get("num_stops", 0),
                        "departure_stop": transit_details.get("departure_stop", {}).get("name", ""),
                        "arrival_stop": transit_details.get("arrival_stop", {}).get("name", ""),
                        "departure_time": transit_details.get("departure_time", {}).get("text", ""),
                        "arrival_time": transit_details.get("arrival_time", {}).get("text", "")
                    }

                leg_info["steps"].append(step_info)

            directions["legs"].append(leg_info)

        return {
            "context": {
                "transit_directions": directions
            }
        }

    except Exception as e:
        logger.exception(f"Transit directions failed: {e}")
        return {
            "context": {
                "transit_directions": {
                    "error": str(e),
                    "origin": {"lat": origin_lat, "lng": origin_lng},
                    "destination": {"lat": dest_lat, "lng": dest_lng}
                }
            }
        }

@tool("WalkingDirections")
def walking_directions(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    """
    Get walking directions between two points.

    Args:
        origin_lat: Origin latitude
        origin_lng: Origin longitude
        dest_lat: Destination latitude
        dest_lng: Destination longitude
    """
    logger.info(f"Getting walking directions from ({origin_lat}, {origin_lng}) to ({dest_lat}, {dest_lng})")

    try:
        data = get_directions(origin_lat, origin_lng, dest_lat, dest_lng, "WALK")

        # Extract route information
        routes = data.get("routes", [])
        if not routes:
            return {
                "context": {
                    "walking_directions": {
                        "error": "No walking routes found",
                        "origin": {"lat": origin_lat, "lng": origin_lng},
                        "destination": {"lat": dest_lat, "lng": dest_lng}
                    }
                }
            }

        # Take the first (best) route
        route = routes[0]
        legs = route.get("legs", [])

        # Build directions summary
        directions = {
            "origin": {"lat": origin_lat, "lng": origin_lng},
            "destination": {"lat": dest_lat, "lng": dest_lng},
            "mode": "walking",
            "total_duration": route.get("duration", "Unknown"),
            "total_distance_meters": route.get("distanceMeters", 0),
            "legs": []
        }

        # Process each leg
        for leg in legs:
            leg_info = {
                "start_location": leg.get("startLocation", {}),
                "end_location": leg.get("endLocation", {}),
                "duration": leg.get("duration", "Unknown"),
                "distance_meters": leg.get("distanceMeters", 0),
                "steps": []
            }

            # Process steps
            steps = leg.get("steps", [])
            for step in steps:
                step_info = {
                    "travel_mode": step.get("travelMode", "UNKNOWN"),
                    "duration": step.get("duration", "Unknown"),
                    "distance_meters": step.get("distanceMeters", 0),
                    "instructions": step.get("navigationInstruction", {}).get("instructions", ""),
                    "maneuver": step.get("navigationInstruction", {}).get("maneuver", "")
                }
                leg_info["steps"].append(step_info)

            directions["legs"].append(leg_info)

        return {
            "context": {
                "walking_directions": directions
            }
        }

    except Exception as e:
        logger.exception(f"Walking directions failed: {e}")
        return {
            "context": {
                "walking_directions": {
                    "error": str(e),
                    "origin": {"lat": origin_lat, "lng": origin_lng},
                    "destination": {"lat": dest_lat, "lng": dest_lng}
                }
            }
        }

@tool("Directions")
def directions(destination: str, origin: Optional[str] = None) -> dict:
    """
    Get directions from origin to destination, automatically handling geolocation.

    This unified tool:
    - Uses geolocation if no origin is provided
    - Defaults to transit directions with walking fallback
    - Handles both address strings and coordinate inputs

    Args:
        destination: Destination address or "lat,lng" coordinates
        origin: Optional origin address or "lat,lng" coordinates. If not provided, uses current location.
    """
    logger.info(f"Getting directions to {destination}" + (f" from {origin}" if origin else " from current location"))

    # Handle special case where origin is 'Current Location' from geolocate
    if origin == 'Current Location':
        origin = None

    try:
        # Import geolocation tools
        from agents.tools.location_tool import geocode_place, geolocate_user

        # Get destination coordinates
        dest_coords = None
        if "," in destination and destination.replace(",", "").replace(".", "").replace("-", "").replace(" ", "").isdigit():
            # Looks like coordinates "lat,lng"
            try:
                lat, lng = map(float, destination.split(","))
                dest_coords = {"lat": lat, "lng": lng}
                logger.info(f"Using destination coordinates: {lat}, {lng}")
            except ValueError:
                pass

        if not dest_coords:
            # Geocode destination address
            geocode_result = geocode_place.invoke({"address": destination})
            if geocode_result.get("slots", {}).get("origin"):
                dest_coords = geocode_result["slots"]["origin"]
                logger.info(f"Geocoded destination: {dest_coords}")
            else:
                return {
                    "context": {
                        "directions": {
                            "error": f"Could not geocode destination: {destination}",
                            "destination": destination
                        }
                    }
                }

        # Get origin coordinates
        origin_coords = None
        if origin:
            if "," in origin and origin.replace(",", "").replace(".", "").replace("-", "").replace(" ", "").isdigit():
                # Looks like coordinates "lat,lng"
                try:
                    lat, lng = map(float, origin.split(","))
                    origin_coords = {"lat": lat, "lng": lng}
                    logger.info(f"Using origin coordinates: {lat}, {lng}")
                except ValueError:
                    pass

            if not origin_coords:
                # Geocode origin address
                geocode_result = geocode_place.invoke({"address": origin})
                if geocode_result.get("slots", {}).get("origin"):
                    origin_coords = geocode_result["slots"]["origin"]
                    logger.info(f"Geocoded origin: {origin_coords}")
                else:
                    return {
                        "context": {
                            "directions": {
                                "error": f"Could not geocode origin: {origin}",
                                "origin": origin,
                                "destination": destination
                            }
                        }
                    }
        else:
            # No origin provided, use geolocation
            geolocate_result = geolocate_user.invoke({})
            if geolocate_result.get("slots", {}).get("origin"):
                origin_coords = geolocate_result["slots"]["origin"]
                logger.info(f"Geolocated user: {origin_coords}")
            else:
                return {
                    "context": {
                        "directions": {
                            "error": "Could not determine your current location. Please provide an origin address.",
                            "destination": destination
                        }
                    }
                }

        # Now get directions using transit first, then walking fallback
        origin_lat = origin_coords["lat"]
        origin_lng = origin_coords["lng"]
        dest_lat = dest_coords["lat"]
        dest_lng = dest_coords["lng"]

        # Try transit directions first
        logger.info("Attempting transit directions")
        try:
            transit_result = transit_directions.invoke({
                "origin_lat": origin_lat,
                "origin_lng": origin_lng,
                "dest_lat": dest_lat,
                "dest_lng": dest_lng
            })
        except Exception as e:
            logger.warning(f"Transit directions failed: {e}")
            transit_result = {
                "context": {
                    "transit_directions": {
                        "error": str(e),
                        "mode": "failed"
                    }
                }
            }

        # Check if we got valid transit directions (not an error)
        transit_data = transit_result.get("context", {}).get("transit_directions", {})
        if not transit_data.get("error") and transit_data.get("mode") != "walking_fallback" and transit_data.get("mode") != "failed":
            # Successful transit directions
            return {
                "context": {
                    "directions": {
                        "mode": "transit",
                        "origin": origin_coords,
                        "destination": dest_coords,
                        "transit_directions": transit_data
                    }
                }
            }

        # Transit failed or returned walking fallback, try walking directions
        logger.info("Transit directions not available, trying walking directions")
        try:
            walking_result = walking_directions.invoke({
                "origin_lat": origin_lat,
                "origin_lng": origin_lng,
                "dest_lat": dest_lat,
                "dest_lng": dest_lng
            })
        except Exception as e:
            logger.warning(f"Walking directions failed: {e}")
            walking_result = {
                "context": {
                    "walking_directions": {
                        "error": str(e)
                    }
                }
            }

        walking_data = walking_result.get("context", {}).get("walking_directions", {})
        if not walking_data.get("error"):
            # Successful walking directions
            return {
                "context": {
                    "directions": {
                        "mode": "walking",
                        "origin": origin_coords,
                        "destination": dest_coords,
                        "walking_directions": walking_data,
                        "note": "Transit directions not available; showing walking directions instead."
                    }
                }
            }

        # Both transit and walking failed
        return {
            "context": {
                "directions": {
                    "error": "Could not find directions to this destination.",
                    "origin": origin_coords,
                    "destination": dest_coords,
                    "transit_error": transit_data.get("error"),
                    "walking_error": walking_data.get("error")
                }
            }
        }

    except Exception as e:
        logger.exception(f"Unified directions failed: {e}")
        return {
            "context": {
                "directions": {
                    "error": str(e),
                    "destination": destination,
                    "origin": origin
                }
            }
        }