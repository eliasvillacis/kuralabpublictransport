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
from .specialists.chitchat import create_chit_chat_specialist

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
        "Chit_Chat": create_chit_chat_specialist,
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
            "You are a query parser for a transportation assistant. Analyze the user query and determine what they want.\n\n"
            "User Query: \"{query}\"\n\n"
            "Query Types to Identify:\n"
            "1. WEATHER: Any mention of weather, temperature, conditions, rain, snow, forecast, etc.\n"
            "2. TRANSIT: Public transportation, buses, trains, subways, schedules\n"
            "3. TRAFFIC: Traffic conditions, road conditions, drive times\n"
            "4. MAPS: Location lookup, directions, places, addresses\n"
            "5. CHIT_CHAT: Greetings, how are you, general conversation without specific requests\n\n"
            "For WEATHER queries (including 'what's the weather like', 'how's the weather', 'is it raining', etc.):\n"
            "{{\n"
            "  \"weather_requests\": [\n"
            "    {{\"location\": \"LOCATION_OR_current_location\", \"time\": \"TIME_OR_now\"}}\n"
            "  ],\n"
            "  \"agents\": [\"Weather\"],\n"
            "  \"query_type\": \"weather\"\n"
            "}}\n\n"
            "For CHIT_CHAT (greetings, casual conversation):\n"
            "{{\n"
            "  \"query_type\": \"chit_chat\",\n"
            "  \"agents\": [\"Chit_Chat\"]\n"
            "}}\n\n"
            "For other agent types, follow similar patterns.\n\n"
            "IMPORTANT: 'what's the weather like' = weather request, not chit-chat!\n"
            "Return ONLY valid JSON. No explanations, no markdown, no code blocks."
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
            # Check if this is a single weather request and enhance accordingly
            is_single_weather = params.get('single_weather', False)
            time_ref = params.get('time_reference', 'now')
            location_ref = params.get('location_reference', '')

            # Compose location context for prompt clarity
            origin_context = f"Origin: {params.get('origin')}" if params.get('origin') else ""
            destination_context = f"Destination: {params.get('destination')}" if params.get('destination') else ""
            location_context = "\n".join(filter(None, [origin_context, destination_context]))

            # Enhanced prompt for more natural, contextual responses
            if is_single_weather:
                # --- Single weather request prompt construction ---
                # This block builds a conversational, context-aware prompt for the LLM
                user_location = params.get('user_location', {})
                user_location_label = user_location.get('label', 'your area') if user_location else 'your area'

                # Determine how to phrase the location in the response
                if location_ref in ['current_location', 'here', 'near me', 'my location']:
                    location_style = f"your current area ({user_location_label})"
                else:
                    location_style = location_ref

                # Phrase the time reference for natural language
                if time_ref == 'now':
                    time_style = "right now"
                elif 'hour' in time_ref:
                    time_style = f"{time_ref}"
                elif time_ref == 'tomorrow':
                    time_style = "tomorrow"
                else:
                    time_style = time_ref

                # Check if the query is about travel/arrival context
                query_lower = params.get('query', '').lower()
                has_travel_context = any(word in query_lower for word in ['land', 'arrive', 'get there', 'flight', 'trip', 'travel'])

                if has_travel_context:
                    context_instruction = "The user is asking about weather in the context of travel/arrival. Acknowledge this context naturally."
                else:
                    context_instruction = "This is a straightforward weather request."

                # Prompt template for the LLM
                prompt_text = f"""You are Vaya, a warm and friendly travel assistant. Provide weather information in a natural, conversational way.

Context: {context_instruction}
Location: {location_style}
Time: {time_style}
Query: "{params.get('query', '')}"

Guidelines:
- Be conversational and warm, but concise (1-2 sentences)
- Include the specific temperature, conditions, wind speed, and humidity from the JSON data
- If it's about travel/landing, acknowledge that context
- Don't use repetitive openings like "Hello!" every time
- Make it feel like helpful advice from a knowledgeable friend
- Vary your phrasing to sound natural

Weather Data:
{params.get('results', 'No results available')}

Provide a natural, friendly response:"""
            else:
                # Use the original prompt for non-weather or multi-agent responses
                # This block is for synthesizing results from multiple agents (e.g., transit, maps, weather)
                prompt_text = f"""You are Vaya, a conversational GPS assistant for public transport and walking. Synthesize the results from the specialist agents into a clear, concise, and friendly response.

Core purpose:
- Help people navigate cities and regions using public transportation and walking.
- Never suggest driving or car-related information.
- Provide weather, transit, and location information for any place the user requests, whether local or distant, as long as the user specifies it.
- If the user asks about multiple places or times, answer each clearly and helpfully.

Response Guidelines:
1. ALWAYS include ALL information from ALL agents that provided useful data.
2. If the user asks for both weather AND location, provide BOTH pieces of information.
3. For weather, explicitly state the temperature (in Fahrenheit), main conditions, wind speed, and humidity using the exact values from the JSON results. Mention any hazards or warnings (e.g., rain, snow, storms, high winds, extreme heat/cold) directly as found in the JSON.
4. Do not use phrases like "looks pleasant" or "nice weather"—always give the actual numbers and conditions.
5. If you have general area information (like "Queens, NY"), use it confidently.
6. Only mention limitations if you truly cannot provide the requested information (e.g., weather more than 10 days in advance, or unavailable data).
7. If the user asks about a distant location, answer if you have the data—do not restrict to local only.
8. Keep responses focused—only provide what was specifically requested or directly relevant.
9. Always prioritize walking and public transit options over driving.

When presenting weather, always include:
- The temperature (in Fahrenheit)
- The main weather conditions (e.g., cloudy, sunny, raining, snowing)
- Any important hazards or warnings (e.g., storms, high winds, extreme heat/cold)
- Wind speed and humidity if available

Do not summarize or omit weather details—always state the temperature, conditions, wind speed, and humidity as numbers/values from the JSON.

Keep responses brief, warm, and professional. Use 1-3 sentences per item. If you cannot answer a part of the user's question, gently explain why and suggest an alternative if possible. Your final response should be in plain text, not JSON.

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

    def compile_multi_weather_results(params):
        """
        Compile multiple weather requests into a single, natural, flowing response.

        Handles scenarios like "weather near me and in Miami" or "weather now and in 2 hours" by
        generating a conversational summary that covers all requested locations/times.
        """
        try:
            weather_collection = params.get('weather_collection', [])
            if not weather_collection:
                return "I couldn't get weather information for your request."
            
            user_location = params.get('user_location', {})
            user_location_label = user_location.get('label', 'your area') if user_location else 'your area'
            
            # Analyze the request pattern to choose the best response style
            locations = [item.get('location', '') for item in weather_collection]
            times = [item.get('time', 'now') for item in weather_collection]
            
            # Determine if this is multi-location, multi-time, or both
            # This helps the LLM structure the response naturally
            unique_locations = set(loc for loc in locations if loc not in ['current_location', 'here', 'near me', 'my location'])
            has_current_location = any(loc in ['current_location', 'here', 'near me', 'my location'] for loc in locations)
            unique_times = set(times)
            
            is_multi_location = len(unique_locations) > 0 and has_current_location
            is_multi_time = len(unique_times) > 1
            
            # Build context for the LLM prompt
            weather_details = []
            for item in weather_collection:
                location = item.get('location', 'unknown')
                time_ref = item.get('time', 'now')
                data = item.get('data', {})
                
                if data.get('error'):
                    continue
                    
                # Format location label
                if location in ['current_location', 'here', 'near me', 'my location']:
                    location_label = user_location_label
                else:
                    location_label = location
                    
                weather_details.append({
                    'location': location_label,
                    'time': time_ref,
                    'data': data
                })
            
            # Create natural language prompt based on the pattern
            if is_multi_location and is_multi_time:
                style_instruction = "You're providing weather for multiple locations at different times. Structure your response to flow naturally, mentioning each location and time clearly. Use transitions like 'Right now here in...' and 'When you're in...' or 'Later in...'"
            elif is_multi_location:
                style_instruction = "You're comparing weather in different places. Use natural transitions like 'Here in...' and 'Over in...' or 'In Miami, it's...' Make it feel like a friendly travel update."
            elif is_multi_time:
                style_instruction = "You're giving a time-based weather forecast for the same area. Create a flowing timeline like 'Right now...' and 'In an hour...' or 'When you land...' Connect the information naturally."
            else:
                style_instruction = "Provide a single, friendly weather update."
            
            prompt_text = f"""You are Vaya, a warm and conversational travel assistant. The user asked about weather, and you need to provide a natural, flowing response that doesn't sound robotic or repetitive.

