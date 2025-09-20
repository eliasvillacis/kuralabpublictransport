"""
Base agent classes for A2A (Agent-to-Agent) architecture.

This module provides the foundation for agents that can participate in
peer-to-peer communication within the multi-agent system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from utils.contracts import WorldState
from utils.logger import get_logger
from langchain_google_genai import ChatGoogleGenerativeAI
from agents.tools.weather_tool import weather_current
from agents.tools.location_tool import geocode_place, geolocate_user, reverse_geocode
from agents.tools.conversation_tool import handle_conversation

logger = get_logger(__name__)

class BaseAgent(ABC):
    """Base class for all A2A agents."""

    def __init__(self, name: str, model_name: str = "gemini-1.5-flash", temperature: float = 0.2):
        self.name = name
        self.llm = self._initialize_llm(model_name, temperature)
        self.memory_context = {}

    def _initialize_llm(self, model_name: str, temperature: float) -> Optional[ChatGoogleGenerativeAI]:
        """Initialize LLM client."""
        try:
            import os
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                return ChatGoogleGenerativeAI(
                    model=model_name,
                    temperature=temperature,
                    google_api_key=api_key
                )
            else:
                logger.warning(f"No GEMINI_API_KEY found for agent {self.name}")
                return None
        except Exception as e:
            logger.error(f"Failed to initialize LLM for agent {self.name}: {e}")
            return None

    @abstractmethod
    def get_name(self) -> str:
        """Return the agent's name."""
        return self.name

    @abstractmethod
    def can_handle(self, world_state: WorldState) -> bool:
        """Check if agent can contribute to current state."""
        pass

    @abstractmethod
    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Process the current state and return deltaState patch."""
        pass

    def should_replan(self, world_state: WorldState) -> bool:
        """Check if replanning is needed. Default implementation."""
        # Check for errors that might require replanning
        if world_state.errors:
            return True

        # Check if current plan is incomplete or invalid
        if "plan" in world_state.context:
            plan = world_state.context["plan"]
            if not plan.get("steps"):
                return True

        return False

    def update_memory_context(self, context: Dict[str, Any]):
        """Update agent's memory context."""
        self.memory_context.update(context)

    def get_memory_context(self) -> Dict[str, Any]:
        """Get agent's current memory context."""
        return self.memory_context.copy()

