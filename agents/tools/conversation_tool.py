import logging
from langchain_core.tools import tool
from langchain_core.language_models import BaseLanguageModel
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from utils.llm_logger import log_llm_usage

logger = logging.getLogger(__name__)

def get_llm_fallback():
    """Get LLM client for conversation fallback."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.3,
            google_api_key=api_key
        )
    return None

@tool("Conversation")
def handle_conversation(message: str) -> dict:
    """
    Handle casual conversation and redirect to transportation assistance.

    Args:
        message: The user's casual message

    Returns:
        dict: WorldState-compatible patch with conversation response
    """
    logger.info(f"Handling casual conversation: {message}")

    message_lower = message.lower().strip()

    # Define comprehensive conversation patterns and responses
    responses = {
        "greeting": {
            "patterns": [
                "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
                "howdy", "hiya", "sup", "yo", "what's up", "wassup", "greetings",
                "morning", "afternoon", "evening", "good day"
            ],
            "response": "Hello! I'm your transportation assistant. I can help you with weather conditions, location services, and navigation planning. What transportation-related question can I help you with today?"
        },
        "wellbeing": {
            "patterns": [
                "how are you", "how r u", "hru", "how do you do", "how's it going",
                "how are things", "what's new", "how have you been", "how's everything",
                "how's life", "how's your day", "how's it", "you good", "you okay"
            ],
            "response": "I'm doing great, thanks for asking! I'm here to help with all your transportation and navigation needs. How can I assist you with your travel plans today?"
        },
        "thanks": {
            "patterns": [
                "thanks", "thank you", "thx", "ty", "appreciate it", "grateful",
                "thank you so much", "thanks a lot", "much appreciated", "cheers"
            ],
            "response": "You're welcome! I'm here whenever you need help with transportation, weather updates, or navigation assistance. What else can I help you with?"
        },
        "small_talk": {
            "patterns": [
                "nice day", "beautiful weather", "how's the weather", "what a day",
                "bored", "nothing much", "just chilling", "tell me something",
                "did you eat", "what did you eat", "are you hungry", "do you sleep",
                "what do you do", "who are you", "what are you", "can you help me",
                "what's your name", "who made you", "where are you from", "how old are you",
                "what can you do", "what are your capabilities", "tell me about yourself"
            ],
            "response": "I'm an AI assistant focused on transportation and navigation! I don't eat or sleep, but I'm always ready to help with weather updates, directions, or location services. What transportation question can I answer for you?"
        },
        "farewell": {
            "patterns": [
                "bye", "goodbye", "see you", "see ya", "later", "take care",
                "good night", "farewell", "so long", "catch you later"
            ],
            "response": "Goodbye! Remember, I'm here whenever you need transportation assistance, weather updates, or navigation help. Safe travels!"
        },
        "agreement": {
            "patterns": [
                "yes", "yeah", "yep", "sure", "okay", "ok", "alright", "fine",
                "sounds good", "that works", "perfect", "great", "awesome"
            ],
            "response": "Great! Now, what transportation-related question can I help you with? I can provide weather updates, directions, or location services."
        },
        "questions": {
            "patterns": [
                "why", "when", "where", "how", "what", "which", "who", "whose"
            ],
            "response": "I'm here to help with transportation questions! I can answer questions about weather conditions, directions, routes, and location services. What specific transportation question do you have?"
        }
    }

    # Determine response type
    response_type = "general"
    selected_response = None

    for rtype, data in responses.items():
        if any(pattern in message_lower for pattern in data["patterns"]):
            response_type = rtype
            selected_response = data["response"]
            break

    # If we found a hardcoded response, use it
    if selected_response:
        return {
            "context": {
                "conversation_response": {
                    "original_message": message,
                    "response_type": response_type,
                    "response_text": selected_response,
                    "method": "hardcoded"
                }
            }
        }

    # LLM fallback for unrecognized patterns
    llm = get_llm_fallback()
    if llm:
        try:
            prompt = f"""
You are a transportation assistant AI. Respond naturally to this casual message, but ALWAYS redirect the conversation to transportation topics.

Keep your response under 60 words. Be friendly but focused on transportation assistance.

User message: "{message}"

Response:"""

            llm_response = llm.invoke([{"role": "user", "content": prompt}])
            response_text = llm_response.content.strip()

            # Log LLM token usage
            try:
                usage = llm_response.usage_metadata
                log_llm_usage(
                    agent="conversation_tool",
                    model=llm.model,
                    usage={
                        'input_tokens': usage['input_tokens'],
                        'output_tokens': usage['output_tokens'],
                        'total_tokens': usage['total_tokens']
                    }
                )
            except Exception as e:
                logger.debug(f"Failed to log LLM usage for conversation_tool: {e}")

            return {
                "context": {
                    "conversation_response": {
                        "original_message": message,
                        "response_type": "llm_fallback",
                        "response_text": response_text,
                        "method": "llm"
                    }
                }
            }
        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")

    # Final fallback if everything fails
    fallback_response = "I'm your transportation assistant! I can help with weather updates, directions, and location services. What transportation question can I answer for you?"
    return {
        "context": {
            "conversation_response": {
                "original_message": message,
                "response_type": "fallback",
                "response_text": fallback_response,
                "method": "fallback"
            }
        }
    }