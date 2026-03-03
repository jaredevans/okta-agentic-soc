# Dynamic LLM-Driven Agent Routing

**Date:** 2026-03-03
**Status:** Approved
**Approach:** Typed Agent Graph

## Problem

The current router asks the LLM what agents to run, then overrides its decisions with hardcoded guardrails. The orchestrator has `if agent_name == "..."` branches for each agent. Adding a new agent requires editing the router, orchestrator, and registry. The LLM call is decorative — it doesn't influence behavior.

## Goals

1. **Easy extensibility** — drop in a new agent (enrichment, notification, etc.) without editing the router or orchestrator.
2. **Context-sensitive routing** — the LLM makes genuine decisions about which agents to include based on the data.
3. **Type safety without rigidity** — agents declare typed contracts (consumes/produces). The LLM composes freely; type compatibility is the only constraint.

## Design

### Agent Contracts

Each agent declares what data types it consumes and produces. This replaces the current `AgentMeta` descriptive-only metadata.

```python
@dataclass
class AgentContract:
    name: str
    description: str              # Rich description for the LLM to reason about
    consumes: List[str]           # Data types this agent needs, e.g. ["List[OktaEvent]"]
    produces: List[str]           # Data types this agent outputs, e.g. ["List[DetectionFinding]"]
    phase_hint: str               # Suggested phase — advisory, not enforced
    side_effects: List[str]       # e.g. ["slack_notification", "jira_ticket"]
    requires_human_approval: bool # Whether output needs human sign-off
```

Example catalog the LLM sees:

```
- detector_agent: Analyzes raw Okta events for anomalies.
  Consumes: List[OktaEvent] -> Produces: List[DetectionFinding]

- enrichment_agent: Looks up IP reputation and threat intel.
  Consumes: DetectionFinding -> Produces: EnrichedFinding

- risk_agent: Scores findings for severity.
  Consumes: DetectionFinding OR EnrichedFinding -> Produces: RiskScore, SecurityIncident

- slack_notifier: Sends alert to security channel.
  Consumes: SecurityIncident -> Produces: NotificationResult
  Side effects: slack_notification
```

### Pipeline Context (Shared State)

A shared context object flows through the pipeline. Agents read their inputs from it and write their outputs back.

```python
class PipelineContext:
    data: Dict[str, Any]         # Keyed by type name: {"List[OktaEvent]": [...], ...}
    metadata: Dict[str, Any]     # Pipeline-level info (run_id, timestamp, source)
    history: List[StepResult]    # Audit trail of what ran and what it produced
```

### Updated BaseAgent Interface

```python
class BaseAgent(ABC):
    name: str
    contract: AgentContract

    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Input and output keyed by type name."""
        ...
```

### Router — LLM as Real Decision-Maker

The router no longer has hardcoded per-kind guardrails. It:

1. Shows the LLM the full agent catalog with contracts
2. Shows what data types are currently available in the context
3. Asks the LLM to compose an ordered pipeline
4. Validates the plan by type-checking: each agent's `consumes` must be satisfied by prior outputs or initial data

```python
class RouterAgent:
    async def run(self, context: PipelineContext) -> RoutePlan:
        catalog = self._describe_agents()       # All registered agents with contracts
        available_types = list(context.data.keys())

        raw_plan = self.llm.chat_json(
            system_prompt=ROUTER_SYSTEM_PROMPT,
            user_prompt=f"""
Available agents:
{catalog}

Data currently available: {available_types}

Context: {context.metadata}

Compose a pipeline of agents to process this data.
Each agent's 'consumes' types must be available from either:
- The initial data above, OR
- A prior agent's 'produces' types.

Return JSON: {{"steps": [{{"agent_name": "...", "reason": "...", "iterate_over": "..." or null}}]}}
""",
            temperature=0.1,
        )

        plan = self._validate_type_compatibility(raw_plan, context)
        return plan
```

`_validate_type_compatibility` walks the plan step-by-step, tracking available types. Agents whose inputs aren't satisfied are removed with a warning — not force-inserted.

### Route Plan with Iteration

The plan supports `iterate_over` so the LLM can express "run this agent per item in a list":

