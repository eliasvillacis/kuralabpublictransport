"""
A2A (Agent-to-Agent) Coordinator for transportation assistant.

Two-agent architecture:
- Planner: Creates structured execution plans
- Executor: Executes plan steps with LLM reasoning

Agents communicate through WorldState with deltaState patches.
"""

import json
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
import os
from utils.contracts import WorldState
from utils.logger import get_logger
from utils.state import deepMerge
from agents.agents import PlanningAgent, ExecutionAgent

# Load environment variables from project root .env if present
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=dotenv_path)

logger = get_logger(__name__)


class A2ACoordinator:
    """Two-agent coordinator managing Planner -> Executor flow."""

    def __init__(self):
        self.planner = PlanningAgent()
        self.executor = ExecutionAgent()
        self.world_state = WorldState()
        self.memory_file = "data/conversation_memory.json"
        self._load_memory()

    def _load_memory(self):
        """Load conversation memory."""
        try:
            with open(self.memory_file, "r") as f:
                data = json.load(f)
                # Restore relevant context if needed
                if data.get("context"):
                    self.world_state.context.update(data["context"])
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_memory(self):
        """Save conversation memory."""
        try:
            data = {
                "context": self.world_state.context,
                "last_updated": datetime.now().isoformat()
            }
            with open(self.memory_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save memory: {e}")

    def process_user_query(self, user_query: str) -> str:
        """Process user query through two-agent flow: Planner -> Executor."""
        logger.info(f"Processing user query: {user_query}")

        # Initialize world state with user query
        self.world_state = WorldState()
        self.world_state.query = {"raw": user_query}

        try:
            # Step 1: Planner creates execution plan
            logger.info("Running Planner agent")
            planner_result = self.planner.process(self.world_state)

            # Apply planner's deltaState to world state
            self.world_state = self._apply_delta(self.world_state, planner_result)

            # Check if planner generated a valid plan
            plan = self.world_state.context.get("plan", {})
            steps = plan.get("steps", [])
            if not steps:
                logger.warning("Planner generated no steps")
                return "I\'m sorry, I couldn\'t understand how to help with that request."

            logger.info(f"Planner generated plan with {len(steps)} steps")

            # Step 2: Executor executes plan and generates final response
            logger.info("Running Executor agent")
            executor_result = self.executor.process(self.world_state)

            # Apply executor's deltaState to world state
            self.world_state = self._apply_delta(self.world_state, executor_result)

            # Extract final response from executor
            final_response = self.world_state.context.get("final_response", "")

            if final_response:
                logger.info("Executor generated final response")
                self._save_memory()
                return final_response
            else:
                logger.warning("Executor did not generate final_response")
                return "I\'m sorry, I couldn\'t complete your request effectively."

        except Exception as e:
            logger.exception(f"Error in A2A processing: {e}")
            error_response = "I encountered an error while processing your request. Please try again."
            # Ensure world_state exists and has a context mapping
            try:
                self.world_state.context["final_response"] = error_response
            except Exception:
                # If world_state is not fully initialized, create a minimal one
                self.world_state = WorldState()
                self.world_state.context["final_response"] = error_response
            self._save_memory()
            return error_response

    def _apply_delta(self, world_state: WorldState, delta: Dict[str, Any]) -> WorldState:
        """Apply deltaState patch to world state."""
        delta_state = delta.get("deltaState", delta)
        merged = world_state.model_dump()
        deepMerge(merged, delta_state)
        return WorldState(**merged)

    def reset_conversation(self):
        """Reset conversation state."""
        self.world_state = WorldState()
        self._save_memory()

    def get_world_state(self) -> WorldState:
        """Get current world state for debugging."""
        return self.world_state


# Global coordinator instance
_coordinator: Optional[A2ACoordinator] = None


def get_coordinator() -> A2ACoordinator:
    """Get or create the global A2A coordinator."""
    global _coordinator
    if _coordinator is None:
        _coordinator = A2ACoordinator()
    return _coordinator
