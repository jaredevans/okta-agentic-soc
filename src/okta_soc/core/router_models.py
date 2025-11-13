from typing import List, Optional
from pydantic import BaseModel


class RouteStep(BaseModel):
    agent_name: str
    reason: str
    when: str  # "now", "after_incident_created", etc.


class RoutePlan(BaseModel):
    phase: str                     # "ingest" | "analysis" | "response"
    steps: List[RouteStep]
    notes: Optional[str] = None
