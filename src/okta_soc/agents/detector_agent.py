from typing import Any, Dict, List
from .base import BaseAgent, AgentContract
from okta_soc.core.models import OktaEvent, DetectionFinding
from okta_soc.detectors.registry import get_all_detectors


class DetectorAgent(BaseAgent):
    contract = AgentContract(
        name="detector_agent",
        description="Analyzes Okta events to detect anomalies like impossible travel, "
        "failed-login bursts, and MFA fatigue. Produces DetectionFindings.",
        consumes=["List[OktaEvent]"],
        produces=["List[DetectionFinding]"],
        phase_hint="ingest",
    )

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        events = [OktaEvent.model_validate(e) if isinstance(e, dict) else e
                  for e in input_data["List[OktaEvent]"]]
        findings: List[DetectionFinding] = []
        for detector in get_all_detectors():
            findings.extend(detector.detect(events))
        return {"List[DetectionFinding]": findings}
