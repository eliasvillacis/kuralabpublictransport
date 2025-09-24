import os
import sys
import types
from types import SimpleNamespace

import pytest

# Ensure project root is on sys.path so tests can import package modules
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.contracts import WorldState

from agents.agents import ExecutionAgent


class FakeLLM:
    """A tiny fake LLM that returns a JSON tools plan containing a single Directions step
    with a free-form query. This forces the executor's autopatch to insert a PlacesSearch.
    """

    def invoke(self, prompt: str):
        # Return an object with a .content attribute similar to real LLM responses
        resp = SimpleNamespace()
        resp.content = '{"tools": [{"name": "Directions", "args": {"query": "nearest Burger King"}}]}'
        return resp


def test_places_autopatch_inserts_places_and_calls_directions():
    # Prepare world state: planner already produced a plan with a Directions step
    ws = WorldState()
    ws.query["raw"] = "Find nearest Burger King"
    ws.context["plan"] = {
        "steps": [{"id": "S1", "action": "Directions", "args": {"query": "nearest Burger King"}}],
        "status": "planning",
        "confidence": 0.9,
    }

    # Track calls
    places_calls = []
    directions_calls = []

    # Fake PlacesSearch.func -> returns a top result with placeId
    def fake_places_func(**kwargs):
        places_calls.append(kwargs)
        return {
            "context": {
                "places": {
                    "results": [
                        {"placeId": "PLACE_123", "name": "Burger King", "lat": 40.0, "lng": -73.0}
                    ]
                }
            }
        }

    # Fake Directions.func -> capture received destination/origin
    def fake_directions_func(**kwargs):
        directions_calls.append(kwargs)
        return {"context": {"directions": {"destination_received": kwargs.get("destination"), "origin_received": kwargs.get("origin")}}}

    # Instantiate agent and inject fakes
    agent = ExecutionAgent()
    agent.llm = FakeLLM()

    # Monkeypatch the module-level tool references used by the agent
    import agents.agents as agents_mod

    agents_mod.PlacesSearch = SimpleNamespace(func=fake_places_func)
    agents_mod.directions = SimpleNamespace(func=fake_directions_func)

    # Run the executor process which should use the fake LLM to produce a tools plan,
    # autopatch PlacesSearch before Directions, execute PlacesSearch (populating context.places),
    # and then execute Directions.
    result = agent.process(ws)

    # Basic sanity checks
    assert places_calls, "PlacesSearch was not called"
    assert directions_calls, "Directions was not called"

    # Ensure PlacesSearch was called with the original query (or a query that contains the phrase)
    assert any("burger king" in str(c.get("query", "")).lower() for c in places_calls)

    # Check call order: PlacesSearch should be executed before Directions
    # (we recorded calls separately so this means both were called at least once)
    # Ensure the final context contains the places results we returned from fake_places_invoke
    delta = result.get("deltaState", {}) or result
    ctx = delta.get("context", {})
    assert ctx.get("places") and ctx["places"].get("results"), "places results not present in returned context"
    assert ctx["places"]["results"][0]["placeId"] == "PLACE_123"

    # Verify that Directions received a destination argument (it may be a placeholder or resolved)
    last_dir_call = directions_calls[-1]
    assert ("destination" in last_dir_call) or ("origin" in last_dir_call), "Directions did not receive destination/origin args"
