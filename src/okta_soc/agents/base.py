from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentContract:
    name: str
    description: str
    consumes: List[str]           # Data type keys this agent reads from PipelineContext
    produces: List[str]           # Data type keys this agent writes to PipelineContext
    phase_hint: str               # "ingest", "analysis", "response" — advisory
    side_effects: List[str] = field(default_factory=list)
    requires_human_approval: bool = False


class BaseAgent(ABC):
    contract: AgentContract

    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Receive input keyed by type name (from contract.consumes).
        Return output keyed by type name (from contract.produces).
        """
        ...
