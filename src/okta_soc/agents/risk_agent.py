from typing import Tuple
from .base import BaseAgent
from okta_soc.core.models import DetectionFinding, RiskScore, Severity
from okta_soc.core.llm import LLMClient


class LLMRiskAgent(BaseAgent):
    name = "risk_agent"

    def __init__(self, llm: LLMClient, promotion_threshold: float = 0.6):
        self.llm = llm
        self.promotion_threshold = promotion_threshold

    async def run(self, finding: DetectionFinding) -> Tuple[RiskScore, bool]:
        system_prompt = (
            "You are a security risk analyst for Okta authentication events. "
            "Given a detection finding, you assign severity, likelihood, impact, "
            "and a numeric risk score between 0 and 1."
        )

        user_prompt = f"""
DetectionFinding (JSON):
{finding.model_dump_json(indent=2)}

Your job:
1. Decide severity: low, medium, high, or critical.
2. Estimate likelihood and impact (0.0–1.0).
3. Compute an overall risk score (0.0–1.0).
4. Explain your reasoning briefly.

Return ONLY JSON:
{{
  "severity": "low|medium|high|critical",
  "likelihood": 0.0,
  "impact": 0.0,
  "score": 0.0,
  "rationale": "string"
}}
"""

        result = self.llm.chat_json(system_prompt, user_prompt)

        severity = Severity(result["severity"].lower())
        risk = RiskScore(
            finding_id=finding.id,
            severity=severity,
            likelihood=float(result["likelihood"]),
            impact=float(result["impact"]),
            score=float(result["score"]),
            rationale=result["rationale"],
        )

        # 🔑 Promotion logic:
        # - promote if score >= threshold
        # - OR if the model says severity is high/critical
        promote = (
            risk.score >= self.promotion_threshold
            or severity in {Severity.HIGH, Severity.CRITICAL}
        )

        return risk, promote
