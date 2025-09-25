
# ===============================
# Vaya Public Transport Assistant - Agent Architecture
# ===============================
#
# This file implements the core agent logic for the Vaya public transport assistant.
# The system uses a two-agent architecture:
#
#   1. PlanningAgent (LLM):
#      - Receives the user query and current world state (memory, slots, context).
#      - Uses an LLM to generate a structured plan (JSON) describing which tools to call and in what order.
#      - Handles slot filling, pronoun resolution, and ambiguous queries using LLM reasoning and prompt engineering.
#      - Returns a plan as a list of steps, each with an action/tool and arguments.
#
#   2. ExecutionAgent (LLM + tools):
#      - Receives the plan and executes each step, calling the appropriate tool/module.
#      - Handles slot reference resolution, tool output merging, and error handling.
#      - Uses LLM reasoning to adaptively execute plans, patch tool arguments, and generate the final user-facing response.
#      - Ensures slots are updated and persisted for future queries (e.g., origin/destination).
#
# The agents communicate via a shared WorldState (blackboard), which tracks slots (origin, destination, etc.),
# context (recent tool outputs), and the current plan. Each agent produces a deltaState patch describing its changes.
#
# Key Concepts:
# - Tools: Modular functions for geolocation, geocoding, directions, weather, places, and conversation.
# - Slot System: Named slots (origin, destination, etc.) are used to pass locations and context between tools and agents.
# - LLM Reasoning: Both agents use LLMs for plan generation, tool selection, and response synthesis, with prompt engineering to guide behavior.
# - Heuristic Guards: The executor includes logic to ensure correct slot usage, avoid stale data, and patch plans for ambiguous or underspecified queries.
#
# See section comments below for details on each class and major function.



from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import os
from datetime import datetime
import json
import re
from utils.contracts import WorldState
from utils.logger import get_logger
from utils.llm_logger import log_llm_usage
from utils.state import deepMerge, compact_world_state
from langchain_google_genai import ChatGoogleGenerativeAI

# Tool imports
from .tools.weather_tool import weather_current
from .tools.location_tool import geocode_place, geolocate_user, reverse_geocode
from .tools.conversation_tool import handle_conversation
from .tools.directions_tool import directions
from .tools.places_tool import places_search as PlacesSearch, place_details as PlaceDetails

logger = get_logger(__name__)

# Tool registry and aliases for convenient resolution
TOOL_REGISTRY = {
    "Geolocate": geolocate_user,
    "Geocode": geocode_place,
    "ReverseGeocode": reverse_geocode,
    "Weather": weather_current,
    "Directions": directions,
    "PlacesSearch": PlacesSearch,
    "PlaceDetails": PlaceDetails,
    "Conversation": handle_conversation,
}

TOOL_ALIASES = {
    "Places": "PlacesSearch",
    "POISearch": "PlacesSearch",
    "FindNearestPOI": "PlacesSearch",
}

def resolve_tool_name(name: str) -> str:
    return TOOL_ALIASES.get((name or "").strip(), (name or "").strip())


class BaseAgent(ABC):
    # -----------------------------
    # BaseAgent: Abstract base class for all agents
    # -----------------------------
    """Abstract base class for all agents in the system."""

    def __init__(self, name: str, model_name: str = "gemini-1.5-flash", temperature: float = 0.2):
        self.name = name
        self.llm = self._initialize_llm(model_name, temperature)
    # LLM is optional; fallback logic is used if unavailable

    def _initialize_llm(self, model_name: str, temperature: float) -> Optional[ChatGoogleGenerativeAI]:
        """
        Initialize LLM client if API key is available.
        """
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

    def _llm_json_request(self, prompt: str, attempts: int = 3, sleep_between: float = 0.5) -> Optional[dict]:
        """
        Ask the LLM to return JSON only. Retry if the response isn't valid JSON. Returns parsed dict or None.
        """
        if not self.llm:
            return None

        last_resp_text = None
        for attempt in range(1, attempts + 1):
            try:
                resp = self.llm.invoke(prompt)
                # Try to log LLM usage if available (guarded)
                try:
                    usage = getattr(resp, 'usage_metadata', None) or getattr(resp, 'usage', None) or {}
                    model_name = getattr(self.llm, 'model', None) or getattr(self.llm, 'model_name', None) or 'unknown'
                    if usage:
                        try:
                            log_llm_usage(agent=self.name, model=model_name, usage={
                                'input_tokens': usage.get('input_tokens', usage.get('input', 0)),
                                'output_tokens': usage.get('output_tokens', usage.get('output', 0)),
                                'total_tokens': usage.get('total_tokens', usage.get('total', usage.get('input', 0) + usage.get('output', 0)))
                            })
                        except Exception:
                            logger.debug('Failed to log LLM usage from BaseAgent._llm_json_request')
                except Exception:
                    pass

                text = str(getattr(resp, 'content', resp)).strip()
                last_resp_text = text
                # extract the first {...} block
                m = re.search(r"\{.*\}", text, re.DOTALL)
                candidate = m.group(0) if m else text
                try:
                    parsed = json.loads(candidate)
                    return parsed
                except Exception as e:
                    logger.warning(f"BaseAgent: LLM JSON parse failed on attempt {attempt}: {e}")
                    prompt = (
                        "The previous response was not valid JSON. Reply ONLY with valid JSON and nothing else. "
                        "Here was the previous response:\n" + text + "\nPlease return only JSON now."
                    )
            except Exception as e:
                logger.warning(f"BaseAgent: LLM invoke failed on attempt {attempt}: {e}")
            try:
                import time
                time.sleep(sleep_between)
            except Exception:
                pass

        logger.debug(f"BaseAgent: LLM final non-JSON response after {attempts} attempts: {last_resp_text}")
        return None

    @abstractmethod
    def get_name(self) -> str:
        """Return the agent's name."""
        return self.name

    @abstractmethod
    def can_handle(self, world_state: WorldState) -> bool:
        """Check if agent can contribute to current state."""
        raise NotImplementedError

    @abstractmethod
    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Process the current state and return deltaState patch."""
        raise NotImplementedError


class PlanningAgent(BaseAgent):
    # -----------------------------
    # PlanningAgent: Uses LLM to generate structured tool plans from user queries
    # -----------------------------
    """LLM-powered agent that creates structured execution plans for user queries."""

    def __init__(self):
        # Use a low-temperature, deterministic model for planning
        super().__init__("planner", "gemini-1.5-flash", 0.2)
        self.planning_prompt = (
            """
You are the Planning Agent. Analyze the user query and create a structured execution plan as a JSON object.

Available actions: Geolocate, Geocode, ReverseGeocode, Weather, Directions, Conversation.
Return ONLY a valid JSON object with a 'steps' list, 'status', and 'confidence'.
See examples below for format. Use memory to resolve pronouns if present.

IMPORTANT: If the user asks 'where am I', 'what is my location', or similar, ALWAYS return a plan with these steps:
    1. Geolocate
    2. ReverseGeocode

Example:
User: "where am I?"
Plan:
{
    "steps": [
        {"action": "Geolocate", "args": {}},
        {"action": "ReverseGeocode", "args": {}}
    ],
    "status": "incomplete",
    "confidence": 1.0
}

IMPORTANT: If the user asks for weather 'near me', 'here', or similar, always include a Geolocate step before Weather, regardless of any previous location slots.

IMPORTANT: If the user asks about a place/address that could refer to multiple locations (e.g., 'Main Street'), and the user's current location (from slots.origin or user profile) is known, prefer the location in the same state or area as the user.

