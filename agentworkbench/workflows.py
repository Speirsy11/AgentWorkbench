from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKBENCH_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATES_DIR = WORKBENCH_DIR / "templates"


@dataclass(frozen=True)
class AgentRole:
    id: str
    name: str
    prompt: str
    goal: str = ""


@dataclass(frozen=True)
class WorkflowTemplate:
    id: str
    name: str
    description: str
    roles: list[AgentRole]
    flow: list[str]
    default_data_files: list[str]
    legacy_runner: str | None = None

    @property
    def role_map(self) -> dict[str, AgentRole]:
        return {role.id: role for role in self.roles}


def _template_from_dict(raw: dict[str, Any]) -> WorkflowTemplate:
    roles = [AgentRole(**role) for role in raw.get("roles", [])]
    return WorkflowTemplate(
        id=raw["id"],
        name=raw["name"],
        description=raw.get("description", ""),
        roles=roles,
        flow=raw.get("flow", [role.id for role in roles]),
        default_data_files=raw.get("default_data_files", []),
        legacy_runner=raw.get("legacy_runner"),
    )


def load_workflow(path_or_id: str, templates_dir: Path = DEFAULT_TEMPLATES_DIR) -> WorkflowTemplate:
    path = Path(path_or_id)
    if not path.exists():
        path = templates_dir / f"{path_or_id}.json"
    if not path.exists():
        available = ", ".join(template.id for template in list_workflows(templates_dir))
        raise FileNotFoundError(f"Workflow '{path_or_id}' not found. Available: {available}")
    return _template_from_dict(json.loads(path.read_text()))


def list_workflows(templates_dir: Path = DEFAULT_TEMPLATES_DIR) -> list[WorkflowTemplate]:
    workflows: list[WorkflowTemplate] = []
    for path in sorted(templates_dir.glob("*.json")):
        workflows.append(_template_from_dict(json.loads(path.read_text())))
    return workflows
