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
from okta_soc.agents.orchestrator import Orchestrator
from okta_soc.ingest.okta_client import OktaClient
from okta_soc.storage.repositories import (
    FindingsRepo,
    IncidentsRepo,
    PlansRepo,
    CommandsRepo,
)


async def fetch_and_process(since: datetime) -> None:
    settings = load_settings()
    okta = OktaClient(settings.okta_org_url, settings.okta_api_token)

    llm = LLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )

    router_agent = RouterAgent(llm)
    detector_agent = DetectorAgent()
    risk_agent = LLMRiskAgent(llm)
    planner_agent = PlannerAgent(llm)
    command_agent = CommandAgent(settings.okta_org_url)

    findings_repo = FindingsRepo()
    incidents_repo = IncidentsRepo()
    plans_repo = PlansRepo()
    commands_repo = CommandsRepo()

    orchestrator = Orchestrator(
        router_agent=router_agent,
        detector_agent=detector_agent,
        risk_agent=risk_agent,
        planner_agent=planner_agent,
        command_agent=command_agent,
        findings_repo=findings_repo,
        incidents_repo=incidents_repo,
        plans_repo=plans_repo,
        commands_repo=commands_repo,
    )

    events: List[OktaEvent] = await okta.fetch_events_since(since)
    await orchestrator.process_raw_events(events)
