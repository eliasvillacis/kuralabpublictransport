"""
A2A (Agent-to-Agent) Coordinator for multi-agent transportation assistant.

This module implements a true A2A architecture where agents communicate peer-to-peer
through a shared WorldState, with replanning capabilities and memory management.
"""

import json
import asyncio
from typing import Dict, List, Any, Optional, Protocol
from dataclasses import dataclass
from datetime import datetime
from utils.contracts import WorldState
from utils.logger import get_logger
from utils.state import deepMerge

logger = get_logger(__name__)

class AgentProtocol(Protocol):
    """Protocol defining the interface for A2A agents."""

    def get_name(self) -> str:
        """Return the agent's name."""
        ...

    def can_handle(self, world_state: WorldState) -> bool:
        """Check if agent can contribute to current state."""
        ...

    def process(self, world_state: WorldState) -> Dict[str, Any]:
        """Process the current state and return deltaState patch."""
        ...

    def should_replan(self, world_state: WorldState) -> bool:
        """Check if replanning is needed based on current state."""
        ...

@dataclass
class AgentMessage:
    """Message structure for A2A communication."""
    agent_name: str
    message_type: str  # 'proposal', 'execution', 'feedback', 'replan'
    content: Dict[str, Any]
    timestamp: datetime
    priority: int = 1

@dataclass
class ConversationMemory:
    """Memory structure for conversation persistence."""
    session_id: str
    messages: List[Dict[str, Any]]
    world_state_history: List[Dict[str, Any]]
    agent_interactions: List[AgentMessage]
    created_at: datetime
    updated_at: datetime

