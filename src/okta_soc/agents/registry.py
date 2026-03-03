from typing import Dict, Optional
from okta_soc.agents.base import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self.agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        name = agent.contract.name
        if name in self.agents:
            raise ValueError(f"Agent '{name}' already registered")
        self.agents[name] = agent

    def get(self, name: str) -> Optional[BaseAgent]:
        return self.agents.get(name)

    def catalog_for_llm(self) -> str:
        lines = []
        for agent in self.agents.values():
            c = agent.contract
            parts = [
                f"- {c.name}: {c.description}",
                f"  Consumes: {', '.join(c.consumes)}",
                f"  Produces: {', '.join(c.produces)}",
                f"  Phase hint: {c.phase_hint}",
            ]
            if c.actions:
                parts.append(f"  Actions: {', '.join(c.actions)}")
            if c.requires_human_approval:
                parts.append("  Requires human approval: yes")
            lines.append("\n".join(parts))
        return "\n\n".join(lines)
