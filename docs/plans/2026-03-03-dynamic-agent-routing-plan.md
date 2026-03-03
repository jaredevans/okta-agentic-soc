# Dynamic LLM-Driven Agent Routing — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the hardcoded router guardrails and orchestrator with a typed-contract system where the LLM genuinely decides which agents to run, constrained only by type compatibility.

**Architecture:** Agents declare `AgentContract` (consumes/produces types). A `PipelineContext` carries typed data between agents. The `RouterAgent` asks the LLM to compose a pipeline from the agent catalog, validates type compatibility, and the `Orchestrator` executes it generically without agent-specific logic.

**Tech Stack:** Python 3.11+, Pydantic 2.x, OpenAI client, async/await

---

### Task 1: AgentContract and Updated BaseAgent

**Files:**
- Modify: `src/okta_soc/agents/base.py`
- Delete contents of: `src/okta_soc/agents/registry.py`

**Step 1: Write the failing test**

Create: `tests/test_agent_contract.py`

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_agent_contract.py -v`
Expected: FAIL — `AgentContract` does not exist yet.

**Step 3: Write minimal implementation**

Replace `src/okta_soc/agents/base.py` with:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentContract:
    name: str
    description: str
    consumes: List[str]           # Data type keys this agent reads from PipelineContext
    produces: List[str]           # Data type keys this agent writes to PipelineContext
    phase_hint: str               # "ingest", "analysis", "response" — advisory
    side_effects: List[str] = field(default_factory=list)
    requires_human_approval: bool = False


class BaseAgent(ABC):
    contract: AgentContract

    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receive input keyed by type name (from contract.consumes).
        Return output keyed by type name (from contract.produces).
        """
        ...
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_agent_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/agents/base.py tests/test_agent_contract.py
git commit -m "feat: add AgentContract dataclass and update BaseAgent interface"
```

---

### Task 2: PipelineContext and StepResult

**Files:**
- Create: `src/okta_soc/core/pipeline_context.py`
- Test: `tests/test_pipeline_context.py`

**Step 1: Write the failing test**

Create: `tests/test_pipeline_context.py`

```python
from okta_soc.core.pipeline_context import PipelineContext, StepResult


def test_pipeline_context_creation():
    ctx = PipelineContext(
        data={"List[OktaEvent]": [{"id": "1"}]},
        metadata={"run_id": "abc", "source": "demo"},
    )
    assert "List[OktaEvent]" in ctx.data
    assert ctx.metadata["run_id"] == "abc"
    assert ctx.history == []


def test_pipeline_context_available_types():
    ctx = PipelineContext(
        data={"List[OktaEvent]": [], "List[DetectionFinding]": []},
        metadata={},
    )
    assert set(ctx.available_types()) == {"List[OktaEvent]", "List[DetectionFinding]"}


def test_step_result():
    result = StepResult(agent="detector_agent", outputs=["List[DetectionFinding]"])
    assert result.agent == "detector_agent"
    assert result.outputs == ["List[DetectionFinding]"]
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_pipeline_context.py -v`
Expected: FAIL — module does not exist.

**Step 3: Write minimal implementation**

Create: `src/okta_soc/core/pipeline_context.py`

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StepResult:
    agent: str
    outputs: List[str]


@dataclass
class PipelineContext:
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    history: List[StepResult] = field(default_factory=list)

    def available_types(self) -> List[str]:
        return list(self.data.keys())
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_pipeline_context.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/core/pipeline_context.py tests/test_pipeline_context.py
git commit -m "feat: add PipelineContext and StepResult for shared pipeline state"
```

---

### Task 3: Updated RoutePlan with iterate_over

**Files:**
- Modify: `src/okta_soc/core/router_models.py`
- Test: `tests/test_router_models.py`

**Step 1: Write the failing test**

Create: `tests/test_router_models.py`

```python
from okta_soc.core.router_models import RoutePlan, RouteStep


def test_route_step_without_iterate():
    step = RouteStep(agent_name="detector_agent", reason="Detect anomalies")
    assert step.iterate_over is None


