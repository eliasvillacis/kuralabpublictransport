
# 🏗️ Vaya Public Transport Assistant - A2A LLM Architecture

**Deployment:**
- Production deployment is via [Render](https://render.com/) with a custom domain and web UI (React/Next.js or similar).
- Routing, geocoding, and weather are handled via Google APIs and Gemini LLM.


## Core Architecture

### Two-Agent A2A (Agent-to-Agent) Pattern

- **Planner Agent (LLM):**
    - Receives the user query and generates a structured execution plan (JSON) with step-by-step actions and arguments.
    - Uses a Gemini LLM (low temperature) for deterministic, structured output.
    - Returns a plan as a deltaState patch to the shared WorldState.

- **Execution Agent (LLM):**
    - Receives the plan and current WorldState, reasons about dependencies, and selects which tools to execute (using LLM reasoning).
    - Uses a Gemini LLM to decide tool invocation order, fill arguments, and handle tool chaining.
    - Executes tools (weather, geocode, directions, places search, etc.), merges their outputs into WorldState, and generates the final user-facing response (via LLM or fallback).
    - Handles placeholder substitution, slot memory, error handling, and context-aware follow-ups (see below).

- **WorldState (Blackboard):**
    - Central, structured state shared by all agents.
    - Includes user query, slots (origin/destination), context (plan, results, units, last POI search, etc.), evidence, errors, and memory.
    - All state changes are made via deltaState patches and merged with `deepMerge()`.

- **Coordinator:**
    - Orchestrates the Planner → Executor flow.
    - Loads/saves conversation memory to disk.
    - Handles world state initialization, delta application, and error fallback.

### Data Flow

```
User Query → Planner (LLM) → Plan JSON (deltaState) → Executor (LLM) → Tool Calls → Tool Results (deltaState) → deepMerge → Final Response
```

- All agent communication is via WorldState patches.
- No direct tool selection or response synthesis is hardcoded; LLMs drive both planning and execution.


### Tooling

- Tools are implemented as LangChain `@tool` functions, returning WorldState-compatible patches.
- Tools include: weather, geocode, geolocate, reverse geocode, directions, places search, conversation.
- Tools are invoked by name and arguments as determined by the Executor LLM.
- **Slot Reference Resolution:** The executor resolves slot references (e.g., 'origin', 'destination') in tool arguments to their actual values (lat/lng dicts) before tool invocation, ensuring tools always receive the correct data.

### Context-Aware POI Search, Directions, and Chained Queries 

- **POI Search (PlacesSearch):**
    - If the user asks for a place (e.g., "nearest dunkin"), the system runs only the PlacesSearch tool and returns a summary of the nearest locations (name, address, distance).
    - If the user query explicitly asks for directions (e.g., "how do I get to the nearest dunkin"), the system chains PlacesSearch and Directions, using the first result as the destination.
    - The agent detects intent for directions using a keyword/phrase list and only invokes Directions if needed.

- **Chained Queries & Context Memory:**
    - The system stores the last PlacesSearch results in `world_state.context['last_places_results']`.
    - If the user follows up with queries like "directions to #2" or "take me to the third one", the agent parses the ordinal/numbered reference, retrieves the correct place from memory, and patches the Directions step to use its details (placeId/address/lat,lng).
    - This enables natural, conversational follow-ups without the user needing to repeat the full place name or address.

- **Autopatching and Plan Correction:**
    - The executor autopatches plans to insert PlacesSearch before Directions if the user query is a POI/brand and Directions lacks a concrete destination.
    - Placeholder substitution supports array indexing (e.g., `${context.places.results[0].placeId}`) for robust data flow between tools.

### Error Handling

- Tools raise exceptions on API failures; agents catch and append errors to `world_state.errors[]`.
- Executor generates fallback responses if LLM or tool execution fails.
- All errors and tool evidence are logged for debugging.
- The system gracefully handles missing info, API failures, and ambiguous queries, always providing a helpful user response.

### Memory

- Conversation memory is persisted in `data/conversation_memory.json` and loaded at startup.
- WorldState context and slots can be restored between sessions.
- The agent can handle context-aware, multi-turn conversations, remembering previous search results and user preferences.

### Example User Flows

- **POI Search Only:**
    - User: "nearest mcdonalds?"
    - System: Returns a list of the nearest McDonald's locations (no directions).

- **Directions to POI:**
    - User: "how do I get to the nearest mcdonalds?"
    - System: Finds the nearest McDonald's, then provides directions from the user's current location.

- **Chained Query:**
    - User: "nearest dunkin?"
    - System: Returns a list of the nearest Dunkin' locations.
    - User: "directions to #2"
    - System: Provides directions to the second Dunkin' in the previous list.

### Key Files

- `main.py`: CLI entry point.
- `agents/agents.py`: Contains both PlanningAgent and ExecutionAgent classes.
- `agents/coordinator.py`: Manages the Planner → Executor flow and memory.
- `agents/tools/`: Tool implementations.
- `utils/contracts.py`: Pydantic models for WorldState, Slots, etc.
- `utils/state.py`: State merging logic (`deepMerge`).
- `utils/logger.py`: Centralized logging configuration.

### Notable Implementation Details

- The system is fully LLM-driven for both planning and tool selection.
- The Executor Agent/LLM produces the final natural-language response.
- All state is managed via structured patches and merged into the canonical WorldState.
- The architecture is modular and easily extensible for new tools or agent types.
- Ambiguous results (multiple locations)
- Incomplete data (missing coordinates)
- Agent signals (execution blocked)

#### Process
```
Problem Detected → Issue Analysis → New Plan Creation → Revised Execution
```

### Technology Stack

#### LangChain vs LangGraph Decision

**Current: LangChain**
- **Rich Tool Ecosystem**: Pre-built Google Maps/Weather integrations
- **Agent Flexibility**: Easy customization of agent behaviors
- **Rapid Prototyping**: Quick experimentation and iteration
- **Community Support**: Extensive documentation and examples

**Alternative: LangGraph**
- **Visual Workflows**: Graph-based process definition
- **Built-in State**: Automatic state persistence and recovery
- **Enterprise Monitoring**: Better observability and debugging
- **Production Ready**: Structured scaling and reliability

**Why LangChain for Vaya:**
- Research/development environment
- High customization needs
- Rapid experimentation required
- Smaller team with deep ML expertise

### A2A vs MCP Architecture

| Aspect | A2A (Current) | MCP (Enterprise) |
|--------|---------------|------------------|
| **Communication** | Peer-to-peer via WorldState | Client-server with protocol |
| **Coordination** | Decentralized, emergent | Centralized orchestration |
| **Scalability** | Horizontal (add agents) | Vertical (scale server) |
| **Complexity** | Higher (race conditions) | Lower (predictable flow) |
| **Use Case** | Research/experimentation | Production enterprise |

### WorldState - The Central Blackboard

```python
class WorldState(BaseModel):
    meta: Dict[str, Any] = {"sessionId": None, "version": "2.0"}
    user: Dict[str, Any] = {"locale": "en-US", "timezone": "America/New_York"}
    query: Dict[str, Any] = {"raw": ""}
    slots: Slots = Field(default_factory=Slots)  # Origin/Destination
    context: Dict[str, Any] = {                   # Execution state
        "plan": {"steps": [], "status": "none"},
        "completed_steps": [],
        "lastWeather": {},
        "units": "imperial",
        "last_places_results": []  # Stores last POI search results for context-aware follow-ups
    }
    evidence: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    memory: Dict[str, Any] = Field(default_factory=dict)
```

**Key Features:**
- **Single Source of Truth**: All agents read/write to same state
- **Immutable Updates**: Changes tracked via deepMerge()
- **Structured Sharing**: Clear format for different data types
- **Memory Integration**: Conversation history and preferences
- **Context-Aware POI Memory**: Enables chained queries and follow-ups referencing previous search results

### API Integration Architecture

#### Fallback Mechanisms
```
Primary Method → Backup Method → Error Handling
Google Client Library → Direct API Calls → Graceful Failure
```

#### Resilience Features
- **Multiple Access Methods**: Official clients + direct HTTP
- **Rate Limiting**: Built-in delays and retry logic
- **Error Handling**: Comprehensive exception catching
- **Caching**: Memory-based result caching

### Error Handling Layers

#### 1. Tool Level
```python
try:
    result = api_call()
    return {"success": True, "data": result}
except APIError:
    return {"success": False, "error": str(e)}
```

#### 2. Agent Level
```python
if tool_failed:
    new_plan = create_backup_plan()
    execute_revised_plan(new_plan)
```

#### 3. System Level
```python
"API rate limit exceeded" → "Please wait a moment, then try again"
"Location not found" → "I couldn't find that location. Could you be more specific?"
```

### Scaling Considerations

#### Current (Research & Development)
- Single process architecture
- File-based memory persistence
- Simple logging and monitoring
- Local state management

#### Enterprise Evolution
- **Phase 1**: Add observability (centralized logging, monitoring)
- **Phase 2**: Distributed state (Redis, databases, message queues)
- **Phase 3**: Production infrastructure (load balancing, containers)
- **Phase 4**: Enterprise features (multi-tenant, compliance)

### Key Technical Innovations

1. **Emergent Intelligence**: Agents solve problems creatively through collaboration
2. **Dynamic Replanning**: Real-time plan modification without restart
3. **Memory-Augmented Conversations**: Context-aware responses with preference learning and POI memory
4. **API Resilience**: Multiple fallback mechanisms for reliability
5. **Peer-to-Peer Coordination**: Direct agent communication without rigid hierarchies

### File Structure

#### Core Components
- `main.py`: CLI interface and system bootstrap
- `agents/coordinator.py`: A2A coordinator managing agent interactions
- `agents/agents.py`: Planning and Execution agents (Synthesis merged into Execution)
- `agents/tools/`: API integration tools (weather, location, places)
- `utils/contracts.py`: Pydantic data models and validation
- `utils/state.py`: State management and deepMerge utilities
- `utils/logger.py`: Centralized logging configuration

#### Data & Configuration
- `data/conversation_memory.json`: Persistent conversation history
- `requirements.txt`: Python dependencies
- `logs/app.log`: Application logging

### Development Workflow

#### Local Setup
```bash
pip install -r requirements.txt
# Set environment variables: GEMINI_API_KEY, GOOGLE_API_KEY
python -m main
```

#### Testing Strategy
```bash
pytest -q  # Run all tests
# Mock LLMs and tools for unit tests
# Test runTurn() with mocked components
```

#### Debugging Approach
- **Logs**: `utils/logger.get_logger(__name__)` → `logs/app.log`
- **State Tracing**: WorldState dumps after each execution step
- **Tool Debugging**: Raw API responses in `deltaState.evidence`
- **LLM Debugging**: Enable DEBUG logging for prompts/responses

### Enterprise Migration Path

**When to Switch to MCP/LangGraph:**
- Production deployment requirements
- Large-scale user serving
- Enterprise compliance needs
- Team growth and structure changes

**Migration Benefits:**
- Better observability and monitoring
- Predictable performance characteristics
- Easier debugging and troubleshooting
- Built-in enterprise features

This A2A architecture provides a solid foundation for multi-agent systems with research-friendly flexibility while maintaining clear paths to enterprise scaling.