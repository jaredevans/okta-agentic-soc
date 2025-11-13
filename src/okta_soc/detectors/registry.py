from typing import List
from .base import BaseDetector
from .impossible_travel import ImpossibleTravelDetector
from .failed_login_burst import FailedLoginBurstDetector


def get_all_detectors() -> List[BaseDetector]:
    return [
        ImpossibleTravelDetector(),
        FailedLoginBurstDetector(),
    ]
