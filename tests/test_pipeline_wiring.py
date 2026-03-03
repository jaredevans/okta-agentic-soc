"""Verify the pipeline wires up correctly and the registry has all agents."""
from okta_soc.agents.base import AgentContract
from okta_soc.agents.registry import AgentRegistry
from okta_soc.agents.detector_agent import DetectorAgent
from okta_soc.agents.risk_agent import LLMRiskAgent
from okta_soc.agents.planner_agent import PlannerAgent
from okta_soc.agents.command_agent import CommandAgent
from okta_soc.agents.escalation_agent import EscalationAgent


def test_all_agents_register_without_error():
    """All five agents can be registered in a single registry."""
    registry = AgentRegistry()
    # These don't need real LLM clients for registration
    registry.register(DetectorAgent())
    # For agents needing LLM, use __new__ to skip __init__
    risk = LLMRiskAgent.__new__(LLMRiskAgent)
    risk.contract = LLMRiskAgent.contract
    registry.register(risk)

    planner = PlannerAgent.__new__(PlannerAgent)
    planner.contract = PlannerAgent.contract
    registry.register(planner)

    cmd = CommandAgent.__new__(CommandAgent)
    cmd.contract = CommandAgent.contract
    registry.register(cmd)

    registry.register(EscalationAgent())

    assert len(registry.agents) == 5
    catalog = registry.catalog_for_llm()
    assert "detector_agent" in catalog
    assert "risk_agent" in catalog
    assert "planner_agent" in catalog
    assert "command_agent" in catalog
    assert "escalation_agent" in catalog
