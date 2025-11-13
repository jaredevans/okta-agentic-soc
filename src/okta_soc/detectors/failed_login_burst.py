from datetime import timedelta
from typing import List
import uuid

from okta_soc.core.models import OktaEvent, DetectionFinding, FindingType
from .base import BaseDetector


class FailedLoginBurstDetector(BaseDetector):
    name = "failed_login_burst"

    def __init__(self, threshold: int = 5, window_minutes: int = 10):
        self.threshold = threshold
        self.window = timedelta(minutes=window_minutes)

    def detect(self, events: List[OktaEvent]) -> List[DetectionFinding]:
        findings: List[DetectionFinding] = []
        events_by_actor: dict[str, List[OktaEvent]] = {}
        for e in events:
            if not e.actor_id:
                continue
            if e.outcome != "FAILURE":
                continue
            events_by_actor.setdefault(e.actor_id, []).append(e)

        for actor_id, evs in events_by_actor.items():
            evs_sorted = sorted(evs, key=lambda e: e.timestamp)
            start_idx = 0
            while start_idx < len(evs_sorted):
                window_events = [evs_sorted[start_idx]]
                j = start_idx + 1
                while j < len(evs_sorted) and (evs_sorted[j].timestamp - evs_sorted[start_idx].timestamp) <= self.window:
                    window_events.append(evs_sorted[j])
                    j += 1
                if len(window_events) >= self.threshold:
                    finding = DetectionFinding(
                        id=str(uuid.uuid4()),
                        finding_type=FindingType.FAILED_LOGIN_BURST,
                        description=f"{len(window_events)} failed logins for actor {actor_id} within {self.window}.",
                        okta_event_ids=[e.id for e in window_events],
                        user_id=actor_id,
                        created_at=window_events[-1].timestamp,
                        metadata={
                            "count": len(window_events),
                            "window_seconds": self.window.total_seconds(),
                        },
                    )
                    findings.append(finding)
                start_idx += 1
        return findings
