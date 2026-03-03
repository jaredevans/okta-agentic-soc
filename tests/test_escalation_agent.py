"""Tests for EscalationAgent."""
from okta_soc.core.models import EscalationResult


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
