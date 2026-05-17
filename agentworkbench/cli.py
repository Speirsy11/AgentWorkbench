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
    llm_provider: str = typer.Option("codex", "--llm-provider"),
    model: str = typer.Option("default", "--model"),
) -> None:
    """Run a configurable workflow once and write a report."""
    payload = run_workflow(
        workflow,
        subject=subject,
        objective=objective,
        data_files=[str(path) for path in data_file] if data_file else None,
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
