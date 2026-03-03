import pytest
import asyncio
from typing import Any, Dict
from unittest.mock import MagicMock

from okta_soc.agents.base import BaseAgent, AgentContract
from okta_soc.agents.registry import AgentRegistry
from okta_soc.agents.orchestrator import Orchestrator
from okta_soc.core.router_models import RoutePlan, RouteStep
from okta_soc.core.pipeline_context import PipelineContext


class MockDetector(BaseAgent):
    contract = AgentContract(
        name="detector_agent",
        description="Detects things",
        consumes=["List[OktaEvent]"],
        produces=["List[DetectionFinding]"],
        phase_hint="ingest",
    )
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        events = input_data["List[OktaEvent]"]
        findings = [{"id": f"f-{e['id']}", "type": "test"} for e in events]
        return {"List[DetectionFinding]": findings}


class MockRisk(BaseAgent):
    contract = AgentContract(
        name="risk_agent",
        description="Scores risk",
        consumes=["DetectionFinding"],
        produces=["RiskScore"],
        phase_hint="analysis",
    )
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        finding = input_data["DetectionFinding"]
        return {"RiskScore": {"finding_id": finding["id"], "score": 0.8}}


def _make_registry():
    reg = AgentRegistry()
    reg.register(MockDetector())
    reg.register(MockRisk())
    return reg


def test_orchestrator_runs_simple_pipeline():
    """Non-iterating pipeline: detector consumes list, produces list."""
    registry = _make_registry()

    async def mock_route(ctx):
        return RoutePlan(
            steps=[RouteStep(agent_name="detector_agent", reason="detect")],
        )

    mock_router = MagicMock()
    mock_router.run = mock_route

    orchestrator = Orchestrator(router=mock_router, registry=registry)
    ctx = asyncio.run(orchestrator.run(
        initial_data={"List[OktaEvent]": [{"id": "e1"}, {"id": "e2"}]},
        metadata={"source": "test"},
    ))

    assert "List[DetectionFinding]" in ctx.data
    assert len(ctx.data["List[DetectionFinding]"]) == 2
    assert len(ctx.history) == 1
    assert ctx.history[0].agent == "detector_agent"


def test_orchestrator_handles_iterate_over():
    """Pipeline with iterate_over: risk_agent runs once per finding."""
    registry = _make_registry()

    async def mock_route(ctx):
        return RoutePlan(steps=[
            RouteStep(agent_name="detector_agent", reason="detect"),
            RouteStep(agent_name="risk_agent", reason="score", iterate_over="List[DetectionFinding]"),
        ])

    mock_router = MagicMock()
    mock_router.run = mock_route

    orchestrator = Orchestrator(router=mock_router, registry=registry)
    ctx = asyncio.run(orchestrator.run(
        initial_data={"List[OktaEvent]": [{"id": "e1"}, {"id": "e2"}]},
        metadata={"source": "test"},
    ))

    assert "List[DetectionFinding]" in ctx.data
    assert "List[RiskScore]" in ctx.data
    assert len(ctx.data["List[RiskScore]"]) == 2
    assert len(ctx.history) == 2
