<!-- Copilot instructions for the Kura public-transport demo app -->
# Kura Public Transport Assistant - AI Coding Guidelines

## Architecture Overview

This project implements a **three-agent multi-agent system** for transportation assistance:

### Core Components
- **`main.py`**: CLI entry point with colorized output and user interaction loop
- **`agents/planner.py`**: PlannerAgent orchestrates the entire flow (Planning → Execution → Synthesis)
- **`agents/executor.py`**: LangChain ReAct agent that executes tools and returns `{"deltaState": {...}, "snippet": "..."}`
- **`agents/synthesizer.py`**: Generates final natural-language responses from WorldState + snippets
- **`utils/contracts.py`**: Pydantic models defining WorldState, Slots, and data contracts
- **`utils/state.py`**: `deepMerge()` utility for applying state patches
- **`agents/tools/`**: Tool implementations (weather, location) that return WorldState-compatible patches

### Data Flow Architecture
```
User Query → Planner LLM → Plan JSON → Executor (LangChain) → Tools → Delta States → deepMerge → Synthesizer LLM → Final Response
```

**WorldState** is the canonical blackboard - all agents communicate via JSON patches merged with `deepMerge()`.

## Critical Developer Workflows

### Local Development Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment variables (.env file in project root)
GEMINI_API_KEY=your_gemini_key_here
GOOGLE_API_KEY=your_google_cloud_key_here

# 3. Run the CLI
python -m main
```

### Testing
```bash
# Run all tests
pytest -q

# Key testing patterns:
# - Mock LLM clients (Planner, Executor, Synthesizer) in unit tests
# - Mock @tool functions to return deterministic deltaState patches
# - Test runTurn() with mocked components for integration testing
```

### Debugging
- **Logs**: Use `utils/logger.get_logger(__name__)` - outputs to `logs/app.log` and console
- **State tracing**: Check WorldState dumps after each executor step
- **Tool debugging**: Tools return raw API responses in `deltaState.evidence` for auditing
- **LLM debugging**: Enable DEBUG logging to see planner prompts and executor reasoning

## Project-Specific Conventions

### LLM Instantiation Pattern
```python
# Always instantiate three separate clients
from langchain_google_genai import ChatGoogleGenerativeAI

self.planner = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash", temperature=0.2, google_api_key=gemini_key
)
self.executor_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro", temperature=0.2, google_api_key=gemini_key
)
self.synthesizer = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro", temperature=0.2, google_api_key=gemini_key
)
```

### Tool Implementation Pattern
```python
@tool("Weather")
def weather_current(lat: float, lng: float, units: str = "IMPERIAL") -> dict:
    """Return WorldState-compatible patch, not raw API data."""
    api_data = call_external_api(lat, lng, units)
    return {
        "context": {
            "lastWeather": {
                "lat": lat, "lng": lng, "units": units,
                "data": api_data  # Store raw API response for auditing
            }
        }
    }
```

### State Management
- **Single source of truth**: All state changes via `deepMerge()` from deltaState patches
- **No direct mutation**: Agents return patches, never modify WorldState directly
- **Validation**: Use Pydantic models in `utils/contracts.py` for type safety

### Executor Response Format
```json
{
  "deltaState": {"context": {"lastWeather": {...}}},
  "snippet": "It's currently 75°F and sunny."
}
```

### Error Handling
- Tools raise exceptions on API failures
- Errors accumulate in `world_state.errors[]`
- Synthesizer uses errors for fallback responses
- Logger captures all exceptions in `runTurn()`

## Integration Points

### External APIs
- **Google Weather API**: `https://weather.googleapis.com/v1/currentConditions:lookup`
- **Google Maps API**: Via `googlemaps` library for geocoding
- **Environment variables**: `GOOGLE_API_KEY` for Google services, `GEMINI_API_KEY` for LLM

### Dependencies
- **LLM**: `langchain-google-genai` with Gemini models
- **Tools**: LangChain `@tool` decorators
- **State**: Pydantic for validation, custom `deepMerge` for patches
- **CLI**: `colorama` for cross-platform colors

## Key Files to Reference

### Architecture Understanding
- `agents/planner.py`: Main orchestration flow and LLM client instantiation
- `utils/contracts.py`: WorldState and data model definitions
- `agents/executor.py`: LangChain agent setup and tool execution

### Implementation Patterns
- `agents/tools/weather_tool.py`: Tool implementation returning deltaState patches
- `agents/synthesizer.py`: Response generation from WorldState + snippets
- `utils/state.py`: State merging logic

### Testing Patterns
- `tests/test_runTurn_mocked.py`: Mocking LLMs and tools for unit tests

## Common Patterns & Anti-Patterns

### ✅ Do This
- Instantiate separate LLM clients for each agent role
- Return deltaState patches from tools, not raw API data
- Use `deepMerge()` for all state updates
- Log via `utils/logger.get_logger(__name__)`
- Mock LLMs and tools in unit tests

### ❌ Don't Do This
- Don't modify WorldState directly - use deltaState patches
- Don't mix synthesis logic into PlannerAgent
- Don't call LLMs without proper error handling
- Don't hardcode API keys - use environment variables
- Don't skip Pydantic validation for state changes

## Development Commands

```bash
# CLI interaction
python -m main

# Testing
pytest -q

# Environment setup
cp .env.example .env  # Add your API keys
```

## Where to Look First When Debugging

1. **State issues**: Check WorldState dumps in logs
2. **API failures**: Look at `world_state.errors[]` and tool evidence
3. **LLM issues**: Enable DEBUG logging for prompts/responses
4. **Planning problems**: Check planner JSON output parsing
5. **Tool execution**: Verify executor deltaState format

If any of these notes are unclear or missing, tell me which part you'd like expanded (examples: more test guidelines, mocking patterns, or prompt-editing safety checks).