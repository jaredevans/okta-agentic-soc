from datetime import timedelta
from typing import List
import uuid

from okta_soc.core.models import OktaEvent, DetectionFinding, FindingType
from .base import BaseDetector


class ImpossibleTravelDetector(BaseDetector):
    name = "impossible_travel"

    def detect(self, events: List[OktaEvent]) -> List[DetectionFinding]:
        findings: List[DetectionFinding] = []
        events_by_actor: dict[str, List[OktaEvent]] = {}
        for e in events:
            if not e.actor_id:
                continue
            events_by_actor.setdefault(e.actor_id, []).append(e)

        for actor_id, evs in events_by_actor.items():
            evs_sorted = sorted(evs, key=lambda e: e.timestamp)
            for i in range(len(evs_sorted) - 1):
                a = evs_sorted[i]
                b = evs_sorted[i + 1]
                if not a.country or not b.country:
                    continue
                if a.country == b.country:
                    continue
                dt = b.timestamp - a.timestamp
                if dt < timedelta(hours=1):
                    finding = DetectionFinding(
                        id=str(uuid.uuid4()),
                        finding_type=FindingType.IMPOSSIBLE_TRAVEL,
                        description=(
                            f"Possible impossible travel for actor {actor_id}: "
                            f"{a.country} -> {b.country} within {dt}."
                        ),
                        okta_event_ids=[a.id, b.id],
                        user_id=actor_id,
                        created_at=b.timestamp,
                        metadata={
                            "from_country": a.country,
                            "to_country": b.country,
                            "time_delta_seconds": dt.total_seconds(),
                        },
                    )
                    findings.append(finding)
        return findings
