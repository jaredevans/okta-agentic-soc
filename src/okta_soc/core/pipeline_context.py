from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StepResult:
    agent: str
    outputs: List[str]


@dataclass
class PipelineContext:
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    history: List[StepResult] = field(default_factory=list)

    def available_types(self) -> List[str]:
        return list(self.data.keys())
