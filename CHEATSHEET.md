
# Vaya Public Transport Assistant — Developer Cheat Sheet

**Deployment:**
- Production deployment is via [Render](https://render.com/) with a custom domain and web UI (React/Next.js or similar).
- Routing, geocoding, and weather are handled via Google APIs and Gemini LLM.


## 🚦 System Overview & Architecture

Vaya is a multi-agent, LLM-driven public transport assistant built for extensibility, reliability, and clarity. It uses a two-agent (A2A) architecture, modular tools, and a shared state (WorldState) for all agent communication. The system is designed for both research and production evolution.

### Core Design
- **A2A (Agent-to-Agent):**
  - **Planner Agent (LLM):** Interprets user intent, emits a structured plan (JSON steps).
  - **Executor Agent (LLM + tools):** Runs the plan, calls tools, merges results, and produces the final response.
- **WorldState (Blackboard):**
  - Central, structured state shared by all agents and tools.
  - All state changes are made by merging deltaState patches using `deepMerge()`.
- **Coordinator:**
  - Orchestrates Planner → Executor flow, manages memory, and handles error fallback.

### Data Flow (A2A)
```
User Input → Planner (LLM) → Plan (JSON steps) → Executor (LLM) → Tool Calls → Tool Results (deltaState) → deepMerge → Final Response
```
- All agent communication is via WorldState patches. No direct function calls between agents.

---

## 🧠 Agent Roles & LLMs

### 1. Planner (LLM)
- Reads user query from `WorldState`.
- Emits a structured plan (JSON: steps array with id, action, args).
- Uses Gemini LLM (low temperature) for deterministic, structured output.
- Handles ambiguous queries by requesting more info or fallback steps.

### 2. Executor (LLM + tools)
- Reads the plan from `WorldState`.
- Uses Gemini LLM to reason about dependencies, fill tool arguments, and select tool order.
- Runs each step by calling the appropriate tool (weather, directions, geocode, places search, etc.).
- Merges tool results into `WorldState` as deltaState patches.
- Produces the final user-facing response (`final_response` in `deltaState.context`).
- Handles tool errors gracefully, provides fallback answers, and autopatches plans as needed.
- **LLM Token Usage:**
  - All LLM calls (planning, execution, response generation) are logged with token counts and model info in `data/llm_token_log.csv` and `data/llm_token_log_summary.json`.
  - This enables cost tracking and usage analytics.

---

## 🗂️ File & Folder Guide

### /agents/
- `agents.py` — Main agent classes (PlanningAgent, ExecutionAgent). Handles LLM calls, plan parsing, tool invocation, slot resolution, autopatching, and context-aware follow-ups.
- `coordinator.py` — Orchestrates Planner → Executor flow, manages memory, and applies deltaState patches.
- `/tools/` — Modular tool implementations:
  - `weather_tool.py` — Weather via Google API
  - `directions_tool.py` — Transit/walking directions (uses geocode, placeId, or lat/lng)
  - `location_tool.py` — Geocoding/geolocation
  - `places_tool.py` — Google Places API (POI/brand search)
  - `conversation_tool.py` — Small talk, fallback

### /utils/
- `contracts.py` — Pydantic models for `WorldState`, `Slots`, etc.
- `state.py` — `deepMerge()` for patching state
- `logger.py` — Logging to `logs/app.log` and console
- `llm_logger.py` — Tracks LLM token usage and logs to disk
- `api_logger.py` — Tracks API call usage and logs to disk

### /data/
- `conversation_memory.json` — Persistent conversation memory
- `api_call_log.csv` / `api_call_log_summary.json` — API usage logs
- `llm_token_log.csv` / `llm_token_log_summary.json` — LLM token/cost logs

### /logs/
- `app.log` — System and error logs

### Root
- `main.py` — CLI entry point
- `requirements.txt` — Python dependencies
- `README.md` — Project documentation
- `ARCHITECTURE.md` — Deep-dive on system design

---

## 🧩 How the Process Works (Step-by-Step)

1. **User Input** → `main.py` (CLI or API)
2. **Coordinator** → Creates initial `WorldState`, starts Planner
3. **Planner (LLM)** → Emits plan (JSON steps)
4. **Executor (LLM)** →
    - Reads plan, reasons about tool order and arguments
    - Calls tools, merges results into WorldState
    - Handles slot/placeholder resolution, autopatching, and context memory
    - Produces final response
5. **Output** → Final response returned to user

All state changes are via deltaState patches merged with `deepMerge()`.

---

## 🛠️ Tool Pattern & Execution

- Tools are simple Python functions (decorated with `@tool("ToolName")`)
- Each tool returns a WorldState-compatible patch (not raw API data)
- Example:
  ```python
  @tool("Weather")
  def weather_current(lat: float, lng: float, units: str = "IMPERIAL") -> dict:
      api_data = call_external_api(lat, lng, units)
      return {
          "context": {
              "lastWeather": {
                  "lat": lat,
                  "lng": lng,
                  "units": units,
                  "data": api_data
              }
          }
      }
  ```
- Tool results are merged into `WorldState` by the Executor
- **Slot Reference Resolution & Autopatching:**
    - Slot reference resolution (e.g., mapping 'origin'/'destination' to lat/lng dicts) and autopatching (inserting missing steps like PlacesSearch or Geocode) are implemented as explicit Python logic, not LLM-driven. The LLM is not used for low-level slot resolution, placeholder substitution, or autopatching—these are handled by code for determinism and reliability.
- **LLM in Executor:**
    - The Executor uses the LLM for:
        - Reasoning about which tools to run and in what order, based on the plan and current state (`_execute_plan_with_llm_reasoning`).
        - Generating the final user-facing response in natural language, using a prompt that summarizes tool results and plan actions.
        - Optionally, for fallback or clarification (e.g., checking if a new destination is specified).
- **Summary:** The LLM in the Executor is for reasoning, response generation, and fallback planning—not for low-level slot resolution or autopatching, which are handled by code.

---

## 🧠 Memory & Context Handling

- **WorldState** is the single source of truth for all agents and tools.
- **Memory** is persisted in `/data/conversation_memory.json` and loaded at startup.
- **Context-aware follow-ups:**
  - After a POI search, the last results are stored in `world_state.context['last_places_results']`.
  - If the user says "directions to #2" or "take me to the third one", the Executor parses the reference, retrieves the correct place, and patches the plan to use its details.
  - This enables natural, multi-turn conversations and chained queries.
- **Slot Memory:**
  - Slots (origin, destination) are updated as tools run, and are used for context in future queries.
- **Evidence & Error Logging:**
  - All tool outputs and errors are logged in `context` and `errors[]` for debugging and auditing.

---

## 📊 API & LLM Token Tracking

- **API Calls:**
  - All tool/API calls are logged in `/data/api_call_log.csv` and `/data/api_call_log_summary.json`.
  - Includes endpoint, parameters, response time, and error info.
- **LLM Token Usage:**
  - All LLM calls (planning, execution, response generation) are logged with token counts and model info in `/data/llm_token_log.csv` and `/data/llm_token_log_summary.json`.
  - This enables cost tracking, usage analytics, and debugging.

---

## 🧪 Testing & Debugging

- **Unit Testing:**
  - Mock LLMs and tools for deterministic results
  - Test tool returns (WorldState patches)
  - Validate agent logic with controlled state
- **Integration Testing:**
  - Test full Planner → Executor → tool flow
  - Use `pytest` (see `tests/`)
- **Debugging:**
  - Check `logs/app.log` for errors
  - Dump `WorldState` after each step to trace merges
  - Tool evidence is stored in `context.<tool>_evidence` for auditing

---

## 🏗️ Common Dev Tasks

### Add a New Tool
1. Create a new file in `agents/tools/`
2. Use `@tool("ToolName")` decorator
3. Return a WorldState-compatible patch
4. Register tool in Executor's action handling
5. Update Planner logic if needed

### Add a New Agent
1. Create new agent class in `agents/agents.py`
2. Implement required methods (`can_handle`, `process`)
3. Register agent in `main.py` coordinator setup
4. Update coordinator logic if needed

### Debugging
1. Check `logs/app.log` for errors
2. Inspect `WorldState` after each step
3. Test tools directly with mock inputs

### Testing
- Run all tests: `pytest -q`
- See `tests/` for examples

---

## 🧭 Design Principles

- **Separation of concerns:** Planner plans, Executor executes, tools act
- **LLM-driven:** Both Planner and Executor are LLMs (Gemini via LangChain)
- **A2A via shared state:** All agent communication is through `WorldState`
- **Tool-based:** All real work is done by modular tools
- **Error resilience:** System continues even if some tools fail
- **Memory persistence:** Conversation memory is saved in `/data/`
- **Context-aware:** System supports chained queries and follow-ups referencing previous results
- **Token & API logging:** All LLM and API usage is tracked for cost and debugging

---

## 📝 Special CLI Commands

- `/status` — Show current system state
- `/memory` — Show conversation memory
- `/reset` — Reset conversation and state

---

## 📚 References

- See `ARCHITECTURE.md` for deep-dive
- See `README.md` for onboarding

---

**If in doubt, check the logs and inspect WorldState!**


