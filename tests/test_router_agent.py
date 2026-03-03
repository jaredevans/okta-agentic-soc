import pytest
import asyncio
from unittest.mock import MagicMock
from typing import Any, Dict

from okta_soc.agents.router_agent import RouterAgent
from okta_soc.agents.base import BaseAgent, AgentContract
from okta_soc.agents.registry import AgentRegistry
from okta_soc.core.pipeline_context import PipelineContext


class StubDetector(BaseAgent):
    contract = AgentContract(
        name="detector_agent",
        description="Detects anomalies",
        consumes=["List[OktaEvent]"],
        produces=["List[DetectionFinding]"],
        phase_hint="ingest",
    )
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {}


class StubRisk(BaseAgent):
    contract = AgentContract(
        name="risk_agent",
        description="Scores risk",
        consumes=["DetectionFinding"],
        produces=["RiskScore", "SecurityIncident"],
        phase_hint="analysis",
    )
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {}


def _make_registry() -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(StubDetector())
    reg.register(StubRisk())
    return reg


def test_validate_type_compatible_plan():
    """A valid plan where each agent's inputs are available."""
    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "steps": [
            {"agent_name": "detector_agent", "reason": "detect"},
            {"agent_name": "risk_agent", "reason": "score", "iterate_over": "List[DetectionFinding]"},
        ]
    }

    registry = _make_registry()
    router = RouterAgent(llm=mock_llm, registry=registry)

    ctx = PipelineContext(
        data={"List[OktaEvent]": []},
        metadata={},
    )

    plan = asyncio.run(router.run(ctx))
    assert len(plan.steps) == 2
    assert plan.steps[0].agent_name == "detector_agent"
    assert plan.steps[1].agent_name == "risk_agent"


def test_validate_removes_invalid_agent():
    """An agent whose inputs aren't available gets removed."""
    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "steps": [
            {"agent_name": "risk_agent", "reason": "score first"},  # needs DetectionFinding, not available
            {"agent_name": "detector_agent", "reason": "detect"},
        ]
    }

    registry = _make_registry()
    router = RouterAgent(llm=mock_llm, registry=registry)

    ctx = PipelineContext(
        data={"List[OktaEvent]": []},
        metadata={},
    )

    plan = asyncio.run(router.run(ctx))
    # risk_agent should be removed (DetectionFinding not available at that point)
    # detector_agent should remain (List[OktaEvent] is available)
    assert len(plan.steps) == 1
    assert plan.steps[0].agent_name == "detector_agent"


def test_validate_rejects_unknown_agent():
    """An agent not in the registry is removed."""
    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "steps": [
            {"agent_name": "nonexistent_agent", "reason": "???"},
            {"agent_name": "detector_agent", "reason": "detect"},
        ]
    }

    registry = _make_registry()
    router = RouterAgent(llm=mock_llm, registry=registry)

    ctx = PipelineContext(
        data={"List[OktaEvent]": []},
        metadata={},
    )

    plan = asyncio.run(router.run(ctx))
    assert len(plan.steps) == 1
    assert plan.steps[0].agent_name == "detector_agent"


class StubPlanner(BaseAgent):
    contract = AgentContract(
        name="planner_agent",
        description="Plans response",
        consumes=["SecurityIncident"],
        produces=["ResponsePlan"],
        phase_hint="response",
    )
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {}


class StubEscalation(BaseAgent):
    contract = AgentContract(
        name="escalation_agent",
        description="Sends Slack notification for high-severity incidents.",
        consumes=["SecurityIncident"],
        produces=["EscalationResult"],
        phase_hint="response",
        side_effects=["slack_notification"],
    )
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {}


def test_auto_iterate_when_list_available():
    """If agent consumes T but only List[T] is available, auto-set iterate_over."""
    mock_llm = MagicMock()
    # LLM forgets to set iterate_over for planner
    mock_llm.chat_json.return_value = {
        "steps": [
            {"agent_name": "detector_agent", "reason": "detect"},
            {"agent_name": "risk_agent", "reason": "score", "iterate_over": "List[DetectionFinding]"},
            {"agent_name": "planner_agent", "reason": "plan"},  # no iterate_over
        ]
    }

    reg = AgentRegistry()
    reg.register(StubDetector())
    reg.register(StubRisk())
    reg.register(StubPlanner())
    router = RouterAgent(llm=mock_llm, registry=reg)

    ctx = PipelineContext(
        data={"List[OktaEvent]": []},
        metadata={},
    )

    plan = asyncio.run(router.run(ctx))
    assert len(plan.steps) == 3
    # planner should have iterate_over auto-set
    assert plan.steps[2].agent_name == "planner_agent"
    assert plan.steps[2].iterate_over == "List[SecurityIncident]"


def test_iterated_step_only_produces_list_types():
    """After an iterated step, only List[T] should be available, not bare T."""
    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "steps": [
            {"agent_name": "detector_agent", "reason": "detect"},
            {"agent_name": "risk_agent", "reason": "score", "iterate_over": "List[DetectionFinding]"},
            {"agent_name": "planner_agent", "reason": "plan"},
        ]
    }

    reg = AgentRegistry()
    reg.register(StubDetector())
    reg.register(StubRisk())
    reg.register(StubPlanner())
    router = RouterAgent(llm=mock_llm, registry=reg)

    ctx = PipelineContext(
        data={"List[OktaEvent]": []},
        metadata={},
    )

    plan = asyncio.run(router.run(ctx))
    # planner should still be included (auto-iterated over List[SecurityIncident])
    assert len(plan.steps) == 3
    assert plan.steps[2].iterate_over == "List[SecurityIncident]"


def test_escalation_included_when_incidents_available():
    """Router can include escalation_agent alongside planner_agent."""
    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "steps": [
            {"agent_name": "detector_agent", "reason": "detect"},
            {"agent_name": "risk_agent", "reason": "score", "iterate_over": "List[DetectionFinding]"},
            {"agent_name": "planner_agent", "reason": "plan"},
            {"agent_name": "escalation_agent", "reason": "notify SOC team"},
        ]
    }

    reg = AgentRegistry()
    reg.register(StubDetector())
    reg.register(StubRisk())
    reg.register(StubPlanner())
    reg.register(StubEscalation())
    router = RouterAgent(llm=mock_llm, registry=reg)

    ctx = PipelineContext(
        data={"List[OktaEvent]": []},
        metadata={},
    )

    plan = asyncio.run(router.run(ctx))
    agent_names = [s.agent_name for s in plan.steps]
    assert "escalation_agent" in agent_names
    assert "planner_agent" in agent_names
    # Both should auto-iterate over List[SecurityIncident]
    for step in plan.steps:
        if step.agent_name in ("planner_agent", "escalation_agent"):
            assert step.iterate_over == "List[SecurityIncident]"
