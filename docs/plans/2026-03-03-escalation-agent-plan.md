# Escalation Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an EscalationAgent that simulates Slack notifications for security incidents, demonstrating genuine LLM routing decisions via the `side_effects` contract field.

**Architecture:** The agent consumes `SecurityIncident`, formats a Slack-style message, logs it (simulated), and produces an `EscalationResult`. No LLM call needed — this is deterministic. The LLM router decides whether to include it based on incident severity context.

**Tech Stack:** Python 3.11+, Pydantic 2.x, dataclasses, pytest

---

### Task 1: EscalationResult Model

**Files:**
- Modify: `src/okta_soc/core/models.py:91` (append after CommandSuggestion)
- Test: `tests/test_escalation_agent.py` (create)

**Step 1: Write the failing test**

Create `tests/test_escalation_agent.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_escalation_agent.py::test_escalation_result_model -v`
Expected: FAIL with `ImportError: cannot import name 'EscalationResult'`

**Step 3: Write minimal implementation**

Add to end of `src/okta_soc/core/models.py` (after line 91):

```python


class EscalationResult(BaseModel):
    incident_id: str
    channel: str
    message: str
    sent: bool
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_escalation_agent.py::test_escalation_result_model -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/okta_soc/core/models.py tests/test_escalation_agent.py
git commit -m "feat: add EscalationResult model"
```

---

### Task 2: EscalationAgent Implementation

**Files:**
- Create: `src/okta_soc/agents/escalation_agent.py`
- Test: `tests/test_escalation_agent.py` (append)

**Step 1: Write the failing test**

Append to `tests/test_escalation_agent.py`:

```python
import pytest
from datetime import datetime, timezone
from okta_soc.agents.escalation_agent import EscalationAgent
from okta_soc.agents.base import AgentContract
from okta_soc.core.models import SecurityIncident, Severity


def test_escalation_agent_has_contract():
    agent = EscalationAgent()
    assert isinstance(agent.contract, AgentContract)
    assert agent.contract.name == "escalation_agent"
    assert "SecurityIncident" in agent.contract.consumes
    assert "EscalationResult" in agent.contract.produces
    assert "slack_notification" in agent.contract.side_effects


@pytest.mark.asyncio
async def test_escalation_agent_formats_message():
    agent = EscalationAgent()
    incident = SecurityIncident(
        id="inc-001",
        finding_id="f-001",
        title="Incident from impossible_travel",
        description="User logged in from two countries within 5 minutes.",
        severity=Severity.CRITICAL,
        risk_score=0.95,
        created_at=datetime.now(timezone.utc),
        status="open",
    )

    outputs = await agent.run({"SecurityIncident": incident})

    result = outputs["EscalationResult"]
    assert result.incident_id == "inc-001"
    assert result.channel == "#soc-critical-alerts"
    assert "CRITICAL" in result.message
    assert "impossible_travel" in result.message
    assert result.sent is True
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_escalation_agent.py::test_escalation_agent_has_contract -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'okta_soc.agents.escalation_agent'`

**Step 3: Write minimal implementation**

Create `src/okta_soc/agents/escalation_agent.py`:

```python
import logging
from typing import Any, Dict

from .base import BaseAgent, AgentContract
from okta_soc.core.models import SecurityIncident, EscalationResult

logger = logging.getLogger(__name__)


class EscalationAgent(BaseAgent):
    contract = AgentContract(
        name="escalation_agent",
        description=(
            "Sends Slack notification for high-severity or critical security incidents. "
            "Should only be included in the pipeline when incidents warrant escalation."
        ),
        consumes=["SecurityIncident"],
        produces=["EscalationResult"],
        phase_hint="response",
        side_effects=["slack_notification"],
    )

    CHANNEL = "#soc-critical-alerts"

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        incident = input_data["SecurityIncident"]
        if isinstance(incident, dict):
            incident = SecurityIncident.model_validate(incident)

        message = (
            f"[{incident.severity.value.upper()}] {incident.title}\n"
            f"Risk score: {incident.risk_score:.2f}\n"
            f"{incident.description}"
        )

        logger.info(
            "[SIMULATED SLACK] #%s → %s",
            self.CHANNEL,
            message,
        )

        result = EscalationResult(
            incident_id=incident.id,
            channel=self.CHANNEL,
            message=message,
            sent=True,
        )
        return {"EscalationResult": result}
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_escalation_agent.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/okta_soc/agents/escalation_agent.py tests/test_escalation_agent.py
git commit -m "feat: add EscalationAgent with simulated Slack notification"
```