Recent memory: {memory}
Query: {query}
Return only the JSON, no other text.
"""
                )

    def get_name(self) -> str:
        """Return the agent's name."""
        return self.name

    def can_handle(self, world_state: WorldState) -> bool:
        """Returns True if there is a user query to plan for."""
        return bool(world_state.query.get("raw"))

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Generate execution plan for user query using LLM only. No heuristic fallback."""
        query = world_state.query.get("raw", "")
        if not query or query.strip() == "":
            return {"deltaState": {"context": {"plan": {"steps": [], "status": "complete"}}}}
        if not self.llm:
            logger.error("PlanningAgent: No LLM client available; cannot generate plan.")
            return {"deltaState": {"context": {"plan": {"steps": [], "status": "failed", "error": "No LLM client available"}}}}

        try:
            compact = compact_world_state(world_state) or {}
            memory_json = json.dumps(compact, indent=2)
        except Exception:
            memory_json = "{}"

        full_prompt = self.planning_prompt.replace("{query}", query).replace("{memory}", memory_json)
        parsed = self._llm_json_request(full_prompt, attempts=3)
        if parsed:
            plan = parsed
            logger.info(f"PlanningAgent: LLM generated plan with {len(plan.get('steps', []))} steps")
            return {
                "deltaState": {
                    "context": {
                        "plan": plan,
                        "last_planning": {
                            "timestamp": str(datetime.utcnow()),
                            "agent": self.name,
                            "method": "llm"
                        }
                    }
                },
                "snippet": f"Generated plan with {len(plan.get('steps', []))} steps"
            }
        else:
            logger.error("PlanningAgent: LLM failed to produce valid JSON plan after retries; no fallback.")
            return {"deltaState": {"context": {"plan": {"steps": [], "status": "failed", "error": "LLM failed to generate plan"}}}}



class ExecutionAgent(BaseAgent):
    # -----------------------------
    # ExecutionAgent: Executes tool plans, manages slots, and generates final responses
    # -----------------------------
    """LLM-powered agent that executes plan steps and generates the final response."""

    def __init__(self):
        super().__init__("executor", "gemini-1.5-flash", 0.2)

    # Shared small helpers used across execution flows
    def _merge_tool_output(self, results: dict, tool_name: str, out: dict):
        """Merge a tool's output into the results dict (slots, context, and other keys)."""
        if not isinstance(out, dict):
            return
        # slots
        if out.get('slots'):
            try:
                for k, v in out.get('slots', {}).items():
                    results.setdefault('slots', {})[k] = v
            except Exception:
                pass
        # context
        if out.get('context'):
            try:
                for k, v in out.get('context', {}).items():
                    results.setdefault('context', {})[k] = v
            except Exception:
                pass
        # other top-level keys attach under context with tool prefix
        for k, v in out.items():
            if k not in ('slots', 'context'):
                results.setdefault('context', {})[f"{tool_name}_{k}"] = v

    def _summarize_weather(self, results: dict) -> dict:
        """Extract lastWeather_* entries into a summary for the final response."""
        try:
            weather_entries = {}
            for k, v in list(results.get('context', {}).items()):
                if isinstance(k, str) and k.startswith('lastWeather_') and isinstance(v, dict):
                    label = k.split('lastWeather_', 1)[1]
                    temp = v.get('temp')
                    summary = v.get('summary')
                    weather_entries[label] = {
                        'temp': temp,
                        'summary': summary,
                        'lat': v.get('lat'),
                        'lng': v.get('lng')
                    }
            if weather_entries:
                results.setdefault('context', {})['final_weather_summary'] = weather_entries
        except Exception:
            pass
        return results

    def get_name(self) -> str:
        """Return the agent's name."""
        return self.name

    def can_handle(self, world_state: WorldState) -> bool:
        """Returns True if there is a plan with steps to execute."""
        plan = world_state.context.get("plan", {})
        steps = plan.get("steps", [])
        return len(steps) > 0

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Execute the plan steps using LLM reasoning or fallback logic."""
        query = world_state.query.get("raw", "")

        if not query:
            return {"deltaState": {"context": {"execution_result": {"status": "no_query"}}}}

        # Get the plan from PlanningAgent
        plan = world_state.context.get("plan", {})
        steps = plan.get("steps", [])

        if not steps:
            logger.warning("ExecutionAgent: No plan steps to execute")
            return {"deltaState": {"context": {"execution_result": {"status": "no_plan"}}}}

        # Use LLM to intelligently execute the plan steps
        if self.llm:
            try:
                logger.info("ExecutionAgent: Using LLM for intelligent plan execution")
                execution_results = self._execute_plan_with_llm_reasoning(steps, world_state, query)
            except Exception as e:
                logger.warning(f"ExecutionAgent: LLM execution failed: {e}")
                execution_results = self._execute_plan_steps_fallback(steps, world_state)
        else:
            logger.info("ExecutionAgent: No LLM available, using fallback execution")
            execution_results = self._execute_plan_steps_fallback(steps, world_state)

        # Ensure slot write-back: if directions or tools returned origin/destination in context,
        # mirror them into execution_results['slots'] so they are persisted by coordinator._save_memory()
        try:
            ctx = execution_results.get('context', {}) or {}
            slots = execution_results.setdefault('slots', {}) or {}
            # directions may be under 'directions' or contain 'transit_directions'
            dir_ctx = ctx.get('directions') or ctx.get('transit_directions') or {}
            if isinstance(dir_ctx, dict):
                for key in ('origin', 'destination'):
                    candidate = dir_ctx.get(key)
                    if isinstance(candidate, dict):
                        have_slot = (slots.get(key) and (slots.get(key).get('name') or slots.get(key).get('lat')))
                        if not have_slot:
                            slots[key] = {
                                'name': candidate.get('name'),
                                'lat': candidate.get('lat'),
                                'lng': candidate.get('lng')
                            }
            execution_results['slots'] = slots
        except Exception:
            pass

        # Generate final response using LLM
        if self.llm:
            try:
                logger.info("ExecutionAgent: Generating final response")
                context_summary = self._prepare_context_summary(world_state, execution_results)

                # Determine what high-level actions the Planner requested so the LLM does not invent
                # unrelated content. If the plan did not request Directions, explicitly forbid giving
                # route suggestions.
                try:
                    plan = world_state.context.get('plan', {}) or {}
                    plan_actions = [s.get('action') for s in plan.get('steps', []) if s.get('action')]
                except Exception:
                    plan_actions = []

                # If we executed directions/transit, provide the full directions block to the LLM
                directions_block = None
                try:
                    dir_ctx = execution_results.get('context', {}) or {}
                    directions_block = dir_ctx.get('directions') or dir_ctx.get('transit_directions')
                except Exception:
                    directions_block = None

                # Build an explicit prompt that forces detailed numbered steps when directions are present
                response_prompt = f"""
You are the Execution Agent for a transportation assistant. Based ONLY on the executed tool results below, provide a concise, factual final response.

User query: {query}
Plan actions: {plan_actions}
Tool execution results: {context_summary}

