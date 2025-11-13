from typing import Dict, Any, List, Optional

from okta_soc.core.router_models import RoutePlan
from okta_soc.core.models import (
    OktaEvent,
    DetectionFinding,
    SecurityIncident,
    ResponsePlan,
    CommandSuggestion,
)
from okta_soc.agents.router_agent import RouterAgent
from okta_soc.agents.detector_agent import DetectorAgent
from okta_soc.agents.risk_agent import LLMRiskAgent
from okta_soc.agents.planner_agent import PlannerAgent
from okta_soc.agents.command_agent import CommandAgent
from okta_soc.agents.base import BaseAgent
from okta_soc.storage.repositories import (
    FindingsRepo,
    IncidentsRepo,
    PlansRepo,
    CommandsRepo,
)


class Orchestrator:
    """
    Two-stage orchestration:

    1) Raw events phase:
       - Ask the router what to do for kind="raw_events"
       - Usually: detector_agent, then risk_agent
       - Produces findings + incidents

    2) Incident phase:
       - For each incident, ask the router again with kind="incident"
       - Router decides whether to involve planner_agent and/or command_agent
    """

    def __init__(
        self,
        router_agent: RouterAgent,
        detector_agent: DetectorAgent,
        risk_agent: LLMRiskAgent,
        planner_agent: PlannerAgent,
        command_agent: CommandAgent,
        findings_repo: FindingsRepo,
        incidents_repo: IncidentsRepo,
        plans_repo: PlansRepo,
        commands_repo: CommandsRepo,
    ):
        self.router_agent = router_agent
        self.detector_agent = detector_agent
        self.risk_agent = risk_agent
        self.planner_agent = planner_agent
        self.command_agent = command_agent
        self.findings_repo = findings_repo
        self.incidents_repo = incidents_repo
        self.plans_repo = plans_repo
        self.commands_repo = commands_repo

        self._agent_map: Dict[str, BaseAgent] = {
            "detector_agent": self.detector_agent,
            "risk_agent": self.risk_agent,
            "planner_agent": self.planner_agent,
            "command_agent": self.command_agent,
        }

    # ---------- Stage 1: from raw Okta events ----------

    async def process_raw_events(self, events: List[OktaEvent]) -> None:
        # Ask router what to do for raw events
        context_raw: Dict[str, Any] = {
            "kind": "raw_events",
            "data": [e.model_dump() for e in events],
        }

        route_plan_raw: RoutePlan = await self.router_agent.run(context_raw)

        findings: List[DetectionFinding] = []
        incidents: List[SecurityIncident] = []

        # Execute ingest/analysis steps as per router
        for step in route_plan_raw.steps:
            agent_name = step.agent_name
            agent = self._agent_map.get(agent_name)
            if not agent:
                continue

            if agent_name == "detector_agent":
                findings = await self.detector_agent.run(events)  # type: ignore[arg-type]
                for f in findings:
                    self.findings_repo.save(f)

            elif agent_name == "risk_agent":
                new_incidents: List[SecurityIncident] = []
                for f in findings:
                    risk, promote = await self.risk_agent.run(f)  # type: ignore[arg-type]
                    if promote:
                        incident = self.incidents_repo.create_from_finding(f, risk)
                        new_incidents.append(incident)
                incidents.extend(new_incidents)

        # Now we have incidents (if any). For each, run the incident-phase orchestration.
        for incident in incidents:
            await self._process_single_incident(incident)

        return

    # ---------- Stage 2: from a single existing incident ----------

    async def _process_single_incident(self, incident: SecurityIncident) -> None:
        """
        Ask the router which response-phase agents to use for this incident
        (typically planner_agent, and optionally command_agent).
        """
        context_incident: Dict[str, Any] = {
            "kind": "incident",
            "data": incident.model_dump(),
        }

        route_plan_incident: RoutePlan = await self.router_agent.run(context_incident)

        response_plan: Optional[ResponsePlan] = None

        for step in route_plan_incident.steps:
            agent_name = step.agent_name
            agent = self._agent_map.get(agent_name)
            if not agent:
                continue

            if agent_name == "planner_agent":
                response_plan = await self.planner_agent.run(incident)  # type: ignore[arg-type]
                self.plans_repo.save(response_plan)

            elif agent_name == "command_agent" and response_plan is not None:
                cmds: List[CommandSuggestion] = await self.command_agent.run(response_plan)  # type: ignore[arg-type]
                for c in cmds:
                    self.commands_repo.save(response_plan.incident_id, c)