def test_route_step_with_iterate():
    step = RouteStep(
        agent_name="risk_agent",
        reason="Score each finding",
        iterate_over="List[DetectionFinding]",
    )
    assert step.iterate_over == "List[DetectionFinding]"


def test_route_plan_no_phase_required():
    """Phase is no longer required — the LLM plan is just steps."""
    plan = RoutePlan(
        steps=[
            RouteStep(agent_name="detector_agent", reason="detect"),
            RouteStep(agent_name="risk_agent", reason="score", iterate_over="List[DetectionFinding]"),
        ],
        notes="test plan",
    )
    assert len(plan.steps) == 2
    assert plan.steps[1].iterate_over == "List[DetectionFinding]"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_router_models.py -v`
Expected: FAIL — `RouteStep` doesn't have `iterate_over`, `RoutePlan` still requires `phase`.

**Step 3: Write minimal implementation**

Replace `src/okta_soc/core/router_models.py` with:

```python
from typing import List, Optional
from pydantic import BaseModel


class RouteStep(BaseModel):
    agent_name: str
    reason: str
    iterate_over: Optional[str] = None  # e.g. "List[SecurityIncident]"


class RoutePlan(BaseModel):
    steps: List[RouteStep]
    notes: Optional[str] = None
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_router_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/core/router_models.py tests/test_router_models.py
git commit -m "feat: update RoutePlan — add iterate_over, remove required phase"
```

---

### Task 4: Agent Registry — Contract-Based Auto-Discovery

**Files:**
- Rewrite: `src/okta_soc/agents/registry.py`
- Test: `tests/test_agent_registry.py`

**Step 1: Write the failing test**

Create: `tests/test_agent_registry.py`

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_agent_registry.py -v`
Expected: FAIL — `AgentRegistry` does not exist.

**Step 3: Write minimal implementation**

Replace `src/okta_soc/agents/registry.py` with:

```python
from typing import Dict, Optional
from okta_soc.agents.base import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self.agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        name = agent.contract.name
        if name in self.agents:
            raise ValueError(f"Agent '{name}' already registered")
        self.agents[name] = agent

    def get(self, name: str) -> Optional[BaseAgent]:
        return self.agents.get(name)

    def catalog_for_llm(self) -> str:
        lines = []
        for agent in self.agents.values():
            c = agent.contract
            parts = [
                f"- {c.name}: {c.description}",
                f"  Consumes: {', '.join(c.consumes)}",
                f"  Produces: {', '.join(c.produces)}",
                f"  Phase hint: {c.phase_hint}",
            ]
            if c.side_effects:
                parts.append(f"  Side effects: {', '.join(c.side_effects)}")
            if c.requires_human_approval:
                parts.append("  Requires human approval: yes")
            lines.append("\n".join(parts))
        return "\n\n".join(lines)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_agent_registry.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/agents/registry.py tests/test_agent_registry.py
git commit -m "feat: add AgentRegistry with contract-based catalog for LLM"
```

---

### Task 5: Migrate Existing Agents to Contract Interface

**Files:**
- Modify: `src/okta_soc/agents/detector_agent.py`
- Modify: `src/okta_soc/agents/risk_agent.py`
- Modify: `src/okta_soc/agents/planner_agent.py`
- Modify: `src/okta_soc/agents/command_agent.py`
- Test: `tests/test_agent_migrations.py`

**Step 1: Write the failing test**

Create: `tests/test_agent_migrations.py`

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_agent_migrations.py -v`
Expected: FAIL — agents don't have `contract` attribute yet.

**Step 3: Migrate each agent**

Modify `src/okta_soc/agents/detector_agent.py`:

```python
from typing import Any, Dict, List
from .base import BaseAgent, AgentContract
from okta_soc.core.models import OktaEvent, DetectionFinding
from okta_soc.detectors.registry import get_all_detectors


class DetectorAgent(BaseAgent):
    contract = AgentContract(
        name="detector_agent",
        description="Analyzes Okta events to detect anomalies like impossible travel, "
        "failed-login bursts, and MFA fatigue. Produces DetectionFindings.",
        consumes=["List[OktaEvent]"],
        produces=["List[DetectionFinding]"],
        phase_hint="ingest",
    )

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        events = [OktaEvent.model_validate(e) if isinstance(e, dict) else e
                  for e in input_data["List[OktaEvent]"]]
        findings: List[DetectionFinding] = []
        for detector in get_all_detectors():
            findings.extend(detector.detect(events))
        return {"List[DetectionFinding]": findings}