{style_instruction}

Important guidelines:
- Don't start each sentence with "Hello!" or "Hi there!" - vary your openings
- Use natural transitions between different locations/times
- Include all the specific numbers (temperature, wind speed, humidity) from the data
- Make it sound like a friendly, knowledgeable local giving travel advice
- Be concise but warm - aim for 2-4 sentences total
- If it's about travel (like "when I land"), acknowledge that context

User's query: "{params.get('query', '')}"

Weather data to include:
{json.dumps(weather_details, indent=2)}

Provide a single, natural response that includes all the weather information in a conversational way:"""

            response = llm.invoke(prompt_text)
            return response.content if hasattr(response, 'content') else str(response)
            
        except Exception as e:
            logger.error(f"Multi-weather compilation failed: {e}")
            return "I'm having trouble putting together that weather information right now."

    def _sanitize_and_log(x):
        """
        Clean up and deduplicate agent names, then log the routing decision for debugging.
        """
        picks = x.get("agent_names", [])
        picks = [p.strip() for p in picks if p and p.strip()]
        seen = set()
        picks = [p for p in picks if p in agent_map and not (p in seen or seen.add(p))]
        x["agent_names"] = picks
        q = (x.get("input") or x.get("query") or "")[:120]
        logger.debug(f"[ROUTER] query='{q}' -> agents={picks}")
        return x

    def _invoke_selected(x):
        """
        Invoke the selected specialist agents in parallel and unwrap the result if needed.
        """
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
        Extract the most recent location from agent results.

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
        more efficient as pure API processors. This function is the main entry point for
        handling user queries and orchestrating agent collaboration.
        """
        user_input = x.get("input", "")
        history = x.get("history", "No previous conversation.")
        # Log the incoming query and history length for debugging
        logger.debug(f"[PROCESS_QUERY] input='{(user_input or '')[:120]}', history_len={len(history) if isinstance(history, list) else 'na'}")

        # Step 1: Extract all weather requests from the user query
        query_info = extract_query_info(user_input, str(history))
        # Log the extracted query info for traceability
        logger.debug(f"[QUERY INFO] {json.dumps(query_info)}")

        all_results = []  # Collects all agent responses
        all_agent_names = set()  # Tracks which agents were used
        last_location = None  # Tracks the most recent location for context

        # Handle weather requests (can be multiple for one query)
        weather_requests = []
        # Extract all weather requests from the query info
        if "weather_requests" in query_info and isinstance(query_info["weather_requests"], list):
            weather_requests = query_info["weather_requests"]
        elif "Weather" in query_info.get("agents", []):
            # Fallback: if no weather_requests but Weather agent is needed, create one request
            weather_requests = [{"location": query_info.get("destination") or query_info.get("origin") or "current_location", "time": "now"}]

        if weather_requests:
            # --- Handle weather requests (can be multiple for one query) ---
            for req in weather_requests:
                location = req.get("location", "current_location")
                time_ref = req.get("time", "now")
                # Prepare context for weather agent
                # This context is passed to the Weather specialist
                weather_context = {
                    "input": user_input,
                    "history": history,
                    "query": user_input,
                    "agent_names": ["Weather"],
                    **{k: v for k, v in x.items() if k not in ["input", "history"]},
                }
                # Add location context based on the request
                if location == "current_location" or location in ["here", "near me", "my location"]:
                    # Use last_location for current location requests
                    pass  # weather agent will use last_location by default
                else:
                    # Use the specified location
                    weather_context["destination"] = location
                # Add time reference if not 'now'
                if time_ref != "now":
                    weather_context["time_reference"] = time_ref

                logger.debug(f"[WEATHER REQUEST] location={location}, time={time_ref}")
                # Call weather agent and get the result
                try:
                    weather_agent = agent_map["Weather"]
                    weather_result = weather_agent(weather_context)
                    # Extract location metadata for context
                    if isinstance(weather_result, dict):
                        last_location = _extract_last_location({"Weather": weather_result}) or last_location
                    # Compile this weather result into a user-friendly response
                    compiler_params = {
                        "query": f"weather for {location}" + (f" {time_ref}" if time_ref != "now" else ""),
                        "history": history,
                        "results": {"Weather": weather_result}
                    }
                    final_response = compile_results(compiler_params)
                    all_results.append({
                        "response": final_response,
                        "agent_names": ["Weather"],
                        "metadata": {"weather_location": last_location} if last_location else {}
                    })
                    all_agent_names.add("Weather")
                except Exception as e:
                    logger.error(f"Error calling weather agent for {location}: {e}")
                    all_results.append({
                        "response": f"Sorry, I couldn't get weather information for {location} right now.",
                        "agent_names": [],
                        "metadata": {}
                    })

        # Handle non-weather queries (chit-chat, location setting, etc.)
        # This block handles fallback and non-weather scenarios
        if not weather_requests:
            # Check if this is a chit-chat request (general conversation)
            if query_info.get("query_type") == "chit_chat" or "Chit_Chat" in query_info.get("agents", []):
                logger.debug(f"[SUPERVISOR] Handling chit-chat request")
                try:
                    chit_chat_agent = agent_map["Chit_Chat"]
                    chat_result = chit_chat_agent(x)
                    return {
                        "response": chat_result.get("response", "Hello! How can I help you with transportation today?"),
                        "agent_names": ["Chit_Chat"],
                        "metadata": chat_result
                    }
                except Exception as e:
                    logger.error(f"Error calling chit-chat agent: {e}")
                    return {
                        "response": "Hello! I'm here to help you with weather, public transit, traffic conditions, and directions. What would you like to know?",
                        "agent_names": ["Chit_Chat"],
                        "metadata": {}
                    }
            # Check if this is a location setting request (user wants to set their location)
            elif query_info.get("intent") == "set_location" and query_info.get("user_location"):
                location_to_set = query_info.get("user_location")
                logger.debug(f"[SUPERVISOR] Handling location setting: '{location_to_set}'")
                try:
                    from utils.google_maps import geocode_place
                    new_location = geocode_place(location_to_set)
                    if new_location:
                        return {
                            "response": f"I've set your location to {new_location.get('label', location_to_set)}. What else can I help you with?",
                            "agent_names": [],
                            "metadata": {"new_user_location": new_location}
                        }
                    else:
                        return {
                            "response": f"I couldn't find that location. Could you be a bit more specific, lovely?",
                            "agent_names": [],
                            "metadata": {}
                        }
                except Exception as e:
                    logger.error(f"Error setting location: {e}")
                    return {
                        "response": "Sorry, I had a little trouble updating your location. Would you mind trying again?",
                        "agent_names": [],
                        "metadata": {}
                    }
            # Fallback: treat as general query - might need other agents
            else:
                logger.debug(f"[SUPERVISOR] Unrecognized query type, treating as chit-chat fallback")
                try:
                    chit_chat_agent = agent_map["Chit_Chat"]
                    chat_result = chit_chat_agent(x)
                    return {
                        "response": chat_result.get("response", "I'm not sure how to help with that. Could you ask about weather, transit, traffic, or directions?"),
                        "agent_names": ["Chit_Chat"],
                        "metadata": chat_result
                    }
                except Exception as e:
                    logger.error(f"Error in fallback chit-chat: {e}")
                    return {
                        "response": "I'm here to help with weather, public transit, traffic, and directions. What can I assist you with?",
                        "agent_names": [],
                        "metadata": {}
                    }

        # For multi-weather requests, compile all results intelligently
        # This block handles cases where the user asks for weather in multiple places/times
        if len(weather_requests) > 1:
            # Collect all weather data for intelligent compilation
            weather_data_collection = []
            for req in weather_requests:
                location = req.get("location", "current_location")
                time_ref = req.get("time", "now")
                # Prepare context for weather agent
                weather_context = {
                    "input": user_input,
                    "history": history,
                    "query": user_input,
                    "agent_names": ["Weather"],
                    **{k: v for k, v in x.items() if k not in ["input", "history"]},
                }
                # Add location context based on the request
                if location == "current_location" or location in ["here", "near me", "my location"]:
                    # Use last_location for current location requests
                    pass  # weather agent will use last_location by default
                else:
                    # Use the specified location
                    weather_context["destination"] = location
                # Add time reference if not 'now'
                if time_ref != "now":
                    weather_context["time_reference"] = time_ref

                logger.debug(f"[WEATHER REQUEST] location={location}, time={time_ref}")
                # Call weather agent and collect structured data
                try:
                    weather_agent = agent_map["Weather"]
                    weather_result = weather_agent(weather_context)
                    # Extract location metadata for context
                    if isinstance(weather_result, dict):
                        last_location = _extract_last_location({"Weather": weather_result}) or last_location
                    weather_data_collection.append({
                        "location": location,
                        "time": time_ref,
                        "data": weather_result,
                        "user_location": last_location
                    })
                    all_agent_names.add("Weather")
                except Exception as e:
                    logger.error(f"Error calling weather agent for {location}: {e}")
                    weather_data_collection.append({
                        "location": location,
                        "time": time_ref,
                        "data": {"error": str(e)},
                        "user_location": None
                    })
            # Compile all weather data into a single, natural response
            multi_weather_response = compile_multi_weather_results({
                "query": user_input,
                "history": history,
                "weather_collection": weather_data_collection,
                "user_location": x.get("last_location")
            })
            return {
                "response": multi_weather_response,
                "agent_names": list(all_agent_names),
                "metadata": {"weather_location": last_location} if last_location else {}
            }
        # Single weather request - use the existing individual compilation but with better styling
        # This block handles the case where only one weather request is present
        elif len(weather_requests) == 1:
            req = weather_requests[0]
            location = req.get("location", "current_location")
            time_ref = req.get("time", "now")
            # Prepare context for weather agent
            weather_context = {
                "input": user_input,
                "history": history,
                "query": user_input,
                "agent_names": ["Weather"],
                **{k: v for k, v in x.items() if k not in ["input", "history"]},
            }
            # Add location context based on the request
            if location == "current_location" or location in ["here", "near me", "my location"]:
                # Use last_location for current location requests
                pass  # weather agent will use last_location by default
            else:
                # Use the specified location
                weather_context["destination"] = location
            # Add time reference if not 'now'
            if time_ref != "now":
                weather_context["time_reference"] = time_ref

            logger.debug(f"[WEATHER REQUEST] location={location}, time={time_ref}")
            # Call weather agent and get the result
            try:
                weather_agent = agent_map["Weather"]
                weather_result = weather_agent(weather_context)
                # Extract location metadata for context
                if isinstance(weather_result, dict):
                    last_location = _extract_last_location({"Weather": weather_result}) or last_location
                # Compile this weather result with enhanced styling
                compiler_params = {
                    "query": user_input,
                    "history": history,
                    "results": {"Weather": weather_result},
                    "user_location": x.get("last_location"),
                    "single_weather": True,
                    "time_reference": time_ref,
                    "location_reference": location
                }
                final_response = compile_results(compiler_params)
                return {
                    "response": final_response,
                    "agent_names": ["Weather"],
                    "metadata": {"weather_location": last_location} if last_location else {}
                }
            except Exception as e:
                logger.error(f"Error calling weather agent for {location}: {e}")
                return {
                    "response": f"Sorry, I couldn't get weather information for {location} right now.",
                    "agent_names": [],
                    "metadata": {}
                }
        # Fallback (shouldn't happen with the new logic)
        return {
            "response": "I'm not sure how to help with that request.",
            "agent_names": [],
            "metadata": {}
        }

    # Instead of returning a RunnableLambda, return a plain function or dict as required by main.py
    def supervisor_entry(x):
        """
        Entry point for the supervisor agent.
        Handles unwrapping of results and ensures a plain dict or string is returned.
        """
        result = process_query(x)
        # Final unwrapping: if result is a Runnable, unwrap
        if hasattr(result, "invoke") and callable(result.invoke):
            return result.invoke(x)
        if callable(result) and not isinstance(result, dict):
            return result(x)
        return result
    return supervisor_entry
