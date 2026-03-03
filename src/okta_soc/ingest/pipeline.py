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
from okta_soc.agents.escalation_agent import EscalationAgent
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
    registry.register(EscalationAgent())

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
        FindingsRepo, IncidentsRepo, PlansRepo, CommandsRepo, EscalationsRepo,
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

    for cmd_list in context.data.get("List[List[CommandSuggestion]]", []):
        if isinstance(cmd_list, list):
            for c in cmd_list:
                commands_repo.save("", c)
        else:
            commands_repo.save("", cmd_list)

    escalations_repo = EscalationsRepo()
    for escalation in context.data.get("List[EscalationResult]", []):
        escalations_repo.save(escalation)