```

Modify `src/okta_soc/agents/risk_agent.py`:

```python
from typing import Any, Dict
from .base import BaseAgent, AgentContract
from okta_soc.core.models import DetectionFinding, RiskScore, Severity, SecurityIncident
from okta_soc.core.llm import LLMClient
from datetime import datetime, timezone
import uuid


class LLMRiskAgent(BaseAgent):
    contract = AgentContract(
        name="risk_agent",
        description="Assigns severity and risk scores to DetectionFindings, "
        "deciding how serious each one is. Promotes high-risk findings to SecurityIncidents.",
        consumes=["DetectionFinding"],
        produces=["RiskScore", "SecurityIncident"],
        phase_hint="analysis",
    )

    def __init__(self, llm: LLMClient, promotion_threshold: float = 0.6):
        self.llm = llm
        self.promotion_threshold = promotion_threshold

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        finding = input_data["DetectionFinding"]
        if isinstance(finding, dict):
            finding = DetectionFinding.model_validate(finding)

        system_prompt = (
            "You are a security risk analyst for Okta authentication events. "
            "Given a detection finding, you assign severity, likelihood, impact, "
            "and a numeric risk score between 0 and 1."
        )

        user_prompt = f"""
DetectionFinding (JSON):
{finding.model_dump_json(indent=2)}

Your job:
1. Decide severity: low, medium, high, or critical.
2. Estimate likelihood and impact (0.0-1.0).
3. Compute an overall risk score (0.0-1.0).
4. Explain your reasoning briefly.

Return ONLY JSON:
{{
  "severity": "low|medium|high|critical",
  "likelihood": 0.0,
  "impact": 0.0,
  "score": 0.0,
  "rationale": "string"
}}
"""

        result = self.llm.chat_json(system_prompt, user_prompt)

        severity = Severity(result["severity"].lower())
        risk = RiskScore(
            finding_id=finding.id,
            severity=severity,
            likelihood=float(result["likelihood"]),
            impact=float(result["impact"]),
            score=float(result["score"]),
            rationale=result["rationale"],
        )

        promote = (
            risk.score >= self.promotion_threshold
            or severity in {Severity.HIGH, Severity.CRITICAL}
        )

        outputs: Dict[str, Any] = {"RiskScore": risk}

        if promote:
            incident = SecurityIncident(
                id=str(uuid.uuid4()),
                finding_id=finding.id,
                title=f"Incident from {finding.finding_type.value}",
                description=finding.description,
                severity=risk.severity,
                risk_score=risk.score,
                created_at=datetime.now(timezone.utc),
                status="open",
                metadata={
                    "finding_type": finding.finding_type.value,
                    **finding.metadata,
                },
            )
            outputs["SecurityIncident"] = incident

        return outputs
```

Modify `src/okta_soc/agents/planner_agent.py`:

```python
from typing import Any, Dict
from .base import BaseAgent, AgentContract
from okta_soc.core.models import SecurityIncident, ResponsePlan, ResponseStep
from okta_soc.core.llm import LLMClient


