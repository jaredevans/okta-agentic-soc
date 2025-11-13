import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List

from okta_soc.core.models import OktaEvent


class OktaClient:
    """
    Demo Okta client that reads events from a local JSON file:

        tests/demo_okta_system_logs.json

    This simulates Okta System Log events for the agentic pipeline.
    """

    def __init__(self, org_url: str, api_token: str):
        self.org_url = org_url.rstrip("/")
        self.api_token = api_token

    async def fetch_events_since(self, since: datetime) -> List[OktaEvent]:
        # Demo mode: ignore the real Okta API, just read from a local file.
        demo_path = Path("tests/demo_okta_system_logs.json")
        if not demo_path.exists():
            return []

        with demo_path.open() as f:
            raw_events = json.load(f)

        events: List[OktaEvent] = []
        for e in raw_events:
            # Parse as aware datetime and normalize to UTC
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            ts_utc = ts.astimezone(timezone.utc)

            # basic filter so you can control window with --hours
            if ts_utc < since:
                continue

            events.append(
                OktaEvent(
                    id=e["id"],
                    event_type=e["event_type"],
                    actor_id=e.get("actor_id"),
                    actor_type=e.get("actor_type"),
                    target_id=e.get("target_id"),
                    ip_address=e.get("ip_address"),
                    user_agent=e.get("user_agent"),
                    city=e.get("city"),
                    country=e.get("country"),
                    outcome=e.get("outcome"),
                    timestamp=ts_utc,
                    raw=e,
                )
            )

        return events
