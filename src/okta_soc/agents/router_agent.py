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
- Prefer agents with actions (e.g., notifications, tickets) only when the situation warrants it.
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
            is_iterating = False

            if step.iterate_over and step.iterate_over in available:
                # LLM explicitly set iterate_over and the list type exists
                is_iterating = True
                satisfied = True
            elif all(t in available for t in contract.consumes):
                # All consumed types are directly available
                satisfied = True
            else:
                # Auto-detect: if agent consumes T but only List[T] is available,
                # automatically set iterate_over
                auto_iterate = None
                for t in contract.consumes:
                    list_key = f"List[{t}]"
                    if t not in available and list_key in available:
                        auto_iterate = list_key
                        break

                if auto_iterate:
                    step = RouteStep(
                        agent_name=step.agent_name,
                        reason=step.reason,
                        iterate_over=auto_iterate,
                    )
                    is_iterating = True
                    satisfied = True
                else:
                    satisfied = False

            if not satisfied:
                continue

            valid_steps.append(step)

            # Track what types become available after this step.
            # When iterating, the orchestrator collects outputs into List[T],
            # so only List[T] is available downstream (not bare T).
            for t in contract.produces:
                if is_iterating:
                    available.add(f"List[{t}]")
                else:
                    available.add(t)
                    available.add(f"List[{t}]")

        plan.steps = valid_steps
        return plan
