# 🏗️ Vaya - A2A Multi-Agent Architecture

## Core Architecture

### A2A (Agent-to-Agent) Pattern
**Peer-to-peer agent communication** through shared **WorldState** blackboard pattern.

**Why A2A vs Traditional Orchestration:**
- **Decentralized**: No single point of failure
- **Scalable**: Easy to add/remove agents
- **Resilient**: System continues if one agent fails
- **Flexible**: Agents communicate opportunistically

### Three-Agent System

#### Planning Agent
- **Purpose**: Creates and validates execution plans
- **Input**: User query + current WorldState
- **Output**: Step-by-step execution plan
- **Replanning**: Dynamically modifies plans when execution fails

#### Execution Agent
- **Purpose**: Executes planned steps using tools
- **Input**: Plan steps + WorldState
- **Output**: API results and state updates
- **Tools**: Weather API, Location services, Geocoding

#### Synthesis Agent
- **Purpose**: Generates natural language responses
- **Input**: Execution results + conversation context
- **Output**: Human-readable final response
- **Features**: Multi-location synthesis, error handling

### Plan & Execute Pattern

#### Planning Phase
```
User Query → Intent Analysis → Step Sequencing → Dependency Mapping → Error Anticipation
```

#### Execution Phase
```
Plan → Step-by-Step Processing → Real-time Adaptation → Result Aggregation → Quality Assurance
```

### Smart Replanning
**Dynamic plan modification** based on runtime conditions:

#### Triggers
- API failures (service unavailable)
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