---

### Task 3: Pipeline Wiring and Persistence

**Files:**
- Modify: `src/okta_soc/ingest/pipeline.py:12` (add import, register agent)
- Modify: `src/okta_soc/ingest/pipeline.py:50-75` (add persistence)
- Modify: `src/okta_soc/storage/repositories.py` (add EscalationsRepo)
- Test: `tests/test_pipeline_wiring.py` (update existing test)

**Step 1: Write the failing test**

Read the current `tests/test_pipeline_wiring.py` and update it. The existing test checks that 4 agents are registered. Update to expect 5:

Update assertion in `tests/test_pipeline_wiring.py` from:

```python
assert len(registry.agents) == 4
```

to:

```python
assert len(registry.agents) == 5
```

And add a new assertion:

```python
assert registry.get("escalation_agent") is not None
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline_wiring.py -v`
Expected: FAIL with `assert 4 == 5`

**Step 3: Implement the wiring**

In `src/okta_soc/ingest/pipeline.py`:

Add import (after line 11, the CommandAgent import):
```python
from okta_soc.agents.escalation_agent import EscalationAgent
```

Add registration (after line 31, the CommandAgent registration):
```python
    registry.register(EscalationAgent())
```

In `src/okta_soc/storage/repositories.py`:

Add `EscalationResult` to the import (line 8):
```python
from okta_soc.core.models import (
    DetectionFinding,
    SecurityIncident,
    ResponsePlan,
    CommandSuggestion,
    RiskScore,
    EscalationResult,
)
```

Add `EscalationsRepo` class (after `CommandsRepo`, after line 95):
```python


class EscalationsRepo:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "escalations.jsonl"

    def save(self, escalation: EscalationResult) -> None:
        with self.path.open("a") as f:
            f.write(escalation.model_dump_json() + "\n")
```

In `src/okta_soc/ingest/pipeline.py`, update `_persist_results`:

Add `EscalationsRepo` to the import block inside the function (line 53):
```python
    from okta_soc.storage.repositories import (
        FindingsRepo, IncidentsRepo, PlansRepo, CommandsRepo, EscalationsRepo,
    )
```

Add after the commands persistence (before the function ends):
```python
    escalations_repo = EscalationsRepo()
    for escalation in context.data.get("List[EscalationResult]", []):
        escalations_repo.save(escalation)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline_wiring.py tests/test_escalation_agent.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/okta_soc/ingest/pipeline.py src/okta_soc/storage/repositories.py tests/test_pipeline_wiring.py
git commit -m "feat: wire EscalationAgent into pipeline with persistence"
```

---

### Task 4: Contract Migration Test

**Files:**
- Modify: `tests/test_agent_migrations.py` (append test)

**Step 1: Write the test**

Append to `tests/test_agent_migrations.py`:

```python
from okta_soc.agents.escalation_agent import EscalationAgent


def test_escalation_agent_has_contract():
    agent = EscalationAgent()
    assert isinstance(agent.contract, AgentContract)
    assert agent.contract.name == "escalation_agent"
    assert "SecurityIncident" in agent.contract.consumes
    assert "EscalationResult" in agent.contract.produces
    assert "slack_notification" in agent.contract.side_effects
```

**Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_agent_migrations.py -v`
Expected: All 5 tests PASS (4 existing + 1 new)

**Step 3: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests PASS (25 existing + 4 new = 29)

**Step 4: Commit**

```bash
git add tests/test_agent_migrations.py
git commit -m "test: add escalation_agent contract migration test"
```

---

### Task 5: Router Test — Escalation Included for High Severity

**Files:**
- Modify: `tests/test_router_agent.py` (append test)

This test verifies the key behavior: the router can include escalation_agent in the pipeline alongside planner_agent, both consuming SecurityIncident.

**Step 1: Write the test**

Append to `tests/test_router_agent.py`:

```python
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
```

**Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_router_agent.py::test_escalation_included_when_incidents_available -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests PASS (30 total)

**Step 4: Commit**

```bash
git add tests/test_router_agent.py
git commit -m "test: verify router includes escalation_agent alongside planner"
```