"""

                # If directions data is available, append it and instruct the LLM to produce step-by-step directions
                if directions_block:
                    try:
                        directions_json = json.dumps(directions_block, indent=2)
                    except Exception:
                        directions_json = str(directions_block)
                    response_prompt += f"\nDirections details (JSON):\n{directions_json}\n"
                    response_prompt += (
                        "IMPORTANT: The user requested directions. Provide a clear, numbered, step-by-step set of instructions (1., 2., 3., ...). "
                        "Include walking steps and transit legs. For transit legs include vehicle type, line name, departure stop, arrival stop, and departure/arrival times when available. "
                        "Start with a one-line summary of total time and distance, then list the numbered steps. Do NOT invent missing times or stops—use only the provided data."
                    )

                # Global safety instructions
                response_prompt += f"\n\nIMPORTANT INSTRUCTIONS:\n- Use only information produced by the executed tools (context and slots). Do not invent or hallucinate routes, travel times, or recommendations.\n- For location queries (e.g., 'where am I'), return the human-readable address and short nearby references only.\n- For weather queries, return only the weather facts produced by the Weather tool.\n- If something went wrong or necessary information is missing, state that clearly and ask a clarifying question.\n\nProvide a natural language response to: {query}\n"

                response = self.llm.invoke(response_prompt)
                final_response = response.content.strip()

                # Log LLM usage (guard attributes for different providers)
                try:
                    usage = getattr(response, 'usage_metadata', {}) or {}
                    model_name = getattr(self.llm, 'model', None) or getattr(self.llm, 'model_name', None) or 'unknown'
                    log_llm_usage(
                        agent=self.name,
                        model=model_name,
                        usage={
                            'input_tokens': usage.get('input_tokens', 0),
                            'output_tokens': usage.get('output_tokens', 0),
                            'total_tokens': usage.get('total_tokens', 0)
                        }
                    )
                except Exception:
                    pass

                delta_state = {
                    "context": {
                        "final_response": final_response,
                        "execution_result": {
                            "status": "success",
                            "method": "llm_tool_selection_response_generation",
                            "tools_executed": len(execution_results.get("tools_executed", []))
                        },
                        "execution_timestamp": str(datetime.utcnow()),
                        "agent": self.name
                    }
                    ,
                    "slots": execution_results.get('slots', {})
                }

                # Merge execution results into context
                for key, value in execution_results.get("context", {}).items():
                    delta_state["context"][key] = value

                return {
                    "deltaState": delta_state,
                    "snippet": f"Executed {len(execution_results.get('tools_executed', []))} tools, generated response"
                }

            except Exception as e:
                logger.warning(f"ExecutionAgent: LLM response generation failed: {e}")

        # Fallback: Generate simple response from execution results
        logger.info("ExecutionAgent: Using fallback response generation")
        final_response = self._generate_fallback_response(world_state, execution_results)

        delta_state = {
            "context": {
                "final_response": final_response,
                "execution_result": {
                    "status": "success",
                    "method": "fallback_response",
                    "tools_executed": len(execution_results.get("tools_executed", []))
                },
                "execution_timestamp": str(datetime.utcnow()),
                "agent": self.name
            }
        }

        # Persist any slots discovered during execution so coordinator can save them
        try:
            delta_state["slots"] = execution_results.get('slots', {})
        except Exception:
            pass

        # Merge execution results
        for key, value in execution_results.get("context", {}).items():
            delta_state["context"][key] = value

        return {
            "deltaState": delta_state,
            "snippet": f"Executed {len(execution_results.get('tools_executed', []))} tools with fallback response"
        }

    def _execute_plan_with_llm_reasoning(self, steps: list, world_state: WorldState, query: str) -> Dict[str, Any]:
        """Use LLM reasoning to execute plan steps intelligently."""
        results = {"context": {}, "slots": {}, "errors": [], "tools_executed": []}

        # Prepare context for LLM reasoning
        current_slots = world_state.slots.model_dump() if hasattr(world_state.slots, 'model_dump') else world_state.slots
        plan_steps = [f"{step.get('action')} ({step.get('id', '')})" for step in steps]
        plan_summary = f"Plan steps: {', '.join(plan_steps)}"

        execution_prompt = f"""
You are the Execution Agent for a transportation assistant. You need to execute the plan steps intelligently.

User query: {query}
{plan_summary}
Current slots: {current_slots}

Available tools:
- Geolocate: Get user's current location (returns coordinates in slots.origin)
- Geocode: Convert address to coordinates (returns coordinates in slots.origin or slots.destination)
- ReverseGeocode: Convert coordinates to human-readable address (needs lat/lng from slots)
- Weather: Get current weather (needs coordinates from slots)
- PlacesSearch: Search for places like restaurants or stores. Use this for queries like "nearest coffee" or "pizza nearby". Requires a 'near' location from Geolocate or a slot.
- PlaceDetails: Get more details about a specific place using its placeId.
- Directions: Get directions between locations (handles geolocation/geocoding automatically). For POIs, use the output of PlacesSearch to provide a destinationPlaceId.
- Conversation: Handle casual conversation

Guidelines:
- Execute plan steps in logical order, respecting dependencies
- For ReverseGeocode: Use coordinates from previous Geolocate/Geocode steps
- For Weather: Use coordinates from slots.origin (or specify 'slot' in args for destination)
- For Geocode: Use 'slot': 'destination' in args for second location
- Pass results between dependent steps
- Only execute tools that are needed and make sense given current information

Analyze the plan and current state, then execute the appropriate tools.
"""

        # Ask LLM to reason step-by-step and suggest tools, then provide JSON.
        tool_selection_prompt = f"""
{execution_prompt}

Please think step-by-step and explain which tools you would use and why.
At the end of your message, include ONLY a single JSON object (no surrounding backticks) containing the planned tools.
The JSON should follow this structure exactly:

{{
    "tools": [
        {{"name": "ToolName", "args": {{}}}}
    ],
    "notes": "optional"
}}

