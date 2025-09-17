# agents/specialists/chitchat.py
# Specialist for handling general conversation, greetings, and guiding users to main features.

import json
from typing import Dict, Any
from langchain.schema.runnable import Runnable, RunnableLambda
from utils.logger import get_logger

logger = get_logger(__name__)

def create_chit_chat_specialist():
    """
    Create a specialist agent for handling general conversation and user guidance.
    This agent handles greetings, casual conversation, and helps guide users 
    toward the main features of the transportation assistant.
    """
    
    def _exec(x: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle chit-chat while gently guiding users to main features.
        """
        try:
            import os
            from langchain_google_genai import ChatGoogleGenerativeAI
            
            api_key = os.getenv("GOOGLE_GENAI_API_KEY")
            if not api_key:
                raise ValueError("Missing GOOGLE_GENAI_API_KEY in environment")
                
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                temperature=0.7,
                google_api_key=api_key,
                convert_system_message_to_human=False
            )
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            return {
                "response": "Hello! How can I help you with transportation today?",
                "conversation_type": "greeting"
            }
        
        query = x.get("query", x.get("input", "")) or ""
        history = x.get("history", "")
        last_location = x.get("last_location", {})
        
        # Context about user's location if available
        location_context = ""
        if last_location and last_location.get("label"):
            location_context = f"The user is currently in {last_location['label']}."
        
        # Determine conversation type
        query_lower = query.lower()
        
        if any(greeting in query_lower for greeting in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
            conversation_type = "greeting"
            prompt_focus = "Respond warmly to their greeting and briefly mention what you can help with (weather, transit, traffic, directions)."
        elif any(question in query_lower for question in ["how are you", "how's it going", "what's up", "hru"]):
            conversation_type = "wellbeing"
            prompt_focus = "Respond positively about how you're doing, then offer to help with transportation needs."
        elif any(thanks in query_lower for thanks in ["thank you", "thanks", "appreciate"]):
            conversation_type = "gratitude"
            prompt_focus = "Acknowledge their thanks warmly and offer continued assistance."
        else:
            conversation_type = "general"
            prompt_focus = "Respond helpfully to their message and guide them toward what you can assist with."
        
        prompt = f"""You are Vaya, a warm and helpful transportation assistant. You help people with:
- Weather conditions and forecasts (any location, any time)
- Public transit information (schedules, routes, delays)
- Traffic conditions and travel times  
- Location lookup and directions

{location_context}

User said: "{query}"

{prompt_focus}

Guidelines:
- Be warm, professional, and friendly with a feminine touch
- Keep responses brief (1-2 sentences)
- Don't claim to lack access to weather/transit data - you do have access!
- Mention specific examples of what you can help with
- Use encouraging language
- If they ask about weather specifically, suggest they ask about weather for their area or any location

Respond naturally and helpfully:"""
        
        try:
            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            return {
                "response": response_text,
                "conversation_type": conversation_type,
                "suggested_actions": [
                    "Ask about weather in your area or any city",
                    "Get public transit directions", 
                    "Check traffic conditions",
                    "Find locations and addresses"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error generating chit-chat response: {e}")
            return {
                "response": "Hello! I'm here to help you with weather, transit, traffic, and directions. What would you like to know?",
                "conversation_type": conversation_type
            }
    
    return RunnableLambda(_exec)