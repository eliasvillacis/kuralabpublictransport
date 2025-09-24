import os
import logging
import requests
import time
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from utils.api_logger import log_api_call

logger = logging.getLogger(__name__)

def get_directions(origin_lat: float, origin_lng: float, dest_lat: Optional[float], dest_lng: Optional[float],
                  dest_place_id: Optional[str] = None,
                  mode: str = "transit", departure_time: Optional[str] = None,
                  transit_mode_filter: Optional[List[str]] = None,
                  routing_preference: Optional[str] = None,
                  alternatives: bool = True) -> dict:
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
        "mode": mode.lower(),  # Google expects 'transit' or 'walking' etc.
        "key": api_key,
        "alternatives": "true" if alternatives else "false"
    }

    # Support place_id-style destination (avoid geocoding when possible)
    if dest_place_id:
        params["destination"] = f"place_id:{dest_place_id}"
    else:
        params["destination"] = f"{dest_lat},{dest_lng}"

    if departure_time:
        params["departure_time"] = departure_time
    else:
        # Default to now for transit
        import time
        params["departure_time"] = str(int(time.time()))

    # Map transit-specific filters to Google params
    if mode.lower() == "transit":
        if transit_mode_filter:
            # Google expects comma-separated transit_mode values (bus, subway, train, tram, rail)
            params["transit_mode"] = ",".join([m.lower() for m in transit_mode_filter])
        if routing_preference:
            # Google param is transit_routing_preference
            params["transit_routing_preference"] = routing_preference

    # Log API call
    # Note: status will be logged after the request completes
    # log_api_call("directions", url, params)

    try:
        start = time.time()
        response = requests.get(url, params=params, timeout=10)
        elapsed_ms = int((time.time() - start) * 1000)
        try:
            response_bytes = len(response.content) if response.content is not None else None
        except Exception:
            response_bytes = None

        # Log API call with status
        try:
            log_api_call(
                tool_name="directions",
                provider="google",
                endpoint="maps/api/directions/json",
                status=response.status_code,
                elapsed_ms=elapsed_ms,
                response_bytes=response_bytes,
                params=params,
                estimated_cost=None,
            )
        except Exception:
            pass

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

        routes = data.get("routes", [])
        if not routes:
            return {"context": {"transit_directions": {"error": "No transit routes found", "origin": {"lat": origin_lat, "lng": origin_lng}, "destination": {"lat": dest_lat, "lng": dest_lng}}}}

        # Normalize the first route into a consistent structure (legs/steps with text fields)
        route = routes[0]
        legs = route.get("legs", [])

        directions = {
            "origin": {"lat": origin_lat, "lng": origin_lng},
            "destination": {"lat": dest_lat, "lng": dest_lng},
            "mode": "transit",
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
                    "travel_mode": step.get("travel_mode") or step.get("travel_mode", "UNKNOWN"),
                    "duration": step.get("duration", {}).get("text", "Unknown"),
                    "distance": step.get("distance", {}).get("text", "Unknown"),
                    "instructions": step.get("html_instructions", "").replace("<b>", "").replace("</b>", "").replace("<div>", "").replace("</div>", ""),
                    "maneuver": step.get("maneuver", "")
                }

                transit_details = step.get("transit_details") or step.get("transit") or {}
                if transit_details:
                    step_info["transit"] = {
                        "line_name": transit_details.get("line", {}).get("name", "") if isinstance(transit_details.get("line"), dict) else transit_details.get("line_name", ""),
                        "vehicle_type": transit_details.get("line", {}).get("vehicle", {}).get("type", "") if isinstance(transit_details.get("line"), dict) else transit_details.get("vehicle_type", ""),
                        "headsign": transit_details.get("headsign", ""),
                        "num_stops": transit_details.get("num_stops", 0),
                        "departure_stop": transit_details.get("departure_stop", {}).get("name", "") if isinstance(transit_details.get("departure_stop"), dict) else transit_details.get("departure_stop", ""),
                        "arrival_stop": transit_details.get("arrival_stop", {}).get("name", "") if isinstance(transit_details.get("arrival_stop"), dict) else transit_details.get("arrival_stop", ""),
                        "departure_time": transit_details.get("departure_time", {}).get("text", "") if isinstance(transit_details.get("departure_time"), dict) else transit_details.get("departure_time", ""),
                        "arrival_time": transit_details.get("arrival_time", {}).get("text", "") if isinstance(transit_details.get("arrival_time"), dict) else transit_details.get("arrival_time", "")
                    }

                leg_info["steps"].append(step_info)

            directions["legs"].append(leg_info)

        return {"context": {"transit_directions": directions}}

    except Exception as e:
        logger.exception(f"Transit directions failed: {e}")
        return {"context": {"transit_directions": {"error": str(e), "origin": {"lat": origin_lat, "lng": origin_lng}, "destination": {"lat": dest_lat, "lng": dest_lng}}}}

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
        data = get_directions(origin_lat, origin_lng, dest_lat, dest_lng, "walking")
        routes = data.get("routes", [])
        if not routes:
            return {"context": {"walking_directions": {"error": "No walking routes found", "origin": {"lat": origin_lat, "lng": origin_lng}, "destination": {"lat": dest_lat, "lng": dest_lng}}}}

        route = routes[0]
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
                    "travel_mode": step.get("travel_mode") or step.get("travel_mode", "WALKING"),
                    "duration": step.get("duration", {}).get("text", "Unknown"),
                    "distance": step.get("distance", {}).get("text", "Unknown"),
                    "instructions": step.get("html_instructions", "").replace("<b>", "").replace("</b>", "").replace("<div>", "").replace("</div>", ""),
                    "maneuver": step.get("maneuver", "")
                }
                leg_info["steps"].append(step_info)

            directions["legs"].append(leg_info)

        return {"context": {"walking_directions": directions}}

    except Exception as e:
        logger.exception(f"Walking directions failed: {e}")
        return {"context": {"walking_directions": {"error": str(e), "origin": {"lat": origin_lat, "lng": origin_lng}, "destination": {"lat": dest_lat, "lng": dest_lng}}}}

