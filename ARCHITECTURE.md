# 🏗️ Vaya Public Transport Assistant - A2A LLM Architecture (2025)

## Core Architecture

### Two-Agent A2A (Agent-to-Agent) Pattern

- **Planner Agent (LLM):**
    - Receives the user query and generates a structured execution plan (JSON) with step-by-step actions and arguments.
    - Uses a Gemini LLM (low temperature) for deterministic, structured output.
    - Returns a plan as a deltaState patch to the shared WorldState.

- **Execution Agent (LLM):**
    - Receives the plan and current WorldState, reasons about dependencies, and selects which tools to execute (using LLM reasoning).
    - Uses a Gemini LLM to decide tool invocation order, fill arguments, and handle tool chaining.
    - Executes tools (weather, geocode, directions, etc.), merges their outputs into WorldState, and generates the final user-facing response (via LLM or fallback).
    - Handles placeholder substitution, slot memory, and error handling.

- **WorldState (Blackboard):**
    - Central, structured state shared by all agents.
    - Includes user query, slots (origin/destination), context (plan, results, units, etc.), evidence, errors, and memory.
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
- Tools include: weather, geocode, geolocate, reverse geocode, directions, conversation.
- Tools are invoked by name and arguments as determined by the Executor LLM.

### Error Handling

- Tools raise exceptions on API failures; agents catch and append errors to `world_state.errors[]`.
- Executor generates fallback responses if LLM or tool execution fails.
- All errors and tool evidence are logged for debugging.

### Memory

- Conversation memory is persisted in `data/conversation_memory.json` and loaded at startup.
- WorldState context and slots can be restored between sessions.

### Key Files

- `main.py`: CLI entry point.
- `agents/agents.py`: Contains both PlanningAgent and ExecutionAgent classes.
- `agents/coordinator.py`: Manages the Planner → Executor flow and memory.
- `agents/tools/`: Tool implementations.
- `utils/contracts.py`: Pydantic models for WorldState, Slots, etc.
- `utils/state.py`: State merging logic (`deepMerge`).

### Notable Implementation Details

- The Synthesis Agent is now merged into the Executor; the Executor LLM produces the final natural-language response.
- The system is fully LLM-driven for both planning and tool selection.
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
        "units": "imperial"
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
3. **Memory-Augmented Conversations**: Context-aware responses with preference learning
4. **API Resilience**: Multiple fallback mechanisms for reliability
5. **Peer-to-Peer Coordination**: Direct agent communication without rigid hierarchies

### File Structure

#### Core Components
- `main.py`: CLI interface and system bootstrap
- `agents/coordinator.py`: A2A coordinator managing agent interactions
- `agents/agents.py`: Three specialized agents (Planning, Execution, Synthesis)
- `agents/tools/`: API integration tools (weather, location)
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