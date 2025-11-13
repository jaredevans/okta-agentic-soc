from dataclasses import dataclass
from typing import Dict


@dataclass
class AgentMeta:
    name: str
    description: str
    input_type: str
    output_type: str
    phase: str          # "ingest", "analysis", "response"
    critical: bool = False


AGENTS: Dict[str, AgentMeta] = {
    "detector_agent": AgentMeta(
        name="detector_agent",
        description="Analyzes Okta events to detect anomalies like impossible travel, failed-login bursts, and MFA fatigue. Produces DetectionFindings.",
        input_type="List[OktaEvent]",
        output_type="List[DetectionFinding]",
        phase="ingest",
        critical=True,
    ),
    "risk_agent": AgentMeta(
        name="risk_agent",
        description="Assigns severity and risk scores to DetectionFindings, deciding how serious each one is.",
        input_type="DetectionFinding",
        output_type="RiskScore",
        phase="analysis",
        critical=True,
    ),
    "planner_agent": AgentMeta(
        name="planner_agent",
        description="Creates a ResponsePlan (steps, rationale) for a given SecurityIncident.",
        input_type="SecurityIncident",
        output_type="ResponsePlan",
        phase="response",
        critical=True,
    ),
    "command_agent": AgentMeta(
        name="command_agent",
        description="Generates read-only commands from a ResponsePlan for a human analyst to review.",
        input_type="ResponsePlan",
        output_type="List[CommandSuggestion]",
        phase="response",
        critical=False,
    ),
}
