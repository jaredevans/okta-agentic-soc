# Okta Agentic SOC

An AI-assisted, agent-based pipeline that mimics a mini Security Operations Center (SOC) for Okta.

It ingests Okta System Log events, runs detectors, asks an LLM to score risk and create response plans, and generates **read-only** remediation commands — all wired together by an LLM-driven router that **genuinely decides** which agents to run, constrained only by typed contracts.

---

## Table of Contents

- [Goals & Use Cases](#goals--use-cases)
- [High-Level Architecture](#high-level-architecture)
- [How the LLM Router Works](#how-the-llm-router-works)
- [Core Data Models](#core-data-models)
- [Agent Contracts](#agent-contracts)
- [Agents](#agents)
  - [RouterAgent](#routeragent)
  - [DetectorAgent](#detectoragent)
  - [LLMRiskAgent](#llmriskagent)
  - [PlannerAgent](#planneragent)
  - [CommandAgent](#commandagent)
  - [EscalationAgent](#escalationagent)
  - [Orchestrator](#orchestrator)
- [Pipeline Context](#pipeline-context)
- [Detectors](#detectors)
- [Storage & Artifacts](#storage--artifacts)
- [CLI Usage](#cli-usage)
- [Configuration](#configuration)
- [Demo Mode vs Real Okta](#demo-mode-vs-real-okta)
- [Extending the System](#extending-the-system)
  - [Adding a New Detector](#adding-a-new-detector)
  - [Adding a New Agent](#adding-a-new-agent)
- [LLM Details & Expectations](#llm-details--expectations)
- [Limitations & Safety Notes](#limitations--safety-notes)
- [Getting Started (Install & Run)](#getting-started-install--run)

---

## Goals & Use Cases

This project is designed as:

- A **reference implementation** for an *agentic security pipeline* focused on Okta events.
- A demo tool for:
  - How to use LLMs as **genuine orchestration routers** that decide which agents to run based on typed contracts.
  - How to combine **deterministic detectors** with **probabilistic LLM analysis**.
  - How **type-safe constraints** can replace hardcoded guardrails while keeping the system safe.
- A starting point that can be extended toward a real SOC integration.

Typical demo scenario:

1. Feed in a small set of Okta System Log events.
2. Run the pipeline.
3. Walk through:
   - What detections were raised.
   - How the LLM scored risk and promoted incidents.
   - How the router decided which agents to run (and why).
   - The final response plan and suggested commands.

---

## High-Level Architecture

The pipeline is driven by a single LLM routing decision. The router sees all available agents and their type contracts, then composes a pipeline. The orchestrator validates and executes it.

```text
         Okta System Logs (demo JSON file)
                          │
                          ▼
                   [ OktaClient ]
                          │
                  List[OktaEvent]
                          │
                          ▼
              ┌───────────────────────┐
              │   RouterAgent (LLM)   │  ← Sees agent catalog + available types
              │                       │     Composes a pipeline of agents
              └───────────────────────┘
                          │
                   RoutePlan (validated by type compatibility)
                          │
                          ▼
              ┌───────────────────────┐
              │     Orchestrator      │  ← Executes plan step-by-step
              │  (generic, no agent-  │     Handles iterate_over for
              │   specific logic)     │     per-item processing
              └───────────────────────┘
                          │
          Typical pipeline composed by LLM:
                          │
          ┌───────────────┼────────────────────────┐
          ▼               ▼                        ▼
  [ DetectorAgent ]  [ RiskAgent ]          [ PlannerAgent ]
   List[OktaEvent]   DetectionFinding ×N    SecurityIncident ×N
        → List[       → RiskScore            → ResponsePlan
     DetectionFinding]  + SecurityIncident       │
                        (if promoted)            ▼
                              │           [ CommandAgent ]
                              │            ResponsePlan ×N
                              │             → List[CommandSuggestion]
                              │
                              ▼
                     [ EscalationAgent ]   ← only if LLM decides
                      SecurityIncident ×N     severity warrants it
                       → EscalationResult
                         (simulated Slack)
                              │
                              ▼
                        data/*.jsonl
```

All intermediate and final artifacts are written as `.jsonl` files in the `data/` directory so you can inspect what happened at each step.

# Screenshots

## Findings

<img src="https://i.imgur.com/mEeVmAB.png" width=700>

## Incidents

<img src="https://i.imgur.com/UpS9r3z.png" width=700>

## Plans

<img src="https://i.imgur.com/4SWQlTo.png" width=700>

## Commands

<img src="https://i.imgur.com/F5dBFlo.png" width=700>

---

## How the LLM Router Works

The key design decision: **the LLM genuinely decides which agents to run**. There are no hardcoded `if kind == "raw_events"` branches or force-inserted agents. Instead, the system uses **typed contracts** as the only constraint.

### What the LLM Sees

The router shows the LLM:

1. **A catalog of all registered agents** with their contracts:
   ```
   - detector_agent: Analyzes Okta events to detect anomalies...
     Consumes: List[OktaEvent]
     Produces: List[DetectionFinding]

   - risk_agent: Assigns severity and risk scores...
     Consumes: DetectionFinding
     Produces: RiskScore, SecurityIncident

   - planner_agent: Creates a ResponsePlan...
     Consumes: SecurityIncident
     Produces: ResponsePlan

   - command_agent: Generates read-only curl commands...
     Consumes: ResponsePlan
     Produces: List[CommandSuggestion]

   - escalation_agent: Sends Slack notification for high-severity incidents.
     Consumes: SecurityIncident
     Produces: EscalationResult
     Actions: slack_notification
   ```

2. **What data types are currently available** in the pipeline (e.g., `["List[OktaEvent]"]`).

3. **Pipeline metadata** (source, time window, etc.).

### What the LLM Returns

The LLM composes an ordered pipeline:

```json
{
  "steps": [
    {"agent_name": "detector_agent", "reason": "Detect anomalies in raw events"},
    {"agent_name": "risk_agent", "reason": "Score each finding", "iterate_over": "List[DetectionFinding]"},
    {"agent_name": "planner_agent", "reason": "Plan response per incident", "iterate_over": "List[SecurityIncident]"},
    {"agent_name": "command_agent", "reason": "Generate commands", "iterate_over": "List[ResponsePlan]"},
    {"agent_name": "escalation_agent", "reason": "Notify SOC team of critical incidents", "iterate_over": "List[SecurityIncident]"}
  ]
}
```

The `iterate_over` field tells the orchestrator to run that agent once per item in a list (e.g., run `risk_agent` once per `DetectionFinding`).

### Type Validation (Not Hardcoded Rules)

After the LLM responds, `_validate_type_compatibility` walks the plan step-by-step:

1. Tracks which data types are available (starting from initial context).
2. For each step, checks: are this agent's `consumes` types available?
3. If not, the step is removed (not force-inserted).
4. After each valid step, adds that agent's `produces` types to the available set.
5. **Auto-detects iteration**: if an agent consumes `T` but only `List[T]` is available, automatically sets `iterate_over`.

This means the **types are the guardrails**. The LLM can't compose a nonsensical pipeline because the type checker won't validate it. But within the space of type-valid pipelines, the LLM has full freedom.

---

## Core Data Models

Key Pydantic models (see `okta_soc/core/models.py`) include:

- **`OktaEvent`** — A normalized view of an Okta System Log event, including:
  - `id`, `event_type`, `actor_id`, `target_id`, `ip_address`, `user_agent`
  - Geo fields (`city`, `country`, `latitude`, `longitude`)
  - `outcome` (`SUCCESS` or `FAILURE`)
  - `timestamp` (timezone-aware `datetime`, normalized to UTC)
  - `raw` (the original event JSON)

- **`DetectionFinding`** — Output of detectors:
  - `id` (UUID), `finding_type`, `description`
  - `okta_event_ids`, `user_id`, `created_at`, `metadata`

- **`RiskScore`** — Risk analysis from the LLM:
  - `severity`: `low | medium | high | critical`
  - `likelihood`, `impact`, `score` (0.0–1.0)
  - `rationale`

- **`SecurityIncident`** — A promoted, trackable incident:
  - `id`, `finding_id`, `title`, `description`
  - `severity`, `risk_score`, `created_at`, `status`

- **`ResponsePlan`** and **`ResponseStep`** — Structured response steps from the LLM:
  - `overall_goal`, `steps` (each with `step_id`, `description`, `rationale`, `requires_human_approval`, `dependencies`)

- **`CommandSuggestion`** — Safe, **read-only** command templates:
  - `step_id`, `description`, `command`, `system`, `read_only`, `notes`

- **`EscalationResult`** — Record of a (simulated) Slack notification:
  - `incident_id`, `channel`, `message`, `sent`

---

## Agent Contracts

Every agent declares a typed contract that describes what data it consumes and produces. This is the foundation of the dynamic routing system.

**File:** `okta_soc/agents/base.py`

```python
@dataclass
class AgentContract:
    name: str               # Unique agent identifier
    description: str        # Rich description for the LLM to reason about
    consumes: List[str]     # Data type keys this agent reads (e.g., ["List[OktaEvent]"])
    produces: List[str]     # Data type keys this agent writes (e.g., ["List[DetectionFinding]"])
    phase_hint: str         # Advisory: "ingest", "analysis", "response"
    actions: List[str]      # e.g., ["slack_notification"] — helps LLM decide when to use
    requires_human_approval: bool  # Whether output needs sign-off
```

The `consumes` and `produces` fields are the wiring rules. An agent can only appear in the pipeline if its inputs are available from a prior step or from the initial context.

**Current agent contracts:**

| Agent | Consumes | Produces | Phase |
|-------|----------|----------|-------|
| `detector_agent` | `List[OktaEvent]` | `List[DetectionFinding]` | ingest |
| `risk_agent` | `DetectionFinding` | `RiskScore`, `SecurityIncident` | analysis |
| `planner_agent` | `SecurityIncident` | `ResponsePlan` | response |
| `command_agent` | `ResponsePlan` | `List[CommandSuggestion]` | response |
| `escalation_agent` | `SecurityIncident` | `EscalationResult` | response |

---

## Agents

All agents implement `BaseAgent` with an `async run(input_data: Dict[str, Any]) -> Dict[str, Any]` method. Input and output are keyed by type name (matching the contract).

### Orchestrator

**File:** `okta_soc/agents/orchestrator.py`

The Orchestrator is fully generic — it has **zero knowledge of specific agents**. It:

1. Creates a `PipelineContext` from initial data and metadata.
2. Asks the `RouterAgent` to compose a pipeline.
3. For each step in the plan:
   - Looks up the agent by name from the `AgentRegistry`.
   - If `iterate_over` is set, runs the agent once per item in the specified list, collecting outputs into `List[T]` keys.
   - Otherwise, runs the agent once with the full context.
   - Records a `StepResult` in the context history for auditability.
4. Returns the final `PipelineContext` with all accumulated data.

Adding a new agent requires **no changes** to the Orchestrator.

---

### RouterAgent

**File:** `okta_soc/agents/router_agent.py`

The RouterAgent is the LLM-driven orchestration controller. It is **not** a `BaseAgent` subclass — it's special infrastructure.

Given a `PipelineContext`, the RouterAgent:

1. Builds a catalog description from all registered agents (via `AgentRegistry.catalog_for_llm()`).
2. Lists what data types are currently available.
3. Asks the LLM to compose an ordered pipeline as JSON.
4. Validates the plan via `_validate_type_compatibility`:
   - Removes unknown agents.
   - Removes agents whose inputs aren't available.
   - Auto-detects when `iterate_over` should be set.
   - Tracks produced types step-by-step.

The LLM has full freedom to include, exclude, or reorder agents — as long as the types line up.

---

### DetectorAgent

**File:** `okta_soc/agents/detector_agent.py`

- **Consumes:** `List[OktaEvent]`
- **Produces:** `List[DetectionFinding]`
- **LLM:** No — purely deterministic.

Calls all registered detectors from `okta_soc/detectors/registry.py` and returns their combined findings.

---

### LLMRiskAgent

**File:** `okta_soc/agents/risk_agent.py`

- **Consumes:** `DetectionFinding` (called per-finding via `iterate_over`)
- **Produces:** `RiskScore`, and conditionally `SecurityIncident`
- **LLM:** Yes — scores risk.

The LLM assigns severity, likelihood, impact, and an overall score. Promotion logic is deterministic:

```python
promote = (
    risk.score >= self.promotion_threshold  # default 0.6
    or severity in {Severity.HIGH, Severity.CRITICAL}
)
```

When promoted, the agent creates a `SecurityIncident` directly in its output. When not promoted, only `RiskScore` is returned.

---

### PlannerAgent

**File:** `okta_soc/agents/planner_agent.py`

- **Consumes:** `SecurityIncident` (called per-incident via `iterate_over`)
- **Produces:** `ResponsePlan`
- **LLM:** Yes — designs response steps.

Uses canonical `step_id` values where possible: `collect_auth_logs`, `analyze_geo_and_devices`, `lock_account`, `notify_user`, `enable_mfa`, `revoke_sessions`, `forensic_review`, `update_incident_status`.

---

### CommandAgent

**File:** `okta_soc/agents/command_agent.py`

- **Consumes:** `ResponsePlan` (called per-plan via `iterate_over`)
- **Produces:** `List[CommandSuggestion]`
- **LLM:** No — deterministic template mapping.

Generates `curl` command templates for known `step_id` values (`lock_account`, `force_password_reset`, `revoke_sessions`, `enable_mfa`). Commands use `{userId}` and `<REDACTED_TOKEN>` placeholders. All marked `read_only=True`.

---

### EscalationAgent

**File:** `okta_soc/agents/escalation_agent.py`

- **Consumes:** `SecurityIncident` (called per-incident via `iterate_over`)
- **Produces:** `EscalationResult`
- **LLM:** No — deterministic.
- **Actions:** `slack_notification`

This is the first agent to use `actions` in its contract. The router includes it whenever `SecurityIncident` will be produced — severity filtering happens inside the agent, not at routing time (since the router runs before risk scoring, it can't know severity yet).

**Internal severity guard:** The agent only sends notifications (`sent=True`) for HIGH or CRITICAL severity. For LOW or MEDIUM, it returns `sent=False` and skips the notification. This means the router can always include it safely.

During a pipeline run, sent notifications are printed to the terminal:

```
📢 [SIMULATED SLACK] #soc-critical-alerts
[CRITICAL] Incident from impossible_travel
Risk score: 0.95
User logged in from two countries within 5 minutes.
```

Currently simulates Slack via `print()`. Ready to wire to a real Slack webhook when needed.

---

## Pipeline Context

**File:** `okta_soc/core/pipeline_context.py`

The `PipelineContext` is the shared state that flows through the pipeline:

```python
@dataclass
class PipelineContext:
    data: Dict[str, Any]         # Keyed by type name: {"List[OktaEvent]": [...], ...}
    metadata: Dict[str, Any]     # Pipeline-level info (source, since, run_id)
    history: List[StepResult]    # Audit trail of what ran and what it produced
```

Agents read their inputs from `context.data` (keyed by their `consumes` types) and write their outputs back (keyed by their `produces` types). The orchestrator manages this flow automatically.

---

## Detectors

Detectors are small, deterministic analyzers for specific patterns in Okta events.

### `ImpossibleTravelDetector`

**File:** `okta_soc/detectors/impossible_travel.py`

- Groups events by `actor_id`.
- For consecutive events with different countries and time delta < 1 hour, emits a `IMPOSSIBLE_TRAVEL` finding.

### `FailedLoginBurstDetector`

**File:** `okta_soc/detectors/failed_login_burst.py`

- Groups events by `actor_id`, filters `outcome == "FAILURE"`.
- Slides a window (default: 10 minutes). If >= 5 failures in that window, emits a `FAILED_LOGIN_BURST` finding.

---

## Storage & Artifacts

**File:** `okta_soc/storage/repositories.py`

All artifacts live in `data/` as JSON Lines (`.jsonl`):

- `data/findings.jsonl` — one `DetectionFinding` per line
- `data/incidents.jsonl` — one `SecurityIncident` per line
- `data/plans.jsonl` — one `ResponsePlan` per line
- `data/commands.jsonl` — one `CommandSuggestion` record per line
- `data/escalations.jsonl` — one `EscalationResult` per line

The `show-all` command pretty-prints all of these with Rich panels.

---

## CLI Usage

```toml
[project.scripts]
okta-soc = "okta_soc.interface.cli:main"
```

### Run the Full Pipeline

```bash
okta-soc --hours 100000   # use a large value for demo data (events are from Nov 2025)
```

This will:

1. Load events from the demo JSON file.
2. Ask the LLM router to compose a pipeline.
3. Execute the pipeline (detection → risk scoring → planning → commands).
4. Write all artifacts into `data/`.

### View All Artifacts

```bash
okta-soc show-all
```

### Convenience Script

```bash
./run.sh
```

Clears previous artifacts, runs the pipeline, and prints results.

---

## Configuration

**File:** `okta_soc/core/config.py`

Settings are loaded from environment variables (via `.env` and `python-dotenv`):

```env
OKTA_ORG_URL="https://example.okta.com"
OKTA_API_TOKEN="REPLACE_ME"
LLM_BASE_URL="http://100.113.108.1:1234/v1"
LLM_MODEL="gpt-oss-20b"
LLM_API_KEY="lm-studio"
```

The `LLMClient` in `okta_soc/core/llm.py` uses the OpenAI-compatible `chat.completions.create` API, so it works with LM Studio, Ollama, vLLM, or any OpenAI-compatible endpoint.

---

## Demo Mode vs Real Okta

**File:** `okta_soc/ingest/okta_client.py`

Currently in **demo mode**:

- Reads from `tests/demo_okta_system_logs.json` (9 events from Nov 2025).
- Filters by the `--hours` time window (use a large value like `100000` for demo data).
- Ignores the real Okta API.

To integrate with real Okta, replace `fetch_events_since()` with calls to the Okta System Log API and map responses into `OktaEvent`.

---

## Extending the System

### Adding a New Detector

1. Create a new file in `okta_soc/detectors/`, implement `BaseDetector`:

   ```python
   class MFAFatigueDetector(BaseDetector):
       name = "mfa_fatigue"

       def detect(self, events: List[OktaEvent]) -> List[DetectionFinding]:
           # your detection logic
           ...
   ```

2. Register it in `okta_soc/detectors/registry.py`:

   ```python
   def get_all_detectors() -> List[BaseDetector]:
       return [
           ImpossibleTravelDetector(),
           FailedLoginBurstDetector(),
           MFAFatigueDetector(),  # new
       ]
   ```

Done. The `DetectorAgent` automatically runs all registered detectors.

---

### Adding a New Agent

This is where the typed contract system shines. **Two steps only — no router or orchestrator changes needed.**

The `EscalationAgent` was added this way. Here's the pattern:

1. **Write the agent class with a contract:**

   ```python
   from okta_soc.agents.base import BaseAgent, AgentContract

   class EscalationAgent(BaseAgent):
       contract = AgentContract(
           name="escalation_agent",
           description="Sends Slack notification for high-severity or critical security incidents.",
           consumes=["SecurityIncident"],
           produces=["EscalationResult"],
           phase_hint="response",
           actions=["slack_notification"],  # tells router this agent takes action
       )

       async def run(self, input_data):
           incident = input_data["SecurityIncident"]
           # ... format message, simulate Slack send ...
           return {"EscalationResult": result}
   ```

2. **Register it in `pipeline.py`:**

   ```python
   registry.register(EscalationAgent())
   ```

That's it. The LLM router sees this agent in its catalog and decides whether to include it based on context. The `actions` field signals the router that this agent takes action beyond producing data. The type system ensures it can only be wired where `SecurityIncident` is available. No router or orchestrator edits required.

**Adding enrichment agents works the same way.** For example, an IP reputation agent that consumes `DetectionFinding` and produces `EnrichedFinding` would slot in between the detector and risk agents — the LLM figures out the ordering from the types.

---

## LLM Details & Expectations

The LLM is used in three roles:

1. **Router (RouterAgent)** — Composes the pipeline. Given the agent catalog and available types, decides which agents to run and in what order. Type validation ensures the plan is sound.

2. **Risk Analysis (LLMRiskAgent)** — Scores risk for each finding. Promotion logic is always enforced by Python, not the model.

3. **Response Planning (PlannerAgent)** — Designs structured response plans with canonical step IDs.

JSON parsing: `LLMClient.chat_json()` forces JSON-only output and does best-effort brace extraction before `json.loads()`.

---

## Limitations & Safety Notes

- **Demo Only**: Uses demo input via `tests/demo_okta_system_logs.json` and template `curl` commands with placeholders.
- **No Auto-Execution**: Commands are marked `read_only` with `{userId}` and `<REDACTED_TOKEN>` placeholders. Intended for human review only.
- **LLM Hallucinations**: While type validation prevents nonsensical pipelines, the LLM can still misjudge risk, over/under-estimate severity, or propose overly aggressive plans. Always treat outputs as recommendations.
- **No Error Recovery**: If the LLM returns malformed JSON or the endpoint is unreachable, the pipeline will crash. Production use would need retry logic and fallbacks.

---

## Getting Started (Install & Run)

```bash
# Install with uv
uv pip install .

# Or with plain pip
pip install .
```

Set up your `.env`:

```env
OKTA_ORG_URL="https://example.okta.com"
OKTA_API_TOKEN="REPLACE_ME"
LLM_BASE_URL="http://100.113.108.1:1234/v1"
LLM_MODEL="gpt-oss-20b"
LLM_API_KEY="lm-studio"
```

Run:

```bash
okta-soc --hours 100000
okta-soc show-all
```

Or use the convenience script:

```bash
./run.sh
```

### Running Tests

```bash
python -m pytest tests/ -v
```

33 tests covering agent contracts, registry, router validation, orchestrator execution, pipeline wiring, and escalation agent behavior.