@tool("Directions")
def directions(destination: str = None, origin: Optional[str] = None,
               destinationPlaceId: Optional[str] = None,
               modePreference: Optional[str] = None,
               transitModes: Optional[List[str]] = None,
               transitRouting: Optional[str] = None,
               maxAlternatives: int = 3,
               includeSteps: bool = True,
               onlyTheseLines: Optional[List[str]] = None,
               avoidLines: Optional[List[str]] = None,
               viaStation: Optional[str] = None) -> dict:
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

    # Defensive checks: if caller passed a 'query' string or provided no destination, return MISSING_INFO
    # so the caller (executor) can insert a PlacesSearch first.
    try:
        if isinstance(destination, dict) and destination.get('query'):
            return {"status": "MISSING_INFO", "reason": "Directions needs a concrete destination, not a query.", "hints": {"suggest": "PlacesSearch(query='<brand or keyword>')"}}
        if isinstance(destination, str) and (not destination.strip()) and not destinationPlaceId:
            return {"status": "MISSING_INFO", "reason": "No destination provided.", "hints": {"suggest": "PlacesSearch(query='<brand or keyword>')"}}
        if isinstance(destination, str) and destination.strip() and 'query' in destination.lower():
            # e.g., someone passed a query-like string; ask for PlacesSearch instead
            return {"status": "MISSING_INFO", "reason": "Directions needs a concrete destination, not a query.", "hints": {"suggest": "PlacesSearch(query='<brand or keyword>')"}}
    except Exception:
        pass

    try:
        # Import geolocation tools (relative import so runtime path is stable)
        from .location_tool import geocode_place, geolocate_user

        # Get destination coordinates or place id
        dest_coords = None
        dest_place_id = destinationPlaceId

        # Support dict destination like {'placeId': 'ChIJ...'} or {'lat':..,'lng':..}
        if isinstance(destination, dict):
            if destination.get('placeId'):
                dest_place_id = destination.get('placeId')
            elif destination.get('lat') is not None and destination.get('lng') is not None:
                dest_coords = {'lat': destination.get('lat'), 'lng': destination.get('lng'), 'name': destination.get('name')}

        if isinstance(destination, str) and "," in destination and destination.replace(",", "").replace(".", "").replace("-", "").replace(" ", "").isdigit():
            # Looks like coordinates "lat,lng"
            try:
                lat, lng = map(float, destination.split(","))
                dest_coords = {"lat": lat, "lng": lng}
                logger.info(f"Using destination coordinates: {lat}, {lng}")
            except ValueError:
                pass

        # If a place id was supplied, use it and skip geocoding
        if not dest_coords and dest_place_id:
            # Do not geocode; we'll instruct get_directions to use a place_id: URI
            dest_coords = {'placeId': dest_place_id}
        elif not dest_coords:
            # Geocode destination address
            geocode_result = geocode_place.invoke({"address": destination})
            # geocode_place returns a slots mapping (slot key depends on call). Prefer destination slot if present.
            slots = geocode_result.get("slots", {}) or {}
            # Try destination slot first, then origin (some tools return origin by default)
            if slots.get("destination"):
                dest_coords = slots.get("destination")
            elif slots.get("origin"):
                dest_coords = slots.get("origin")
            else:
                # If raw is present, try to extract geometry
                raw = geocode_result.get("raw") or {}
                try:
                    first = raw[0] if isinstance(raw, list) and raw else raw
                    geom = first.get("geometry", {}) if isinstance(first, dict) else {}
                    loc = geom.get("location", {})
                    if loc.get("lat") and loc.get("lng"):
                        dest_coords = {"lat": loc.get("lat"), "lng": loc.get("lng"), "name": first.get("formatted_address")}
                except Exception:
                    dest_coords = None

            if not dest_coords:
                return {"context": {"directions": {"error": f"Could not geocode destination: {destination}", "destination": destination}}}

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
                slots = geocode_result.get("slots", {}) or {}
                if slots.get("origin"):
                    origin_coords = slots.get("origin")
                elif slots.get("destination"):
                    origin_coords = slots.get("destination")
                else:
                    raw = geocode_result.get("raw") or {}
                    try:
                        first = raw[0] if isinstance(raw, list) and raw else raw
                        geom = first.get("geometry", {}) if isinstance(first, dict) else {}
                        loc = geom.get("location", {})
                        if loc.get("lat") and loc.get("lng"):
                            origin_coords = {"lat": loc.get("lat"), "lng": loc.get("lng"), "name": first.get("formatted_address")}
                    except Exception:
                        origin_coords = None

                if not origin_coords:
                    return {"context": {"directions": {"error": f"Could not geocode origin: {origin}", "origin": origin, "destination": destination}}}
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

        # Now get directions using the unified get_directions() which returns Routes v1 schema
        origin_lat = origin_coords["lat"]
        origin_lng = origin_coords["lng"]

        # If dest_coords contains placeId then we will call Google with destination="place_id:<id>"
        dest_place_id = None
        if isinstance(dest_coords, dict) and dest_coords.get('placeId'):
            dest_place_id = dest_coords.get('placeId')
            dest_lat = None
            dest_lng = None
        else:
            dest_lat = dest_coords["lat"]
            dest_lng = dest_coords["lng"]

        # Build single mode choice from modePreference param; default to transit then walking
        if modePreference:
            mode_pref = [modePreference]
        else:
            mode_pref = ["transit", "walking"]

        # Helper: normalize one google route to our compact schema
        def normalize_route(r, mode_choice, include_steps_flag=True):
            legs = r.get("legs", [])
            norm = {
                "mode": mode_choice,
                "summary": r.get("summary", ""),
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
                if include_steps_flag:
                    for step in leg.get("steps", []):
                        step_info = {
                            "travel_mode": step.get("travel_mode") or step.get("travel_mode", "UNKNOWN"),
                            "duration": step.get("duration", {}).get("text", "Unknown"),
                            "distance": step.get("distance", {}).get("text", "Unknown"),
                            "instructions": step.get("html_instructions", "").replace("<b>", "").replace("</b>", "").replace("<div>", "").replace("</div>", ""),
                            "maneuver": step.get("maneuver", "")
                        }
                        td = step.get("transit_details") or step.get("transit") or {}
                        if td:
                            line = td.get("line") or {}
                            line_short = line.get("short_name") if isinstance(line, dict) else None
                            line_name = line.get("name") if isinstance(line, dict) else None
                            step_info["transit"] = {
                                "line_short": line_short or td.get("line_short_name") or None,
                                "line_name": line_name or td.get("line_name") or None,
                                "vehicle_type": line.get("vehicle", {}).get("type", "") if isinstance(line, dict) else td.get("vehicle_type", ""),
                                "departure_stop": td.get("departure_stop", {}).get("name", "") if isinstance(td.get("departure_stop"), dict) else td.get("departure_stop", ""),
                                "arrival_stop": td.get("arrival_stop", {}).get("name", "") if isinstance(td.get("arrival_stop"), dict) else td.get("arrival_stop", ""),
                                "departure_time": td.get("departure_time", {}).get("text", "") if isinstance(td.get("departure_time"), dict) else td.get("departure_time", ""),
                                "arrival_time": td.get("arrival_time", {}).get("text", "") if isinstance(td.get("arrival_time"), dict) else td.get("arrival_time", "")
                            }
                        leg_info["steps"].append(step_info)
                norm["legs"].append(leg_info)
            return norm

        # Fetch routes for each mode preference (stop when we get viable routes)
        last_errors = {}
        all_routes = []
        # Accept modePreference either as a single string or a list
        resolved_mode_pref = []
        for mp in mode_pref:
            if isinstance(mp, list):
                resolved_mode_pref.extend(mp)
            else:
                resolved_mode_pref.append(mp)

        for mode_choice in resolved_mode_pref:
            try:
                mc = (mode_choice or "").lower()
                # Translate LLM-friendly single modes into Google params
                # If user asked for bus/train/subway/tram/rail, we should call mode=transit & transit_mode=<value>
                transit_specific = {"bus", "train", "subway", "tram", "rail"}
                if mc in transit_specific:
                    call_mode = "transit"
                    call_transit_modes = [mc]
                elif mc in {"walking", "driving", "bicycling"}:
                    call_mode = mc
                    call_transit_modes = transitModes
                else:
                    # default to transit if unknown or explicitly 'transit'
                    call_mode = "transit"
                    call_transit_modes = transitModes

                # Map our parameter names to the get_directions() signature
                    data = get_directions(
                    origin_lat, origin_lng, dest_lat, dest_lng,
                    dest_place_id=dest_place_id,
                    mode=call_mode,
                    departure_time=None,
                    transit_mode_filter=call_transit_modes,
                    routing_preference=transitRouting,
                    alternatives=(maxAlternatives > 1)
                )
                routes = data.get("routes", [])
                if routes:
                    for r in routes:
                        # mark the route with the original requested mode for traceability
                        try:
                            r.setdefault("_requested_mode", mode_choice)
                        except Exception:
                            pass
                        all_routes.append((call_mode, r))
                    # If user asked only one explicit mode, don't try others
                    if modePreference:
                        break
            except Exception as e:
                logger.warning(f"Directions fetch for mode {mode_choice} failed: {e}")
                last_errors[mode_choice] = str(e)

        # VIA station two-hop option: prefer a stitched route at the front
        stitched_routes = []
        if viaStation and "transit" in [m.lower() for m in mode_pref]:
            try:
                from .location_tool import geocode_place
                geocode_result = geocode_place.invoke({"address": viaStation})
                slots = geocode_result.get("slots", {}) or {}
                station_coords = None
                if slots.get("destination"):
                    station_coords = slots.get("destination")
                elif slots.get("origin"):
                    station_coords = slots.get("origin")
                else:
                    raw = geocode_result.get("raw") or {}
                    try:
                        first = raw[0] if isinstance(raw, list) and raw else raw
                        geom = first.get("geometry", {}) if isinstance(first, dict) else {}
                        loc = geom.get("location", {})
                        if loc.get("lat") and loc.get("lng"):
                            station_coords = {"lat": loc.get("lat"), "lng": loc.get("lng"), "name": first.get("formatted_address")}
                    except Exception:
                        station_coords = None

                if station_coords:
                    # leg1: origin -> station
                    leg1 = get_directions(origin_lat, origin_lng, station_coords["lat"], station_coords["lng"], mode="transit", alternatives=False)
                    # leg2: station -> dest (support place_id)
                    leg2 = get_directions(station_coords["lat"], station_coords["lng"], dest_lat, dest_lng, dest_place_id=dest_place_id, mode="transit", alternatives=False)
                    # stitch minimal representation: combine legs
                    r1 = leg1.get("routes", [])
                    r2 = leg2.get("routes", [])
                    if r1 and r2:
                        stitched = {
                            "summary": f"Via {viaStation}",
                            "legs": (r1[0].get("legs", []) if r1 else []) + (r2[0].get("legs", []) if r2 else []),
                        }
                        stitched_routes.append(("transit", stitched))
            except Exception as e:
                logger.warning(f"Via-station flow failed: {e}")

        # Combine stitched routes first, then all_routes
        combined = stitched_routes + all_routes

        # Helper to extract set of lines from a route
        def route_lines(route_tuple):
            _, r = route_tuple
            lines = set()
            for leg in r.get("legs", []):
                for step in leg.get("steps", []):
                    td = step.get("transit_details") or step.get("transit") or {}
                    if td:
                        line = td.get("line") or {}
                        if isinstance(line, dict):
                            short = line.get("short_name")
                            name = line.get("name")
                            if short:
                                lines.add(str(short))
                            if name:
                                lines.add(str(name))
                        else:
                            # fallback keys
                            if td.get("line_name"):
                                lines.add(str(td.get("line_name")))
                            if td.get("line_short_name"):
                                lines.add(str(td.get("line_short_name")))
            return lines

        preferred = []
        others = []
        only_set = set(onlyTheseLines or [])
        avoid_set = set(avoidLines or [])

        for rt in combined:
            lines = route_lines(rt)
            # If avoidLines intersect, treat as lower priority
            if avoid_set and lines & avoid_set:
                others.append(rt)
                continue
            if only_set and lines and lines.isdisjoint(only_set):
                # route does not include any preferred lines
                others.append(rt)
                continue
            preferred.append(rt)

        ranked = preferred + others

        # Cap to maxAlternatives
        final = ranked[: maxAlternatives if maxAlternatives and maxAlternatives > 0 else 3]

        # Normalize and respect includeSteps
        normalized_routes = [normalize_route(r, mode_choice=m, include_steps_flag=includeSteps) for (m, r) in final]

        # If nothing matched, return error with last_errors
        if not normalized_routes:
            return {"context": {"directions": {"error": "No routes found after applying filters", "origin": origin_coords, "destination": dest_coords, "errors": last_errors}}}

        return {"context": {"directions": {"modePreference": modePreference or mode_pref, "origin": origin_coords, "destination": dest_coords, "routes": normalized_routes}}}

        # If we got here, none of the mode preferences yielded routes
        return {"context": {"directions": {"error": "No routes found for any preferred modes", "origin": origin_coords, "destination": dest_coords, "errors": last_errors}}}

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