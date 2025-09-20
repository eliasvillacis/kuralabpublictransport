"""
Contract schemas for the multi-agent transportation assistant.

This module defines the Pydantic models used for:
1. The shared WorldState (the blackboard)
2. Input contracts for specialists (what they need to do their job)
3. Output contract for specialists (what they return to the PlannerAgent)
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional

class GeoPoint(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None

class Slots(BaseModel):
    origin: Dict[str, Any] = {"name": None, "lat": None, "lng": None}
    destination: Dict[str, Any] = {"name": None, "lat": None, "lng": None}
    departureTime: Optional[str] = None
    modePrefs: List[str] = []

class WorldState(BaseModel):
    """
    The central blackboard for the multi-agent system.
    Stores the current state of the conversation, user preferences,
    slot values, and evidence collected.
    """
    meta: Dict[str, Any] = {"sessionId": None, "version": "2.0", "architecture": "A2A"}
    user: Dict[str, Any] = {"locale": "en-US", "timezone": "America/New_York"}
    query: Dict[str, Any] = {"raw": ""}
    slots: Slots = Field(default_factory=Slots)
    context: Dict[str, Any] = {
        "city": "New York",
        "units": "imperial",
        "plan": {"steps": [], "status": "none", "confidence": 0.0},
        "completed_steps": [],
        "execution_result": {},
        "last_planning": None,
        "last_execution": None,
        "final_response": None
    }
    evidence: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    memory: Dict[str, Any] = Field(default_factory=dict)  # A2A memory integration

class GeocodeIn(BaseModel):
    """Input contract for the geocoding specialist."""
    originName: Optional[str] = None
    destinationName: Optional[str] = None
    cityHint: Optional[str] = None

class TransitIn(BaseModel):
    """Input contract for the transit specialist."""
    origin: GeoPoint
    destination: GeoPoint
    departureTime: Optional[str]
    modePrefs: List[str] = []
    optimizeFor: str = "reliability"
    constraints: Dict[str, Any] = {"maxTransfers": 3}

class SpecialistOut(BaseModel):
    """
    Output contract for all specialists.
    Includes:
    - status: ok, error
    - confidence: 0.0 to 1.0
    - deltaState: updates to merge into the WorldState
    - snippet: natural language answer fragment
    - evidence: raw responses, IDs, etc. for auditing
    - errors: any error messages to log
    """
    status: str
    confidence: float = 0.0
    deltaState: Dict[str, Any] = Field(default_factory=dict)
    snippet: str = ""
    evidence: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)