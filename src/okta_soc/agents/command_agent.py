from typing import Any, Dict, List, Optional
from .base import BaseAgent, AgentContract
from okta_soc.core.models import ResponsePlan, CommandSuggestion
from okta_soc.core.config import load_settings


class CommandAgent(BaseAgent):
    contract = AgentContract(
        name="command_agent",
        description="Generates read-only curl commands from a ResponsePlan "
        "for a human analyst to review and execute.",
        consumes=["ResponsePlan"],
        produces=["List[CommandSuggestion]"],
        phase_hint="response",
    )

    def __init__(self, okta_org_url: Optional[str] = None):
        settings = load_settings()
        self.okta_org_url = (okta_org_url or settings.okta_org_url).rstrip("/")

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        plan = input_data["ResponsePlan"]
        if isinstance(plan, dict):
            plan = ResponsePlan.model_validate(plan)

        suggestions: List[CommandSuggestion] = []

        for step in plan.steps:
            sid = step.step_id

            if sid == "lock_account":
                cmd = (
                    "curl -X POST "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/lifecycle/suspend "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json' "
                    "-H 'Content-Type: application/json'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Suspend the Okta user account.",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Replace {userId} and token before running.",
                    )
                )

            elif sid == "force_password_reset":
                cmd = (
                    "curl -X POST "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/lifecycle/reset_password?sendEmail=true "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json' "
                    "-H 'Content-Type: application/json'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Force user password reset and send email.",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Replace {userId} and token before running.",
                    )
                )

            elif sid == "revoke_sessions":
                cmd = (
                    "curl -X DELETE "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/sessions "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Revoke all active sessions for the user.",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Replace {userId} and token before running.",
                    )
                )

            elif sid == "enable_mfa":
                cmd = (
                    "# Example: enroll an MFA factor for the user via Okta API\n"
                    "curl -X POST "
                    f"{self.okta_org_url}/api/v1/users/{{userId}}/factors "
                    "-H 'Authorization: SSWS <REDACTED_TOKEN>' "
                    "-H 'Accept: application/json' "
                    "-H 'Content-Type: application/json' "
                    "-d '{\"factorType\": \"token:software:totp\", \"provider\": \"OKTA\"}'"
                )
                suggestions.append(
                    CommandSuggestion(
                        step_id=sid,
                        description="Enable MFA for the user (template, adjust factorType/provider).",
                        command=cmd,
                        system="okta_api",
                        read_only=True,
                        notes="Adjust factorType/provider and {userId} before running.",
                    )
                )

        return {"List[CommandSuggestion]": suggestions}
