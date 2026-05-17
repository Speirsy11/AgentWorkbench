from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from .runner import RUNS_DIR, run_workflow
from .web import serve
from .workflows import list_workflows

app = typer.Typer(
    name="AgentWorkbench",
    help="Configurable multi-agent workflows for analysing anything with the right roles and data pack.",
)


@app.command()
def workflows() -> None:
    """List available workflow templates."""
    for workflow in list_workflows():
        typer.echo(f"{workflow.id}\t{workflow.name}\t{workflow.description}")


@app.command()
def run(
    subject: str = typer.Argument(..., help="Thing to analyse, e.g. BTC-USD, a repo, a business idea."),
    objective: str = typer.Option("Produce a decision-ready analysis.", "--objective", "-o"),
    workflow: str = typer.Option("general_research", "--workflow", "-w"),
    data_file: Optional[List[Path]] = typer.Option(None, "--data-file", "-d"),
    repo_path: Optional[Path] = typer.Option(None, "--repo-path", "-r", help="Local repository to snapshot and include as the data pack."),
    pr: Optional[str] = typer.Option(None, "--pr", help="GitHub pull request number or URL to include via gh pr view/diff. Requires --repo-path."),
    max_repo_bytes: int = typer.Option(180_000, "--max-repo-bytes", help="Maximum bytes from the repository snapshot."),
    llm_provider: str = typer.Option("codex", "--llm-provider"),
    model: str = typer.Option("default", "--model"),
) -> None:
    """Run a configurable workflow once and write a report."""
    payload = run_workflow(
        workflow,
        subject=subject,
        objective=objective,
        data_files=[str(path) for path in data_file] if data_file else None,
        repo_path=str(repo_path) if repo_path else None,
        pr=pr,
        max_repo_bytes=max_repo_bytes,
        llm_provider=llm_provider,
        model=model,
    )
    typer.echo(f"Run complete: {payload.get('id', subject)}")
    if "id" in payload:
        typer.echo(f"Report: {RUNS_DIR / payload['id'] / 'report.md'}")


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Start the lightweight AgentWorkbench web UI."""
    serve(host=host, port=port)


if __name__ == "__main__":
    app()
