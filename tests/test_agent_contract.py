import pytest
from okta_soc.agents.base import BaseAgent, AgentContract


def test_agent_contract_has_required_fields():
    contract = AgentContract(
        name="test_agent",
        description="A test agent",
        consumes=["List[OktaEvent]"],
        produces=["List[DetectionFinding]"],
        phase_hint="ingest",
    )
    assert contract.name == "test_agent"
    assert contract.consumes == ["List[OktaEvent]"]
    assert contract.produces == ["List[DetectionFinding]"]
    assert contract.side_effects == []
    assert contract.requires_human_approval is False


def test_agent_contract_with_side_effects():
    contract = AgentContract(
        name="notifier",
        description="Sends alerts",
        consumes=["SecurityIncident"],
        produces=["NotificationResult"],
        phase_hint="response",
        side_effects=["slack_notification"],
        requires_human_approval=False,
    )
    assert contract.side_effects == ["slack_notification"]


def test_base_agent_requires_contract():
    """A concrete agent must have a contract attribute."""
    with pytest.raises(TypeError):
        # Can't instantiate abstract class without contract
        BaseAgent()
