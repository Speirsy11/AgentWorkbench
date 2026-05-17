from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients.factory import create_llm_client

from .repository_snapshot import create_repository_snapshot
from .workflows import WorkflowTemplate, load_workflow

WORKBENCH_HOME = Path(os.getenv("AGENTWORKBENCH_HOME", Path.home() / ".agentworkbench"))
RUNS_DIR = Path(os.getenv("AGENTWORKBENCH_RUNS_DIR", WORKBENCH_HOME / "runs"))


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return cleaned or "run"


def _message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    return str(content)


def load_data_pack(files: list[str], base_dir: Path | None = None) -> str:
    base_dir = base_dir or Path.cwd()
    sections: list[str] = []
    for item in files:
        path = Path(item)
        if not path.is_absolute():
            # Prefer caller cwd, then package-provided data packs.
            candidate = base_dir / path
            path = candidate if candidate.exists() else Path(__file__).resolve().parent / path
        if path.is_dir():
            for child in sorted(path.glob("**/*")):
                if child.is_file():
                    sections.append(f"# {child.name}\n{child.read_text(errors='replace')}")
        elif path.exists():
            sections.append(f"# {path.name}\n{path.read_text(errors='replace')}")
        else:
            raise FileNotFoundError(f"Data file not found: {item}")
    return "\n\n---\n\n".join(sections)


def build_prompt(
    *,
    role_name: str,
    role_goal: str,
    role_prompt: str,
    subject: str,
    objective: str,
    data_pack: str,
    prior_outputs: list[dict[str, str]],
) -> str:
    prior = "\n\n".join(
        f"## {entry['role']}\n{entry['output']}" for entry in prior_outputs
    ) or "No prior role outputs yet."
    return f"""You are {role_name} in a configurable multi-agent analysis workflow.

Role goal:
{role_goal or 'Complete your assigned analysis role clearly and usefully.'}

Role instructions:
{role_prompt}

Thing being analysed:
{subject}

Overall objective:
{objective}

Available data pack:
{data_pack or 'No external data pack was provided. Make uncertainty explicit.'}

Prior role outputs:
{prior}

Return a concise, structured markdown response for your role. Do not invent data; flag missing inputs explicitly.
"""


def run_generic_workflow(
    workflow: WorkflowTemplate,
    *,
    subject: str,
    objective: str,
    data_files: list[str] | None = None,
    repo_path: str | None = None,
    pr: str | None = None,
    max_repo_bytes: int = 180_000,
    llm_provider: str = "codex",
    model: str = "default",
    output_dir: Path = RUNS_DIR,
    llm: Any | None = None,
) -> dict[str, Any]:
    data_files = data_files if data_files is not None else workflow.default_data_files
    data_pack_parts: list[str] = []
    source_metadata: dict[str, Any] = {}
    if data_files:
        data_pack_parts.append(load_data_pack(data_files))
    if repo_path:
        snapshot = create_repository_snapshot(repo_path, pr=pr, max_bytes=max_repo_bytes)
        data_pack_parts.append(snapshot.content)
        source_metadata["repository_snapshot"] = snapshot.metadata()
    data_pack = "\n\n---\n\n".join(part for part in data_pack_parts if part)
    role_map = workflow.role_map
    llm = llm or create_llm_client(llm_provider, model).get_llm()

    outputs: list[dict[str, str]] = []
    for role_id in workflow.flow:
        role = role_map[role_id]
        prompt = build_prompt(
            role_name=role.name,
            role_goal=role.goal,
            role_prompt=role.prompt,
            subject=subject,
            objective=objective,
            data_pack=data_pack,
            prior_outputs=outputs,
        )
        result = llm.invoke(prompt)
        outputs.append({"role": role.name, "role_id": role.id, "output": _message_content(result)})

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{_safe_id(workflow.id)}-{_safe_id(subject)[:40]}"
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workflow": asdict(workflow),
        "subject": subject,
        "objective": objective,
        "data_files": data_files,
        "repo_path": repo_path,
        "pull_request": pr,
        "source_metadata": source_metadata,
        "llm_provider": llm_provider,
        "model": model,
        "outputs": outputs,
    }
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2))
    (run_dir / "report.md").write_text(render_report(payload))
    return payload


def run_legacy_tradingagents(
    *,
    ticker: str,
    analysis_date: str,
    llm_provider: str = "codex",
    model: str = "default",
    selected_analysts: list[str] | None = None,
) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config.update({
        "llm_provider": llm_provider,
        "quick_think_llm": model,
        "deep_think_llm": model,
    })
    graph = TradingAgentsGraph(
        selected_analysts=selected_analysts or ["market", "social", "news", "fundamentals"],
        debug=False,
        config=config,
    )
    _, decision = graph.propagate(ticker, analysis_date)
    return {"ticker": ticker, "analysis_date": analysis_date, "decision": decision}


def run_workflow(
    workflow_id_or_path: str,
    *,
    subject: str,
    objective: str,
    data_files: list[str] | None = None,
    repo_path: str | None = None,
    pr: str | None = None,
    max_repo_bytes: int = 180_000,
    llm_provider: str = "codex",
    model: str = "default",
    output_dir: Path = RUNS_DIR,
) -> dict[str, Any]:
    workflow = load_workflow(workflow_id_or_path)
    if workflow.legacy_runner == "tradingagents":
        return run_legacy_tradingagents(
            ticker=subject,
            analysis_date=datetime.now(timezone.utc).date().isoformat(),
            llm_provider=llm_provider,
            model=model,
        )
    return run_generic_workflow(
        workflow,
        subject=subject,
        objective=objective,
        data_files=data_files,
        repo_path=repo_path,
        pr=pr,
        max_repo_bytes=max_repo_bytes,
        llm_provider=llm_provider,
        model=model,
        output_dir=output_dir,
    )


def render_report(run: dict[str, Any]) -> str:
    lines = [
        f"# {run['workflow']['name']}: {run['subject']}",
        "",
        f"Objective: {run['objective']}",
        f"Created: {run['created_at']}",
        "",
    ]
    source_metadata = run.get("source_metadata") or {}
    repo_snapshot = (
        source_metadata.get("repository_snapshot")
        if isinstance(source_metadata, dict)
        else None
    )
    if repo_snapshot:
        lines.extend([
            "## Review input",
            "",
            f"- Repository: `{repo_snapshot.get('repo_path')}`",
            f"- Git HEAD: `{repo_snapshot.get('git_head') or 'unknown'}`",
            *([f"- Pull request: `{repo_snapshot.get('pull_request')}`"] if repo_snapshot.get("pull_request") else []),
            f"- Files included: {repo_snapshot.get('files_included')} / {repo_snapshot.get('total_files_seen')}",
            f"- Snapshot bytes: {repo_snapshot.get('bytes_included')}",
            f"- Truncated: {repo_snapshot.get('truncated')}",
            "",
        ])
    for output in run["outputs"]:
        lines.extend([f"## {output['role']}", "", output["output"], ""])
    return "\n".join(lines)


def list_runs(runs_dir: Path = RUNS_DIR) -> list[dict[str, Any]]:
    if not runs_dir.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(runs_dir.glob("*/run.json"), reverse=True):
        try:
            raw = json.loads(path.read_text())
            runs.append({
                "id": raw["id"],
                "created_at": raw.get("created_at"),
                "workflow": raw.get("workflow", {}).get("name"),
                "subject": raw.get("subject"),
                "report_path": str(path.parent / "report.md"),
            })
        except Exception:
            continue
    return runs
