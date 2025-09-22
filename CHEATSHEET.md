
# Vaya Public Transport Assistant — Quick Reference Cheat Sheet

## 🚦 System Overview

This project is a multi-agent, LLM-driven public transport assistant. It uses a two-agent (A2A) architecture:

- **Planner (LLM):** Interprets user intent and emits a structured plan (JSON steps)
- **Executor (LLM + tools):** Runs the plan, calls tools, and produces the final user-facing response

Agents communicate only via a shared `WorldState` (blackboard pattern). All state changes are made by merging deltaState patches using `deepMerge()`.

---

## 🧠 Agent Roles

### 1. Planner (LLM)
- Reads user query from `WorldState`
- Emits a structured plan (JSON: steps array with id, action, args)
- Prefers transit directions for routing, requests geocoding/geolocation as needed
- Includes fallbacks (e.g., walking) if transit is unavailable

### 2. Executor (LLM + tools)
- Reads the plan from `WorldState`
- Runs each step by calling the appropriate tool (weather, directions, geocode, etc.)
- Merges tool results into `WorldState` as deltaState patches
- Produces the final assistant-facing response (`final_response` in `deltaState.context`)
- Handles tool errors gracefully, provides fallback answers

---

## 🗂️ Key Files & Folders

**/agents/**
- `agents.py` — Planner and Executor agent classes
- `coordinator.py` — Orchestrates Planner → Executor flow, manages memory and state
- `/tools/` — Modular tool implementations:
  - `weather_tool.py` — Weather via Google API
  - `directions_tool.py` — Transit/walking directions
  - `location_tool.py` — Geocoding/geolocation
  - `conversation_tool.py` — Small talk, fallback

**/utils/**
- `contracts.py` — Pydantic models for `WorldState`, `Slots`, etc.
- `state.py` — `deepMerge()` for patching state
- `logger.py` — Logging to `logs/app.log` and console

**/data/**
- `conversation_memory.json` — Persistent conversation memory

**/logs/**
- `app.log` — System and error logs

**Root**
- `main.py` — CLI entry point
- `requirements.txt` — Python dependencies
- `README.md` — Project documentation

---

## 🔄 Data Flow (A2A)

1. **User Input** → `main.py` (CLI)
2. **Coordinator** → Creates initial `WorldState`, starts Planner
3. **Planner** → Emits plan (JSON steps)
4. **Executor** → Runs steps, calls tools, merges results
5. **Output** → Final response returned to user

All state changes are via deltaState patches merged with `deepMerge()`.

---

## 🛠️ Tool Pattern

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

---

## 🧩 State Management

- All state is managed via `WorldState` (see `utils/contracts.py`)
- Agents/tools **never** mutate state directly; they return deltaState patches
- Use `deepMerge()` (in `utils/state.py`) to apply patches
- All state changes are validated by Pydantic models

---

## 🚨 Error Handling

- Tools raise exceptions on API failures; Executor catches and appends errors to `world_state.errors[]`
- Executor provides fallback answers (e.g., walking if transit fails)
- All errors and tool evidence are logged in `logs/app.log`

---

## 🧪 Testing & Debugging

### Unit Testing
- Mock LLMs and tools for deterministic results
- Test tool returns (WorldState patches)
- Validate agent logic with controlled state

### Integration Testing
- Test full Planner → Executor → tool flow
- Use `pytest` (see `tests/`)

### Debugging
- Check `logs/app.log` for errors
- Dump `WorldState` after each step to trace merges
- Tool evidence is stored in `context.<tool>_evidence` for auditing

---

## 🚀 Onboarding & Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up API keys
Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_gemini_key_here
GOOGLE_API_KEY=your_google_key_here
```

### 3. Run the CLI
```bash
python -m main
```

### 4. Try example queries
- Weather: `What's the weather in Miami?`
- Directions: `How do I get from Miami to Orlando by transit?`
- Location: `Where am I?`
- Multi-step: `What's the weather in Miami and New York?`

---

## 🏗️ Common Dev Tasks

### Add a New Tool
1. Create a new file in `agents/tools/`
2. Use `@tool("ToolName")` decorator
3. Return a WorldState-compatible patch
4. Register tool in Executor's action handling
5. Update Planner logic if needed

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

### Basic Setup:
```bash
# Install dependencies
pip install -r requirements.txt

# Set up API keys in .env file
GEMINI_API_KEY=your_gemini_key
GOOGLE_API_KEY=your_google_key

# Run the system
python main.py
```

### Testing Different Scenarios:
- **Weather:** "What's the weather in Miami?"
- **Location:** "Where am I?"
- **Conversation:** "Hi how are you?"
- **Multi-step:** "What's the weather in Miami and New York?"

This architecture makes the system reliable, maintainable, and easy to understand because each part has a clear job and they work together through the shared WorldState.

## File Structure and Organization

The project is organized into clear folders that separate different types of code:

### `/agents/` - The AI Programs
- **`agents.py`** - Contains the two main agent classes (PlanningAgent, ExecutionAgent)
- **`coordinator.py`** - Manages communication between agents
- **`/tools/`** - Contains the specialized tools that do actual work:
  - `weather_tool.py` - Gets weather data from Google APIs
  - `location_tool.py` - Handles location services (geocoding, reverse geocoding)
  - `conversation_tool.py` - Handles casual conversation

### `/utils/` - Helper Code
- **`contracts.py`** - Defines data structures (WorldState, Slots, etc.)
- **`state.py`** - Functions for merging data updates
- **`logger.py`** - Logging system for debugging and monitoring

### `/data/` - Persistent Storage
- **`conversation_memory.json`** - Saves conversation history between sessions

### `/logs/` - System Logs
- **`app.log`** - Records all system activity for debugging

### Root Files
- **`main.py`** - Entry point that starts the chat interface
- **`requirements.txt`** - Lists all Python packages needed
- **`README.md`** - Project documentation

## Understanding the Data Flow

### Normal Request Flow:
1. **User Input** → `main.py` receives the message
2. **Coordinator** → `coordinator.py` creates WorldState and starts the process
3. **Planning** → PlanningAgent analyzes the request and creates a plan
4. **Execution** → ExecutionAgent runs each step and creates the final response
5. **Output** → Response goes back to user through `main.py`

### Error Handling Flow:
1. **Detection** → Any agent/tool detects a problem
2. **Recording** → Error gets added to `world_state.errors`
3. **Recovery** → Coordinator may trigger replanning
4. **Fallback** → ExecutionAgent provides helpful error message
5. **Logging** → Everything gets recorded in `logs/app.log`

## Key Design Patterns Used

### 1. Agent-to-Agent (A2A) Communication
Instead of one big AI trying to do everything, the system uses specialized agents that communicate through shared state. This makes the system:
- More reliable (one agent failing doesn't break everything)
- Easier to maintain (each agent has a clear job)
- More flexible (new agents can be added easily)

### 2. Tool-Based Architecture
Real work is done by specialized tools rather than the agents themselves. This separates:
- **Decision making** (agents decide what to do)
- **Action execution** (tools do the actual work)
- **Response generation** (agents format the results)

### 3. Shared State Pattern
All agents read from and write to the same WorldState object. This provides:
- **Consistency** - all agents see the same information
- **Persistence** - state survives between agent interactions
- **Debugging** - easy to see what happened at each step

### 4. Error Resilience
The system is designed to continue working even when parts fail:
- API calls might fail, but the system tries alternatives
- Invalid input gets handled gracefully
- Failed steps get logged but don't stop the whole process

## Common Development Tasks

### Adding a New Tool:
1. Create new file in `agents/tools/`
2. Use `@tool("ToolName")` decorator
3. Return data in WorldState-compatible format
4. Add tool to ExecutionAgent's action handling
5. Update PlanningAgent to create plans using the new tool

### Adding a New Agent:
1. Create new agent class in `agents/agents.py`
2. Implement required methods (`can_handle`, `process`)
3. Register agent in `main.py` coordinator setup
4. Update coordinator logic if needed

### Debugging Issues:
1. Check `logs/app.log` for error messages
2. Look at WorldState dumps in memory
3. Test individual tools with direct function calls
4. Use the `status` command to see system state

## Testing and Quality Assurance

### Unit Testing:
- Test individual tools with mock API responses
- Test agent logic with controlled WorldState inputs
- Verify error handling with simulated failures

### Integration Testing:
- Test complete conversation flows
- Verify agent communication works correctly
- Test memory persistence across sessions

### Manual Testing Scenarios:
- Weather queries for different locations
- Location-based questions
- Casual conversation handling
- Error conditions (invalid locations, API failures)
- Multi-step requests (weather for multiple cities)

This architecture makes the system both powerful and maintainable. Each component has a clear responsibility, and they work together through well-defined interfaces and shared state management.
You: weather in Miami

# Use special commands
You: /status
You: /memory
You: /reset
```

---

## 🛠️ How to Set Up Vaya (For Beginners)

### Step 1: Get the Ingredients
```bash
# Install Python stuff (like getting cooking ingredients)
pip install -r requirements.txt
```

### Step 2: Get Your Keys
```bash
# You need special passwords for Google services
# Create a .env file with:
GEMINI_API_KEY=your_gemini_key_here
GOOGLE_API_KEY=your_google_key_here
```

### Step 3: Start Talking!
```bash
# Start the conversation
python main.py

# Ask anything!
You: weather in Miami
You: where am I
You: directions to airport
```

---

### Why Agent-to-Agent (A2A) Architecture?

The A2A approach was chosen over traditional single-agent systems because:

1. **Modularity**: Each agent has a clear, focused responsibility
2. **Reliability**: If one agent fails, others can continue working
3. **Scalability**: New agents can be added without rewriting existing code
4. **Debugging**: Easier to isolate and fix problems in specific agents
5. **Testing**: Each agent can be tested independently

### Shared State vs Direct Communication

Instead of agents talking directly to each other, they use a shared WorldState because:

1. **Consistency**: All agents see the same information at the same time
2. **Persistence**: State survives between agent interactions
3. **Debugging**: Easy to inspect the complete system state at any point
4. **Flexibility**: New agents can be added without changing existing communication patterns

### Tool-Based Execution

The system separates planning (what to do) from execution (how to do it) because:

1. **Reusability**: Tools can be used by different agents or even other systems
2. **Testing**: Tools can be tested independently with mock inputs
3. **Maintenance**: API changes only affect the specific tool, not the agent logic
4. **Performance**: Tools can be optimized independently


