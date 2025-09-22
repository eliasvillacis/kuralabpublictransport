<!-- Copilot instructions for the Kura public-transport demo app -->
# Kura Public Transport Assistant - AI Coding Guidelines

## Architecture Overview

This project now uses a simplified, two-agent architecture for transportation assistance:

### Core Components
- **`main.py`**: CLI entry point with colorized output and user interaction loop
- **Planner (LLM)**: Responsible for understanding user intent and emitting a structured plan (JSON) describing the steps to satisfy the user's request. The Planner should prefer transit directions for routing queries, request geocoding/geolocation when needed, and include fallbacks (e.g., walking) when transit is not available.
- **Executor (LLM + tools)**: Runs the Planner's steps, calls tools (geocode, geolocate, transit/walking directions, weather, conversation), and returns the final assistant-facing result. The Executor's output is considered the final natural-language answer (there is no separate synthesizer agent).
- **`utils/contracts.py`**: Pydantic models defining WorldState, Slots, and data contracts
- **`utils/state.py`**: `deepMerge()` utility for applying state patches
- **`agents/tools/`**: Tool implementations (weather, location, directions, conversation) that return WorldState-compatible patches

### Data Flow Architecture
```
User Query → Planner (LLM) → Plan JSON → Executor (LLM + tools) → Tools → Delta States → deepMerge → Final Response (from Executor)
```

WorldState remains the canonical blackboard; agents communicate via deltaState patches merged with `deepMerge()`.

## Critical Developer Workflows

### Local Development Setup
```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment variables (.env file in project root)
GEMINI_API_KEY=your_gemini_key_here
GOOGLE_API_KEY=your_google_cloud_key_here

# 3. Run the CLI
python -m main
```

### Testing
```powershell
# Run tests
pytest -q

# Key testing patterns:
# - Mock LLM clients (Planner, Executor) in unit tests
# - Mock @tool functions to return deterministic deltaState patches
# - Test runTurn()/coordinator flows with mocked agents for integration testing
```

### Debugging
- **Logs**: Use `utils/logger.get_logger(__name__)` - outputs to `logs/app.log` and console
- **State tracing**: Dump WorldState after each executor step to inspect delta merges
- **Tool debugging**: Tools should return raw API responses inside `deltaState.context.<tool>_evidence` for auditing
- **LLM debugging**: Enable DEBUG logging to view planner prompts, executor reasoning, and parsed plan JSON

## Project-Specific Conventions

### LLM Instantiation Pattern
```python
from langchain_google_genai import ChatGoogleGenerativeAI

# Instantiate one client for Planner and one (optional) for Executor
self.planner = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.2, google_api_key=gemini_key)
self.executor_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.2, google_api_key=gemini_key)
```

Notes:
- The Planner should be the primary LLM that produces the structured plan. Keep Planner temperature low (0.0-0.3) for predictable JSON.
- The Executor may use a slightly stronger model if you want it to reason about tool outputs before creating the final answer. The Executor is responsible for producing the final natural-language response and must not hand that responsibility to any other component.

### Tool Implementation Pattern
```python
@tool("Weather")
def weather_current(lat: float, lng: float, units: str = "IMPERIAL") -> dict:
    """Return WorldState-compatible patch, not raw API data."""
    api_data = call_external_api(lat, lng, units)
    return {
        "context": {
            "lastWeather": {
                "lat": lat,
                "lng": lng,
                "units": units,
                "data": api_data  # Store raw API response for auditing
            }
        }
    }
```

### State Management
- Single source of truth: All state changes via `deepMerge()` from deltaState patches
- No direct mutation: Agents return patches, never modify WorldState directly
- Validation: Use Pydantic models in `utils/contracts.py` for type safety

### Executor Response Format
```json
{
  "deltaState": {"context": {"transit_directions": {...}, "final_response": "..." }},
  "snippet": "Human-friendly assistant summary"
}
```

Notes:
- The Executor should include a `final_response` text field inside `deltaState.context` when it has completed the user-facing reply.
- Tools should populate structured fields (e.g., `transit_directions`, `walking_directions`, `lastWeather`) and may include raw evidence under `context.*_evidence` for auditing.

### Error Handling
- Tools raise exceptions on API failures; agents should catch and append errors to `world_state.errors[]` via deltaState patches
- Executor should generate graceful, user-friendly fallback messages when tools fail (e.g., "Couldn't find transit routes; here's walking directions instead")
- Logger captures and persists exceptions in `logs/app.log`

## Integration Points

### External APIs
- Google Weather API: `https://weather.googleapis.com/v1/currentConditions:lookup`
- Google Maps API: via `googlemaps` library for geocoding
- Environment variables: `GOOGLE_API_KEY` for Google services, `GEMINI_API_KEY` for LLM

### Dependencies
- LLM: `langchain-google-genai` (Gemini models) or any compatible chat LLM wrapper
- Tools: LangChain `@tool` decorators or simple function wrappers that return WorldState-compatible patches
- State: Pydantic for validation, custom `deepMerge` for patches
- CLI: `colorama` for cross-platform colors

## Key Files to Reference

### Architecture Understanding
- `agents/planner.py` (or `agents/agents.py` Planner class): Planner logic and LLM prompt to produce plan JSON
- `utils/contracts.py`: WorldState and data model definitions
- `agents/executor.py` (or `agents/agents.py` Execution class): Executor logic, tool invocations, and final response generation

### Implementation Patterns
- `agents/tools/weather_tool.py`: Tool implementation returning deltaState patches
- `agents/tools/directions_tool.py`: Transit and walking directions with fallback behavior
- `utils/state.py`: State merging logic (deepMerge)

### Testing Patterns
- `tests/test_runTurn_mocked.py`: Mocking LLMs and tools for unit tests

## Common Patterns & Anti-Patterns

### ✅ Do This
- Planner emits structured, validated plan JSON (include `steps` array with `id`, `action`, and `args`)
- Executor returns the final `final_response` text in `deltaState.context`
- Return deltaState patches from tools, not raw API data
- Use `deepMerge()` for all state updates
- Mock LLMs and tools in unit tests; provide deterministic tool returns for CI

### ❌ Don't Do This
- Don't rely on a separate Synthesizer agent — Executor must produce the final answer
- Don't modify WorldState directly - use deltaState patches
- Don't mix heavy synthesis logic into Planner; planning should remain structured
- Don't call LLMs without prompt validation and error handling
- Don't hardcode API keys - use environment variables

## Development Commands
```powershell
# CLI interaction
python -m main

# Testing
pytest -q

# Environment setup
Copy-Item .env.example .env  # Add your API keys (PowerShell)
```

## Where to Look First When Debugging

1. State issues: Check WorldState dumps in logs
2. API failures: Look at `world_state.errors[]` and tool evidence
3. LLM issues: Enable DEBUG logging for prompts/responses
4. Planning problems: Check planner JSON output parsing and ensure valid `steps` array
5. Tool execution: Verify Executor returns `final_response` in `deltaState.context`

If any of these notes are unclear or missing, tell me which part you'd like expanded (examples: more test guidelines, mocking patterns, or prompt-editing safety checks).