from agentworkbench.runner import run_generic_workflow
from agentworkbench.workflows import load_workflow


class FakeLLM:
    def invoke(self, prompt):
        class Response:
            content = "fake role output"
        assert "Thing being analysed" in prompt
        return Response()


def test_loads_general_workflow():
    workflow = load_workflow("general_research")
    assert workflow.id == "general_research"
    assert workflow.flow == ["analyst", "critic", "decision"]


def test_runs_generic_workflow_with_fake_llm(tmp_path):
    workflow = load_workflow("general_research")
    data_file = tmp_path / "brief.md"
    data_file.write_text("Important facts")
    payload = run_generic_workflow(
        workflow,
        subject="Test subject",
        objective="Test objective",
        data_files=[str(data_file)],
        output_dir=tmp_path / "runs",
        llm=FakeLLM(),
    )
    assert payload["subject"] == "Test subject"
    assert len(payload["outputs"]) == 3
    assert (tmp_path / "runs" / payload["id"] / "report.md").exists()
