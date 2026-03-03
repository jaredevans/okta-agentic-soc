from okta_soc.core.pipeline_context import PipelineContext, StepResult


def test_pipeline_context_creation():
    ctx = PipelineContext(
        data={"List[OktaEvent]": [{"id": "1"}]},
        metadata={"run_id": "abc", "source": "demo"},
    )
    assert "List[OktaEvent]" in ctx.data
    assert ctx.metadata["run_id"] == "abc"
    assert ctx.history == []


def test_pipeline_context_available_types():
    ctx = PipelineContext(
        data={"List[OktaEvent]": [], "List[DetectionFinding]": []},
        metadata={},
    )
    assert set(ctx.available_types()) == {"List[OktaEvent]", "List[DetectionFinding]"}


def test_step_result():
    result = StepResult(agent="detector_agent", outputs=["List[DetectionFinding]"])
    assert result.agent == "detector_agent"
    assert result.outputs == ["List[DetectionFinding]"]
