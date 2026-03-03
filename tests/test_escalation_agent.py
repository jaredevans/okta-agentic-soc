"""Tests for EscalationAgent."""
import asyncio
from datetime import datetime, timezone
from okta_soc.core.models import EscalationResult, SecurityIncident, Severity


def test_escalation_result_model():
    result = EscalationResult(
        incident_id="inc-123",
        channel="#soc-critical-alerts",
        message="[CRITICAL] Incident from impossible_travel",
        sent=True,
    )
    assert result.incident_id == "inc-123"
    assert result.channel == "#soc-critical-alerts"
    assert result.sent is True


# --- EscalationAgent tests (TDD: written before the agent exists) ---

from okta_soc.agents.escalation_agent import EscalationAgent
from okta_soc.agents.base import AgentContract


def test_escalation_agent_has_contract():
    agent = EscalationAgent()
    assert isinstance(agent.contract, AgentContract)
    assert agent.contract.name == "escalation_agent"
    assert "SecurityIncident" in agent.contract.consumes
    assert "EscalationResult" in agent.contract.produces
    assert "slack_notification" in agent.contract.side_effects


def _make_incident(severity: Severity) -> SecurityIncident:
    return SecurityIncident(
        id="inc-001",
        finding_id="f-001",
        title="Incident from impossible_travel",
        description="User logged in from two countries within 5 minutes.",
        severity=severity,
        risk_score=0.95,
        created_at=datetime.now(timezone.utc),
        status="open",
    )


def test_escalation_agent_sends_for_critical():
    agent = EscalationAgent()
    incident = _make_incident(Severity.CRITICAL)
    outputs = asyncio.run(agent.run({"SecurityIncident": incident}))
    result = outputs["EscalationResult"]
    assert result.incident_id == "inc-001"
    assert result.channel == "#soc-critical-alerts"
    assert "CRITICAL" in result.message
    assert "impossible_travel" in result.message
    assert result.sent is True


def test_escalation_agent_sends_for_high():
    agent = EscalationAgent()
    incident = _make_incident(Severity.HIGH)
    outputs = asyncio.run(agent.run({"SecurityIncident": incident}))
    result = outputs["EscalationResult"]
    assert result.sent is True


def test_escalation_agent_skips_for_medium():
    agent = EscalationAgent()
    incident = _make_incident(Severity.MEDIUM)
    outputs = asyncio.run(agent.run({"SecurityIncident": incident}))
    result = outputs["EscalationResult"]
    assert result.sent is False


def test_escalation_agent_skips_for_low():
    agent = EscalationAgent()
    incident = _make_incident(Severity.LOW)
    outputs = asyncio.run(agent.run({"SecurityIncident": incident}))
    result = outputs["EscalationResult"]
    assert result.sent is False
