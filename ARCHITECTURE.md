<p align="center">
  <h1>🗺️ Vaya – System Architecture</h1>
  <p><em>Modular multi-agent conversational AI for urban navigation and travel</em></p>
</p>

---


## 📖 Overview

Vaya is a modular, multi-agent conversational AI system for urban navigation and city travel. It features a centralized LLM-driven supervisor (Gemini) that handles all natural language understanding (NLU), query routing, and response synthesis. Specialist agents (weather, transit, traffic, maps, chit-chat) are lightweight, stateless, and API-focused, with robust fallbacks for missing or ambiguous data. The system is optimized for multi-query handling (e.g., "weather here and in Miami"), and is designed for **extensibility, maintainability, and cost-effective deployment** (local Python, Docker, or cloud).

---


## 🔄 High-Level Flow

User Input (CLI, API, WhatsApp)
→ `main.py` / `server.py` (entrypoints)
→ `supervisor.py` (LLM: NLU, routing, NLG, multi-query handling)
→ `agents/specialists/*` (API calls: weather, maps, traffic, transit; LLM for chit-chat)
→ `supervisor.py` (LLM synthesis, fallback handling)
→ Output to user (CLI, WhatsApp via Twilio, web UI, etc.)

---


## ⚙️ Key Components & File-by-File Guide

- **main.py** — CLI entrypoint for local dev/testing. Handles user input, session memory, and passes queries to the supervisor agent. Attempts to determine a default user location at startup.
- **server.py** — FastAPI web server for API, WhatsApp, and web UI. Exposes endpoints for chat, Twilio webhook, and health checks. Handles context passing and session management.
- **agents/supervisor.py** — The "brain" of the system:
  - Uses Gemini LLM for all NLU (intent/entity extraction), query routing, and NLG (response synthesis).
  - Handles multi-query input (e.g., "weather here and in Miami").
  - Implements robust fallback logic: if a specialist fails or data is missing, supervisor gracefully explains or suggests alternatives.
  - Only the supervisor and chit-chat agent use the LLM; all other specialists are pure API wrappers.
  - Orchestrates the full agent pipeline and returns a single, natural response.