class PlanningAgent(BaseAgent):
    """Agent responsible for creating and updating plans."""

    def __init__(self):
        super().__init__("planner", "gemini-1.5-flash", 0.2)
        self.planning_prompt = """
You are the Planning Agent in an A2A multi-agent system. Your role is to create and update execution plans.

Current WorldState: {world_state}

Based on the current state, determine what steps need to be taken to fulfill the user's query.
Consider:
- What information is already available
- What steps have been completed (check completed_steps list)
- What errors have occurred
- What additional steps are needed

CRITICAL: Do NOT create duplicate steps. If a step has already been completed (appears in completed_steps), do NOT include it in the new plan.

Output a JSON plan with the following structure:
{{
    "steps": [
        {{
            "id": "S1",
            "action": "Geolocate|Geocode|Weather|Transit",
            "args": {{...}},
            "reasoning": "Why this step is needed"
        }}
    ],
    "status": "planning|replanning|complete",
    "confidence": 0.0-1.0
}}

Rules:
- For location queries like "where am i", "what's my location", "where am I located", "where am I": FIRST Geolocate to get coordinates, THEN ReverseGeocode to convert coordinates to address
- For location queries without specific places: include Geolocate step first, then create Weather step using the geocoded coordinates
- For specific place names: include Geocode step for that place with the place name as the "address" parameter, then create Weather step using the geocoded coordinates
- For weather queries with multiple locations (e.g., "weather in Miami and Texas" or "weather near me, in Miami, in Texas"): create separate Geocode/Geolocate + Weather steps for EACH location mentioned
- For transit queries (e.g., "from X to Y"): include separate Geocode steps for both origin and destination locations
- Weather steps need lat/lng coordinates
- ALWAYS create a Weather step immediately after each Geocode/Geolocate step for weather queries
- ONLY include steps that have NOT been completed yet (check completed_steps array)
- If all needed steps are already completed, set status to "complete"
- Set confidence based on how well the plan addresses the query
- ALWAYS include the "address" parameter in Geocode step args, never leave it empty
- For multiple locations in weather queries, use sequential step IDs (S1, S2, S3, etc.) and create both Geocode/Geolocate and Weather steps for each location
"""

    def get_name(self) -> str:
        """Return the agent's name."""
        return self.name

    def can_handle(self, world_state: WorldState) -> bool:
        """Planning agent can always contribute when there's a query."""
        return bool(world_state.query.get("raw"))

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Generate or update execution plan."""
        if not self.llm:
            return {"deltaState": {"errors": ["Planning LLM not available"]}}

        try:
            # Build context for planning
            context = {
                "query": world_state.query.get("raw", ""),
                "current_slots": world_state.slots.model_dump(),
                "existing_plan": world_state.context.get("plan", {}),
                "completed_steps": world_state.context.get("completed_steps", []),
                "errors": world_state.errors
            }

            # Extract existing_plan for easier reference
            existing_plan = context["existing_plan"]
            completed_steps = context["completed_steps"]

            # Check for casual conversation and greetings - handle with Conversation tool
            query_text = context.get("query", "").lower().strip()
            casual_phrases = [
                "hi", "hello", "hey", "how are you", "how r u", "what's up", "sup",
                "good morning", "good afternoon", "good evening", "did you", "do you",
                "are you", "can you", "what do you", "who are you", "what are you",
                "why", "when", "where", "how", "what", "which", "who", "whose",
                "bye", "goodbye", "see you", "thanks", "thank you", "yes", "yeah",
                "yep", "sure", "okay", "ok", "alright", "fine", "tell me", "nice",
                "beautiful", "bored", "nothing", "just", "morning", "afternoon", "evening"
            ]
            is_casual = any(phrase in query_text for phrase in casual_phrases) or len(query_text.split()) <= 5
            if is_casual and not any(word in query_text for word in ["weather", "location", "where am i", "transit", "route", "directions", "from", "to", "bus", "train", "subway", "drive", "walk", "bike"]):
                # For casual conversation, create a plan with Conversation tool
                plan = {
                    "steps": [
                        {
                            "id": "S1",
                            "action": "Conversation",
                            "args": {"message": context.get("query", "")},
                            "reasoning": "Handle casual conversation and redirect to transportation assistance"
                        }
                    ],
                    "status": "planning",
                    "confidence": 0.9
                }
                return {
                    "deltaState": {
                        "context": {
                            "plan": plan,
                            "last_planning": {
                                "timestamp": str(datetime.now()),
                                "agent": self.name
                            }
                        }
                    },
                    "snippet": f"Planning complete. Generated {len(plan.get('steps', []))} steps with {plan.get('confidence', 0.0):.1f} confidence."
                }

            # Check for location queries and handle them explicitly
            is_location_query = any(phrase in query_text for phrase in [
                "where am i", "where am i?", "what's my location", "where am i located", 
                "where am i right now", "my location", "current location", "where am i at"
            ])
            is_weather_query = any(word in query_text for word in ["weather", "temperature", "forecast", "rain", "sunny", "cloudy", "hot", "cold", "weatehr"])  # Include common typos
            
            # Handle location queries regardless of completed steps
            if is_location_query:
                # Check if we need to add location-related steps
                needs_geolocate = not any(step["id"] == "S1" for step in existing_plan.get("steps", []))
                needs_reverse_geocode = not any(step["id"] == "S2" for step in existing_plan.get("steps", []))
                needs_weather = is_weather_query and not any(step["id"] == "S3" for step in existing_plan.get("steps", []))
                
                new_steps = []
                step_counter = len(existing_plan.get("steps", [])) + 1
                
                if needs_geolocate:
                    new_steps.append({
                        "id": f"S{step_counter}",
                        "action": "Geolocate",
                        "args": {},
                        "reasoning": "Get user's current coordinates for location query"
                    })
                    step_counter += 1
                    
                if needs_reverse_geocode:
                    new_steps.append({
                        "id": f"S{step_counter}",
                        "action": "ReverseGeocode", 
                        "args": {},
                        "reasoning": "Convert coordinates to human-readable address"
                    })
                    step_counter += 1
                    
                if needs_weather:
                    new_steps.append({
                        "id": f"S{step_counter}",
                        "action": "Weather",
                        "args": {"units": "IMPERIAL"},
                        "reasoning": "Get current weather for user's location"
                    })
                
                if new_steps:
                    # Add new steps to existing plan
                    updated_plan = existing_plan.copy()
                    updated_plan["steps"] = existing_plan.get("steps", []) + new_steps
                    updated_plan["status"] = "planning"
                    
                    return {
                        "deltaState": {
                            "context": {
                                "plan": updated_plan,
                                "last_planning": {
                                    "timestamp": str(datetime.now()),
                                    "agent": self.name
                                }
                            }
                        },
                        "snippet": f"Planning updated. Added {len(new_steps)} steps to existing plan."
                    }
            
            if existing_plan.get("steps"):
                # Filter out completed steps from existing plan
                pending_steps = [
                    step for step in existing_plan["steps"] 
                    if step["id"] not in completed_steps
                ]
                
                # If no pending steps, return complete status
                if not pending_steps:
                    return {
                        "deltaState": {
                            "context": {
                                "plan": {
                                    "steps": [],
                                    "status": "complete",
                                    "confidence": 1.0
                                },
                                "last_planning": {
                                    "timestamp": str(datetime.now()),
                                    "agent": self.name
                                }
                            }
                        },
                        "snippet": "All planned steps completed."
                    }
                
                # If we have pending steps, continue with the existing plan (don't replan)
                # This prevents the LLM from regenerating duplicate steps
                return {
                    "deltaState": {
                        "context": {
                            "plan": {
                                "steps": pending_steps,
                                "status": "in_progress", 
                                "confidence": existing_plan.get("confidence", 0.8)
                            },
                            "last_planning": {
                                "timestamp": str(datetime.now()),
                                "agent": self.name
                            }
                        }
                    },
                    "snippet": f"Continuing with {len(pending_steps)} remaining steps."
                }
                
                # Update context with filtered steps
                context["existing_plan"] = {**existing_plan, "steps": pending_steps}

            # Generate plan using LLM
            messages = [
                {"role": "system", "content": self.planning_prompt},
                {"role": "user", "content": f"Create/update plan for: {context}"}
            ]

            response = self.llm.invoke(messages)
            plan_text = response.content.strip()

            # Extract JSON from response
            import re, json
            json_match = re.search(r'\{.*\}', plan_text, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group(0))
            else:
                plan = {"steps": [], "status": "error", "confidence": 0.0}

            # Return deltaState with plan
            return {
                "deltaState": {
                    "context": {
                        "plan": plan,
                        "last_planning": {
                            "timestamp": str(datetime.now()),
                            "agent": self.name
                        }
                    }
                },
                "snippet": f"Planning complete. Generated {len(plan.get('steps', []))} steps with {plan.get('confidence', 0.0):.1f} confidence."
            }

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return {
                "deltaState": {
                    "errors": [f"Planning error: {str(e)}"],
                    "context": {
                        "plan": {"steps": [], "status": "error", "confidence": 0.0}
                    }
                }
            }

class ExecutionAgent(BaseAgent):
    """Agent responsible for executing planned steps."""

    def __init__(self):
        super().__init__("executor", "gemini-1.5-pro", 0.2)
        self.execution_prompt = """