class PlannerAgent(BaseAgent):
    contract = AgentContract(
        name="planner_agent",
        description="Creates a ResponsePlan (steps, rationale) for a given SecurityIncident.",
        consumes=["SecurityIncident"],
        produces=["ResponsePlan"],
        phase_hint="response",
    )

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        incident = input_data["SecurityIncident"]
        if isinstance(incident, dict):
            incident = SecurityIncident.model_validate(incident)

        system_prompt = (
            "You are an incident response planner for Okta security incidents. "
            "You design step-by-step response plans that are safe and appropriate."
        )

        user_prompt = f"""
SecurityIncident (JSON):
{incident.model_dump_json(indent=2)}

Design a concise but clear response plan.

Rules:
- Focus on containment, eradication, recovery, and communication as appropriate.
- Assume actions will be reviewed by a human analyst before execution.
- All steps should be safe and non-destructive.
- Mark steps that MUST be human-approved before execution.
- When possible, use one of these canonical step_id values:
  - "collect_auth_logs"
  - "analyze_geo_and_devices"
  - "lock_account"
  - "notify_user"
  - "enable_mfa"
  - "revoke_sessions"
  - "forensic_review"
  - "update_incident_status"
- You may still add other step_ids if needed, but prefer the canonical ones above.

Return ONLY JSON:
{{
  "overall_goal": "string",
  "steps": [
    {{
      "step_id": "string",
      "description": "string",
      "rationale": "string",
      "requires_human_approval": true,
      "dependencies": ["optional_step_id"]
    }}
  ],
  "notes": "string or null"
}}
"""

        raw = self.llm.chat_json(system_prompt, user_prompt)

        steps = [
            ResponseStep(
                step_id=s["step_id"],
                description=s["description"],
                rationale=s["rationale"],
                requires_human_approval=bool(s.get("requires_human_approval", True)),
                dependencies=s.get("dependencies", []),
            )
            for s in raw.get("steps", [])
        ]

        plan = ResponsePlan(
            incident_id=incident.id,
            overall_goal=raw.get("overall_goal", "Respond to Okta security incident."),
            steps=steps,
            notes=raw.get("notes"),
        )
        return {"ResponsePlan": plan}
```

Modify `src/okta_soc/agents/command_agent.py`:

```python
from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentContract
from okta_soc.core.models import ResponsePlan, CommandSuggestion
from okta_soc.core.config import load_settings


class CommandAgent(BaseAgent):
    contract = AgentContract(
        name="command_agent",
        description="Generates read-only curl commands from a ResponsePlan "
        "for a human analyst to review and execute.",
        consumes=["ResponsePlan"],
        produces=["List[CommandSuggestion]"],
        phase_hint="response",
    )

    def __init__(self, okta_org_url: Optional[str] = None):
        settings = load_settings()
        self.okta_org_url = (okta_org_url or settings.okta_org_url).rstrip("/")

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        plan = input_data["ResponsePlan"]
        if isinstance(plan, dict):
            plan = ResponsePlan.model_validate(plan)

        suggestions: List[CommandSuggestion] = []

        for step in plan.steps:
            sid = step.step_id

            if sid == "lock_account":
                cmd = (
                    "curl -X POST "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/lifecycle/suspend "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json' "
                    "-H 'Content-Type: application/json'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Suspend the Okta user account.",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Replace {userId} and token before running.",
                    )
                )

            elif sid == "force_password_reset":
                cmd = (
                    "curl -X POST "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/lifecycle/reset_password?sendEmail=true "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json' "
                    "-H 'Content-Type: application/json'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Force user password reset and send email.",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Replace {userId} and token before running.",
                    )
                )

            elif sid == "revoke_sessions":
                cmd = (
                    "curl -X DELETE "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/sessions "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Revoke all active sessions for the user.",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Replace {userId} and token before running.",
                    )
                )

            elif sid == "enable_mfa":
                cmd = (
                    "# Example: enroll an MFA factor for the user via Okta API\n"
                    "curl -X POST "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/factors "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json' "
                    "-H 'Content-Type: application/json' "
                    "-d '{\"factorType\": \"token:software:totp\", \"provider\": \"OKTA\"}'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Enable MFA for the user (template, adjust factorType/provider).",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Adjust factorType/provider and {userId} before running.",
                    )
                )

        return {"List[CommandSuggestion]": suggestions}
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_agent_migrations.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/agents/detector_agent.py src/okta_soc/agents/risk_agent.py \
  src/okta_soc/agents/planner_agent.py src/okta_soc/agents/command_agent.py \
  tests/test_agent_migrations.py
