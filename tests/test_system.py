"""
Test the A2A (Agent-to-Agent) coordinator system.
"""

import sys
import os
import pytest
from datetime import datetime
from unittest.mock import Mock, patch

# Ensure project root is on path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.coordinator import A2ACoordinator
from agents.agents import PlanningAgent, ExecutionAgent
from utils.contracts import WorldState


def test_coordinator_initialization():
    """Test A2A coordinator initialization."""
    coordinator = A2ACoordinator()

    assert isinstance(coordinator.planner, PlanningAgent)
    assert isinstance(coordinator.executor, ExecutionAgent)
    assert isinstance(coordinator.world_state, WorldState)


@patch('agents.agents.PlanningAgent.process')
@patch('agents.agents.ExecutionAgent.process')
def test_process_user_query_success(mock_executor_process, mock_planner_process):
    """Test successful processing of user query through planner → executor flow."""
    coordinator = A2ACoordinator()

    # Mock planner response with a plan
    mock_planner_process.return_value = {
        "deltaState": {
            "context": {
                "plan": {
                    "steps": [{"id": "S1", "action": "Directions", "args": {"destination": "test"}}],
                    "status": "planning",
                    "confidence": 0.9
                }
            }
        },
        "snippet": "Generated plan"
    }

    # Mock executor response with final answer
    mock_executor_process.return_value = {
        "deltaState": {
            "context": {
                "final_response": "Here are directions to your destination."
            }
        },
        "snippet": "Executed plan"
    }

    result = coordinator.process_user_query("How do I get to the store?")

    assert result == "Here are directions to your destination."
    mock_planner_process.assert_called_once()
    mock_executor_process.assert_called_once()


@patch('agents.agents.PlanningAgent.process')
def test_process_user_query_planner_fails(mock_planner_process):
    """Test handling when planner fails to generate a plan."""
    coordinator = A2ACoordinator()

    # Mock planner response with no steps
    mock_planner_process.return_value = {
        "deltaState": {
            "context": {
                "plan": {
                    "steps": [],
                    "status": "failed"
                }
            }
        },
        "snippet": "No plan generated"
    }

    result = coordinator.process_user_query("Invalid query")

    assert "couldn't understand" in result.lower()
    mock_planner_process.assert_called_once()


@patch('agents.agents.PlanningAgent.process')
@patch('agents.agents.ExecutionAgent.process')
def test_process_user_query_executor_fails(mock_executor_process, mock_planner_process):
    """Test handling when executor fails to generate final response."""
    coordinator = A2ACoordinator()

    # Mock planner response with a plan
    mock_planner_process.return_value = {
        "deltaState": {
            "context": {
                "plan": {
                    "steps": [{"id": "S1", "action": "Directions", "args": {"destination": "test"}}],
                    "status": "planning",
                    "confidence": 0.9
                }
            }
        },
        "snippet": "Generated plan"
    }

    # Mock executor response without final_response
    mock_executor_process.return_value = {
        "deltaState": {
            "context": {
                "some_result": "data"
            }
        },
        "snippet": "Executed but no response"
    }

    result = coordinator.process_user_query("How do I get to the store?")

    assert "couldn't complete" in result.lower()
    mock_planner_process.assert_called_once()
    mock_executor_process.assert_called_once()


def test_reset_conversation():
    """Test conversation reset functionality."""
    coordinator = A2ACoordinator()

    # Add some state
    coordinator.world_state.context["test"] = "data"
    coordinator.world_state.query["raw"] = "test query"

    coordinator.reset_conversation()

    # Check that added data is removed but defaults remain
    assert "test" not in coordinator.world_state.context
    assert coordinator.world_state.query["raw"] == ""  # Should be reset
    assert coordinator.world_state.context["city"] == "New York"  # Default should remain


def test_get_world_state():
    """Test getting current world state."""
    coordinator = A2ACoordinator()

    state = coordinator.get_world_state()

    assert isinstance(state, WorldState)


def test_get_coordinator_singleton():
    """Test that get_coordinator returns a singleton instance."""
    from agents.coordinator import get_coordinator

    coord1 = get_coordinator()
    coord2 = get_coordinator()

    assert coord1 is coord2
    assert isinstance(coord1, A2ACoordinator)