You are the Execution Agent in an A2A multi-agent system. Your role is to execute individual steps from the plan.

Current Step: {current_step}
World State: {world_state}

Execute this step and return the results. Use available tools to gather information.

Output format:
{{
    "deltaState": {{
        "context": {{
            "execution_result": {{...}},
            "completed_steps": ["step_id"]
        }},
        "slots": {{...}}  // Update slots if location data found
    }},
    "snippet": "Brief description of what was executed and found"
}}

Available actions: Geolocate, Geocode, Weather, Transit
"""

    def get_name(self) -> str:
        """Return the agent's name."""
        return self.name

    def can_handle(self, world_state: WorldState) -> bool:
        """Execution agent can handle when there's a plan with pending steps."""
        plan = world_state.context.get("plan", {})
        steps = plan.get("steps", [])
        completed = world_state.context.get("completed_steps", [])

        # Check if there are uncompleted steps
        for step in steps:
            if step["id"] not in completed:
                return True
        return False

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Execute the next pending step."""
        if not self.llm:
            return {"deltaState": {"errors": ["Execution LLM not available"]}}

        try:
            # Find next pending step
            plan = world_state.context.get("plan", {})
            steps = plan.get("steps", [])
            completed = world_state.context.get("completed_steps", [])

            current_step = None
            for step in steps:
                if step["id"] not in completed:
                    current_step = step
                    break

            if not current_step:
                return {
                    "deltaState": {
                        "context": {
                            "execution_status": "no_pending_steps"
                        }
                    }
                }

            # Execute step based on action
            result = self._execute_step(current_step, world_state)

            # Mark step as completed
            new_completed = completed + [current_step["id"]]

            # Prepare deltaState updates
            delta_state = {
                "context": {
                    "execution_result": result,
                    "completed_steps": new_completed,
                    "last_execution": {
                        "step_id": current_step["id"],
                        "timestamp": str(datetime.now()),
                        "agent": self.name
                    }
                }
            }
            
            # If this is a weather step, store the result separately for multi-location synthesis
            if current_step.get("action") == "Weather" and result.get("status") == "success":
                # Get existing weather results or create empty dict
                existing_weather_results = world_state.context.get("weather_results", {})
                
                # Use the step ID as the key to store weather data for this location
                step_id = current_step["id"]
                existing_weather_results[step_id] = {
                    "location": {
                        "lat": result.get("raw", {}).get("context", {}).get("lastWeather", {}).get("lat"),
                        "lng": result.get("raw", {}).get("context", {}).get("lastWeather", {}).get("lng")
                    },
                    "weather": result.get("weather", {}),
                    "timestamp": str(datetime.now())
                }
                
                delta_state["context"]["weather_results"] = existing_weather_results

            # Update slots and context based on execution result
            if result.get("status") == "success":
                if current_step["action"] in ["Geolocate", "Geocode"]:
                    # Store geocoded location in context for weather steps to reference
                    location = result.get("location", {})
                    if location:
                        # Initialize geocoded_locations if it doesn't exist
                        if "geocoded_locations" not in delta_state["context"]:
                            delta_state["context"]["geocoded_locations"] = {}
                        
                        # Store location by step ID for weather steps to reference
                        location_key = f"step_{current_step['id']}"
                        delta_state["context"]["geocoded_locations"][location_key] = {
                            "lat": location.get("lat"),
                            "lng": location.get("lng"),
                            "name": location.get("name", "Unknown Location"),
                            "address": current_step.get("args", {}).get("address", "current location")
                        }
                        
                        # Also update origin slot for backward compatibility
                        delta_state["slots"] = {
                            "origin": {
                                "lat": location.get("lat"),
                                "lng": location.get("lng"),
                                "name": location.get("name", "Unknown Location")
                            }
                        }
                elif current_step["action"] == "ReverseGeocode":
                    # Store reverse geocoding result in context
                    address = result.get("address", "")
                    address_components = result.get("address_components", {})
                    if address:
                        delta_state["context"]["reverse_geocode_result"] = {
                            "formatted_address": address,
                            "address_components": address_components,
                            "coordinates": {
                                "lat": current_step.get("args", {}).get("lat"),
                                "lng": current_step.get("args", {}).get("lng")
                            }
                        }
                elif current_step["action"] == "Weather":
                    # Update context with weather data
                    weather_data = result.get("weather", {})
                    if weather_data:
                        delta_state["context"]["lastWeather"] = weather_data
                elif current_step["action"] == "Conversation":
                    # Store conversation response in context
                    conversation_data = result.get("raw", {}).get("context", {}).get("conversation_response", {})
                    if conversation_data:
                        delta_state["context"]["conversation_response"] = conversation_data

            logger.info(f"ExecutionAgent returning deltaState: {delta_state}")
            return {
                "deltaState": delta_state,
                "snippet": f"Executed step {current_step['id']}: {result.get('summary', 'Complete')}"
            }

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return {
                "deltaState": {
                    "errors": [f"Execution error: {str(e)}"]
                }
            }

    def _execute_step(self, step: Dict[str, Any], world_state: WorldState) -> Dict[str, Any]:
        """Execute a specific step based on its action."""
        action = step.get("action", "")
        args = step.get("args", {})

        if action == "Geolocate":
            return self._execute_geolocate()
        elif action == "Geocode":
            return self._execute_geocode(args.get("address", ""))
        elif action == "ReverseGeocode":
            return self._execute_reverse_geocode(args.get("lat"), args.get("lng"), world_state)
        elif action == "Weather":
            return self._execute_weather(args, world_state)
        elif action == "Conversation":
            return self._execute_conversation(args.get("message", ""))
        else:
            return {"summary": f"Unknown action: {action}", "status": "error"}

    def _execute_geolocate(self) -> Dict[str, Any]:
        """Execute geolocation to find user's current location."""
        try:
            result = geolocate_user.invoke({})
            return {
                "summary": "User location determined",
                "location": result.get("slots", {}).get("origin", {}),
                "status": "success",
                "raw": result
            }
        except Exception as e:
            return {
                "summary": f"Geolocation failed: {str(e)}",
                "status": "error",
                "error": str(e)
            }

    def _execute_geocode(self, address: str) -> Dict[str, Any]:
        """Execute geocoding for a specific address."""
        try:
            result = geocode_place.invoke({"address": address})
            return {
                "summary": f"Geocoded address: {address}",
                "location": result.get("slots", {}).get("origin", {}),
                "status": "success",
                "raw": result
            }
        except Exception as e:
            return {
                "summary": f"Geocoding failed for {address}: {str(e)}",
                "status": "error",
                "error": str(e)
            }

    def _execute_reverse_geocode(self, lat: float = None, lng: float = None, world_state: WorldState = None) -> Dict[str, Any]:
        """Execute reverse geocoding to convert coordinates to human-readable address."""
        # If coordinates not provided in args, look for them in geocoded locations or origin slot
        if not lat or not lng:
            if world_state:
                # First try geocoded locations (from recent Geolocate step)
                geocoded_locations = world_state.context.get("geocoded_locations", {})
                if geocoded_locations:
                    # Get the most recent geocoding step
                    location_keys = list(geocoded_locations.keys())
                    if location_keys:
                        latest_location = geocoded_locations[location_keys[-1]]
                        lat = latest_location.get("lat")
                        lng = latest_location.get("lng")
                
                # Fallback to origin slot
                if not lat or not lng:
                    lat = world_state.slots.origin.get("lat")
                    lng = world_state.slots.origin.get("lng")

        if not lat or not lng:
            return {"summary": "Missing coordinates for reverse geocoding", "status": "error"}

        try:
            result = reverse_geocode.invoke({"lat": lat, "lng": lng})
            reverse_data = result.get("context", {}).get("reverse_geocode_result", {})
            return {
                "summary": f"Reverse geocoded coordinates: {lat}, {lng}",
                "address": reverse_data.get("formatted_address", "Unknown address"),
                "address_components": reverse_data.get("address_components", {}),
                "status": "success",
                "raw": result
            }
        except Exception as e:
            return {
                "summary": f"Reverse geocoding failed for {lat}, {lng}: {str(e)}",
                "status": "error",
                "error": str(e)
            }

    def _execute_weather(self, args: Dict[str, Any], world_state: WorldState) -> Dict[str, Any]:
        """Execute weather lookup."""
        lat = args.get("lat")
        lng = args.get("lng")
        
        # If coordinates not provided in args, look for them in geocoded locations
        if not lat or not lng:
            geocoded_locations = world_state.context.get("geocoded_locations", {})
            
            # For weather steps, try to find the most appropriate geocoded location
            # This is a heuristic: use the most recently geocoded location
            if geocoded_locations:
                # Get the most recent geocoding step
                location_keys = list(geocoded_locations.keys())
                if location_keys:
                    latest_location = geocoded_locations[location_keys[-1]]
                    lat = latest_location.get("lat")
                    lng = latest_location.get("lng")

        # Fallback to origin slot
        if not lat or not lng:
            lat = world_state.slots.origin.get("lat")
            lng = world_state.slots.origin.get("lng")

        if not lat or not lng:
            return {"summary": "Missing coordinates for weather lookup", "status": "error"}

        try:
            result = weather_current.invoke({"lat": lat, "lng": lng, "units": args.get("units", "IMPERIAL")})
            weather_data = result.get("context", {}).get("lastWeather", {})
            return {
                "summary": f"Weather data retrieved for {lat}, {lng}",
                "weather": {
                    "temperature": weather_data.get("temp"),
                    "conditions": weather_data.get("summary", ""),
                    "humidity": weather_data.get("humidity"),
                    "wind_speed": weather_data.get("wind_speed"),
                    "feels_like": weather_data.get("feels_like")
                },
                "status": "success",
                "raw": result
            }
        except Exception as e:
            return {
                "summary": f"Weather lookup failed: {str(e)}",
                "status": "error",
                "error": str(e)
            }

    def _execute_conversation(self, message: str) -> Dict[str, Any]:
        """Execute conversation handling."""
        try:
            result = handle_conversation.invoke({"message": message})
            conversation_data = result.get("context", {}).get("conversation_response", {})
            
            return {
                "summary": f"Handled conversation: {conversation_data.get('response_type', 'general')}",
                "response": conversation_data.get("response_text", ""),
                "status": "success",
                "raw": result
            }
        except Exception as e:
            return {
                "summary": f"Conversation handling failed: {str(e)}",
                "status": "error",
                "error": str(e)
            }

