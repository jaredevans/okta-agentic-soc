from typing import Any, Dict, Set

from .base import BaseAgent
from okta_soc.core.llm import LLMClient
from okta_soc.core.router_models import RoutePlan, RouteStep
from okta_soc.agents.registry import AGENTS


class RouterAgent(BaseAgent):
    name = "router_agent"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, context: Dict[str, Any]) -> RoutePlan:
        """
        LLM-driven router with guardrails.

        - For kind == "raw_events":
            * Always include detector_agent (first).
            * Always include risk_agent (after detector).

        - For kind == "incident":
            * Always include planner_agent.
            * For high/critical incidents, also include command_agent.
        """
        agents_desc = "\n".join(
            f"- {m.name}: {m.description} "
            f"(phase={m.phase}, input={m.input_type}, output={m.output_type}, critical={m.critical})"
            for m in AGENTS.values()
        )

        kind = context.get("kind", "")

        system_prompt = (
            "You are an orchestration router for a security automation platform "
            "that analyzes Okta security events. "
            "You NEVER execute actions yourself. You only decide which agents (tools) "
            "should be called and in what order. Be concise and deterministic."
        )

        # Extra guidance based on context kind
        if kind == "raw_events":
            routing_rules = """
Routing rules for kind == "raw_events":
- The phase MUST be "ingest" or "analysis".
- detector_agent MUST be included.
- risk_agent MUST be included, after detector_agent.
- The typical order is: detector_agent, then risk_agent.
- Do NOT include planner_agent or command_agent here.
"""
        elif kind == "incident":
            routing_rules = """
Routing rules for kind == "incident":
- The phase MUST be "response".
- planner_agent MUST be included.
- If the incident severity is high or critical, command_agent SHOULD also be included.
- The typical order is: planner_agent, then optionally command_agent.
"""
        else:
            routing_rules = """
Routing rules:
- Choose a reasonable phase from: ingest, analysis, response.
- Use only agents that make sense for the provided context.
"""

        user_prompt = f"""
Available agents:
{agents_desc}

Context (JSON-like):
{context}

{routing_rules}

General instructions:
- Select only agents relevant to this context.
- Prefer critical=true agents when needed.
- Respect logical dependencies. For example:
  - detector_agent must run before risk_agent.
  - risk_agent must run before planner_agent.
  - planner_agent must run before command_agent.
- If context.kind == "raw_events": focus on detection and risk scoring.
- If context.kind == "incident": focus on planning and (optionally) command generation.
- Minimize unnecessary agents.

Return ONLY JSON with this structure:
{{
  "phase": "ingest|analysis|response",
  "steps": [
    {{
      "agent_name": "string",
      "reason": "string",
      "when": "string"
    }}
  ],
  "notes": "string or null"
}}
"""

        # Lower temperature to make routing decisions more stable
        raw = self.llm.chat_json(system_prompt, user_prompt, temperature=0.01)
        plan = RoutePlan.model_validate(raw)

        # ------------------------------------------------------------------
        # Guardrails: enforce minimal, sensible plans for each context kind
        # ------------------------------------------------------------------
        step_names: Set[str] = {s.agent_name for s in plan.steps}

        if kind == "raw_events":
            # Ensure detector_agent is present and first
            if "detector_agent" not in step_names:
                plan.steps.insert(
                    0,
                    RouteStep(
                        agent_name="detector_agent",
                        reason="Required to analyze raw Okta events and produce findings.",
                        when="now",
                    ),
                )
                step_names.add("detector_agent")

            # Ensure risk_agent is present and after detector_agent
            if "risk_agent" not in step_names:
                plan.steps.append(
                    RouteStep(
                        agent_name="risk_agent",
                        reason="Required to score findings and decide incident promotion.",
                        when="after_detector_agent",
                    )
                )
                step_names.add("risk_agent")

            # Filter out obviously wrong agents for raw_events
            plan.steps = [
                s
                for s in plan.steps
                if s.agent_name in {"detector_agent", "risk_agent"}
            ]
            plan.phase = "ingest"

        elif kind == "incident":
            # Extract severity if present
            severity = None
            data = context.get("data") or {}
            if isinstance(data, dict):
                severity = str(data.get("severity", "")).lower()

            # Ensure planner_agent is present
            if "planner_agent" not in step_names:
                plan.steps.insert(
                    0,
                    RouteStep(
                        agent_name="planner_agent",
                        reason="Required to generate a response plan for the incident.",
                        when="now",
                    ),
                )
                step_names.add("planner_agent")

            # For high/critical incidents, ensure command_agent is included
            if severity in {"high", "critical"} and "command_agent" not in step_names:
                plan.steps.append(
                    RouteStep(
                        agent_name="command_agent",
                        reason="Generate read-only commands for the response plan.",
                        when="after_planner_agent",
                    )
                )
                step_names.add("command_agent")

            # Only keep response-phase agents here
            plan.steps = [
                s
                for s in plan.steps
                if s.agent_name in {"planner_agent", "command_agent"}
            ]
            plan.phase = "response"

        # For other kinds, we just trust the model's plan without extra constraints.

        return plan
