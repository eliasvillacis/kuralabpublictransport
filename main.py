# main.py
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables FIRST
load_dotenv()

# Import logger and supervisor AFTER loading env
from utils.logger import get_logger
from agents.supervisor import create_supervisor
from utils.google_maps import get_location_from_source, geocode_place

logger = get_logger("main")

# --- Application Setup ---
supervisor = create_supervisor()
chat_history = []

# Initialize default location by getting it once at startup
def initialize_default_location():
    """Get default location at startup for more reliable location fallback"""
    try:
        # Try to get public IP for better geolocation
        import requests
        ip_response = requests.get("https://api.ipify.org", timeout=5)
        if ip_response.status_code == 200:
            public_ip = ip_response.text.strip()
            if public_ip and not public_ip.startswith("192.168") and not public_ip.startswith("10."):
                logger.info(f"Getting default location from IP: {public_ip}")
                geo = get_location_from_source({"ip": public_ip})
                if geo:
                    logger.info(f"Successfully obtained default location: {geo.get('label', 'Unknown')}")
                    return geo
                else:
                    logger.warning("Could not obtain location from IP")
    except Exception as e:
        logger.warning(f"Error getting default location: {e}")
    
    # Hard-coded fallback if everything else fails
    logger.warning("Using hard-coded default location")
    return {
        "lat": 40.7128, "lon": -74.0060,  # NYC coordinates
        "label": "New York City, NY, USA", 
        "source": "default"
    }

# Get default location at startup
default_location = initialize_default_location()

# Store last resolved location for weather (initialized with default)
last_location = default_location.copy()

def handle_message(user_query: str, client_ip: str = None) -> str:
    global last_location, default_location
    
    # Create a structured list of message objects for the agent's memory
    recent_history_objects = []
    for msg in chat_history[-6:]:  # Use last 3 turns of history
        if msg.startswith("User:"):
            recent_history_objects.append(HumanMessage(content=msg[6:]))
        elif msg.startswith("Assistant:"):
            recent_history_objects.append(AIMessage(content=msg[11:]))
    
    # Handle different types of location context
    location_context = {}
    
    # Location priority:
    # 1. Current client_ip (if provided)
    # 2. Last known location from previous queries
    # 3. Default location from startup
    
    if client_ip:
        # First priority: Use client IP from current web request
        location_context["client_ip"] = client_ip
        logger.debug(f"Using client IP for potential location: {client_ip}")
    else:
        # Second priority: already handled via last_location
        logger.debug("No explicit location source, using last known or default location")
    
    # Always ensure we have a valid location by providing defaults
    if last_location["lat"] is None:
        last_location = default_location.copy()
        logger.debug(f"Using default location: {default_location.get('label', 'Unknown')}")

    # Pass context to supervisor
    context = {
        "input": user_query,
        "history": recent_history_objects,
        "last_location": last_location.copy(),  # Always provide a location
        **location_context  # Add any additional location context
    }
    
    # Handle the response from our updated supervisor
    response = supervisor(context)

    # If the response contains a new location, update last_location
    metadata = None
    if hasattr(response, "metadata") and isinstance(response.metadata, dict):
        metadata = response.metadata
    elif isinstance(response, dict) and "metadata" in response and isinstance(response["metadata"], dict):
        metadata = response["metadata"]
    if metadata:
        # Handle new user location setting
        new_user_location = metadata.get("new_user_location")
        if new_user_location:
            logger.info(f"Updating user location to: {new_user_location.get('label', 'Unknown')}")
            last_location = new_user_location
        
        # Handle weather location updates
        loc = metadata.get("weather_location")
        if loc and all(k in loc for k in ("lat", "lon")):
            # Only update if we got a real location (not just the default again)
            if "source" not in loc or loc["source"] != "default":
                logger.info(f"Updating last_location to: {loc.get('label', 'Unknown')}")
                last_location = loc

    # Get the assistant's reply content
    if hasattr(response, "content"):
        reply = response.content
    elif isinstance(response, dict) and "response" in response:
        reply = response["response"]
    else:
        reply = str(response)

    # Store the new turn in our simple in-memory list
    chat_history.append(f"User: {user_query}")
    chat_history.append(f"Assistant: {reply}")
    
    return reply

# --- Example Command-Line Conversation Loop ---
if __name__ == "__main__":
    logger.info("Assistant starting and waiting for input...")
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                print("Assistant: Goodbye!")
                break
            try:
                assistant_response = handle_message(user_input)
                print("Assistant:", assistant_response)
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                print("Assistant: Sorry, I encountered an error while processing your request. Please try again.")
        except KeyboardInterrupt:
            print("\nAssistant: Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error reading input: {e}")
            print("Assistant: Sorry, something went wrong. Please try again.")

