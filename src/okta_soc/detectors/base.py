from abc import ABC, abstractmethod
from typing import List
from okta_soc.core.models import OktaEvent, DetectionFinding


class BaseDetector(ABC):
    name: str

    @abstractmethod
    def detect(self, events: List[OktaEvent]) -> List[DetectionFinding]:
        ...
