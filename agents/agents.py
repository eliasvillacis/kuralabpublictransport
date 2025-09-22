"""
Kura Public Transport Assistant - Agent Architecture

Two-agent architecture for transportation assistance:
- Planner (LLM): Produces structured JSON plans for user queries
- Executor (LLM + tools): Executes plan steps and generates final responses

WorldState remains the canonical blackboard; agents communicate via deltaState patches.
"""

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
from agents.tools.weather_tool import weather_current
from agents.tools.location_tool import geocode_place, geolocate_user, reverse_geocode
from agents.tools.conversation_tool import handle_conversation
from agents.tools.directions_tool import directions

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Base class for all agents in the A2A architecture."""

    def __init__(self, name: str, model_name: str = "gemini-1.5-flash", temperature: float = 0.2):
        self.name = name
        self.llm = self._initialize_llm(model_name, temperature)
        # No FORCE_LLM enforcement by default; fallbacks allowed when LLM unavailable

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

    def _llm_json_request(self, prompt: str, attempts: int = 3, sleep_between: float = 0.5) -> Optional[dict]:
        """Ask the LLM to return JSON only. Retry a few times if the response isn't valid JSON.

        Returns the parsed JSON dict on success, or None on failure.
        """
        if not self.llm:
            return None

        last_resp_text = None
        for attempt in range(1, attempts + 1):
            try:
                resp = self.llm.invoke(prompt)
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
                    # prepare corrective prompt for next attempt
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

        # log final raw text for debugging
        logger.debug(f"BaseAgent: LLM final non-JSON response after {attempts} attempts: {last_resp_text}")
        return None

    @abstractmethod
    def get_name(self) -> str:
        """Return the agent\'s name."""
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
    """LLM-powered PlanningAgent that creates structured execution plans."""

    def __init__(self):
        # Planner should use a low-temperature, more deterministic model
        super().__init__("planner", "gemini-1.5-flash", 0.2)
        self.planning_prompt = """
You are the Planning Agent in a transportation assistant system. Analyze user queries and create structured execution plans.

Available actions:
- Geolocate: Get user's current location (use for "near me", "here", "my location")
- Geocode: Convert address to coordinates (use for specific addresses)
- ReverseGeocode: Convert coordinates to human-readable address
- Weather: Get current weather conditions
- Directions: Get directions between locations (automatically handles geolocation, geocoding, and transit/walking modes)
- Conversation: Handle casual conversation and greetings

CRITICAL: Return ONLY a valid JSON object with this exact structure:
{
  "steps": [
    {
      "id": "S1",
      "action": "ActionName",
      "args": {"key": "value"}
    }
  ],
  "status": "planning",
  "confidence": 0.9
}

Examples:
For "weather near me":
{
  "steps": [
    {"id": "S1", "action": "Geolocate", "args": {}},
    {"id": "S2", "action": "Weather", "args": {}}
  ],
  "status": "planning",
  "confidence": 0.9
}

For "directions to Central Park":
{
  "steps": [
    {"id": "S1", "action": "Directions", "args": {"destination": "Central Park"}}
  ],
  "status": "planning",
  "confidence": 0.9
}

Guidelines:
- For directions queries: Use Directions action (handles everything automatically)
- For weather queries with "near me": Use Geolocate, then Weather
- For weather at specific location: Use Geocode, then Weather
- For location queries ("where am I"): Use Geolocate, then ReverseGeocode
- For casual conversation: Use Conversation

Query: {query}

Return only the JSON, no other text.
"""

    def get_name(self) -> str:
        """Return the agent\'s name."""
        return self.name

    def can_handle(self, world_state: WorldState) -> bool:
        """Planning agent can handle when there\'s a user query."""
        return bool(world_state.query.get("raw"))

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Generate execution plan for user query."""
        query = world_state.query.get("raw", "")
        if not query:
            return {"deltaState": {"context": {"plan": {"steps": [], "status": "complete"}}}}
        # Try LLM planning first. Support limited retries for transient LLM failures.
        max_retries = 2
        if not self.llm:
            logger.info("PlanningAgent: No LLM client available; falling back to heuristic planning")
            return self._heuristic_plan(query)

        last_exc = None
        # Use the helper to request JSON from LLM
        full_prompt = self.planning_prompt.replace("{query}", query)
        parsed = self._llm_json_request(full_prompt, attempts=max_retries + 1)
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
            logger.warning("PlanningAgent: LLM failed to produce valid JSON plan after retries")

        # If we reach here, LLM planning failed after retries; fall back to heuristics
        logger.info(f"PlanningAgent: LLM planning failed after retries: {last_exc}; using heuristic fallback")
        return self._heuristic_plan(query)

    def _heuristic_plan(self, query: str) -> Dict[str, Any]:
        """Fallback heuristic planning when LLM fails."""
        q = query.lower()

        # Check for directions queries
        if any(word in q for word in ["directions", "get to", "how to get", "take me to", "from", "to"]):
            return {
                "deltaState": {
                    "context": {
                        "plan": {
                            "steps": [{"id": "S1", "action": "Directions", "args": {"destination": query}}],
                            "status": "planning",
                            "confidence": 0.8
                        },
                        "last_planning": {
                            "timestamp": str(datetime.utcnow()),
                            "agent": self.name,
                            "method": "heuristic"
                        }
                    }
                },
                "snippet": "Heuristic directions plan"
            }

        # Check for weather queries
        elif "weather" in q:
            if "me" in q or "here" in q or "my location" in q:
                steps = [
                    {"id": "S1", "action": "Geolocate", "args": {}},
                    {"id": "S2", "action": "Weather", "args": {}}
                ]
            else:
                location = query.replace("weather", "").replace("in", "").replace("for", "").strip()
                steps = [
                    {"id": "S1", "action": "Geocode", "args": {"address": location}},
                    {"id": "S2", "action": "Weather", "args": {}}
                ]

            return {
                "deltaState": {
                    "context": {
                        "plan": {
                            "steps": steps,
                            "status": "planning",
                            "confidence": 0.7
                        },
                        "last_planning": {
                            "timestamp": str(datetime.utcnow()),
                            "agent": self.name,
                            "method": "heuristic"
                        }
                    }
                },
                "snippet": f"Heuristic weather plan: {len(steps)} steps"
            }

        # Default to conversation
        else:
            return {
                "deltaState": {
                    "context": {
                        "plan": {
                            "steps": [{"id": "S1", "action": "Conversation", "args": {"message": query}}],
                            "status": "planning",
                            "confidence": 0.6
                        },
                        "last_planning": {
                            "timestamp": str(datetime.utcnow()),
                            "agent": self.name,
                            "method": "heuristic"
                        }
                    }
                },
                "snippet": "Heuristic conversation plan"
            }


class ExecutionAgent(BaseAgent):
    """LLM-powered ExecutionAgent that executes plan steps with intelligent reasoning."""

    def __init__(self):
        super().__init__("executor", "gemini-1.5-flash", 0.2)

    def get_name(self) -> str:
        """Return the agent\'s name."""
        return self.name

    def can_handle(self, world_state: WorldState) -> bool:
        """Execution agent can handle when there\'s a plan with steps."""
        plan = world_state.context.get("plan", {})
        steps = plan.get("steps", [])
        return len(steps) > 0

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Use LLM reasoning to execute the plan steps intelligently."""
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

        # Generate final response using LLM
        if self.llm:
            try:
                logger.info("ExecutionAgent: Generating final response")
                context_summary = self._prepare_context_summary(world_state, execution_results)

                response_prompt = f"""
