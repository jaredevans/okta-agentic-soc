"""Verify all existing agents implement the new contract interface."""
from okta_soc.agents.base import AgentContract
from okta_soc.agents.detector_agent import DetectorAgent
from okta_soc.agents.risk_agent import LLMRiskAgent
from okta_soc.agents.planner_agent import PlannerAgent
from okta_soc.agents.command_agent import CommandAgent


def test_detector_agent_has_contract():
    agent = DetectorAgent()
    assert isinstance(agent.contract, AgentContract)
    assert agent.contract.name == "detector_agent"
    assert "List[OktaEvent]" in agent.contract.consumes
    assert "List[DetectionFinding]" in agent.contract.produces


def test_risk_agent_has_contract():
    # LLMRiskAgent needs an LLM client — pass None, we only check contract
    agent = LLMRiskAgent.__new__(LLMRiskAgent)
    assert isinstance(agent.contract, AgentContract)
    assert agent.contract.name == "risk_agent"
    assert "DetectionFinding" in agent.contract.consumes
    assert "RiskScore" in agent.contract.produces


def test_planner_agent_has_contract():
    agent = PlannerAgent.__new__(PlannerAgent)
    assert isinstance(agent.contract, AgentContract)
    assert agent.contract.name == "planner_agent"
    assert "SecurityIncident" in agent.contract.consumes
    assert "ResponsePlan" in agent.contract.produces


def test_command_agent_has_contract():
    agent = CommandAgent.__new__(CommandAgent)
    assert isinstance(agent.contract, AgentContract)
    assert agent.contract.name == "command_agent"
    assert "ResponsePlan" in agent.contract.consumes
    assert "List[CommandSuggestion]" in agent.contract.produces