git commit -m "feat: migrate all agents to contract-based interface"
```

---

### Task 6: New RouterAgent — LLM Composes, Types Validate

**Files:**
- Rewrite: `src/okta_soc/agents/router_agent.py`
- Test: `tests/test_router_agent.py`

**Step 1: Write the failing test**

Create: `tests/test_router_agent.py`

```python
import pytest
from unittest.mock import MagicMock, AsyncMock
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

    import asyncio
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

    import asyncio
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

    import asyncio
    plan = asyncio.run(router.run(ctx))
    assert len(plan.steps) == 1
    assert plan.steps[0].agent_name == "detector_agent"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_router_agent.py -v`
Expected: FAIL — `RouterAgent` still has old signature.

**Step 3: Write minimal implementation**

Replace `src/okta_soc/agents/router_agent.py` with:

```python
from typing import Any, Dict, List, Set

from okta_soc.core.llm import LLMClient
from okta_soc.core.router_models import RoutePlan, RouteStep
from okta_soc.core.pipeline_context import PipelineContext
from okta_soc.agents.registry import AgentRegistry


ROUTER_SYSTEM_PROMPT = """\
You are an orchestration router for a security automation platform that analyzes Okta security events.
You NEVER execute actions yourself. You only decide which agents should be called and in what order.

Your job:
1. Look at the available agents and their type contracts (what they consume and produce).
2. Look at what data is currently available in the pipeline context.
3. Compose an ordered pipeline of agents that processes the available data.

Rules:
- Each agent's "consumes" types must be satisfied by either the initial available data or a prior agent's "produces" types.
- Use "iterate_over" when an agent consumes a single item but the pipeline has a list of that type.
  For example, if risk_agent consumes "DetectionFinding" but the pipeline has "List[DetectionFinding]",
  set iterate_over to "List[DetectionFinding]" so the orchestrator runs it once per item.
- Only include agents that are relevant to the current data and context.
- Prefer agents with side_effects only when the situation warrants it (e.g., high severity incidents).
- Be concise and deterministic.
"""


class RouterAgent:
    def __init__(self, llm: LLMClient, registry: AgentRegistry):
        self.llm = llm
        self.registry = registry

    async def run(self, context: PipelineContext) -> RoutePlan:
        catalog = self.registry.catalog_for_llm()
        available_types = context.available_types()

        user_prompt = f"""
Available agents:
{catalog}

Data currently available in pipeline: {available_types}

Pipeline metadata/context: {context.metadata}

Compose a pipeline of agents to process this data.

Return ONLY JSON:
{{
  "steps": [
    {{
      "agent_name": "string",
      "reason": "string",
      "iterate_over": "string or null"
    }}
  ],
  "notes": "string or null"
}}
"""

        raw = self.llm.chat_json(ROUTER_SYSTEM_PROMPT, user_prompt, temperature=0.1)
        raw_steps = raw.get("steps", [])
        steps = [
            RouteStep(
                agent_name=s["agent_name"],
                reason=s.get("reason", ""),
                iterate_over=s.get("iterate_over"),
            )
            for s in raw_steps
        ]
        plan = RoutePlan(steps=steps, notes=raw.get("notes"))

        # Validate type compatibility
        plan = self._validate_type_compatibility(plan, context)
        return plan

    def _validate_type_compatibility(
        self, plan: RoutePlan, context: PipelineContext
    ) -> RoutePlan:
        available: Set[str] = set(context.available_types())
        valid_steps: List[RouteStep] = []

        for step in plan.steps:
            agent = self.registry.get(step.agent_name)
            if agent is None:
                continue  # Unknown agent, skip

            contract = agent.contract

            # Check if all consumed types are available
            # Account for iterate_over: if iterating, the list type must be available
            # and the singular consumed type is provided per-item by the orchestrator
            if step.iterate_over and step.iterate_over in available:
                # The agent consumes individual items; the list is available
                satisfied = True
            else:
                satisfied = all(t in available for t in contract.consumes)

            if not satisfied:
                continue  # Inputs not available, skip this agent

            valid_steps.append(step)

            # Add this agent's produces to available types for downstream agents
            for t in contract.produces:
                available.add(t)
                available.add(f"List[{t}]")  # iteration collects into lists

        plan.steps = valid_steps
        return plan
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_router_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/agents/router_agent.py tests/test_router_agent.py
git commit -m "feat: rewrite RouterAgent — LLM composes pipeline, types validate"
```

---

### Task 7: Generic Orchestrator

**Files:**
- Rewrite: `src/okta_soc/agents/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing test**