You are the Execution Agent for a transportation assistant. Based on the executed tool results, provide a helpful final response.

User query: {query}
Tool execution results: {context_summary}

Guidelines:
- For directions: Provide clear route information with transit/walking options
- For weather: Include temperature, conditions, and relevant details
- For locations: Provide readable addresses, not coordinates
- Be helpful and provide complete answers
- If something went wrong, provide graceful fallback responses

Provide a natural language response to: {query}
"""

                response = self.llm.invoke(response_prompt)
                final_response = response.content.strip()

                # Log LLM usage
                try:
                    usage = response.usage_metadata
                    log_llm_usage(
                        agent=self.name,
                        model=self.llm.model,
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
- Directions: Get directions between locations (handles geolocation/geocoding automatically)
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
        tool_selection_prompt = execution_prompt + "\n\nPlease think step-by-step and explain which tools you would use and why. Then, provide a JSON list of tools at the end in the format: {'tools':[{'name':'ToolName','args':{...}}], 'notes': 'optional'}"
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

        # If tool selection succeeded, execute the selected tools
        if tools_plan:
            logger.info(f"ExecutionAgent: Executing selected tools: {tools_plan}")

            # Function to substitute placeholders like {{slots.origin.lat}}
            def substitute_placeholders(value, world_state):
                if isinstance(value, str) and '{{' in value and '}}' in value:
                    import re
                    def replacer(match):
                        path = match.group(1).strip()
                        parts = path.split('.')
                        obj = world_state
                        try:
                            for part in parts:
                                if hasattr(obj, part):
                                    obj = getattr(obj, part)
                                elif isinstance(obj, dict) and part in obj:
                                    obj = obj[part]
                                else:
                                    raise AttributeError(f"Cannot access {part} on {obj}")
                            return obj
                        except (AttributeError, KeyError, TypeError):
                            return match.group(0)  # return original if not found
                    return re.sub(r'\{\{([^}]+)\}\}', replacer, value)
                return value

            # helper to merge tool output into results
            def _merge_tool_output(tool_name, out):
                if not isinstance(out, dict):
                    return
                # slots
                if out.get('slots'):
                    try:
                        # merge slot dicts
                        for k, v in out.get('slots', {}).items():
                            results['slots'][k] = v
                    except Exception:
                        pass
                # context
                if out.get('context'):
                    try:
                        for k, v in out.get('context', {}).items():
                            results['context'][k] = v
                    except Exception:
                        pass
                # any other top-level keys (raw, etc.) attach under context
                for k, v in out.items():
                    if k not in ('slots', 'context'):
                        results['context'][f"{tool_name}_{k}"] = v

            for tool in tools_plan:
                tool_name = tool.get('name')
                tool_args = tool.get('args', {}) or {}
                # Substitute placeholders in args
                tool_args = {k: substitute_placeholders(v, world_state) for k, v in tool_args.items()}

                try:
                    # Use .invoke on tools (langchain BaseTool) with a dict input
                    if tool_name == "Geolocate":
                        result = geolocate_user.invoke({})
                    elif tool_name == "Geocode":
                        result = geocode_place.invoke({"address": tool_args.get('address', tool_args.get('query', tool_args.get('location', ''))), "slot": tool_args.get('slot', 'origin')})
                    elif tool_name == "ReverseGeocode":
                        lat = tool_args.get('lat') or (current_slots.get('origin') or {}).get('lat')
                        lng = tool_args.get('lng') or (current_slots.get('origin') or {}).get('lng')
                        result = reverse_geocode.invoke({"lat": lat, "lng": lng}) if lat is not None and lng is not None else None
                    elif tool_name == "Weather":
                        slot = tool_args.get('slot', 'origin')
                        lat = tool_args.get('lat') or (current_slots.get(slot) or {}).get('lat')
                        lng = tool_args.get('lng') or (current_slots.get(slot) or {}).get('lng')
                        units = (world_state.context.get('units') or world_state.user.get('units') or 'imperial')
                        if lat is None or lng is None:
                            raise ValueError("Missing coordinates for Weather tool")
                        result = weather_current.invoke({"lat": lat, "lng": lng, "units": units})
                        if result and 'context' in result and 'lastWeather' in result['context']:
                            slot_used = tool_args.get('slot', 'origin')
                            result['context'][f'lastWeather_{slot_used}'] = result['context'].pop('lastWeather')
                    elif tool_name == "Directions":
                        # Fill destination/origin from slots if not provided
                        if not tool_args.get('destination'):
                            dest_name = current_slots.get('destination', {}).get('name')
                            if dest_name:
                                tool_args['destination'] = dest_name
                        if not tool_args.get('origin'):
                            origin_name = current_slots.get('origin', {}).get('name')
                            if origin_name:
                                tool_args['origin'] = origin_name
                        result = directions.invoke({"destination": tool_args.get('destination', ''), "origin": tool_args.get('origin')})
                    elif tool_name == "Conversation":
                        result = handle_conversation.invoke({"message": tool_args.get('message', query)})
                    else:
                        logger.warning(f"ExecutionAgent: Unknown tool: {tool_name}")
                        continue

                    logger.info(f"ExecutionAgent: Tool {tool_name} executed successfully: {result}")
                    results["tools_executed"].append(tool_name)
                    _merge_tool_output(tool_name, result)
                    current_slots.update(results['slots'])

                except Exception as e:
                    logger.warning(f"ExecutionAgent: Error executing tool {tool_name}: {e}")
                    results["errors"].append(f"Error executing tool {tool_name}: {e}")

            return results

        # Fallback: Execute plan steps one by one
        logger.info("ExecutionAgent: Falling back to per-step execution")
        for step in steps:
            action = step.get("action")
            args = step.get("args", {})

            try:
                if action == "Geolocate":
                    result = geolocate_user.invoke({})
                elif action == "Geocode":
                    result = geocode_place.invoke({"address": args.get("address", args.get('query', ''))})
                elif action == "ReverseGeocode":
                    lat = args.get("lat") or (current_slots.get('origin') or {}).get('lat')
                    lng = args.get("lng") or (current_slots.get('origin') or {}).get('lng')
                    result = reverse_geocode.invoke({"lat": lat, "lng": lng}) if lat and lng else None
                elif action == "Weather":
                    lat = args.get("lat") or (current_slots.get('origin') or {}).get('lat')
                    lng = args.get("lng") or (current_slots.get('origin') or {}).get('lng')
                    units = (world_state.context.get('units') or world_state.user.get('units') or 'imperial')
                    result = weather_current.invoke({"lat": lat, "lng": lng, "units": units}) if lat is not None and lng is not None else None
                elif action == "Directions":
                    result = directions.invoke({"destination": args.get("destination", ""), "origin": args.get('origin')})
                else:
                    logger.warning(f"ExecutionAgent: Unknown action: {action}")
                    continue

                logger.info(f"ExecutionAgent: Action {action} executed successfully: {result}")
                results["tools_executed"].append(action)
                # Update slots/context with the result
                if isinstance(result, dict):
                    # merge slots and context
                    if result.get('slots'):
                        try:
                            for k, v in result.get('slots', {}).items():
                                results['slots'][k] = v
                        except Exception:
                            pass
                    if result.get('context'):
                        try:
                            for k, v in result.get('context', {}).items():
                                results['context'][k] = v
                        except Exception:
                            pass
                    # other keys -> context
                    for k, v in result.items():
                        if k not in ('slots', 'context'):
                            results['context'][k] = v

            except Exception as e:
                logger.warning(f"ExecutionAgent: Error executing action {action}: {e}")
                results["errors"].append(f"Error executing action {action}: {e}")

        return results

    def _prepare_context_summary(self, world_state: WorldState, execution_results: dict) -> dict:
        """Produce a compact summary of world_state + execution results for LLM prompt.

        Uses compact_world_state to reduce prompt size and attaches tool execution summary.
        """
        try:
            compact = compact_world_state(world_state)
        except Exception:
            compact = {}

        summary = {
            "compact_world": compact,
            "tools_executed": execution_results.get('tools_executed', []),
            "errors": execution_results.get('errors', [])
        }
        return summary

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
            mode = td.get('mode') or td.get('transit_directions', {}).get('mode')
            if mode:
                return f"I found {mode} directions for you. See details above."

        # Last resort
        errors = execution_results.get('errors', [])
        if errors:
            return f"I attempted to run some tools but encountered errors: {errors[0]}"

        return "I couldn't determine your location. Please provide an address or allow location access."

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
            mode = td.get('mode') or td.get('transit_directions', {}).get('mode')
            if mode:
                return f"I found {mode} directions for you. See details above."

        # Last resort
        errors = execution_results.get('errors', [])
        if errors:
            return f"I attempted to run some tools but encountered errors: {errors[0]}"

        return "I couldn't determine your location. Please provide an address or allow location access."
