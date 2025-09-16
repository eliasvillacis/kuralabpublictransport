# agents/supervisor.py
import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    Runnable, RunnableParallel, RunnablePassthrough, RunnableLambda
)

from utils.logger import get_logger
from .specialists.weather import create_weather_agent
from .specialists.traffic import create_traffic_agent
from .specialists.transit import create_transit_agent
from .specialists.maps import create_maps_agent

logger = get_logger(__name__)

def create_supervisor() -> Runnable:
    # --- LLM and agent map setup ---
    api_key = os.getenv("GOOGLE_GENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_GENAI_API_KEY in environment")

    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0,  # Lower temperature for more consistent outputs
        google_api_key=api_key,
        convert_system_message_to_human=False
    )

    agent_factory_map = {
        "Weather": create_weather_agent,
        "Traffic": create_traffic_agent,
        "Transit": create_transit_agent,
        "Maps": create_maps_agent,
    }
    # Wrap each agent so it always returns a dict, never a RunnableLambda
    def _wrap_agent(agent):
        def wrapped(x):
            # Always use .invoke(x) for langchain agents
            if hasattr(agent, "invoke") and callable(agent.invoke):
                return agent.invoke(x)
            # If agent is a plain function, call it
            if callable(agent):
                return agent(x)
            raise TypeError(f"Agent is not callable or invokable: {type(agent)}")
        return wrapped
    agent_map = {name: _wrap_agent(factory()) for name, factory in agent_factory_map.items()}

    # --- Deterministic keyword agent helper ---
    def _keyword_agents(user_query: str) -> list[str]:
        import re
        q = user_query.lower()
        hits = set()
        if re.search(r"\b(where am i|my location|current location|where\s+are\s+we)\b", q):
            hits.add("Maps")
        if re.search(r"\b(map|route|directions?|address|geocode|place)\b", q):
            hits.add("Maps")
        if re.search(r"\b(weather|temperature|temp|forecast|raining|snow(ing)?|wind|humidity|later|tonight|tomorrow)\b", q):
            hits.add("Weather")
        if re.search(r"\b(traffic|congestion|accident|delay on|i-?\d{1,3})\b", q):
            hits.add("Traffic")
        if re.search(r"\b(subway|bus|train|metro|tram|mta|next (bus|train)|arrive by|depart at)\b", q):
            hits.add("Transit")
        return sorted(hits)

    # --- LLM-based extraction helper ---
    def extract_query_info(query: str, history: str = "") -> dict:
        prompt = ChatPromptTemplate.from_template(
            "You are an intelligent routing system for a transportation assistant. Your job is to understand what the user wants and determine which specialist agents to call.\n\n"
            "Available Specialist Agents:\n"
            "- Weather: Provides current weather conditions, temperature, wind, humidity for any location\n"
            "- Traffic: Provides real-time traffic conditions, route planning with traffic data, travel times\n"
            "- Transit: Provides public transportation schedules, delays, route information for buses/trains/subway\n"
            "- Maps: Provides location lookup, address geocoding, place search, basic directions\n\n"
            "Based on the user's query, determine which agents are needed and extract relevant information.\n"
            "Return ONLY a single valid JSON object as your entire output. Do NOT include any explanations, examples, markdown, or code blocks. Do NOT include any text before or after the JSON."
        )
        import ast, re
        response = None
        try:
            response = llm.invoke(prompt.format(query=query, history=history))
            content = response.content.strip()
            # Remove code block markers if present
            if content.startswith('```'):
                content = re.sub(r'^```[a-zA-Z]*', '', content).strip()
                if content.endswith('```'):
                    content = content[:-3].strip()
            # Remove lines with // comments or example lines
            content = '\n'.join([
                line for line in content.splitlines()
                if '//' not in line and not line.strip().startswith('**Example') and not line.strip().startswith('User Query:')
            ])
            # Find JSON object
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                try:
                    return json.loads(json_str)
                except Exception:
                    fixed = json_str.replace("'", '"')
                    try:
                        return json.loads(fixed)
                    except Exception:
                        try:
                            return ast.literal_eval(json_str)
                        except Exception:
                            pass
            logger.error(f"Failed to extract or parse LLM response: {content}")
        except Exception as e:
            logger.error(f"Failed to extract or parse LLM response: {e} | {getattr(response, 'content', None)}")
        return {"query_type": "general", "is_chit_chat": False}
    import re

    def route_query(context):
        """Route the query to appropriate agents based on extracted information."""
        user_query = context.get("query", "") or context.get("input", "")
        history = context.get("history", "")
        
        # Extract query information directly
        query_info = extract_query_info(user_query, str(history))

        # Add origin/destination to the context if they're available
        if query_info.get("origin"):
            context["origin"] = query_info["origin"]
        if query_info.get("destination"):
            context["destination"] = query_info["destination"]

        logger.debug(f"[QUERY INFO] {json.dumps(query_info)}")

        # Handle new LLM output schema: if 'error' is present and not null, treat as chit-chat/unprocessable
        if query_info.get("error"):
            logger.debug(f"[ROUTING] LLM returned error: {query_info['error']}")
            return []

        # Handle location setting requests directly
        if query_info.get("intent") == "set_location" and query_info.get("user_location"):
            logger.debug(f"[ROUTING] Location setting detected: '{query_info.get('user_location')}'")
            context["set_location"] = query_info.get("user_location")
            return []  # No agents, supervisor will handle location setting

        # Handle chit-chat, future forecasts, or past queries directly
        if query_info.get("is_chit_chat", False) or query_info.get("intent") == "general_conversation":
            logger.debug(f"[ROUTING] Chit-chat detected for query: '{user_query}'")
            return []  # No agents, supervisor will respond directly

        # Handle future forecast requests (beyond what our weather specialist can handle)
        if query_info.get("is_future_forecast", False):
            logger.debug(f"[ROUTING] Future forecast request detected: '{user_query}'")
            return []  # Handle with a friendly explanation about limitations

        # Handle past data requests (we don't have historical data)
        if query_info.get("is_past_query", False):
            logger.debug(f"[ROUTING] Past data request detected: '{user_query}'")
            return []  # Handle with a friendly explanation about limitations

        # Handle new LLM output schema: extract agent names from 'agents' array
        agent_names = []
        if isinstance(query_info.get("agents"), list):
            for agent in query_info["agents"]:
                if isinstance(agent, dict) and "agent" in agent and agent["agent"]:
                    agent_names.append(agent["agent"])

        # Fallback: if no agents found, use legacy logic
        if not agent_names:
            logger.debug("[ROUTING] No agents found in 'agents' array, falling back to legacy routing")
            # Use the explicit needs flags (legacy fallback)
            if query_info.get("needs_weather", False):
                agent_names.append("Weather")
            if query_info.get("needs_traffic", False):
                agent_names.append("Traffic")
            if query_info.get("needs_transit", False):
                agent_names.append("Transit")
            if query_info.get("needs_maps", False):
                agent_names.append("Maps")
            # Also infer from intent if needs flags aren't set
            intent = query_info.get("intent", "").lower()
            if "weather" in intent and "Weather" not in agent_names:
                agent_names.append("Weather")
            if "traffic" in intent and "Traffic" not in agent_names:
                agent_names.append("Traffic")
            if "transit" in intent and "Transit" not in agent_names:
                agent_names.append("Transit")
            if any(x in intent for x in ["direction", "map", "route", "location"]) and "Maps" not in agent_names:
                agent_names.append("Maps")
            # Also use query_type for backward compatibility
            if query_info.get("query_type") == "route_request" and "Maps" not in agent_names:
                agent_names.append("Maps")
            if query_info.get("query_type") == "transit_info" and "Transit" not in agent_names:
                agent_names.append("Transit")
            if query_info.get("query_type") == "weather_info" and "Weather" not in agent_names:
                agent_names.append("Weather")
        if query_info.get("query_type") == "traffic_info" and "Traffic" not in agent_names:
            agent_names.append("Traffic")

        # Save origin/destination to context if present
        if query_info.get("origin"):
            context["origin"] = query_info["origin"]
        if query_info.get("destination"):
            context["destination"] = query_info["destination"]

        # Fallback if no agents selected
        if not agent_names:
            agent_names = ["Weather"]  # Default fallback

        logger.debug(f"[ROUTING OUTPUT] agents={agent_names}")
        return agent_names

    def compile_results(params):
        """
        Compile specialist agent results into a final natural language response.
        
        This is the core NLG (Natural Language Generation) component that takes
        structured data from specialist agents and creates a coherent, conversational
        response for the user. It uses the LLM to synthesize information from multiple
        specialists into a single unified response.
        """
        try:
            # Include location context information for better responses
            origin_context = f"Origin: {params.get('origin')}" if params.get('origin') else ""
            destination_context = f"Destination: {params.get('destination')}" if params.get('destination') else ""
            location_context = "\n".join(filter(None, [origin_context, destination_context]))
            
            prompt_text = f"""You are Vaya, a conversational GPS assistant for urban navigation. Synthesize the results from the specialist agents into a clear, concise response.

Your core purpose: Help people navigate their immediate surroundings primarily via walking and public transportation. Never suggest driving directions or car-related information.

Response Guidelines:
1. ALWAYS include ALL information from ALL agents that provided useful data.
2. If user asks for both weather AND location, provide BOTH pieces of information.
3. For weather, you MUST explicitly state the temperature (in Fahrenheit), main conditions, wind speed, and humidity using the exact values from the JSON results. Do not summarize, generalize, or omit these details. If there are any hazards or warnings (e.g., rain, snow, storms, high winds, extreme heat/cold), mention them directly as found in the JSON.
4. Do not use phrases like "looks pleasant" or "nice weather"—always give the actual numbers and conditions.
5. If you have general area information (like "Queens, NY"), use it confidently.
6. Only mention limitations if you truly cannot provide the requested information.
7. When explaining limitations about distant locations, do NOT provide unsolicited local information.
8. Keep responses focused - only provide what was specifically requested or directly relevant.

Key constraints to communicate when necessary:
1. You focus ONLY on the user's current location and immediate surroundings.
2. For information about distant locations, explain you're designed for local navigation and can't provide information about distant places.
3. For weather beyond 24 hours or historical data, briefly suggest a specialized app.
4. Always prioritize walking and public transit options over driving.

When presenting weather, always include:
- The temperature (in Fahrenheit)
- The main weather conditions (e.g., cloudy, sunny, raining, snowing)
- Any important hazards or warnings (e.g., storms, high winds, extreme heat/cold)
- Wind speed and humidity if available

Do not summarize or omit weather details—always state the temperature, conditions, wind speed, and humidity as numbers/values from the JSON.

Keep responses brief and to the point. Use 1-3 sentences. When users ask about distant places, ONLY explain your limitations and suggest alternatives - do not provide unrelated local information. Your final response should be in plain text, not JSON.

Conversation History:
{params.get('history', 'No previous conversation.')}

User's Latest Query: {params.get('query', '')}

{location_context if location_context else ""}

Specialist JSON Results:
{params.get('results', 'No results available')}"""
            response = llm.invoke(prompt_text)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"Compilation failed: {e}")
            return f"I'm sorry, I encountered an error processing your request: {str(e)}"

    def _sanitize_and_log(x):
        picks = x.get("agent_names", [])
        picks = [p.strip() for p in picks if p and p.strip()]
        seen = set()
        picks = [p for p in picks if p in agent_map and not (p in seen or seen.add(p))]
        x["agent_names"] = picks
        q = (x.get("input") or x.get("query") or "")[:120]
        logger.debug(f"[ROUTER] query='{q}' -> agents={picks}")
        return x

    def _invoke_selected(x):
        selected = x["agent_names"]
        if not selected:
            return {"note": "No specialists selected. Providing a general response."}
        # Always unwrap RunnableParallel result immediately
        parallel = RunnableParallel({name: agent_map[name] for name in selected})
        result = parallel.invoke(x)
        # If result is a Runnable, unwrap
        if hasattr(result, "invoke") and callable(result.invoke):
            return result.invoke(x)
        if callable(result) and not isinstance(result, dict):
            return result(x)
        return result

    def _extract_last_location(agent_results: dict) -> dict | None:
        """
        Prefer Maps location if present; otherwise fall back to Weather metadata.
        Returns a dict like: {"lat": ..., "lon": ..., "label": ..., "accuracy": ...} or None.
        """
        # 1) Prefer Maps (explicit lat/lon/address)
        maps_result = agent_results.get("Maps")
        if isinstance(maps_result, dict) and "latitude" in maps_result and "longitude" in maps_result:
            return {
                "lat": maps_result["latitude"],
                "lon": maps_result["longitude"],
                "label": maps_result.get("address", "Unknown Location"),
                "accuracy": maps_result.get("accuracy")
            }

        # 2) Weather may carry metadata on the result object (.metadata) or under ["metadata"]
        weather_result = agent_results.get("Weather")
        if weather_result is not None:
            # attribute-style metadata
            meta = getattr(weather_result, "metadata", None)
            if isinstance(meta, dict) and isinstance(meta.get("weather_location"), dict):
                wl = meta["weather_location"]
                if all(k in wl for k in ("lat", "lon")):
                    return {
                        "lat": wl["lat"],
                        "lon": wl["lon"],
                        "label": wl.get("label", "Unknown Location"),
                        "accuracy": wl.get("accuracy")
                    }
            # dict-style metadata
            if isinstance(weather_result, dict):
                m = weather_result.get("metadata")
                if isinstance(m, dict) and isinstance(m.get("weather_location"), dict):
                    wl = m["weather_location"]
                    if all(k in wl for k in ("lat", "lon")):
                        return {
                            "lat": wl["lat"],
                            "lon": wl["lon"],
                            "label": wl.get("label", "Unknown Location"),
                            "accuracy": wl.get("accuracy")
                        }

        return None

    def process_query(x):
        """
        Main supervisor logic for the centralized LLM architecture.
        
        Process flow:
        1. LLM-based NLU: Extract key information directly from the query
        2. Routing: Determine which specialist agents to call
        3. Information passing: Pass structured data to selected specialists
        4. Specialist processing: Specialists process data without their own LLMs
        5. LLM-based NLG: Synthesize specialist results into a coherent response
        
        This architecture centralizes LLM use in the supervisor, making specialists
        more efficient as pure API processors.
        """
        user_input = x.get("input", "")
        history = x.get("history", "No previous conversation.")
        logger.debug(f"[PROCESS_QUERY] input='{(user_input or '')[:120]}', history_len={len(history) if isinstance(history, list) else 'na'}")

        # Step 1: Extract info and route to get agent names (empty list means chit-chat)
        routing_context = {
            "query": user_input, 
            "history": history,
            # Pass through the location context
            "last_location": x.get("last_location")
        }
        agent_names = route_query(routing_context)

        if not agent_names:
            # Check if this is a location setting request
            if routing_context.get("set_location"):
                location_to_set = routing_context.get("set_location")
                logger.debug(f"[SUPERVISOR] Handling location setting: '{location_to_set}'")
                
                try:
                    from utils.google_maps import geocode_place
                    new_location = geocode_place(location_to_set)
                    if new_location:
                        # Return a response that will trigger location update in main.py
                        return {
                            "response": f"Got it! I've set your location to {new_location.get('label', location_to_set)}. What can I help you with?",
                            "agent_names": [],
                            "metadata": {"new_user_location": new_location}
                        }
                    else:
                        return {
                            "response": f"I couldn't find that location. Please try being more specific with the address.",
                            "agent_names": [],
                            "metadata": {}
                        }
                except Exception as e:
                    logger.error(f"Error setting location: {e}")
                    return {
                        "response": "Sorry, I had trouble updating your location. Please try again.",
                        "agent_names": [],
                        "metadata": {}
                    }
            
            # Chit-chat: respond directly, skip specialists
            logger.debug(f"[SUPERVISOR] Responding to chit-chat directly: '{(user_input or '')[:120]}'")
            
            # Get location context for chat
            location_context = ""
            last_location = x.get("last_location")
            if last_location:
                location_context = f"\n\nCurrent context: The user is in {last_location}."
            
            # For chit-chat, let the LLM handle it directly
            chat_prompt = f"""You are Vaya, a conversational GPS assistant for urban navigation with a friendly, upbeat personality. 

Your core purpose and traits:
- Help navigate the user's immediate surroundings with enthusiasm
- Focus on walking and public transportation only
- Never suggest driving or car-related information
- Direct and concise communication with a touch of warmth
- Share occasional fun facts about neighborhoods or transit systems
- Express enthusiasm for sustainable transportation options
- Respond in complete but brief sentences (1-3 sentences)
- When asked about distant locations, explain your focus is on local navigation
- Remember you are designed for "here and now" navigation assistance
- Be confident and helpful with the location information you have
- Avoid saying "I can't" or expressing limitations unless absolutely necessary

Limitations to explain when needed:
- Focus on current or near-future travel needs
- For weather beyond 24 hours, recommend a weather app
- Specialize in real-time transportation questions
- Best with walking directions and public transit options{location_context}

Respond conversationally to this casual question: {user_input}"""
            try:
                response = llm.invoke(chat_prompt)
                chat_response = response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                chat_response = "How can I help you with public transportation today?"
                
            return {
                "response": chat_response,
                "agent_names": [],
                "metadata": {}
            }

        # Step 2: Prepare context for agents
        # Include extracted origin/destination if available
        x_with_agents = {
            "input": user_input,
            "history": history,
            "query": user_input,  # keep for agents that read 'query'
            "agent_names": agent_names,
            **{k: v for k, v in x.items() if k not in ["input", "history"]},
            # Add any extracted location info from routing
            **({"origin": routing_context.get("origin")} if "origin" in routing_context else {}),
            **({"destination": routing_context.get("destination")} if "destination" in routing_context else {})
        }
        x_sanitized = _sanitize_and_log(x_with_agents)

        # Step 3: Invoke selected agents
        agent_results = _invoke_selected(x_sanitized)

        # Step 4: Extract last_location from Maps or Weather
        last_location = None
        if isinstance(agent_results, dict):
            last_location = _extract_last_location(agent_results)

        # Step 5: Compile results
        compiler_params = {
            "query": user_input,
            "history": history,
            "results": agent_results,
            # Add origin/destination context for more natural responses
            "origin": x_with_agents.get("origin"),
            "destination": x_with_agents.get("destination")
        }
        final_response = compile_results(compiler_params)

        result = {
            "response": final_response,
            "agent_names": agent_names,
            "metadata": {"weather_location": last_location} if last_location else {}
        }
        # Final unwrapping: if result is a Runnable, unwrap
        if hasattr(result, "invoke") and callable(result.invoke):
            return result.invoke(x)
        if callable(result) and not isinstance(result, dict):
            return result(x)
        return result

    # Instead of returning a RunnableLambda, return a plain function or dict as required by main.py
    def supervisor_entry(x):
        result = process_query(x)
        # Final unwrapping: if result is a Runnable, unwrap
        if hasattr(result, "invoke") and callable(result.invoke):
            return result.invoke(x)
        if callable(result) and not isinstance(result, dict):
            return result(x)
        return result
    return supervisor_entry
