from typing import Any, Dict
from .base import BaseAgent, AgentContract
from okta_soc.core.models import DetectionFinding, RiskScore, Severity, SecurityIncident
from okta_soc.core.llm import LLMClient
from datetime import datetime, timezone
import uuid


class LLMRiskAgent(BaseAgent):
    contract = AgentContract(
        name="risk_agent",
        description="Assigns severity and risk scores to DetectionFindings, "
        "deciding how serious each one is. Promotes high-risk findings to SecurityIncidents.",
        consumes=["DetectionFinding"],
        produces=["RiskScore", "SecurityIncident"],
        phase_hint="analysis",
    )

    def __init__(self, llm: LLMClient, promotion_threshold: float = 0.6):
        self.llm = llm
        self.promotion_threshold = promotion_threshold

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        finding = input_data["DetectionFinding"]
        if isinstance(finding, dict):
            finding = DetectionFinding.model_validate(finding)

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
2. Estimate likelihood and impact (0.0-1.0).
3. Compute an overall risk score (0.0-1.0).
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

        promote = (
            risk.score >= self.promotion_threshold
            or severity in {Severity.HIGH, Severity.CRITICAL}
        )

        outputs: Dict[str, Any] = {"RiskScore": risk}

        if promote:
            incident = SecurityIncident(
                id=str(uuid.uuid4()),
                finding_id=finding.id,
                title=f"Incident from {finding.finding_type.value}",
                description=finding.description,
                severity=risk.severity,
                risk_score=risk.score,
                created_at=datetime.now(timezone.utc),
                status="open",
                metadata={
                    "finding_type": finding.finding_type.value,
                    **finding.metadata,
                },
            )
            outputs["SecurityIncident"] = incident

        return outputs
