import logging
from typing import Any, Dict

from .base import BaseAgent, AgentContract
from okta_soc.core.models import SecurityIncident, Severity, EscalationResult

logger = logging.getLogger(__name__)

ESCALATION_SEVERITIES = {Severity.HIGH, Severity.CRITICAL}


class EscalationAgent(BaseAgent):
    contract = AgentContract(
        name="escalation_agent",
        description=(
            "Sends Slack notification for security incidents. "
            "Include this agent whenever SecurityIncidents will be produced. "
            "The agent internally filters by severity and only notifies for HIGH or CRITICAL."
        ),
        consumes=["SecurityIncident"],
        produces=["EscalationResult"],
        phase_hint="response",
        actions=["slack_notification"],
    )

    CHANNEL = "#soc-critical-alerts"

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        incident = input_data["SecurityIncident"]
        if isinstance(incident, dict):
            incident = SecurityIncident.model_validate(incident)

        should_send = incident.severity in ESCALATION_SEVERITIES

        message = (
            f"[{incident.severity.value.upper()}] {incident.title}\n"
            f"Risk score: {incident.risk_score:.2f}\n"
            f"{incident.description}"
        )

        if should_send:
            print(f"\n\U0001f4e2 [SIMULATED SLACK] {self.CHANNEL}\n{message}\n")
            logger.info(
                "[SIMULATED SLACK] #%s \u2192 %s",
                self.CHANNEL,
                message,
            )

        result = EscalationResult(
            incident_id=incident.id,
            channel=self.CHANNEL,
            message=message,
            sent=should_send,
        )
        return {"EscalationResult": result}
