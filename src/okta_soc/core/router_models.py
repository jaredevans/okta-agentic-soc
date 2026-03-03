from typing import List, Optional
from pydantic import BaseModel


class RouteStep(BaseModel):
    agent_name: str
    reason: str
    iterate_over: Optional[str] = None  # e.g. "List[SecurityIncident]"


class RoutePlan(BaseModel):
    steps: List[RouteStep]
    notes: Optional[str] = None