- **agents/specialists/** — Domain-specific, stateless helpers:
  - `maps.py` — Geocoding, directions, and place search (Google Maps APIs). No LLM; uses supervisor-extracted info.
  - `traffic.py` — Real-time road traffic and travel time (Google Routes API). Returns mock data if API key is missing.
  - `transit.py` — Public transit status, delays, and disruptions (Transitland API). Returns mock data if API key is missing.
  - `weather.py` — Weather conditions and forecasts (Google Weather API). No LLM; processes structured supervisor data. Handles explicit time/location, geocoding, and fallback to last known or default location.
  - `chitchat.py` — Handles greetings, fallback, and small talk. Uses Gemini LLM for open-ended conversation and user guidance. If LLM is unavailable, returns a friendly default message.
- **utils/logger.py** — Centralized logging setup. Ensures consistent log formatting, file/console output, and prevents duplicate logs.
- **utils/google_maps.py** — Utility functions for geocoding, IP-based location lookup, and address parsing using Google Maps APIs.
- **logs/app.log** — Log file output (if enabled).
- **tests/** — Automated tests for agent routing and integration:
  - `test_routing.py` — Tests agent/supervisor routing logic.
  - `conftest.py` — Pytest fixtures for test setup.
- **requirements.txt** — Python dependencies.
- **.env.example** — Example environment variable file (API keys, config).
- **docker-compose.yml** — Container orchestration for local/prod deployment.

---


## 🧩 Agent Roles & Fallbacks

### Supervisor (LLM-Centric)
- Uses Gemini LLM for all natural language understanding (NLU), query parsing, and response generation (NLG).
- Extracts intents, times, places, and multi-query structure from user input.
- Routes queries to the appropriate specialists, including handling multiple requests in a single input.
- Synthesizes all specialist outputs into a single, natural response.
- Implements robust fallback logic:
  - If a specialist fails, returns an error, or data is missing, the supervisor explains the limitation and suggests alternatives.
  - If the user asks for unsupported features (e.g., weather 30 days out), supervisor gently explains boundaries.
- Only the supervisor and chit-chat agent use the LLM, keeping costs predictable and logic centralized.

### Specialists (Stateless, API-Driven)
- **weather, maps, traffic, transit** — Pure API wrappers. No LLM calls. Stateless and fast. Handle ambiguous/missing data by returning clear errors or using fallback locations.
- **chitchat** — Exception: uses Gemini LLM for open-ended conversation, greetings, and fallback when the user input is not actionable by other agents.
- All specialists return normalized outputs for supervisor integration.
- Modular and swappable by design. Each agent is a single file, easy to extend or replace.


---


## 📡 Data Flow (Detailed)

1. **User Input**: CLI, API, or WhatsApp (via Twilio)  
2. **Entrypoint**: `main.py` or `server.py` captures input and context  
3. **Supervisor**: Gemini parses, routes to specialists  
4. **Specialists**: Call APIs, return structured outputs  
5. **Supervisor**: Synthesizes everything into one response  
6. **Output**: Returned to CLI, FastAPI Server, or WhatsApp  

---


## 🔑 Technical Decisions & Optimizations

- **Centralized LLM**: Only the supervisor and chit-chat agent use Gemini. This keeps costs predictable, debugging simple, and logic centralized.
- **Multi-Query Optimization**: Supervisor can handle multiple requests in a single input (e.g., "weather here and in Miami"). Results are compiled and synthesized into a single, natural response.
- **Stateless by Default**: Each query is independent (session memory planned for future multi-turn conversations).
- **Direct Function Calls**: No LangChain `@tool` wrappers — all agent calls are explicit and debuggable.
- **Robust Fallbacks**: If a specialist fails or data is missing, supervisor and agents provide clear, user-friendly explanations and suggestions.
- **Environment-Driven Config**: All API keys and config via `.env` for security and portability.
- **Docker-First**: Local dev supported, but production deployment is optimized with Compose and health checks.

---

## 📂 File Structure (Expanded)

```
agents/
  supervisor.py         # LLM supervisor: NLU, routing, synthesis, fallback logic
  specialists/
    maps.py             # Geocoding, directions, place search (Google Maps APIs)
    traffic.py          # Real-time traffic, travel time (Google Routes API)
    transit.py          # Public transit status, delays (Transitland API)
    weather.py          # Weather conditions/forecasts (Google Weather API)
    chitchat.py         # Chit-chat, fallback, and small talk (Gemini LLM)
utils/
  logger.py             # Centralized logging setup
  google_maps.py        # Geocoding and IP-based location utilities
logs/
  app.log               # Log file output (if enabled)
tests/
  test_routing.py       # Automated agent/supervisor routing tests
  conftest.py           # Pytest fixtures for test setup
main.py                 # CLI entrypoint for local dev/testing
server.py               # FastAPI web server for API/WhatsApp/web UI
requirements.txt        # Python dependencies
.env.example            # Example environment variable file
docker-compose.yml      # Container orchestration for local/prod deployment
```
---

## 🧪 Test Suite Deep Dive

### Goals
- Fast (seconds) feedback loop
- Zero dependency on real API keys in CI
- Deterministic outputs (no LLM paraphrase drift)
- Validate routing, parsing, and compilation glue—not upstream vendor reliability

### Files
| File | Purpose |
|------|---------|
| `tests/conftest.py` | Session‑scoped supervisor fixture + environment setup (`TEST_MODE=1`, dummy `GOOGLE_GENAI_API_KEY`). |
| `tests/test_routing.py` | Assertions around query classification, agent selection, and response token presence. |

If more domains are added (e.g., pricing, alerts), prefer adding new focused test modules (`test_transit.py`, etc.) rather than bloating `test_routing.py`.

### `conftest.py` Mechanics
1. Inserts project root into `sys.path` (ensures direct import of `agents.supervisor`).
2. Forces a harmless dummy `GOOGLE_GENAI_API_KEY` so code paths that merely check key presence don’t crash.
3. Sets `TEST_MODE=1` to skip LLM instantiation and external calls.
4. Exposes a `supervisor_instance` fixture returning the callable supervisor entry function.

### Test Mode Behavior (Runtime)
When `TEST_MODE=1`:
- Supervisor sets `llm=None`.
- Query parsing: regex + keyword extraction for weather (“weather in X and Y”).
- Single / multi‑location weather responses: deterministic stub strings (`<City> now: 70F clear`).
- Chit‑chat: fixed friendly fallback if LLM absent.
- No specialist API call is required for multi‑location stubs (early short‑circuit). Single-location may still invoke lightweight specialist logic if desired, but remains deterministic.

### Assertions Strategy
Each test aims to assert STRUCTURE + INTENT, not style:
- Agent presence: `"Weather" in agent_names` or `"Chit_Chat"` chosen.
- Location tokens present for multi‑weather queries.
- No brittle string matching on full sentences (keeps refactors easy).

### Adding New Tests
1. Add or extend a stub path if the new feature would otherwise hit external APIs under `TEST_MODE`.
2. Write a test asserting minimal contract (e.g., agent routed + key field present in response dict).
3. Avoid over‑specifying natural language phrasing.
4. If introducing slow or real network tests, mark them:
  ```python
  @pytest.mark.external
  def test_real_weather_live(): ...
  ```
  And exclude them from default CI runs (`pytest -m "not external"`).

### Common Pitfalls Avoided
- Flaky LLM responses: eliminated by stubs.
- Network rate limits / quota: avoided in CI.
- JSON shape drift from external providers: not asserted in core tests (could be covered by optional integration layer later).

### Extension Ideas
- Add schema validation with Pydantic models for agent outputs, then assert `.model_validate()` in tests.
- Introduce property-based tests (Hypothesis) for parsing edge cases (“weather in   New   York and    Tokyo”).
- Snapshot test (optional) for multi‑agent synthesis once style stabilizes.

### Why Not More Tests Yet?
Deliberately minimal to keep maintenance friction low while core architecture evolves. As APIs stabilize, layer deeper validation iteratively.

---

## ✅ Summary

Vaya is designed to be modular, extensible, and easy to evolve. Its centralized LLM supervisor, agent fallbacks, and clear separation of concerns make it straightforward to extend, debug, and deploy in local or experimental environments. The file-by-file structure and explicit agent roles also help new contributors onboard quickly and understand how each piece fits together. While the architecture lays a strong foundation, production-grade hardening (security, scaling, monitoring) would be needed before a real deployment

---