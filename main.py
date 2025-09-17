"""
main.py
Entry point for the Vaya CLI assistant. Handles user interaction, session memory, and passes queries to the supervisor agent.
"""
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables before importing anything that depends on them
load_dotenv()

from utils.logger import get_logger
from agents.supervisor import create_supervisor
from utils.google_maps import get_location_from_source, geocode_place

# Optional: Enable colorized CLI output if colorama is available
try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    # Fallback: No color support
    class MockColors:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    Fore = Back = Style = MockColors()
    COLORS_AVAILABLE = False

logger = get_logger("main")

# --- Application Setup ---
supervisor = create_supervisor()  # LLM-powered agent router
chat_history = []  # Simple in-memory chat history for context

def initialize_default_location():
    """
    Attempt to determine a default user location at startup.
    Tries public IP-based geolocation, falls back to NYC if unavailable.
    Returns a dict with lat/lon/label/source.
    """
    try:
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
    # Fallback: New York City
    logger.warning("Using hard-coded default location")
    return {
        "lat": 40.7128, "lon": -74.0060,  # NYC coordinates
        "label": "New York City, NY, USA",
        "source": "default"
    }
default_location = initialize_default_location()

# Store last resolved location for weather (initialized with default)
last_location = default_location.copy()


def handle_message(user_query: str, client_ip: str = None) -> str:
    """
    Process a user query, manage location context, and interact with the supervisor agent.
    - Maintains chat history for context.
    - Handles location resolution (client IP, last known, or default).
    - Updates last_location if supervisor returns new info.
    Returns the assistant's reply as a string.
    """
    global last_location, default_location

    # Build recent chat history for context (last 3 turns)
    recent_history_objects = []
    for msg in chat_history[-6:]:
        if msg.startswith("User:"):
            recent_history_objects.append(HumanMessage(content=msg[6:]))
        elif msg.startswith("Assistant:"):
            recent_history_objects.append(AIMessage(content=msg[11:]))

    # Location context: prioritize client IP, then last known, then default
    location_context = {}
    if client_ip:
        location_context["client_ip"] = client_ip
        logger.debug(f"Using client IP for potential location: {client_ip}")
    else:
        logger.debug("No explicit location source, using last known or default location")

    # Ensure we always have a valid location
    if last_location["lat"] is None:
        last_location = default_location.copy()
        logger.debug(f"Using default location: {default_location.get('label', 'Unknown')}")

    # Build context for supervisor agent
    context = {
        "input": user_query,
        "history": recent_history_objects,
        "last_location": last_location.copy(),
        **location_context
    }

    # Get response from supervisor (LLM agent router)
    response = supervisor(context)

    # Update last_location if supervisor returns new info
    metadata = None
    if hasattr(response, "metadata") and isinstance(response.metadata, dict):
        metadata = response.metadata
    elif isinstance(response, dict) and "metadata" in response and isinstance(response["metadata"], dict):
        metadata = response["metadata"]
    if metadata:
        new_user_location = metadata.get("new_user_location")
        if new_user_location:
            logger.info(f"Updating user location to: {new_user_location.get('label', 'Unknown')}")
            last_location = new_user_location
        loc = metadata.get("weather_location")
        if loc and all(k in loc for k in ("lat", "lon")):
            if "source" not in loc or loc["source"] != "default":
                logger.info(f"Updating last_location to: {loc.get('label', 'Unknown')}")
                last_location = loc

    # Extract reply text from supervisor response
    if hasattr(response, "content"):
        reply = response.content
    elif isinstance(response, dict) and "response" in response:
        reply = response["response"]
    else:
        reply = str(response)

    # Store turn in chat history
    chat_history.append(f"User: {user_query}")
    chat_history.append(f"Assistant: {reply}")

    return reply

# --- Enhanced Command-Line Interface ---

def print_welcome():
    """
    Print a welcoming startup message with color and usage tips.
    """
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.YELLOW}🚀 VAYA TRANSPORTATION ASSISTANT")
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.WHITE}Your AI-powered companion for transportation insights!")
    print(f"\n{Fore.GREEN}✨ I can help you with:")
    print(f"{Fore.WHITE}   🌤️  Weather conditions and forecasts")
    print(f"{Fore.WHITE}   🚗 Traffic and route information")
    print(f"{Fore.WHITE}   🚌 Public transit schedules")
    print(f"{Fore.WHITE}   📍 Location-based services")
    print(f"\n{Fore.MAGENTA}💬 Type your questions naturally, or try:")
    print(f"{Fore.WHITE}   • 'What's the weather like?'")
    print(f"{Fore.WHITE}   • 'How's traffic to downtown?'")
    print(f"{Fore.WHITE}   • 'Show me transit options'")
    print(f"\n{Fore.YELLOW}📝 Commands: {Fore.WHITE}'exit' or 'quit' to end, Ctrl+C for quick exit")
    print(f"{Fore.CYAN}{'-'*60}\n")

def print_goodbye():
    """
    Print a friendly goodbye message with color.
    """
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.GREEN}👋 Thank you for using Vaya Transportation Assistant!")
    print(f"{Fore.WHITE}   Safe travels and see you next time!")
    print(f"{Fore.CYAN}{'='*60}\n")

if __name__ == "__main__":
    logger.info("Transportation Assistant starting up...")
    
    # Display welcome message
    print_welcome()
    
    while True:
        try:
            # Enhanced prompt with color and emoji
            user_input = input(f"{Fore.BLUE}🗨️  You: {Fore.WHITE}").strip()
            
            # Handle empty input
            if not user_input:
                print(f"{Fore.CYAN}💭 Assistant: {Fore.WHITE}I'm here and listening! Feel free to ask me anything about transportation, weather, or travel.\n")
                continue
                
            # Handle exit commands
            if user_input.lower() in ["exit", "quit", "bye", "goodbye"]:
                print_goodbye()
                break
                
            try:
                assistant_response = handle_message(user_input)
                print(f"{Fore.GREEN}🤖 Assistant: {Fore.WHITE}{assistant_response}\n")
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                print(f"{Fore.RED}⚠️  Assistant: {Fore.WHITE}I encountered an issue processing your request. Please try rephrasing or try again!\n")
                
        except KeyboardInterrupt:
            print_goodbye()
            break
        except Exception as e:
            logger.error(f"Error reading input: {e}")
            print(f"{Fore.RED}❌ Assistant: {Fore.WHITE}Something unexpected happened. Let's try again!")

