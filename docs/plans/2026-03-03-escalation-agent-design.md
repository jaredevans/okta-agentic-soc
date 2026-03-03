# Escalation Agent Design

**Goal:** Add an EscalationAgent that simulates Slack notifications for high-severity incidents, demonstrating genuine LLM routing decisions via the `side_effects` contract field.

**Architecture:** The escalation agent consumes `SecurityIncident`, formats a Slack message, logs it (simulated), and produces an `EscalationResult`. The LLM router decides whether to include it based on incident severity — this is the first agent where the router makes a genuinely context-sensitive decision.

## Agent Contract

- **name**: `escalation_agent`
- **description**: "Sends Slack notification for high-severity or critical security incidents."
- **consumes**: `["SecurityIncident"]`
- **produces**: `["EscalationResult"]`
- **phase_hint**: `"response"`
- **side_effects**: `["slack_notification"]`

## New Model: EscalationResult

```python
class EscalationResult(BaseModel):
    incident_id: str
    channel: str          # e.g., "#soc-critical-alerts"
    message: str          # The formatted Slack message text
    sent: bool            # Always True in simulation
```

## Behavior

1. Receive a `SecurityIncident`.
2. Format a Slack-style notification message containing: severity, title, description, risk score.
3. Log the message to stdout (simulated send).
4. Return `EscalationResult` with channel, message, and `sent=True`.

No LLM call needed — this is a deterministic agent.

## Router Integration

- The router system prompt already says: "Prefer agents with side_effects only when the situation warrants it."
- The agent description explicitly mentions high-severity/critical, guiding the LLM.
- The router sees severity in the pipeline metadata/context and decides whether to include escalation.
- This is the first agent that uses `side_effects`, making the LLM routing decision genuinely meaningful.

## Pipeline Wiring

- Register `EscalationAgent()` in `pipeline.py` alongside existing agents.
- Persist `EscalationResult` to `data/escalations.jsonl`.
- The agent iterates over `List[SecurityIncident]` (same pattern as planner/command agents).
