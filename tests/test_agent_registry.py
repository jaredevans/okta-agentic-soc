import pytest
from typing import Any, Dict
from okta_soc.agents.base import BaseAgent, AgentContract
from okta_soc.agents.registry import AgentRegistry


class FakeDetector(BaseAgent):
    contract = AgentContract(
        name="fake_detector",
        description="Detects fake things",
        consumes=["List[OktaEvent]"],
        produces=["List[DetectionFinding]"],
        phase_hint="ingest",
    )

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {"List[DetectionFinding]": []}


class FakeRisk(BaseAgent):
    contract = AgentContract(
        name="fake_risk",
        description="Scores risk",
        consumes=["DetectionFinding"],
        produces=["RiskScore", "SecurityIncident"],
        phase_hint="analysis",
    )

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {"RiskScore": {}, "SecurityIncident": {}}


def test_register_and_list_agents():
    registry = AgentRegistry()
    det = FakeDetector()
    risk = FakeRisk()
    registry.register(det)
    registry.register(risk)

    assert "fake_detector" in registry.agents
    assert "fake_risk" in registry.agents
    assert len(registry.agents) == 2


def test_get_agent():
    registry = AgentRegistry()
    det = FakeDetector()
    registry.register(det)
    assert registry.get("fake_detector") is det
    assert registry.get("nonexistent") is None


def test_catalog_description():
    registry = AgentRegistry()
    registry.register(FakeDetector())
    catalog = registry.catalog_for_llm()
    assert "fake_detector" in catalog
    assert "List[OktaEvent]" in catalog
    assert "List[DetectionFinding]" in catalog


def test_duplicate_registration_raises():
    registry = AgentRegistry()
    registry.register(FakeDetector())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeDetector())
