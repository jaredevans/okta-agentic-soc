# Okta Agentic SOC

An AI-assisted, agent-based pipeline that mimics a mini Security Operations Center (SOC) for Okta.

It ingests Okta System Log events, runs detectors, asks an LLM to score risk and create response plans, and then generates **read-only** remediation commands — all wired together by an LLM-driven router with hard guardrails.

---

## Table of Contents

- [Goals & Use Cases](#goals--use-cases)
- [High-Level Architecture](#high-level-architecture)
- [Core Data Models](#core-data-models)
- [Agents](#agents)
  - [RouterAgent](#routeragent)
  - [DetectorAgent](#detectoragent)
  - [LLMRiskAgent](#llmriskagent)
  - [PlannerAgent](#planneragent)
  - [CommandAgent](#commandagent)
  - [Orchestrator](#orchestrator)
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
- A teaching/demo tool for:
  - How to use LLMs as **orchestration routers** and **risk/response assistants**.
  - How to combine **deterministic detectors** with **probabilistic LLM analysis**.
- A starting point that can be extended toward a real SOC integration.

Typical demo scenario:

1. Feed in a small set of Okta System Log events.
2. Run the pipeline for a time window (e.g., last 24 hours).
3. Walk through:
   - What detections were raised.
   - How the LLM scored risk and promoted incidents.
   - How the router decided which agents to run.
   - The final response plan and suggested commands.

---

## High-Level Architecture

At a high level, the pipeline looks like this:

```text
          Okta System Logs (demo JSON file for now)
                           │
                           ▼
                    [ OktaClient ]
                           │
                           ▼
                  [ Orchestrator.stage1 ]
                           │
                 (kind = "raw_events")
                           │
                  ┌───────────────────┐
                  │   RouterAgent     │  ← LLM decides which analysis agents
                  └───────────────────┘     to run (with guardrails)
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
        [ DetectorAgent ]     [ LLMRiskAgent ]
              │                       │
        Findings (.jsonl)       Risk + Incidents
                                         │
                                         ▼
                  [ Orchestrator.stage2 per incident ]
                           │
                    (kind = "incident")
                           │
                  ┌───────────────────┐
                  │   RouterAgent     │  ← LLM chooses planner/command agents
                  └───────────────────┘
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
          [ PlannerAgent ]     [ CommandAgent ]
                 │                   │
         ResponsePlans (.jsonl)  CommandSuggestions (.jsonl)

```

All intermediate and final artifacts are written as `.jsonl` files in the `data/` directory so you can inspect what happened at each step.

---

## Core Data Models

Key Pydantic models (see `okta_soc/core/models.py`) include:

- **`OktaEvent`**  
  A normalized view of an Okta System Log event, including:
  - `id`, `event_type`, `actor_id`, `target_id`, `ip_address`, `user_agent`
  - Geo fields (`city`, `country`, `latitude`, `longitude`)
  - `outcome` (`SUCCESS` or `FAILURE`)
  - `timestamp` (timezone-aware `datetime`, normalized to UTC)
  - `raw` (the original event JSON)

- **`DetectionFinding`**  
  Output of detectors — a single suspicious pattern or anomaly:
  - `id` (UUID)
  - `finding_type` (`IMPOSSIBLE_TRAVEL`, `FAILED_LOGIN_BURST`, `MFA_FATIGUE`, `OTHER`)
  - `description`
  - `okta_event_ids` (events that triggered this finding)
  - `user_id`
  - `created_at`
  - `metadata` (detector-specific details)

- **`RiskScore`**  
  Risk analysis from the LLM:
  - `severity`: `low | medium | high | critical`
  - `likelihood`: 0.0–1.0
  - `impact`: 0.0–1.0
  - `score`: overall 0.0–1.0
  - `rationale`: short explanation

- **`SecurityIncident`**  
  A promoted, trackable incident:
  - `id` (UUID)
  - `finding_id` (source finding)
  - `title`, `description`
  - `severity`, `risk_score`
  - `created_at` (UTC)
  - `status` (`open | triaged | closed`)
  - `metadata` (enriched context)

- **`ResponsePlan`** and **`ResponseStep`**  
  Structured response steps produced by the LLM:
  - `overall_goal`: what the plan is trying to achieve
  - `steps`: list of `ResponseStep` entries
    - `step_id` (canonical IDs like `lock_account`, `revoke_sessions`, etc.)
    - `description`
    - `rationale`
    - `requires_human_approval`
    - `dependencies` (optional list of step_ids)

- **`CommandSuggestion`**  
  Safe, **read-only** command templates for humans to review:
  - `step_id`
  - `description`
  - `command` (e.g., `curl` templates)
  - `system` (e.g., `"okta_api"`)
  - `read_only` (bool)
  - `notes`

---

## Agents

All agents implement a minimal async `run()` method and are orchestrated in two stages.

### Orchestrator

**File:** `okta_soc/agents/orchestrator.py`

The Orchestrator performs **two stages** of orchestration.

#### Stage 1: Raw Events

Method: `process_raw_events(events: List[OktaEvent])`

1. Build router context:
   ```python
   context_raw = {
       "kind": "raw_events",
       "data": [e.model_dump() for e in events],
   }
   ```
2. Ask `RouterAgent` for a route plan (`RoutePlan`).
3. Execute steps in order:
   - If `detector_agent`:
     - Run detector agent on `events`.
     - Save each `DetectionFinding` via `FindingsRepo`.
   - If `risk_agent`:
     - For each finding:
       - Run `LLMRiskAgent` to get `(RiskScore, promote)`.
       - If `promote` is `True`, create a `SecurityIncident` via `IncidentsRepo`.

4. If no findings are promoted to incidents, the response stage is skipped (no plans or commands are generated).

---

#### Stage 2: Per Incident

Method: `_process_single_incident(incident: SecurityIncident)`

For each `incident`:

1. Build router context:
   ```python
   context_incident = {
       "kind": "incident",
       "data": incident.model_dump(),
   }
   ```
2. Ask `RouterAgent` for a route plan (`RoutePlan`) for response.
3. Execute steps:
   - If `planner_agent`:
     - Run `PlannerAgent` to get a `ResponsePlan`.
     - Save via `PlansRepo`.
   - If `command_agent`:
     - Run `CommandAgent` on the `ResponsePlan`.
     - Save each `CommandSuggestion` via `CommandsRepo`.

---

### RouterAgent

**File:** `okta_soc/agents/router_agent.py`  
**Purpose:** LLM-driven orchestration router with hard guardrails.

Given a context like:

- `{"kind": "raw_events", "data": [...]}` or
- `{"kind": "incident", "data": {...}}`

The RouterAgent:

1. Shows the LLM a catalog of available agents from `okta_soc/agents/registry.py` (name, description, input type, output type, phase, criticality).
2. Provides **routing rules** that depend on `context["kind"]`:

   - For `kind == "raw_events"`:
     - Phase must be `ingest` or `analysis`.
     - `detector_agent` **must** be included.
     - `risk_agent` **must** be included **after** `detector_agent`.
     - `planner_agent` and `command_agent` must **not** be used.

   - For `kind == "incident"`:
     - Phase must be `response`.
     - `planner_agent` **must** be included.
     - For `high` or `critical` incidents, `command_agent` **should** be included.

3. Asks the LLM to return **only JSON**:
   ```json
   {
     "phase": "ingest|analysis|response",
     "steps": [
       {
         "agent_name": "string",
         "reason": "string",
         "when": "string"
       }
     ],
     "notes": "string or null"
   }
   ```

4. **Guardrails layer** (non-negotiable logic in Python):
   - For `raw_events`:
     - Ensures `detector_agent` is present and first.
     - Ensures `risk_agent` is present and after detector.
     - Drops any agents that aren’t `detector_agent` or `risk_agent`.
     - Forces `phase = "ingest"`.
   - For `incident`:
     - Ensures `planner_agent` is present.
     - If severity is `high` or `critical`, ensures `command_agent` is present.
     - Drops agents that are not `planner_agent` or `command_agent`.
     - Forces `phase = "response"`.

The result is a **LLM-guided but rule-constrained** routing plan that prevents the model from doing something nonsensical.

---

### DetectorAgent

**File:** `okta_soc/agents/detector_agent.py`

- Responsible for turning raw `OktaEvent` lists into `DetectionFinding` objects.
- It doesn’t use the LLM: it just calls all registered detectors from `okta_soc/detectors/registry.py`.

Workflow:

```python
events: List[OktaEvent] → DetectorAgent.run(events) → List[DetectionFinding]
```

In this demo, there are two detectors:

- `ImpossibleTravelDetector`
- `FailedLoginBurstDetector`

(See [Detectors](#detectors) below.)

---

### LLMRiskAgent

**File:** `okta_soc/agents/risk_agent.py`

- Uses the LLM to **score risk** for each `DetectionFinding`.
- Returns:
  - A `RiskScore` object.
  - A boolean `promote` flag that decides whether to create an incident.

The prompt instructs the LLM to:

1. Choose severity (`low | medium | high | critical`).
2. Assign numeric `likelihood` and `impact`.
3. Compute `score` (0.0–1.0).
4. Provide a short `rationale`.

Promotion logic (hard-coded, not in the LLM):

```python
promote = (
    risk.score >= self.promotion_threshold
    or severity in {Severity.HIGH, Severity.CRITICAL}
)
```

By default, `promotion_threshold` is `0.6`. So:

- **High risk score** OR **high/critical severity** ⇒ promote to `SecurityIncident`.
- Anything else ⇒ treated as lower priority (no incident created).

---

### PlannerAgent

**File:** `okta_soc/agents/planner_agent.py`

- Takes a `SecurityIncident`.
- Asks the LLM to design a **structured response plan**.
- The plan uses canonical `step_id` values where possible, such as:

  - `collect_auth_logs`
  - `analyze_geo_and_devices`
  - `lock_account`
  - `notify_user`
  - `enable_mfa`
  - `revoke_sessions`
  - `forensic_review`
  - `update_incident_status`

The LLM is required to return exactly one JSON object:

```json
{
  "overall_goal": "string",
  "steps": [
    {
      "step_id": "string",
      "description": "string",
      "rationale": "string",
      "requires_human_approval": true,
      "dependencies": ["optional_step_id"]
    }
  ],
  "notes": "string or null"
}
```

The planner enforces:

- All steps must be **safe** and **non-destructive**.
- Everything is assumed to be **reviewed by a human analyst** before execution.

The result is converted into a `ResponsePlan` with `ResponseStep` entries.

---

### CommandAgent

**File:** `okta_soc/agents/command_agent.py`

- Converts a `ResponsePlan` into a list of `CommandSuggestion` objects.
- Only handles specific `step_id`s:
  - `lock_account`
  - `force_password_reset`
  - `revoke_sessions`
  - `enable_mfa`

For each known `step_id`, it generates a **template** `curl` command against the Okta API:

- Uses `OKTA_ORG_URL` from config.
- Leaves `{userId}` and `SSWS` token placeholders for humans to fill in.
- Marks commands as `read_only=True` in the metadata (semantically: “do not auto-execute”).

Example (simplified):

```bash
curl -X POST \
  https://your-org.okta.com/api/v1/users/{userId}/lifecycle/suspend \
  -H 'Authorization: SSWS <REDACTED_TOKEN>' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json'
```

The idea: **LLM suggests what to do**, but **humans decide if/how to run it.**

---

## Detectors

Detectors are small, deterministic analyzers for specific patterns in Okta events.

### `ImpossibleTravelDetector`

**File:** `okta_soc/detectors/impossible_travel.py`

Logic:

- Group events by `actor_id`.
- Sort each actor’s events by timestamp.
- For each consecutive pair `(a, b)`:
  - If either event has no `country`, skip.
  - If `a.country == b.country`, skip.
  - Compute `dt = b.timestamp - a.timestamp`.
  - If `dt < 1 hour`, emit a `DetectionFinding`:
    - `finding_type = IMPOSSIBLE_TRAVEL`
    - Description like:
      > Possible impossible travel for actor bob: FR -> US within 0:25:00.

### `FailedLoginBurstDetector`

**File:** `okta_soc/detectors/failed_login_burst.py`

Parameters:

- `threshold` (default: 5)
- `window_minutes` (default: 10)

Logic:

- Group events by `actor_id`.
- Keep only events with `outcome == "FAILURE"`.
- For each actor’s failed events (sorted by time):
  - Slide a window of width `window_minutes`.
  - If within that window there are ≥ `threshold` failures:
    - Emit `DetectionFinding` with:
      - `finding_type = FAILED_LOGIN_BURST`
      - `description` like:
        > 7 failed logins for actor alice within 0:10:00.
      - `metadata` includes count and window length.

---

## Storage & Artifacts

**File:** `okta_soc/storage/repositories.py`  
All artifacts live in `data/` as JSON Lines (`.jsonl`):

- `data/findings.jsonl` – one `DetectionFinding` per line.
- `data/incidents.jsonl` – one `SecurityIncident` per line.
- `data/plans.jsonl` – one `ResponsePlan` per line.
- `data/commands.jsonl` – one `{incident_id, command}` record per line.

The `show-all` interface nicely pretty-prints all of these.

---

## CLI Usage

The CLI entrypoint is defined in `pyproject.toml`:

```toml
[project.scripts]
okta-soc = "okta_soc.interface.cli:main"
```

After installing the project (see below), you can use:

### Run the Full Pipeline

```bash
okta-soc --hours 24
```

This will:

1. Load events from the demo JSON file (see [Demo Mode vs Real Okta](#demo-mode-vs-real-okta)).
2. Run Stage 1 (detection + risk).
3. Run Stage 2 (planning + commands) for any promoted incidents.
4. Write all artifacts into `data/`.

### View All Artifacts

```bash
okta-soc show-all
```

This calls `run_show_all()` in `okta_soc/interface/show_all.py`, which:

- Reads all `.jsonl` files under `data/`.
- Pretty-prints:
  - Findings
  - Incidents
  - Plans
  - Commands

with Rich panels and indent guides.

### Convenience Script

A helper script is included:

**File:** `run.sh`

```bash
#!/bin/zsh
rm -f data/*.jsonl
uv run python -m okta_soc.interface.cli --hours 24
uv run python -m okta_soc.interface.cli show-all
```

This:

1. Clears all previous artifacts.
2. Runs the pipeline for the last 24 hours.
3. Prints all results.

---

## Configuration

**File:** `okta_soc/core/config.py`

Settings are loaded from environment variables (via `.env` and `python-dotenv`):

```env
OKTA_ORG_URL="https://example.okta.com"
OKTA_API_TOKEN="REPLACE_ME"
LLM_BASE_URL="http://localhost:1234/v1"
LLM_MODEL="gpt-oss-20b"
LLM_API_KEY="lm-studio"   # or whatever your endpoint expects
```

Defaults (if not set):

- `OKTA_ORG_URL`: `https://example.okta.com`
- `OKTA_API_TOKEN`: `REPLACE_ME`
- `LLM_BASE_URL`: `http://192.168.1.225:1234/v1`
- `LLM_MODEL`: `gpt-oss-20b`
- `LLM_API_KEY`: `lm-studio`

The `LLMClient` in `okta_soc/core/llm.py` uses the OpenAI-compatible `chat.completions.create` API.

---

## Demo Mode vs Real Okta

Currently, `OktaClient` is in **demo mode**:

**File:** `okta_soc/ingest/okta_client.py`

- Ignores the real Okta API.
- Reads from a local JSON file:

  ```text
  tests/demo_okta_system_logs.json
  ```

- Parses timestamps to timezone-aware UTC datetimes.
- Filters out events older than the `since` time passed to `fetch_events_since()`.

This makes the system easy to demo without real Okta credentials.

To integrate with real Okta, you’d replace the implementation of `fetch_events_since()` with calls to the Okta System Log API and map those responses into `OktaEvent`.

---

## Extending the System

### Adding a New Detector

1. Create a new file in `okta_soc/detectors/`, e.g. `impossible_mfa.py`.
2. Implement a class inheriting `BaseDetector`:

   ```python
   from datetime import timedelta
   from typing import List
   import uuid

   from okta_soc.core.models import OktaEvent, DetectionFinding, FindingType
   from .base import BaseDetector

   class ImpossibleMFADetector(BaseDetector):
       name = "impossible_mfa"

       def detect(self, events: List[OktaEvent]) -> List[DetectionFinding]:
           findings = []
           # ... your detection logic ...
           return findings
   ```

3. Register it in `okta_soc/detectors/registry.py`:

   ```python
   from .impossible_mfa import ImpossibleMFADetector

   def get_all_detectors() -> List[BaseDetector]:
       return [
           ImpossibleTravelDetector(),
           FailedLoginBurstDetector(),
           ImpossibleMFADetector(),  # new
       ]
   ```

Done. The `DetectorAgent` will automatically run your new detector.

---

### Adding a New Agent

1. Implement a new agent in `okta_soc/agents/`, e.g. `notify_agent.py`:

   ```python
   from .base import BaseAgent

   class NotifyAgent(BaseAgent):
       name = "notify_agent"

       async def run(self, incident):
           # e.g. draft an email or Slack message
           ...
   ```

2. Register it in `okta_soc/agents/registry.py`:

   ```python
   from .notify_agent import NotifyAgent

   AGENTS: Dict[str, AgentMeta] = {
       # existing agents...
       "notify_agent": AgentMeta(
           name="notify_agent",
           description="Drafts notifications to users or admins about incidents.",
           input_type="SecurityIncident",
           output_type="NotificationDraft",
           phase="response",
           critical=False,
       ),
   }
   ```

3. Update `Orchestrator` / `RouterAgent` logic if you want the router to consider it.

   - Add to `_agent_map` in `Orchestrator.__init__`.
   - Update routing rules and/or guardrails in `RouterAgent` for new `step_id` patterns or phases.

---

## LLM Details & Expectations

The LLM is used in three roles:

1. **Router (RouterAgent)**
   - Decides which agents to run and in what order based on structured context.
   - Forced into a small JSON schema.
   - Guardrails heavily constrain possible outputs.

2. **Risk Analysis (LLMRiskAgent)**
   - Assigns severity and numerical risk metrics to `DetectionFinding`.
   - Responsible for the qualitative reasoning `"rationale"`.
   - Promotion logic is **always** enforced by Python, not the model.

3. **Response Planning (PlannerAgent)**
   - Maps incidents to a structured `ResponsePlan` using canonical step IDs.
   - Must output **only JSON**; any extra text is stripped.
   - Design goal: make response plans interpretable, editable, and auditable.

JSON parsing:

- `LLMClient.chat_json()` wraps `chat()`, forces the model to output JSON, and does a best-effort brace extraction before `json.loads()`.

If the model returns extra commentary, the code tries to salvage the JSON block between the first `{` and the last `}`.

---

## Limitations & Safety Notes

- **Demo Only**: The current implementation uses demo input via `tests/demo_okta_system_logs.json` and template `curl` commands with placeholders. It does not talk to Okta by default.
- **No Auto-Execution**: Commands produced by `CommandAgent` are:
  - Marked as `read_only` in their metadata.
  - Obviously templated with `{userId}` and `<REDACTED_TOKEN>`.
  - Intended for **human review** only.
- **LLM Hallucinations**: While guardrails and schemas reduce nonsense, the LLM can still:
  - Misjudge risk.
  - Over/under-estimate severity.
  - Propose overly aggressive plans.  
  Always treat outputs as **recommendations**, not truth.
- **Time & Geo Assumptions**: Detectors use simple time and country comparisons; real-world mileage may vary and should be tuned for:
  - Travel patterns.
  - Known VPN regions.
  - Normal user behavior.

---

## Getting Started (Install & Run)

From the project root:

```bash
# (Optional) using uv
uv run pip install .

# Or with plain pip
pip install .
```

Set up your `.env`:

```env
OKTA_ORG_URL="https://example.okta.com" # Can leave unmodified for demo
OKTA_API_TOKEN="REPLACE_ME" # Can leave unmodified for demo
LLM_BASE_URL="http://localhost:1234/v1"
LLM_MODEL="gpt-oss-20b"
LLM_API_KEY="lm-studio"
```

Run the pipeline and show results:

```bash
okta-soc --hours 24
okta-soc show-all
```

Or use the convenience script:

```bash
./run.sh
```

Then explore the structured artifacts in `data/` to see how the agentic SOC pipeline behaved end-to-end.
