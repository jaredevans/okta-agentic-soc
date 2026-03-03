from okta_soc.core.router_models import RoutePlan, RouteStep


def test_route_step_without_iterate():
    step = RouteStep(agent_name="detector_agent", reason="Detect anomalies")
    assert step.iterate_over is None


def test_route_step_with_iterate():
    step = RouteStep(
        agent_name="risk_agent",
        reason="Score each finding",
        iterate_over="List[DetectionFinding]",
    )
    assert step.iterate_over == "List[DetectionFinding]"


def test_route_plan_no_phase_required():
    """Phase is no longer required — the LLM plan is just steps."""
    plan = RoutePlan(
        steps=[
            RouteStep(agent_name="detector_agent", reason="detect"),
            RouteStep(agent_name="risk_agent", reason="score", iterate_over="List[DetectionFinding]"),
        ],
        notes="test plan",
    )
    assert len(plan.steps) == 2
    assert plan.steps[1].iterate_over == "List[DetectionFinding]"
