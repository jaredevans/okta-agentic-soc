import json
from pathlib import Path
from typing import Iterable

from datetime import datetime, timezone

from okta_soc.core.models import (
    DetectionFinding,
    SecurityIncident,
    ResponsePlan,
    CommandSuggestion,
    RiskScore,
)


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


class FindingsRepo:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "findings.jsonl"

    def save(self, finding: DetectionFinding) -> None:
        with self.path.open("a") as f:
            f.write(finding.model_dump_json() + "\n")


class IncidentsRepo:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "incidents.jsonl"

    def save(self, incident: SecurityIncident) -> None:
        with self.path.open("a") as f:
            f.write(incident.model_dump_json() + "\n")

    def create_from_finding(
        self,
        finding: DetectionFinding,
        risk: RiskScore,
    ) -> SecurityIncident:
        import uuid

        incident = SecurityIncident(
            id=str(uuid.uuid4()),
            finding_id=finding.id,
            title=f"Incident from {finding.finding_type.value}",
            description=finding.description,
            severity=risk.severity,
            risk_score=risk.score,
            # ✅ timezone-aware UTC
            created_at=datetime.now(timezone.utc),
            status="open",
            metadata={
                "finding_type": finding.finding_type.value,
                **finding.metadata,
            },
        )
        self.save(incident)
        return incident

    def load_all(self) -> Iterable[SecurityIncident]:
        if not self.path.exists():
            return []
        incidents: list[SecurityIncident] = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                incidents.append(SecurityIncident.model_validate_json(line))
        return incidents


class PlansRepo:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "plans.jsonl"

    def save(self, plan: ResponsePlan) -> None:
        with self.path.open("a") as f:
            f.write(plan.model_dump_json() + "\n")


class CommandsRepo:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "commands.jsonl"

    def save(self, incident_id: str, command: CommandSuggestion) -> None:
        record = {
            "incident_id": incident_id,
            "command": command.model_dump(),
        }
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")
