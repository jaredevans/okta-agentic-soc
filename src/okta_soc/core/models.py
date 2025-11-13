from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingType(str, Enum):
    IMPOSSIBLE_TRAVEL = "impossible_travel"
    FAILED_LOGIN_BURST = "failed_login_burst"
    MFA_FATIGUE = "mfa_fatigue"
    OTHER = "other"


class OktaEvent(BaseModel):
    id: str
    event_type: str
    actor_id: Optional[str]
    actor_type: Optional[str]
    target_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    outcome: Optional[str] = None  # SUCCESS / FAILURE
    timestamp: datetime
    raw: Dict[str, Any] = Field(default_factory=dict)


class DetectionFinding(BaseModel):
    id: str
    finding_type: FindingType
    description: str
    okta_event_ids: List[str]
    user_id: Optional[str]
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RiskScore(BaseModel):
    finding_id: str
    severity: Severity
    likelihood: float  # 0.0 - 1.0
    impact: float      # 0.0 - 1.0
    score: float       # overall 0.0 - 1.0
    rationale: str


class SecurityIncident(BaseModel):
    id: str
    finding_id: str
    title: str
    description: str
    severity: Severity
    risk_score: float
    created_at: datetime
    status: str = "open"  # open / triaged / closed
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResponseStep(BaseModel):
    step_id: str
    description: str
    rationale: str
    requires_human_approval: bool = True
    dependencies: List[str] = Field(default_factory=list)


class ResponsePlan(BaseModel):
    incident_id: str
    overall_goal: str
    steps: List[ResponseStep]
    notes: Optional[str] = None


class CommandSuggestion(BaseModel):
    step_id: str
    description: str
    command: str
    system: str  # e.g. "okta_api", "okta_cli", "siem", "email"
    read_only: bool = True
    notes: Optional[str] = None
