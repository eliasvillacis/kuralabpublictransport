"""
Test the A2A (Agent-to-Agent) coordinator system.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from agents.coordinator import A2ACoordinator, AgentMessage
from agents.agents import PlanningAgent, ExecutionAgent, SynthesisAgent
from utils.contracts import WorldState

class MockAgent:
    """Mock agent for testing."""

    def __init__(self, name, can_handle=True, should_replan=False):
        self.name = name
        self.can_handle_result = can_handle
        self.should_replan_result = should_replan
        self.process_calls = []

    def get_name(self):
        return self.name

    def can_handle(self, world_state):
        return self.can_handle_result

    def should_replan(self, world_state):
        return self.should_replan_result

    def process(self, world_state):
        self.process_calls.append(world_state)
        return {
            "deltaState": {
                "context": {
                    f"{self.name}_processed": True,
                    "test_data": f"processed_by_{self.name}"
                }
            },
            "snippet": f"Processed by {self.name}"
        }

def test_coordinator_initialization():
    """Test A2A coordinator initialization."""
    coordinator = A2ACoordinator()

    assert len(coordinator.agents) == 0
    assert isinstance(coordinator.world_state, WorldState)
    assert coordinator.max_iterations == 10
    assert coordinator.replanning_enabled == True

def test_agent_registration():
    """Test agent registration and unregistration."""
    coordinator = A2ACoordinator()
    agent = MockAgent("test_agent")

    # Register agent
    coordinator.register_agent(agent)
    assert "test_agent" in coordinator.agents
    assert coordinator.agents["test_agent"] == agent

    # Unregister agent
    coordinator.unregister_agent("test_agent")
    assert "test_agent" not in coordinator.agents

def test_message_broadcasting():
    """Test message broadcasting between agents."""
    coordinator = A2ACoordinator()
    agent1 = MockAgent("agent1")
    agent2 = MockAgent("agent2")

    coordinator.register_agent(agent1)
    coordinator.register_agent(agent2)

    # Broadcast message
    message = AgentMessage(
        agent_name="agent1",
        message_type="test",
        content={"test": "data"},
        timestamp=datetime.now()
    )

    coordinator.broadcast_message(message)

    # Check message queue
    assert len(coordinator.message_queue) == 1
    assert coordinator.message_queue[0].agent_name == "agent1"
    assert coordinator.message_queue[0].message_type == "test"

def test_get_active_agents():
    """Test getting agents that can handle current state."""
    coordinator = A2ACoordinator()
    world_state = WorldState()

    # Agent that can handle
    agent1 = MockAgent("agent1", can_handle=True)
    # Agent that cannot handle
    agent2 = MockAgent("agent2", can_handle=False)

    coordinator.register_agent(agent1)
    coordinator.register_agent(agent2)

    active_agents = coordinator._get_active_agents()

    assert len(active_agents) == 1
    assert active_agents[0] == agent1

def test_should_replan():
    """Test replanning decision logic."""
    coordinator = A2ACoordinator()
    world_state = WorldState()

    # Agent that doesn't need replanning
    agent1 = MockAgent("agent1", should_replan=False)
    # Agent that needs replanning
    agent2 = MockAgent("agent2", should_replan=True)

    coordinator.register_agent(agent1)
    coordinator.register_agent(agent2)

    # Should return True because agent2 needs replanning
    assert coordinator._should_replan() == True

def test_delta_application():
    """Test applying deltaState patches to world state."""
    coordinator = A2ACoordinator()
    world_state = WorldState()

    # Apply a delta
    delta = {
        "deltaState": {
            "context": {
                "test_field": "test_value",
                "plan": {"steps": [{"id": "S1", "action": "test"}]}
            },
            "errors": ["test error"]
        }
    }

    new_world_state = coordinator._apply_delta(world_state, delta)

    assert new_world_state.context["test_field"] == "test_value"
    assert new_world_state.context["plan"]["steps"][0]["id"] == "S1"
    assert "test error" in new_world_state.errors

@patch('agents.coordinator.MemoryManager')
def test_memory_integration(mock_memory_manager):
    """Test memory manager integration."""
    mock_memory = Mock()
    mock_memory_manager.return_value = mock_memory
    mock_memory.get_recent_context.return_value = {"test": "context"}

    coordinator = A2ACoordinator()

    # Test memory context retrieval
    context = coordinator.get_memory_context()
    assert context == {"test": "context"}
    mock_memory.get_recent_context.assert_called_once()

def test_conversation_reset():
    """Test conversation reset functionality."""
    coordinator = A2ACoordinator()

    # Add some state
    coordinator.world_state.query = {"raw": "test query"}
    coordinator.message_queue.append(AgentMessage(
        agent_name="test",
        message_type="test",
        content={},
        timestamp=None
    ))

    # Reset conversation
    coordinator.reset_conversation()

    # Check reset
    assert coordinator.world_state.query["raw"] == ""
    assert len(coordinator.message_queue) == 0

if __name__ == "__main__":
    # Run basic tests
    test_coordinator_initialization()
    test_agent_registration()
    test_message_broadcasting()
    test_get_active_agents()
    test_should_replan()
    test_delta_application()
    test_conversation_reset()

    print("✅ All A2A coordinator tests passed!")