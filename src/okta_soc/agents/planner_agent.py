from .base import BaseAgent
from okta_soc.core.models import SecurityIncident, ResponsePlan, ResponseStep
from okta_soc.core.llm import LLMClient


class PlannerAgent(BaseAgent):
    name = "planner_agent"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, incident: SecurityIncident) -> ResponsePlan:
        system_prompt = (
            "You are an incident response planner for Okta security incidents. "
            "You design step-by-step response plans that are safe and appropriate."
        )

        # We give the model canonical step IDs that the CommandAgent understands.
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
        return plan
