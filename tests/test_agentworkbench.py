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


from agentworkbench.repository_snapshot import create_repository_snapshot


def test_code_review_workflow_loads():
    workflow = load_workflow("code_review_board")
    assert workflow.id == "code_review_board"
    assert workflow.flow[-2:] == ["fix_prompt_writer", "review_chair"]


def test_repository_snapshot_excludes_secrets(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo")
    (repo / "app.py").write_text("print('hello')")
    (repo / ".env").write_text("SECRET=do-not-include")
    snapshot = create_repository_snapshot(repo, max_bytes=10_000)
    assert snapshot.pull_request is None
    assert "app.py" in snapshot.content
    assert "SECRET=do-not-include" not in snapshot.content
    assert snapshot.files_included >= 2


def test_repository_snapshot_formats_pr_url(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo")
    snapshot = create_repository_snapshot(
        repo,
        pr="https://github.com/example/demo/pull/42",
        max_bytes=10_000,
    )
    assert snapshot.pull_request == "example/demo#42"
    assert "Pull request snapshot" in snapshot.content