Create: `tests/test_orchestrator.py`

```python
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

    mock_router = MagicMock()
    mock_router.run = lambda ctx: asyncio.coroutine(lambda: RoutePlan(
        steps=[RouteStep(agent_name="detector_agent", reason="detect")],
    ))()

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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL — `Orchestrator` still has old constructor.

**Step 3: Write minimal implementation**

Replace `src/okta_soc/agents/orchestrator.py` with:

```python
from typing import Any, Dict, List

from okta_soc.core.pipeline_context import PipelineContext, StepResult
from okta_soc.agents.registry import AgentRegistry


class Orchestrator:
    """
    Generic pipeline orchestrator.

    Asks the router to compose a pipeline of agents, then executes each step.
    Agents read from and write to a shared PipelineContext.
    Supports iterate_over for agents that process individual items from a list.
    """

    def __init__(self, router: Any, registry: AgentRegistry):
        self.router = router
        self.registry = registry

    async def run(
        self, initial_data: Dict[str, Any], metadata: Dict[str, Any]
    ) -> PipelineContext:
        context = PipelineContext(data=initial_data, metadata=metadata)

        plan = await self.router.run(context)

        for step in plan.steps:
            agent = self.registry.get(step.agent_name)
            if agent is None:
                continue

            if step.iterate_over and step.iterate_over in context.data:
                # Run agent once per item in the list
                items = context.data[step.iterate_over]
                collected: Dict[str, List[Any]] = {}

                for item in items:
                    inputs = {t: item for t in agent.contract.consumes}
                    outputs = await agent.run(inputs)

                    for key, value in outputs.items():
                        list_key = f"List[{key}]"
                        if list_key not in collected:
                            collected[list_key] = []
                        collected[list_key].append(value)

                context.data.update(collected)
            else:
                # Run agent once with full context data
                inputs = {t: context.data[t] for t in agent.contract.consumes if t in context.data}
                outputs = await agent.run(inputs)
                context.data.update(outputs)

            context.history.append(
                StepResult(
                    agent=step.agent_name,
                    outputs=list(agent.contract.produces),
                )
            )

        return context
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/agents/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: rewrite Orchestrator — generic, contract-driven pipeline execution"
```

---

### Task 8: Update Pipeline Wiring and CLI

**Files:**
- Modify: `src/okta_soc/ingest/pipeline.py`
- Modify: `src/okta_soc/core/config.py` (update default LLM URL)
- Test: run full pipeline end-to-end

**Step 1: Write the failing test**

Create: `tests/test_pipeline_wiring.py`

```python
"""Verify the pipeline wires up correctly and the registry has all agents."""
from okta_soc.agents.base import AgentContract
from okta_soc.agents.registry import AgentRegistry
from okta_soc.agents.detector_agent import DetectorAgent
from okta_soc.agents.risk_agent import LLMRiskAgent
from okta_soc.agents.planner_agent import PlannerAgent
from okta_soc.agents.command_agent import CommandAgent


def test_all_agents_register_without_error():
    """All four agents can be registered in a single registry."""
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

    assert len(registry.agents) == 4
    catalog = registry.catalog_for_llm()
    assert "detector_agent" in catalog
    assert "risk_agent" in catalog
    assert "planner_agent" in catalog
    assert "command_agent" in catalog
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/test_pipeline_wiring.py -v`
Expected: May pass or fail depending on task 5 state. Either way, proceed.

**Step 3: Update pipeline.py and config.py**

Replace `src/okta_soc/ingest/pipeline.py` with:

```python
from datetime import datetime
from typing import List

from okta_soc.core.models import OktaEvent
from okta_soc.core.config import load_settings
from okta_soc.core.llm import LLMClient
from okta_soc.agents.router_agent import RouterAgent
from okta_soc.agents.detector_agent import DetectorAgent
from okta_soc.agents.risk_agent import LLMRiskAgent
from okta_soc.agents.planner_agent import PlannerAgent
from okta_soc.agents.command_agent import CommandAgent
from okta_soc.agents.registry import AgentRegistry
from okta_soc.agents.orchestrator import Orchestrator
from okta_soc.ingest.okta_client import OktaClient