class MemoryManager:
    """Manages conversation memory with file persistence."""

    def __init__(self, memory_file: str = "data/conversation_memory.json"):
        self.memory_file = memory_file
        self.current_memory: Optional[ConversationMemory] = None
        self.load_memory()

    def load_memory(self):
        """Load memory from file."""
        try:
            with open(self.memory_file, 'r') as f:
                data = json.load(f)
                self.current_memory = ConversationMemory(
                    session_id=data['session_id'],
                    messages=data['messages'],
                    world_state_history=data['world_state_history'],
                    agent_interactions=[
                        AgentMessage(
                            agent_name=msg['agent_name'],
                            message_type=msg['message_type'],
                            content=msg['content'],
                            timestamp=datetime.fromisoformat(msg['timestamp']),
                            priority=msg.get('priority', 1)
                        ) for msg in data['agent_interactions']
                    ],
                    created_at=datetime.fromisoformat(data['created_at']),
                    updated_at=datetime.fromisoformat(data['updated_at'])
                )
        except (FileNotFoundError, json.JSONDecodeError):
            self.current_memory = ConversationMemory(
                session_id=f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                messages=[],
                world_state_history=[],
                agent_interactions=[],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

    def save_memory(self):
        """Save current memory to file."""
        if self.current_memory:
            data = {
                'session_id': self.current_memory.session_id,
                'messages': self.current_memory.messages,
                'world_state_history': self.current_memory.world_state_history,
                'agent_interactions': [
                    {
                        'agent_name': msg.agent_name,
                        'message_type': msg.message_type,
                        'content': msg.content,
                        'timestamp': msg.timestamp.isoformat(),
                        'priority': msg.priority
                    } for msg in self.current_memory.agent_interactions
                ],
                'created_at': self.current_memory.created_at.isoformat(),
                'updated_at': self.current_memory.updated_at.isoformat()
            }
            with open(self.memory_file, 'w') as f:
                json.dump(data, f, indent=2)

    def add_message(self, message: Dict[str, Any]):
        """Add a user/agent message to memory."""
        if self.current_memory:
            self.current_memory.messages.append(message)
            self.current_memory.updated_at = datetime.now()
            self.save_memory()

    def add_world_state(self, world_state: WorldState):
        """Add world state snapshot to memory."""
        if self.current_memory:
            self.current_memory.world_state_history.append(world_state.model_dump())
            self.current_memory.updated_at = datetime.now()
            self.save_memory()

    def add_agent_interaction(self, message: AgentMessage):
        """Add agent interaction to memory."""
        if self.current_memory:
            self.current_memory.agent_interactions.append(message)
            self.current_memory.updated_at = datetime.now()
            self.save_memory()

    def get_recent_context(self, limit: int = 5) -> Dict[str, Any]:
        """Get recent conversation context."""
        if not self.current_memory:
            return {}

        return {
            'recent_messages': self.current_memory.messages[-limit:],
            'current_world_state': self.current_memory.world_state_history[-1] if self.current_memory.world_state_history else {},
            'agent_interactions': [
                {
                    'agent': msg.agent_name,
                    'type': msg.message_type,
                    'content': msg.content
                } for msg in self.current_memory.agent_interactions[-limit:]
            ]
        }

class A2ACoordinator:
    """A2A Coordinator managing peer-to-peer agent interactions."""

    def __init__(self):
        self.agents: Dict[str, AgentProtocol] = {}
        self.world_state = WorldState()
        self.memory = MemoryManager()
        self.message_queue: List[AgentMessage] = []
        self.max_iterations = 10
        self.replanning_enabled = True

    def register_agent(self, agent: AgentProtocol):
        """Register an agent with the coordinator."""
        self.agents[agent.get_name()] = agent
        logger.info(f"Registered agent: {agent.get_name()}")

    def unregister_agent(self, agent_name: str):
        """Unregister an agent."""
        if agent_name in self.agents:
            del self.agents[agent_name]
            logger.info(f"Unregistered agent: {agent_name}")

    def broadcast_message(self, message: AgentMessage):
        """Broadcast message to all agents."""
        self.message_queue.append(message)
        self.memory.add_agent_interaction(message)
        logger.info(f"Broadcast message from {message.agent_name}: {message.message_type}")

    def process_user_query(self, user_query: str) -> str:
        """Process user query through A2A coordination."""
        logger.info(f"Processing user query: {user_query}")

        # Initialize world state with user query
        self.world_state = WorldState()
        self.world_state.query = {"raw": user_query}
        self.memory.add_message({"role": "user", "content": user_query})
        self.memory.add_world_state(self.world_state)

        iteration = 0
        final_response = ""

        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"A2A Iteration {iteration}")

            # Check for replanning need
            if self.replanning_enabled and self._should_replan():
                replan_result = self._execute_replanning()
                if replan_result:
                    logger.info("Replanning executed")
                    continue

            # Let agents process in order of priority
            active_agents = self._get_active_agents()

            if not active_agents:
                logger.info("No active agents found, ending conversation")
                break

            # Process each active agent
            for agent in active_agents:
                try:
                    if agent.can_handle(self.world_state):
                        logger.info(f"Processing with agent: {agent.get_name()}")

                        # Agent processes and returns deltaState
                        delta = agent.process(self.world_state)

                        # Apply delta to world state
                        self.world_state = self._apply_delta(self.world_state, delta)

                        # Store in memory
                        self.memory.add_world_state(self.world_state)

                        # Broadcast agent result
                        message = AgentMessage(
                            agent_name=agent.get_name(),
                            message_type="execution",
                            content={"delta": delta},
                            timestamp=datetime.now()
                        )
                        self.broadcast_message(message)

                        # Check if we have a final response
                        delta_state = delta.get("deltaState", delta)
                        if "final_response" in delta_state.get("context", {}):
                            final_response = delta_state["context"]["final_response"]
                            break

                        # CRITICAL FIX: Only synthesize if ALL execution steps are complete
                        synthesizer = self.agents.get("synthesizer")
                        executor = self.agents.get("executor")
                        
                        # Check if executor still has pending steps
                        has_pending_steps = False
                        if executor and executor.can_handle(self.world_state):
                            has_pending_steps = True
                        
                        # Only synthesize if synthesizer can handle AND no pending execution steps
                        if synthesizer and synthesizer.can_handle(self.world_state) and not has_pending_steps:
                            logger.info("All execution steps complete - synthesizing final response")
                            synth_delta = synthesizer.process(self.world_state)
                            self.world_state = self._apply_delta(self.world_state, synth_delta)
                            
                            synth_delta_state = synth_delta.get("deltaState", synth_delta)
                            if "final_response" in synth_delta_state.get("context", {}):
                                final_response = synth_delta_state["context"]["final_response"]
                                break

                except Exception as e:
                    logger.error(f"Error processing agent {agent.get_name()}: {e}")
                    error_delta = {"errors": [f"Agent {agent.get_name()} error: {str(e)}"]}
                    self.world_state = self._apply_delta(self.world_state, {"deltaState": error_delta})

            if final_response:
                break

        # Store final response in memory
        if final_response:
            self.memory.add_message({"role": "assistant", "content": final_response})

        return final_response or "I'm sorry, I couldn't process your request effectively."

    def _get_active_agents(self) -> List[AgentProtocol]:
        """Get agents that can currently contribute."""
        active = []
        for agent in self.agents.values():
            if agent.can_handle(self.world_state):
                active.append(agent)
        return active

    def _should_replan(self) -> bool:
        """Check if replanning is needed."""
        # Check if any agent signals need for replanning
        for agent in self.agents.values():
            if agent.should_replan(self.world_state):
                return True

        # Check for errors that might require replanning
        if self.world_state.errors:
            return True

        return False

    def _execute_replanning(self) -> bool:
        """Execute replanning logic."""
        # Find planner agent
        planner = self.agents.get("planner")
        if not planner:
            return False

        try:
            # Generate new plan based on current state
            replan_delta = planner.process(self.world_state)

            # Apply replanning changes
            self.world_state = self._apply_delta(self.world_state, replan_delta)

            # Broadcast replanning message
            message = AgentMessage(
                agent_name="coordinator",
                message_type="replan",
                content={"replan_delta": replan_delta},
                timestamp=datetime.now()
            )
            self.broadcast_message(message)

            return True

        except Exception as e:
            logger.error(f"Replanning failed: {e}")
            return False

    def _apply_delta(self, world_state: WorldState, delta: Dict[str, Any]) -> WorldState:
        """Apply deltaState patch to world state."""
        delta_state = delta.get("deltaState", delta)
        merged = world_state.model_dump()
        deepMerge(merged, delta_state)
        return WorldState(**merged)

    def get_memory_context(self) -> Dict[str, Any]:
        """Get current memory context for agents."""
        return self.memory.get_recent_context()

    def reset_conversation(self):
        """Reset conversation and start new memory session."""
        self.world_state = WorldState()
        self.memory = MemoryManager()
        self.message_queue = []

# Global coordinator instance
_coordinator = None

def get_coordinator() -> A2ACoordinator:
    """Get or create the global A2A coordinator."""
    global _coordinator
    if _coordinator is None:
        _coordinator = A2ACoordinator()
    return _coordinator