Return only the JSON object at the end of the message.
"""
        try:
            reasoning_response = self.llm.invoke(tool_selection_prompt)
            reasoning_text = str(getattr(reasoning_response, 'content', reasoning_response)).strip()
            logger.info(f"ExecutionAgent: LLM reasoning: {reasoning_text[:500]}...")
        except Exception as e:
            logger.warning(f"ExecutionAgent: LLM reasoning invocation failed: {e}")
            reasoning_text = ""

    # Try to extract JSON tools list if LLM provided one
        tools_plan = None
        try:
            # Try to extract from ```json ... ```
            json_match = re.search(r'```json\s*(.*?)\s*```', reasoning_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
            else:
                # Fallback to {.*}
                json_match = re.search(r'\{.*\}', reasoning_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                else:
                    parsed = None
            if parsed:
                tools_plan = parsed.get('tools') or parsed.get('tool_list') or parsed.get('actions')
                logger.info(f"ExecutionAgent: Extracted JSON tools plan from reasoning: {tools_plan}")
        except Exception as e:
            logger.debug(f"ExecutionAgent: Could not parse JSON from reasoning: {e}")

        # If no explicit JSON list, infer tools from free-form reasoning using keyword matching
        if not tools_plan and reasoning_text:
            candidate_tools = []
            reasoning_lower = reasoning_text.lower()
            known_actions = ["geolocate", "geocode", "reversegeocode", "reverse geocode", "weather", "directions", "conversation"]
            for act in known_actions:
                if act in reasoning_lower:
                    # normalize names to canonical tool names
                    if "reverse" in act:
                        candidate_tools.append({"name": "ReverseGeocode", "args": {}})
                    elif act == "geocode":
                        candidate_tools.append({"name": "Geocode", "args": {}})
                    elif act == "geolocate":
                        candidate_tools.append({"name": "Geolocate", "args": {}})
                    elif act == "weather":
                        candidate_tools.append({"name": "Weather", "args": {}})
                    elif act == "directions":
                        candidate_tools.append({"name": "Directions", "args": {}})
                    elif act == "conversation":
                        candidate_tools.append({"name": "Conversation", "args": {}})
            if candidate_tools:
                tools_plan = candidate_tools
                logger.info(f"ExecutionAgent: Inferred tools from reasoning: {tools_plan}")

        # small helper to detect explicit 'where am i' style queries
        def _is_where_am_i(q: str) -> bool:
            if not q:
                return False
            lq = q.lower().strip()
            return 'where am i' in lq or lq.startswith('where am i') or 'what is my location' in lq or 'where am i now' in lq

        # robust merge helper: avoid overwriting a geolocated origin with a geocoded origin
        def _should_overwrite_slot(slot_name: str, new_slot: dict, tool_name: str = None) -> bool:
            try:
                # Always allow overwrite if explicitly set by Geocode for origin (user intent)
                if tool_name == 'Geocode' and slot_name == 'origin':
                    return True
                # Always allow overwrite if new_slot has '__user_provided' flag (set above for explicit user input)
                if isinstance(new_slot, dict) and new_slot.get('__user_provided'):
                    return True
                # prefer existing geolocate origin over geocode
                existing = results['slots'].get(slot_name) or (current_slots.get(slot_name) if isinstance(current_slots, dict) else None)
                if not existing:
                    return True
                existing_source = existing.get('__source') if isinstance(existing, dict) else None
                new_source = new_slot.get('__source') if isinstance(new_slot, dict) else None
                # If existing is geolocate, don't overwrite with geocode
                if existing_source == 'geolocate' and new_source == 'geocode':
                    return False
                # If existing lacks coords but new provides them, allow overwrite
                existing_has = bool(existing.get('lat') and existing.get('lng')) if isinstance(existing, dict) else False
                new_has = bool(new_slot.get('lat') and new_slot.get('lng')) if isinstance(new_slot, dict) else False
                if not existing_has and new_has:
                    return True
                # Otherwise default to allowing overwrite
                return True
            except Exception:
                return True

        # If tool selection succeeded, execute the selected tools
        if tools_plan:
            logger.info(f"ExecutionAgent: Executing selected tools: {tools_plan}")

            # Autopatch places: ensure any Directions steps with 'query' or POI-like utterances
            # get a PlacesSearch inserted before them and rewrite to destinationPlaceId.
            BRANDS = {"burger king","dunkin","dunkin donuts","mcdonalds","mcdonald","starbucks","pizza","coffee","cafe","bagel","donuts","pharmacy","7-eleven"}
            NEAR_TERMS = {"near me","nearby","closest","nearest","around"}

            def is_poi_intent(utter: str) -> bool:
                u = (utter or "").lower()
                return any(t in u for t in NEAR_TERMS) or any(b in u for b in BRANDS)

            def autopatch_places(plan, world_state):
                # Extract utterance from world_state.query
                utter = ''
                try:
                    query_obj = getattr(world_state, 'query', None)
                    if query_obj:
                        if hasattr(query_obj, 'raw'):
                            utter = query_obj.raw
                        elif isinstance(query_obj, dict):
                            utter = query_obj.get('raw', '')
                        else:
                            utter = str(query_obj)
                except Exception:
                    utter = ''

                poi_intent = is_poi_intent(utter)

                # Check if PlacesSearch is already in the plan
                has_places_search = any(step.get('name') == 'PlacesSearch' for step in plan)

                # Detect explicit origin and destination in the user query (robust to order)
                import re
                explicit_origin = None
                explicit_dest = None
                # Match 'from X to Y', 'to Y from X', 'get to Y from X', etc.
                m1 = re.search(r'from ([^\n\r]+?) to ([^\n\r]+)', utter, re.IGNORECASE)
                m2 = re.search(r'to ([^\n\r]+?) from ([^\n\r]+)', utter, re.IGNORECASE)
                m3 = re.search(r'get to ([^\n\r]+?) from ([^\n\r]+)', utter, re.IGNORECASE)
                if m1:
                    explicit_origin = m1.group(1).strip()
                    explicit_dest = m1.group(2).strip()
                elif m2:
                    explicit_dest = m2.group(1).strip()
                    explicit_origin = m2.group(2).strip()
                elif m3:
                    explicit_dest = m3.group(1).strip()
                    explicit_origin = m3.group(2).strip()
                # Fallback: try 'from X' and 'to Y' anywhere
                if not explicit_origin:
                    m_from = re.search(r'from ([^\n\r]+)', utter, re.IGNORECASE)
                    if m_from:
                        explicit_origin = m_from.group(1).strip()
                if not explicit_dest:
                    m_to = re.search(r'to ([^\n\r]+)', utter, re.IGNORECASE)
                    if m_to:
                        explicit_dest = m_to.group(1).strip()

                # If both explicit origin and destination are found, insert Geocode steps for both before Directions
                new = []
                for step in plan:
                    name = step.get('name') or step.get('action') or ''
                    args = step.setdefault('args', {})

                    if name == 'Directions':
                        # Insert Geocode for origin if explicit
                        if explicit_origin:
                            new.append({'name': 'Geocode', 'args': {'address': explicit_origin, 'slot': 'origin'}})
                        # Insert Geocode for destination if explicit
                        if explicit_dest:
                            new.append({'name': 'Geocode', 'args': {'address': explicit_dest, 'slot': 'destination'}})

                        has_dest = any(k in args for k in ("destination","destinationPlaceId","destinationLatLng"))

                        # A) if planner stuffed a 'query' into Directions, split it out
                        if 'query' in args:
                            q = args.pop('query')
                            if not has_places_search:
                                new.append({'name':'PlacesSearch','args':{'query': q, 'rankBy':'distance', 'maxResults':5}})
                            args['destinationPlaceId'] = '${context.places.results[0].placeId}'
                            args.pop('destination', None)
                        # B) if no destination and the utterance is a POI intent, add Places or use existing
                        elif not has_dest and poi_intent:
                            q = utter
                            if not has_places_search:
                                new.append({'name':'PlacesSearch','args':{'query': q, 'rankBy':'distance', 'maxResults':5}})
                            args['destinationPlaceId'] = '${context.places.results[0].placeId}'
                            args.pop('destination', None)

                    new.append(step)
                return new

            try:
                tools_plan = autopatch_places(tools_plan, world_state)
                # ensure PlacesSearch have near or Geolocate inserted
                tools_plan = ensure_places_has_near(tools_plan, world_state)
                logger.info("Final tools_plan (post-autopatch): %s", json.dumps(tools_plan, indent=2))
            except Exception:
                logger.debug("Autopatch places failed; proceeding with original tools_plan")

            # Helper: resolve slot-like synonyms into actual lat/lng dicts when possible
            SLOT_SYNONYMS = {"origin", "current location", "my location", "here"}

            def resolve_slotish(value, slots):
                # If already a dict with lat/lng, pass through
                if isinstance(value, dict) and value.get('lat') is not None and value.get('lng') is not None:
                    return value
                if isinstance(value, str):
                    v = value.strip().lower()
                    if v in SLOT_SYNONYMS and isinstance(slots, dict) and slots.get('origin'):
                        o = slots.get('origin')
                        try:
                            return {"lat": o.get('lat'), "lng": o.get('lng')}
                        except Exception:
                            return value
                return value

            # Ensure PlacesSearch steps have a 'near' argument; if slots.origin missing, add Geolocate step first
            def ensure_places_has_near(plan, world_state):
                slots = world_state.slots.model_dump() if hasattr(world_state.slots, 'model_dump') else world_state.slots
                origin = slots.get('origin')
                new = []
                for step in plan:
                    name = resolve_tool_name(step.get('name', ''))
                    args = step.setdefault('args', {})
                    if name == 'PlacesSearch':
                        if not args.get('near'):
                            if origin and origin.get('lat') and origin.get('lng'):
                                args['near'] = {"lat": origin.get('lat'), "lng": origin.get('lng')}
                            else:
                                # Insert a geolocate before this PlacesSearch
                                new.append({'name': 'Geolocate', 'args': {}})
                    new.append(step)
                return new

            # Run ensure_places_has_near to make sure PlacesSearch steps can execute
            try:
                tools_plan = ensure_places_has_near(tools_plan, world_state)
            except Exception:
                pass

            # --- Executor-level guard: If the user's query appears to specify a new destination
            # (e.g. contains an address like '116-11 Liberty Ave' or 'to 123 Main St') and the
            # plan includes Directions but does not include a Geocode for that destination,
            # prepend a Geocode step to ensure we don't reuse a stale slots.destination.
            def _extract_address_from_query(q: str) -> Optional[str]:
                if not q:
                    return None
                # look for phrases like 'to X' or 'get to X' or 'how do i get to X'
                m = re.search(r"\b(?:to|get to|how to get to|how do i get to|towards|go to)\s+(.+)$", q, re.IGNORECASE)
                if m:
                    addr = m.group(1).strip().strip('?.!')
                    # cut off trailing conversational fragments (via/by/from/in)
                    addr = re.split(r"\s+via\s+|\s+by\s+|\s+from\s+|\s+in\s+", addr, flags=re.IGNORECASE)[0].strip()
                    return addr
                return None

            def _looks_like_address(s: str) -> bool:
                if not s:
                    return False
                # common house number patterns like '116-11', '123', etc.
                if re.search(r"\d{1,5}[-\s]?\d{0,5}", s):
                    return True
                # common street type indicators
                if re.search(r"\b(st|street|ave|avenue|rd|road|blvd|boulevard|ln|lane|way|drive|dr|court|ct|pkwy|parkway|terrace|pl|place)\b", s, re.IGNORECASE):
                    return True
                return False

            try:
                has_directions = any((t.get('name') == 'Directions') for t in tools_plan)
                has_geocode_destination = any(
                    (t.get('name') == 'Geocode' and (
                        (t.get('args') or {}).get('slot') == 'destination' or
                        (t.get('args') or {}).get('address') or
                        (t.get('args') or {}).get('query')
                    )) for t in tools_plan
                )
                if has_directions and not has_geocode_destination:
                    # First, prefer asking the LLM whether the user's query indicates a new destination
                    should_prepend = False
                    address_candidate = None
                    try:
                        if self.llm:
                            # Prepare a short JSON-only prompt asking whether the query replaces the current destination
                            cur_dest = ''
                            try:
                                dest_slot = current_slots.get('destination') or {}
                                cur_dest = dest_slot.get('name', '') if isinstance(dest_slot, dict) else ''
                            except Exception:
                                cur_dest = ''

                            llm_check_prompt = json.dumps({
                                'instruction': 'Decide if the user query specifies a new destination that is different from the current remembered destination. Return JSON only.',
                                'query': query,
                                'current_destination_name': cur_dest,
                                'response_format': {'update_destination': 'bool', 'address': 'string (best candidate address or empty)'}
                            }, indent=2)

                            parsed_check = self._llm_json_request(llm_check_prompt, attempts=1)
                            if parsed_check and isinstance(parsed_check, dict):
                                update_flag = parsed_check.get('update_destination')
                                addr = parsed_check.get('address') or None
                                if update_flag:
                                    should_prepend = True
                                    address_candidate = addr or None
                    except Exception:
                        should_prepend = False

                    # If LLM did not decide to update, fall back to conservative heuristic extraction
                    if not should_prepend:
                        try:
                            extracted = _extract_address_from_query(query)
                            # Relaxed heuristic: accept any non-trivial extracted phrase as a candidate
                            # (handles place names like 'Limitless Fitness' or 'Washington Sq Park')
                            if extracted:
                                low = extracted.lower().strip()
                                if low and low not in ('me', 'here') and len(low) > 1:
                                    address_candidate = extracted
                                    should_prepend = True
                        except Exception:
                            should_prepend = False

                    if should_prepend and address_candidate:
                        # compare against current destination slot name to avoid unnecessary geocode
                        try:
                            dest_slot = current_slots.get('destination') or {}
                            existing_name = dest_slot.get('name', '') if isinstance(dest_slot, dict) else ''
                        except Exception:
                            existing_name = ''

                        if not existing_name or address_candidate.lower() not in existing_name.lower():
                            tools_plan.insert(0, {'name': 'Geocode', 'args': {'address': address_candidate, 'slot': 'destination'}})
                            logger.info(f"ExecutionAgent: Prepending Geocode for address '{address_candidate}' (LLM/heuristic) to tools_plan to avoid stale destination")
            except Exception:
                # non-fatal: if our heuristics fail, proceed with original tools_plan
                pass

            # Function to substitute placeholders like {{slots.origin.lat}} or ${temp_slot.lat}
            # This resolver will try to return native values (numbers/dicts) when the whole
            # string is a single ${...} expression so downstream tools receive correct types.
            def substitute_placeholders(value, world_state, current_slots, results):
                import re

                def _lookup_path(path: str):
                    parts = path.split('.')
                    # 1) Try recent tool results slots
                    obj = results.get('slots', {}) if isinstance(results, dict) else {}
                    try:
                        cur = obj
                        for part in parts:
                            # Handle array indexing like 'results[0]'
                            if '[' in part and part.endswith(']'):
                                key, index_str = part.split('[', 1)
                                index_str = index_str.rstrip(']')
                                if isinstance(cur, dict) and key in cur:
                                    cur = cur[key]
                                else:
                                    raise KeyError
                                if isinstance(cur, list) and index_str.isdigit():
                                    cur = cur[int(index_str)]
                                else:
                                    raise KeyError
                            else:
                                if isinstance(cur, dict) and part in cur:
                                    cur = cur[part]
                                else:
                                    raise KeyError
                        return cur
                    except Exception:
                        pass

                    # 2) Try current_slots
                    obj = current_slots or {}
                    try:
                        cur = obj
                        for part in parts:
                            # Handle array indexing like 'results[0]'
                            if '[' in part and part.endswith(']'):
                                key, index_str = part.split('[', 1)
                                index_str = index_str.rstrip(']')
                                if isinstance(cur, dict) and key in cur:
                                    cur = cur[key]
                                else:
                                    raise KeyError
                                if isinstance(cur, list) and index_str.isdigit():
                                    cur = cur[int(index_str)]
                                else:
                                    raise KeyError
                            else:
                                if isinstance(cur, dict) and part in cur:
                                    cur = cur[part]
                                else:
                                    raise KeyError
                        return cur
                    except Exception:
                        pass

                    # 3) Try world_state attributes/dicts
                    try:
                        cur = world_state
                        for part in parts:
                            # Handle array indexing like 'results[0]'
                            if '[' in part and part.endswith(']'):
                                key, index_str = part.split('[', 1)
                                index_str = index_str.rstrip(']')
                                if hasattr(cur, key):
                                    cur = getattr(cur, key)
                                elif isinstance(cur, dict) and key in cur:
                                    cur = cur[key]
                                else:
                                    raise AttributeError
                                if isinstance(cur, list) and index_str.isdigit():
                                    cur = cur[int(index_str)]
                                else:
                                    raise AttributeError
                            else:
                                if hasattr(cur, part):
                                    cur = getattr(cur, part)
                                elif isinstance(cur, dict) and part in cur:
                                    cur = cur[part]
                                else:
                                    raise AttributeError
                        return cur
                    except Exception:
                        return None

                # Handle strings containing {{...}} using previous behavior (return strings)
                if isinstance(value, str) and '{{' in value and '}}' in value:
                    def replacer(match):
                        path = match.group(1).strip()
                        found = _lookup_path(path)
                        return str(found) if found is not None else match.group(0)
                    return re.sub(r'\{\{([^}]+)\}\}', replacer, value)

                # Handle ${...} placeholders. If the entire value is a single ${...} pattern,
                # return the native object (number/dict) so tools receive proper types.
                if isinstance(value, str):
                    full_match = re.fullmatch(r'\$\{([^}]+)\}', value.strip())
                    if full_match:
                        path = full_match.group(1).strip()
                        found = _lookup_path(path)
                        return found if found is not None else value

                    # If ${...} appears inside a larger string, replace occurrences with their string form
                    def replacer2(match):
                        path = match.group(1).strip()
                        found = _lookup_path(path)
                        return str(found) if found is not None else match.group(0)
                    if '${' in value and '}' in value:
                        return re.sub(r'\$\{([^}]+)\}', replacer2, value)

                return value

            # If user explicitly asked 'where am i', ALWAYS geolocate first (never use stale origin)
            try:
                if _is_where_am_i(query):
                    # Always insert Geolocate as the first step
                    tools_plan = [ {'name': 'Geolocate', 'args': {}} ] + [t for t in tools_plan if t.get('name') != 'Geolocate']
                    # Ensure ReverseGeocode is present after Geolocate
                    has_rev = any((t.get('name') == 'ReverseGeocode') for t in tools_plan)
                    if not has_rev:
                        tools_plan.insert(1, {'name': 'ReverseGeocode', 'args': {}})
            except Exception:
                pass

            # If user asks for weather 'near me', 'here', or similar, ALWAYS geolocate before Weather
            try:
                weather_near_me = False
                ql = (query or '').lower()
                if 'weather' in ql and any(kw in ql for kw in ['near me', 'here', 'my location', 'current location']):
                    weather_near_me = True
                # Also check for Weather tool with no explicit coordinates
                for idx, t in enumerate(tools_plan):
                    if t.get('name') == 'Weather':
                        coords = t.get('args', {}).get('coordinates') or ''
                        if weather_near_me or not coords:
                            # Insert Geolocate before Weather if not already present
                            has_geo = any((tt.get('name') == 'Geolocate') for tt in tools_plan[:idx])
                            if not has_geo:
                                tools_plan = tools_plan[:idx] + [{'name': 'Geolocate', 'args': {}}] + tools_plan[idx:]
                            break
            except Exception:
                pass


            # --- PATCH: If user did not ask for directions, only run PlacesSearch and return results ---
            # Detect if the user query is a pure POI/PlacesSearch (e.g. 'nearest dunkin')
            user_query = world_state.query.get('raw', '').lower() if hasattr(world_state, 'query') else ''
            wants_directions = any(
                kw in user_query for kw in [
                    'directions', 'how do i get', 'how to get', 'route', 'take me', 'get to', 'navigate', 'go to', 'how do i go', 'how can i get', 'how can i go', 'how do i reach', 'how can i reach', 'how do i travel', 'how can i travel', 'transit', 'walk', 'bus', 'subway', 'train', 'drive', 'driving', 'walking', 'public transport', 'public transit', 'commute', 'travel to', 'show me directions', 'show directions', 'show route', 'show me how', 'show me the way', 'show me the route', 'show me the directions'
                ]
            )
            # If the plan is just PlacesSearch (or PlacesSearch + Directions) and the user did NOT ask for directions, only run PlacesSearch
            only_places = False
            if tools_plan and len(tools_plan) >= 1:
                # If first tool is PlacesSearch and (no Directions or Directions is second)
                first_is_places = tools_plan[0].get('name') == 'PlacesSearch'
                has_directions = any(t.get('name') == 'Directions' for t in tools_plan)
                if first_is_places and (not has_directions or (len(tools_plan) == 2 and tools_plan[1].get('name') == 'Directions')) and not wants_directions:
                    only_places = True

            if only_places:
                # Only run PlacesSearch, skip Directions
                tool = tools_plan[0]
                tool_name = tool.get('name')
                tool_args = tool.get('args', {}) or {}
                # Substitute placeholders and resolve slots
                tool_args = {k: substitute_placeholders(v, world_state, current_slots, results) for k, v in tool_args.items()}
                if tool_name == "PlacesSearch" and not tool_args.get("near") and current_slots.get("origin"):
                    tool_args["near"] = current_slots["origin"]
                result = PlacesSearch.func(**tool_args)
                # merge tool output
                if isinstance(result, dict):
                    self._merge_tool_output(results, tool_name, result)
                # Generate a summary of the nearest locations
                places = (result.get('context', {}) or {}).get('places', {})
                results['context'] = results.get('context', {})
                results['context']['places'] = places
                # Prepare a user-facing summary
                summary_lines = []
                results_list = places.get('results', []) if isinstance(places, dict) else []
                if results_list:
                    summary_lines.append(f"Here are the nearest results for '{tool_args.get('query','')}':")
                    for i, p in enumerate(results_list[:5]):
                        summary_lines.append(f"{i+1}. {p.get('name','?')} — {p.get('address','?')} ({p.get('distanceMeters','?')} meters away)")
                else:
                    summary_lines.append("No results found.")
                results['context']['final_response'] = '\n'.join(summary_lines)
                return results

            # --- END PATCH ---

            for idx, tool in enumerate(tools_plan):
                try:
                    next_tool = tools_plan[idx + 1] if idx + 1 < len(tools_plan) else {}
                    
                    # Substitute placeholders before passing to the execution step
                    tool_args = tool.get('args', {}) or {}
                    substituted_args = {k: substitute_placeholders(v, world_state, current_slots, results) for k, v in tool_args.items()}
                    tool_with_substituted_args = {'name': tool.get('name'), 'args': substituted_args}

                    result = self._execute_tool_step(tool_with_substituted_args, world_state, current_slots, results, next_tool)

                    logger.info(f"ExecutionAgent: Tool {tool['name']} executed successfully: {result}")
                    results["tools_executed"].append(tool['name'])
                    
                    # merge tool output using the shared helper, preserving overwrite rules for slots
                    if isinstance(result, dict):
                        # slots: use overwrite heuristic
                        if result.get('slots'):
                            for k, v in result.get('slots', {}).items():
                                try:
                                    if _should_overwrite_slot(k, v, tool['name']):
                                        results.setdefault('slots', {})[k] = v
                                except Exception:
                                    results.setdefault('slots', {})[k] = v
                        # context and others: use shared merge helper
                        self._merge_tool_output(results, tool['name'], result)
                    
                    current_slots.update(results.get('slots', {}))

                except Exception as e:
                    logger.warning(f"ExecutionAgent: Error executing tool {tool.get('name')}: {e}")
                    results["errors"].append(f"Error executing tool {tool.get('name')}: {e}")

            # After executing all selected tools, synthesize a compact weather summary
            results = self._summarize_weather(results)
            return results

        # If LLM reasoning fails or there's no LLM, fall back to simple step execution
        return self._execute_plan_steps_fallback(steps, world_state)

    def _execute_plan_steps_fallback(self, steps: list, world_state: WorldState) -> Dict[str, Any]:
        """Execute plan steps sequentially as a fallback."""
        logger.info("ExecutionAgent: Falling back to per-step execution")
        results = {"context": {}, "slots": {}, "errors": [], "tools_executed": []}
        current_slots = world_state.slots.model_dump() if hasattr(world_state.slots, 'model_dump') else world_state.slots

        for idx, step in enumerate(steps):
            try:
                next_step = steps[idx + 1] if idx + 1 < len(steps) else {}
                # In fallback, the action is the name
                tool_spec = {'name': step.get('action'), 'args': step.get('args', {})}
                
                result = self._execute_tool_step(tool_spec, world_state, current_slots, results, next_step)
                
                logger.info(f"ExecutionAgent: Action {step.get('action')} executed successfully: {result}")
                results["tools_executed"].append(step.get('action'))
                
                if isinstance(result, dict):
                    self._merge_tool_output(results, step.get('action'), result)
                
                current_slots.update(results.get('slots', {}))

            except Exception as e:
                logger.warning(f"ExecutionAgent: Error executing action {step.get('action')}: {e}")
                results["errors"].append(f"Error executing action {step.get('action')}: {e}")
        
        results = self._summarize_weather(results)
        return results

    def _execute_tool_step(self, tool: dict, world_state: WorldState, current_slots: dict, results: dict, next_tool: Optional[dict] = None) -> Optional[dict]:
        """
        Executes a single tool step. This is the centralized execution logic.
        """
        tool_name = tool.get('name')
        tool_args = tool.get('args', {}) or {}
        query = world_state.query.get("raw", "")
        
        # --- SLOT REFERENCE RESOLUTION ---
        slot_fields = []
        if tool_name in ("PlacesSearch",):
            slot_fields = ["near"]
        elif tool_name in ("Directions",):
            slot_fields = ["origin", "destination"]
        elif tool_name in ("Geocode",):
            slot_fields = ["origin", "destination"]
        
        for field in slot_fields:
            val = tool_args.get(field)
            if isinstance(val, dict) and val.get('lat') is not None and val.get('lng') is not None:
                val['__user_provided'] = True
                tool_args[field] = val
                results.setdefault('slots', {})[field] = val
                continue
            if isinstance(val, str) and val not in current_slots:
                geocode_res = geocode_place.func(address=val, slot=field)
                slot_val = geocode_res.get('slots', {}).get(field)
                if slot_val:
                    slot_val['__user_provided'] = True
                    tool_args[field] = slot_val
                    results.setdefault('slots', {})[field] = slot_val
                continue
            if isinstance(val, str) and val in current_slots:
                tool_args[field] = current_slots[val]
        
        if tool_name == "PlacesSearch" and not tool_args.get("near") and current_slots.get("origin"):
            tool_args["near"] = current_slots["origin"]
        
        # --- TOOL EXECUTION ---
        if tool_name == "Geolocate":
            return geolocate_user.func()
        
        elif tool_name == "PlacesSearch":
            return PlacesSearch.func(**tool_args)

        elif tool_name == "PlaceDetails":
            return PlaceDetails.func(**tool_args)

        elif tool_name == "Conversation":
            return handle_conversation.func(message=tool_args.get('message', query))

        elif tool_name == "Geocode":
            # For weather queries, always write to 'destination' slot
            is_weather_query = False
            if next_tool and next_tool.get('name', '') == 'Weather':
                is_weather_query = True
            elif 'weather' in (query or '').lower():
                is_weather_query = True
            default_slot = tool_args.get('slot') or ('destination' if is_weather_query else 'origin')
            if not tool_args.get('slot') and next_tool:
                if next_tool.get('name', '') in ('Weather', 'Directions'):
                    dest_slot = current_slots.get('destination') or {}
                    if not (dest_slot.get('name') or dest_slot.get('lat') or dest_slot.get('lng')):
                        default_slot = 'destination'
            if tool_args.get('slot') == 'origin' and next_tool:
                if next_tool.get('name', '') in ('Weather', 'Directions'):
                    default_slot = 'destination'
            address = tool_args.get('address') or tool_args.get('query') or tool_args.get('location') or tool_args.get('destination') or tool_args.get('place')
            if not address:
                q = query or ''
                addr_guess = re.sub(r"\b(weather|directions|to|in|near|how to get|how do i get)\b", "", q, flags=re.IGNORECASE).strip()
                if addr_guess and addr_guess.lower() not in ('me', 'here', ''):
                    address = addr_guess
            return geocode_place.func(address=address, slot=default_slot)

        elif tool_name == "ReverseGeocode":
            origin_slot = current_slots.get('origin') or {}
            origin_source = origin_slot.get('__source') if isinstance(origin_slot, dict) else None
            
            if origin_source == 'geocode' and not (tool_args.get('lat') or tool_args.get('lng')):
                geo_res = geolocate_user.func()
                self._merge_tool_output(results, 'Geolocate', geo_res)
                current_slots.update(results.get('slots', {}))
                origin_slot = current_slots.get('origin') or {}
            
            lat = tool_args.get('lat') or origin_slot.get('lat')
            lng = tool_args.get('lng') or origin_slot.get('lng')
            return reverse_geocode.func(lat=lat, lng=lng) if lat is not None and lng is not None else None

        elif tool_name == "Weather":
            slot, label, units = tool_args.get('slot'), tool_args.get('label') or tool_args.get('tag'), (world_state.context.get('units') or 'imperial')
            coords = tool_args.get('coordinates') or tool_args.get('location')
            lat, lng = tool_args.get('lat'), tool_args.get('lng')

            if isinstance(coords, dict):
                lat, lng = lat or coords.get('lat'), lng or coords.get('lng')
            elif isinstance(coords, str):
                sref = current_slots.get(coords) if isinstance(current_slots, dict) else None
                if sref and isinstance(sref, dict): lat, lng = lat or sref.get('lat'), lng or sref.get('lng')

            # Always prefer destination slot for weather queries if present
            dest_slot = current_slots.get('destination', {})
            if (lat is None or lng is None) and dest_slot.get('lat') and dest_slot.get('lng'):
                lat, lng = lat or dest_slot.get('lat'), lng or dest_slot.get('lng')

            if (lat is None or lng is None) and slot:
                s = current_slots.get(slot, {})
                lat, lng = lat or s.get('lat'), lng or s.get('lng')

            if (lat is None or lng is None) and tool_args.get('address'):
                geocode_res = geocode_place.invoke({"address": tool_args.get('address')})
                gslots = geocode_res.get('slots', {})
                if gslots:
                    first_slot = next(iter(gslots.values()))
                    lat, lng = lat or first_slot.get('lat'), lng or first_slot.get('lng')

            if lat is None or lng is None:
                origin_slot = current_slots.get('origin', {})
                if not (origin_slot.get('lat') and origin_slot.get('lng')) or origin_slot.get('__source') == 'geocode':
                    geo_res = geolocate_user.invoke({})
                    self._merge_tool_output(results, 'Geolocate', geo_res)
                    current_slots.update(results.get('slots', {}))
                    origin_slot = current_slots.get('origin', {})
                lat, lng = lat or origin_slot.get('lat'), lng or origin_slot.get('lng')

            if lat is None or lng is None: raise ValueError("Missing coordinates for Weather tool")

            result = weather_current.func(lat=lat, lng=lng, units=units)
            if result and 'context' in result and 'lastWeather' in result['context']:
                key = f"lastWeather_{label or slot or f'{lat}_{lng}'}"
                # Add a suffix if the key already exists to prevent overwrites
                i = 1
                base_key = key
                while key in results.get('context', {}):
                    key = f"{base_key}_{i}"
                    i += 1
                result['context'][key] = result['context'].pop('lastWeather')
            return result
        
        elif tool_name == "Directions":
            dest_val = tool_args.get('destination')
            orig_val = tool_args.get('origin')

            if not dest_val:
                dest_slot = current_slots.get('destination', {})
                dest_val = f"{dest_slot.get('lat')},{dest_slot.get('lng')}" if dest_slot.get('lat') else dest_slot.get('name')
            if not orig_val:
                origin_slot = current_slots.get('origin', {})
                orig_val = f"{origin_slot.get('lat')},{origin_slot.get('lng')}" if origin_slot.get('lat') else origin_slot.get('name')

            if isinstance(dest_val, dict): dest_val = f"{dest_val.get('lat')},{dest_val.get('lng')}"
            if isinstance(orig_val, dict): orig_val = f"{orig_val.get('lat')},{orig_val.get('lng')}"
            
            if not orig_val:
                geo_res = geolocate_user.invoke({})
                self._merge_tool_output(results, 'Geolocate', geo_res)
                current_slots.update(results.get('slots', {}))
                origin_slot = current_slots.get('origin', {})
                orig_val = f"{origin_slot.get('lat')},{origin_slot.get('lng')}" if origin_slot.get('lat') else None
            
            return directions.func(destination=dest_val or "", origin=orig_val)

        else:
            logger.warning(f"ExecutionAgent: Unknown tool in execution step: {tool_name}")
            return None

    def _prepare_context_summary(self, world_state: WorldState, execution_results: dict) -> str:
        """Prepare a summary of execution results for LLM response generation."""
        summaries = []

        # Location info
        origin_data = execution_results.get('slots', {}).get('origin')
        if not origin_data and world_state.slots.origin:
            origin_data = world_state.slots.origin.dict() if hasattr(world_state.slots.origin, 'dict') else world_state.slots.origin
        origin = origin_data or {}
        if origin.get('name'):
            summaries.append(f"Origin: {origin['name']} (lat: {origin.get('lat')}, lng: {origin.get('lng')})")

        dest_data = execution_results.get('slots', {}).get('destination')
        if not dest_data and world_state.slots.destination:
            dest_data = world_state.slots.destination.dict() if hasattr(world_state.slots.destination, 'dict') else world_state.slots.destination
        dest = dest_data or {}
        if dest.get('name'):
            summaries.append(f"Destination: {dest['name']} (lat: {dest.get('lat')}, lng: {dest.get('lng')})")

        # Accuracy info
        accuracy_note = execution_results.get('context', {}).get('accuracy_note')
        if accuracy_note:
            summaries.append(f"Location accuracy: {accuracy_note}")

        # Reverse geocode info
        rg = execution_results.get('context', {}).get('reverse_geocode_result')
        if rg and rg.get('formatted_address'):
            summaries.append(f"Address: {rg['formatted_address']}")

        # Weather info
        weather_origin = execution_results.get('context', {}).get('lastWeather_origin')
        if weather_origin:
            temp = weather_origin.get('temp')
            summary = weather_origin.get('summary')
            summaries.append(f"Weather in origin: {summary or 'unknown conditions'}, {temp}°" if temp else f"Weather in origin: {summary or 'unknown'}")

        weather_dest = execution_results.get('context', {}).get('lastWeather_destination')
        if weather_dest:
            temp = weather_dest.get('temp')
            summary = weather_dest.get('summary')
            summaries.append(f"Weather in destination: {summary or 'unknown conditions'}, {temp}°" if temp else f"Weather in destination: {summary or 'unknown'}")

        # Include any other labeled weather keys (lastWeather_<label>) so multi-weather calls are included
        try:
            for key, val in execution_results.get('context', {}).items():
                if isinstance(key, str) and key.startswith('lastWeather_') and key not in ('lastWeather_origin', 'lastWeather_destination'):
                    label = key.split('lastWeather_', 1)[1]
                    if isinstance(val, dict):
                        temp = val.get('temp')
                        summary = val.get('summary')
                        if temp is not None:
                            summaries.append(f"Weather ({label}): {summary or 'unknown conditions'}, {temp}°")
                        else:
                            summaries.append(f"Weather ({label}): {summary or 'unknown'}")
        except Exception:
            pass

        # Directions info
        directions_data = execution_results.get('context', {}).get('directions')
        if directions_data and isinstance(directions_data, dict):
            transit_dir = directions_data.get('transit_directions')
            if transit_dir:
                mode = transit_dir.get('mode')
                total_duration = transit_dir.get('total_duration')
                total_distance = transit_dir.get('total_distance')
                summaries.append(f"Directions mode: {mode}, duration: {total_duration}, distance: {total_distance}")
                
                # Extract key steps
                legs = transit_dir.get('legs', [])
                for i, leg in enumerate(legs):
                    if i > 0:
                        summaries.append(f"Leg {i+1}:")
                    steps = leg.get('steps', [])
                    transit_steps = [step for step in steps if step.get('travel_mode') == 'TRANSIT']
                    if transit_steps:
                        for step in transit_steps[:3]:  # Limit to first 3 transit steps
                            transit_info = step.get('transit', {})
                            line = transit_info.get('line_name', 'Unknown line')
                            vehicle = transit_info.get('vehicle_type', 'Transit')
                            headsign = transit_info.get('headsign', '')
                            departure = transit_info.get('departure_stop', '')
                            arrival = transit_info.get('arrival_stop', '')
                            dep_time = transit_info.get('departure_time', '')
                            arr_time = transit_info.get('arrival_time', '')
                            summaries.append(f"  Take {vehicle} {line} from {departure} to {arrival} ({dep_time} - {arr_time})")
                    else:
                        # If no transit, mention walking or other
                        walking_steps = [step for step in steps if step.get('travel_mode') == 'WALKING']
                        if walking_steps:
                            total_walk = sum(float(step.get('duration', '0 mins').split()[0]) for step in walking_steps if 'mins' in step.get('duration', ''))
                            summaries.append(f"  Walking: {total_walk} mins total")
            else:
                mode = directions_data.get('mode')
                if mode:
                    summaries.append(f"Directions: {mode} route available")

        # Tools executed
        tools = execution_results.get('tools_executed', [])
        if tools:
            summaries.append(f"Tools executed: {', '.join(tools)}")

        # Errors
        errors = execution_results.get('errors', [])
        if errors:
            summaries.append(f"Errors encountered: {errors[0]}")

        return "\n".join(summaries) if summaries else "No specific results from tool execution."

    def _generate_fallback_response(self, world_state: WorldState, execution_results: dict) -> str:
        """Create a simple human-readable response from execution results when LLM fails."""
        # If reverse geocode result present, prefer a direct address reply
        ctx = execution_results.get('context', {}) or {}
        # If we have a final_response in context already, return it
        if ctx.get('final_response'):
            return ctx.get('final_response')

        # Check for reverse geocode
        rg = ctx.get('reverse_geocode_result') or ctx.get('reverse_geocode')
        if rg and isinstance(rg, dict):
            addr = rg.get('formatted_address') or rg.get('address') or rg.get('display_name')
            if addr:
                return f"You are near: {addr}."

        # Check slots.origin
        origin = execution_results.get('slots', {}).get('origin') or (world_state.slots.origin if hasattr(world_state.slots, 'origin') else world_state.slots.get('origin'))
        if origin and origin.get('name'):
            return f"You appear to be near {origin.get('name')} (lat={origin.get('lat')}, lng={origin.get('lng')})."

        # Weather result
        lw = ctx.get('lastWeather')
        if lw:
            temp = lw.get('temp')
            summary = lw.get('summary')
            return f"Current conditions: {summary or 'unknown'}, temperature {temp if temp is not None else 'unknown'}."

        # Directions or transit info
        td = ctx.get('transit_directions') or ctx.get('directions')
        if td and isinstance(td, dict):
            # Prefer nested transit_directions when present
            transit = td.get('transit_directions') if td.get('transit_directions') else td
            try:
                mode = transit.get('mode') or transit.get('travel_mode') or 'route'
                total_duration = transit.get('total_duration') or transit.get('duration') or ''
                total_distance = transit.get('total_distance') or transit.get('distance') or ''
                parts = [f"I found {mode} directions for you."]
                if total_duration:
                    parts.append(f"Total time: {total_duration}.")
                if total_distance:
                    parts.append(f"Distance: {total_distance}.")

                # Build step-by-step instructions
                legs = transit.get('legs', []) or []
                step_lines = []
                step_i = 1
                for leg in legs:
                    steps = leg.get('steps', []) or []
                    for s in steps:
                        travel_mode = s.get('travel_mode') or s.get('mode') or ''
                        duration = s.get('duration') or ''
                        instr = s.get('instructions') or s.get('instruction') or s.get('summary') or ''
                        if travel_mode and travel_mode.upper() == 'TRANSIT' or s.get('transit'):
                            transit_info = s.get('transit', {}) or {}
                            line = transit_info.get('line_name') or transit_info.get('line') or ''
                            vehicle = transit_info.get('vehicle_type') or ''
                            dep = transit_info.get('departure_stop') or transit_info.get('departure') or ''
                            arr = transit_info.get('arrival_stop') or transit_info.get('arrival') or ''
                            dep_time = transit_info.get('departure_time') or ''
                            arr_time = transit_info.get('arrival_time') or ''
                            step_lines.append(f"{step_i}. Take {vehicle} {line} from {dep} to {arr} ({dep_time} - {arr_time})")
                        else:
                            # Walking or other non-transit steps
                            if instr:
                                step_lines.append(f"{step_i}. {instr} {f'({duration})' if duration else ''}".strip())
                            else:
                                step_lines.append(f"{step_i}. {travel_mode or 'Proceed'} {f'for {duration}' if duration else ''}".strip())
                        step_i += 1

                if step_lines:
                    parts.append("Steps:")
                    parts.extend(step_lines)

                return " ".join(parts)
            except Exception:
                return "I found directions for you. See details above."

        # Last resort
        errors = execution_results.get('errors', [])
        if errors:
            return f"I attempted to run some tools but encountered errors: {errors[0]}"

        return "I couldn't determine your location. Please provide an address or allow location access."