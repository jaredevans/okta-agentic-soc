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