```python
class RouteStep(BaseModel):
    agent_name: str
    reason: str
    iterate_over: Optional[str] = None  # e.g. "List[SecurityIncident]"

class RoutePlan(BaseModel):
    steps: List[RouteStep]
    notes: Optional[str] = None
```

Example LLM output:

```json
{
  "steps": [
    {"agent_name": "detector_agent", "reason": "Detect anomalies in raw events"},
    {"agent_name": "risk_agent", "reason": "Score each finding", "iterate_over": "List[DetectionFinding]"},
    {"agent_name": "planner_agent", "reason": "Plan response per incident", "iterate_over": "List[SecurityIncident]"},
    {"agent_name": "command_agent", "reason": "Generate commands for plans", "iterate_over": "List[ResponsePlan]"}
  ]
}
```

### Generic Orchestrator

The orchestrator no longer knows about specific agents. It:

1. Asks the router to compose a pipeline
2. For each step: pulls inputs from context, runs the agent, stores outputs back
3. Handles `iterate_over` by unwrapping lists and running the agent per item
4. Persists outputs via type-registered repos

```python
class Orchestrator:
    def __init__(self, router: RouterAgent, agents: Dict[str, BaseAgent], repos: Dict[str, BaseRepo]):
        self.router = router
        self.agents = agents
        self.repos = repos

    async def run(self, initial_data: Dict[str, Any], metadata: Dict[str, Any]) -> PipelineContext:
        context = PipelineContext(data=initial_data, metadata=metadata)
        plan = await self.router.run(context)

        for step in plan.steps:
            agent = self.agents[step.agent_name]

            if step.iterate_over and step.iterate_over in context.data:
                items = context.data[step.iterate_over]
                all_outputs = []
                for item in items:
                    inputs = {t: item for t in agent.contract.consumes}
                    outputs = await agent.run(inputs)
                    all_outputs.append(outputs)
                    self._persist(outputs)
                self._merge_outputs(context, all_outputs)
            else:
                inputs = {t: context.data[t] for t in agent.contract.consumes}
                outputs = await agent.run(inputs)
                context.data.update(outputs)
                self._persist(outputs)

            context.history.append(StepResult(agent=step.agent_name, outputs=list(outputs.keys())))

        return context
```

### Adding a New Agent (Developer Experience)

Two steps only:

1. **Write the agent class with a contract:**

```python
class SlackNotifierAgent(BaseAgent):
    contract = AgentContract(
        name="slack_notifier",
        description="Sends a formatted alert to the #security-alerts Slack channel.",
        consumes=["SecurityIncident"],
        produces=["NotificationResult"],
        phase_hint="response",
        side_effects=["slack_notification"],
        requires_human_approval=False,
    )

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        incident = input_data["SecurityIncident"]
        result = await self.slack_client.post_alert(incident)
        return {"NotificationResult": result}
```

2. **Register it** (decorator or explicit entry in registry).

No router or orchestrator changes needed. The LLM sees it in the catalog and can choose to include it.

### Storage

Repos register by data type rather than being wired per-agent:

```python
repos = {
    "List[DetectionFinding]": FindingsRepo(),
    "List[SecurityIncident]": IncidentsRepo(),
    "ResponsePlan": PlansRepo(),
    "CommandSuggestion": CommandsRepo(),
}
```

## Summary of Changes

| Component | Current | Proposed |
|-----------|---------|----------|
| Agent metadata | Descriptive strings, unused | Typed contracts (consumes/produces) that drive wiring |
| Router | LLM suggests, Python overrides | LLM composes freely, validated by type compatibility |
| Orchestrator | Hardcoded `if agent_name ==` branches | Generic: pull inputs, run agent, store outputs |
| Adding an agent | Edit agent + router + orchestrator | Write agent class with contract, register it |
| Pipeline flow | Two hardcoded stages | Emergent from type dependencies |
| Iteration | Hardcoded `for incident in incidents` | Router declares `iterate_over`, orchestrator handles generically |
| Storage | Per-agent repo wiring | Repos register for data types |

## Configuration

- LLM endpoint: `LLM_BASE_URL` (current default should be updated to `http://100.113.108.1:1234/v1`)
