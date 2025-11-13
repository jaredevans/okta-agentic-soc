from typing import List
from .base import BaseAgent
from okta_soc.core.models import OktaEvent, DetectionFinding
from okta_soc.detectors.registry import get_all_detectors


class DetectorAgent(BaseAgent):
    name = "detector_agent"

    async def run(self, events: List[OktaEvent]) -> List[DetectionFinding]:
        findings: List[DetectionFinding] = []
        for detector in get_all_detectors():
            findings.extend(detector.detect(events))
        return findings
