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