class SynthesisAgent(BaseAgent):
    """Agent responsible for synthesizing final responses."""

    def __init__(self):
        super().__init__("synthesizer", "gemini-1.5-flash", 0.2)  # Changed from pro to flash for cost savings
        self.synthesis_prompt = """
You are the Synthesis Agent in an A2A multi-agent system. Your role is to create natural, user-friendly responses from collected data.

World State: {world_state}

Based on all the collected information, create a comprehensive response to the user's original query.
Consider:
- Weather information in context.lastWeather
- Location data in slots.origin/destination
- Reverse geocoding results in context.reverse_geocode_result
- Location accuracy information in context.accuracy and context.accuracy_note
- Any errors that occurred
- Completed execution results

For location queries like "where am i", ALWAYS use the reverse geocoding result (context.reverse_geocode_result.formatted_address) to provide a human-readable address. NEVER display raw coordinates like "40.6847488, -73.8295808" to users - always convert them to readable addresses first.

For weather information:
- Only mention "feels like" temperature if it's different from the actual temperature
- Format temperatures as "77.1°F" (keep natural precision)
- Do NOT round location accuracy values - keep them as precise as possible

If location accuracy information is available AND the user asked about location, mention it to help users understand the precision of the location data (e.g., "This location is based on IP geolocation with approximately 1.1 miles accuracy").

For transit queries, if you have geocoded locations but no transit directions, explain that transit planning is not yet available but you can provide location information.

Output a single, natural-language response suitable for a user. Do not output JSON, just the response text.
"""

    def get_name(self) -> str:
        """Return the agent's name."""
        return self.name

    def can_handle(self, world_state: WorldState) -> bool:
        """Synthesis agent can handle when execution is complete or useful data is available."""
        plan = world_state.context.get("plan", {})
        completed_steps = world_state.context.get("completed_steps", [])
        total_steps = len(plan.get("steps", []))

        # Can synthesize if all steps completed OR we have weather data for weather queries
        has_completed_all_steps = len(completed_steps) >= total_steps and total_steps > 0
        has_empty_plan = total_steps == 0  # Empty plan indicates casual conversation
        has_weather_data = "lastWeather" in world_state.context
        has_location_data = bool(world_state.slots.origin or world_state.slots.destination)
        has_errors = bool(world_state.errors)

        # For weather queries, only synthesize when we have weather data
        query = world_state.query.get("raw", "").lower()
        is_weather_query = any(word in query for word in ["weather", "temperature", "forecast", "rain", "sunny"])
        is_transit_query = any(word in query for word in ["from", "to", "get to", "directions", "transit", "travel"])
        is_location_query = any(word in query for word in ["where", "location", "address", "here", "my location"])

        if is_weather_query:
            # For multi-location weather queries, check if we have weather for all planned locations
            plan = world_state.context.get("plan", {})
            steps = plan.get("steps", [])
            weather_steps = [step for step in steps if step.get("action") == "Weather"]
            completed_weather_steps = [step for step in weather_steps if step["id"] in completed_steps]
            
            # If we have multiple weather steps planned, wait for all of them
            if len(weather_steps) > 1:
                return len(completed_weather_steps) >= len(weather_steps) and not has_errors
            else:
                # Single location weather query - synthesize when we have weather data
                return has_weather_data and not has_errors
        elif is_transit_query:
            # For transit queries, synthesize when we have geocoded locations (even without transit tool)
            return has_location_data and not has_errors
        elif is_location_query:
            # For location queries, wait for ALL steps to complete (including reverse geocoding)
            return has_completed_all_steps and not has_errors
        else:
            return has_completed_all_steps or has_empty_plan or (has_weather_data and not has_errors)

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Synthesize final response from world state."""
        if not self.llm:
            return {"deltaState": {"errors": ["Synthesis LLM not available"]}}

        try:
            # Check for conversation response first
            conversation_response = world_state.context.get("conversation_response", {})
            if conversation_response.get("response_text"):
                return {
                    "deltaState": {
                        "context": {
                            "final_response": conversation_response["response_text"],
                            "synthesis_timestamp": str(datetime.now()),
                            "agent": self.name
                        }
                    },
                    "snippet": "Conversation response synthesized"
                }

            # Check if this is a multi-location weather query (more than one geocoded location)
            geocoded_locations = world_state.context.get("geocoded_locations", {})
            query = world_state.query.get("raw", "").lower()
            is_weather_query = any(word in query for word in ["weather", "temperature", "forecast", "rain", "sunny"])
            
            # Only use multi-location synthesis if we have multiple geocoded locations
            if is_weather_query and len(geocoded_locations) > 1:
                # Handle multi-location weather synthesis
                return self._synthesize_multi_location_weather(world_state, geocoded_locations)
            
            # Build synthesis context for single location or non-weather queries
            query = world_state.query.get("raw", "").lower()
            is_location_query = any(word in query for word in ["where", "location", "address", "here", "my location"])
            is_weather_query = any(word in query for word in ["weather", "temperature", "forecast", "rain", "sunny"])
            
            context = {
                "query": world_state.query.get("raw", ""),
                "weather": world_state.context.get("lastWeather", {}),
                "origin": world_state.slots.origin,
                "destination": world_state.slots.destination,
                "reverse_geocode": world_state.context.get("reverse_geocode_result", {}),
                "errors": world_state.errors,
                "execution_results": world_state.context.get("execution_result", {})
            }
            
            # Only include accuracy information if user asked about location
            if is_location_query:
                context["accuracy"] = world_state.context.get("accuracy", None)
                context["accuracy_note"] = world_state.context.get("accuracy_note", "")
            # For weather-only queries, ensure no accuracy information is included
            elif is_weather_query:
                # Remove any accuracy info that might be in execution_results
                if "execution_results" in context and isinstance(context["execution_results"], dict):
                    execution_results = context["execution_results"].copy()
                    if "raw" in execution_results and isinstance(execution_results["raw"], dict):
                        raw_data = execution_results["raw"].copy()
                        if "context" in raw_data and isinstance(raw_data["context"], dict):
                            raw_context = raw_data["context"].copy()
                            # Remove accuracy keys
                            for key in ["accuracy", "accuracy_note"]:
                                raw_context.pop(key, None)
                            raw_data["context"] = raw_context
                        execution_results["raw"] = raw_data
                    context["execution_results"] = execution_results

            # For weather-only queries, create a filtered world_state that doesn't include accuracy info
            synthesis_world_state = world_state
            if not is_location_query and is_weather_query:
                # Create a filtered copy of world_state without accuracy information
                filtered_context = world_state.context.copy()
                # Remove accuracy-related keys from context
                accuracy_keys = ["accuracy", "accuracy_note"]
                for key in accuracy_keys:
                    filtered_context.pop(key, None)
                
                # Create a new world_state-like dict with filtered context
                synthesis_world_state = {
                    "query": world_state.query,
                    "slots": world_state.slots,
                    "context": filtered_context,
                    "errors": world_state.errors
                }

            # Generate response using LLM
            messages = [
                {"role": "system", "content": self.synthesis_prompt.format(world_state=synthesis_world_state)},
                {"role": "user", "content": f"Synthesize response for: {context}"}
            ]

            response = self.llm.invoke(messages)
            synthesized_text = response.content.strip()

            return {
                "deltaState": {
                    "context": {
                        "final_response": synthesized_text,
                        "synthesis_timestamp": str(datetime.now()),
                        "agent": self.name
                    }
                },
                "snippet": "Final response synthesized"
            }

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            fallback_response = self._generate_fallback_response(world_state)
            return {
                "deltaState": {
                    "context": {
                        "final_response": fallback_response
                    },
                    "errors": [f"Synthesis error: {str(e)}"]
                }
            }

    def _synthesize_multi_location_weather(self, world_state: WorldState, geocoded_locations: Dict) -> Dict[str, Any]:
        """Synthesize response for multi-location weather queries."""
        try:
            weather_parts = []
            weather_results = world_state.context.get("weather_results", {})
            
            # Process each geocoded location
            for step_key, location_data in geocoded_locations.items():
                location_name = location_data.get("name", location_data.get("address", "Unknown location"))
                
                # Find corresponding weather data
                # Weather steps are created immediately after geocode steps
                # So geocode S1 -> weather S2, geocode S3 -> weather S4, etc.
                weather_data = None
                if step_key.startswith("step_"):
                    # Extract the step number and add 1 to get the weather step
                    try:
                        step_num = int(step_key.replace("step_S", ""))
                        weather_step_key = f"S{step_num + 1}"
                        if weather_step_key in weather_results:
                            weather_data = weather_results[weather_step_key].get("weather")
                    except (ValueError, KeyError):
                        pass
                
                if weather_data:
                    temp = weather_data.get("temperature")
                    conditions = weather_data.get("conditions")
                    humidity = weather_data.get("humidity")
                    wind_speed = weather_data.get("wind_speed")
                    
                    if temp is not None:
                        weather_desc = f"{location_name}: {temp}°F, {conditions}"
                        if humidity is not None:
                            weather_desc += f", {humidity}% humidity"
                        if wind_speed is not None:
                            weather_desc += f", {wind_speed} mph wind"
                        weather_parts.append(weather_desc)
                    else:
                        weather_parts.append(f"{location_name}: Weather data unavailable")
                else:
                    weather_parts.append(f"{location_name}: Weather data unavailable")
            
            # Create final response
            if weather_parts:
                response_text = "Here's the weather for the locations you asked about:\n" + "\n".join(f"• {part}" for part in weather_parts)
            else:
                response_text = "I'm sorry, I couldn't retrieve weather information for the requested locations."
            
            return {
                "deltaState": {
                    "context": {
                        "final_response": response_text,
                        "synthesis_timestamp": str(datetime.now()),
                        "agent": self.name
                    }
                },
                "snippet": "Multi-location weather response synthesized"
            }
            
        except Exception as e:
            logger.error(f"Multi-location weather synthesis failed: {e}")
            return {
                "deltaState": {
                    "context": {
                        "final_response": "I'm sorry, I encountered an error while processing the weather information for multiple locations."
                    },
                    "errors": [f"Multi-location synthesis error: {str(e)}"]
                }
            }

    def _generate_fallback_response(self, world_state: WorldState) -> str:
        """Generate fallback response when synthesis fails."""
        query = world_state.query.get("raw", "").lower().strip()

        # Handle casual conversation and greetings
        casual_phrases = ["hi", "hello", "hey", "how are you", "how r u", "what's up", "sup", "good morning", "good afternoon", "good evening"]
        if any(phrase in query for phrase in casual_phrases) or len(query.split()) <= 3:
            return "Hello! I'm your transportation assistant. I can help you with weather conditions, location services, and navigation planning. What transportation-related question can I help you with today?"

        # Check for reverse geocoding results first
        reverse_geocode = world_state.context.get("reverse_geocode_result", {})
        if reverse_geocode and any(word in query for word in ["where", "location", "address", "here"]):
            formatted_address = reverse_geocode.get("formatted_address")
            if formatted_address:
                return f"You are currently located at: {formatted_address}"

        if "weather" in query:
            weather = world_state.context.get("lastWeather", {})
            if weather:
                temp = weather.get("temp", "unknown")
                return f"The temperature is {temp}°F."
            return "I couldn't retrieve weather information at this time."

        if world_state.errors:
            return f"I encountered some issues: {', '.join(world_state.errors)}"

        return "I'm sorry, I couldn't process your request effectively."