async def fetch_and_process(since: datetime) -> None:
    settings = load_settings()
    okta = OktaClient(settings.okta_org_url, settings.okta_api_token)

    llm = LLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )

    # Build agent registry
    registry = AgentRegistry()
    registry.register(DetectorAgent())
    registry.register(LLMRiskAgent(llm))
    registry.register(PlannerAgent(llm))
    registry.register(CommandAgent(settings.okta_org_url))

    # Build router and orchestrator
    router = RouterAgent(llm=llm, registry=registry)
    orchestrator = Orchestrator(router=router, registry=registry)

    # Fetch events
    events: List[OktaEvent] = await okta.fetch_events_since(since)

    # Run pipeline — the LLM decides what agents to use
    context = await orchestrator.run(
        initial_data={"List[OktaEvent]": events},
        metadata={"source": "okta", "since": since.isoformat()},
    )

    # Persist results
    _persist_results(context)


def _persist_results(context) -> None:
    """Save pipeline outputs to JSONL files."""
    from okta_soc.storage.repositories import (
        FindingsRepo, IncidentsRepo, PlansRepo, CommandsRepo,
    )

    findings_repo = FindingsRepo()
    incidents_repo = IncidentsRepo()
    plans_repo = PlansRepo()
    commands_repo = CommandsRepo()

    for finding in context.data.get("List[DetectionFinding]", []):
        findings_repo.save(finding)

    for incident in context.data.get("List[SecurityIncident]", []):
        incidents_repo.save(incident)

    for plan in context.data.get("List[ResponsePlan]", []):
        plans_repo.save(plan)

    for cmd in context.data.get("List[List[CommandSuggestion]]", []):
        if isinstance(cmd, list):
            for c in cmd:
                commands_repo.save("", c)
        else:
            commands_repo.save("", cmd)
```

Update `src/okta_soc/core/config.py` — change default LLM URL:

```python
import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    okta_org_url: str = os.getenv("OKTA_ORG_URL", "https://example.okta.com")
    okta_api_token: str = os.getenv("OKTA_API_TOKEN", "REPLACE_ME")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://100.113.108.1:1234/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-oss-20b")


def load_settings() -> Settings:
    return Settings()
```

**Step 4: Run all tests**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/okta_soc/ingest/pipeline.py src/okta_soc/core/config.py tests/test_pipeline_wiring.py
git commit -m "feat: rewire pipeline to use registry + generic orchestrator, update LLM URL"
```

---

### Task 9: End-to-End Smoke Test with Real LLM

**Files:**
- No new files — manual verification

**Step 1: Clear old artifacts**

Run: `rm -f data/*.jsonl`

**Step 2: Run the full pipeline**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m okta_soc.interface.cli --hours 24`

Observe:
- The LLM is called to compose the pipeline (check console output)
- Detections run, findings are created
- Risk scoring runs per finding
- Incidents are promoted
- Planner and command agents run for incidents

**Step 3: Verify artifacts**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m okta_soc.interface.cli show-all`

Expected: Findings, incidents, plans, and commands are displayed — same functional behavior as before, but now driven by LLM routing decisions.

**Step 4: Run all tests one final time**

Run: `cd /Users/jared/github_projects/okta-agentic-soc && python -m pytest tests/ -v`
Expected: ALL PASS

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: end-to-end verification of dynamic agent routing"
```

---

### Task Summary

| Task | What | Files Changed |
|------|------|---------------|
| 1 | AgentContract + BaseAgent | `agents/base.py` |
| 2 | PipelineContext + StepResult | `core/pipeline_context.py` |
| 3 | RoutePlan with iterate_over | `core/router_models.py` |
| 4 | AgentRegistry with catalog | `agents/registry.py` |
| 5 | Migrate 4 agents to contracts | `agents/{detector,risk,planner,command}_agent.py` |
| 6 | New RouterAgent | `agents/router_agent.py` |
| 7 | Generic Orchestrator | `agents/orchestrator.py` |
| 8 | Pipeline wiring + config | `ingest/pipeline.py`, `core/config.py` |
| 9 | E2E smoke test | (verification only) |
