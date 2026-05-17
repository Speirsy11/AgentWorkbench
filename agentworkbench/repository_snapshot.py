from __future__ import annotations

import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
    ".openclaw",
}

SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
}

TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".dockerfile",
    ".env.example",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lock",
    ".md",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

PRIORITY_NAMES = {
    "README.md",
    "pyproject.toml",
    "package.json",
    "pnpm-workspace.yaml",
    "tsconfig.json",
    "vite.config.ts",
    "next.config.ts",
    "Dockerfile",
    "docker-compose.yml",
}


@dataclass(frozen=True)
class RepositorySnapshot:
    repo_path: str
    git_head: str | None
    total_files_seen: int
    files_included: int
    bytes_included: int
    truncated: bool
    content: str

    def metadata(self) -> dict[str, object]:
        raw = asdict(self)
        raw.pop("content", None)
        return raw


def _git(repo: Path, args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=repo, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _candidate_files(repo: Path) -> list[Path]:
    git_files = _git(repo, ["ls-files"])
    if git_files:
        paths = [repo / line for line in git_files.splitlines() if line.strip()]
    else:
        paths = [p for p in repo.rglob("*") if p.is_file()]
    return sorted((p for p in paths if _is_allowed(repo, p)), key=_sort_key)


def _is_allowed(repo: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(repo)
    except ValueError:
        return False
    parts = set(rel.parts)
    if parts & DEFAULT_EXCLUDES:
        return False
    if path.name in SECRET_NAMES:
        return False
    if path.name.endswith((".pem", ".key", ".p12", ".sqlite", ".db")):
        return False
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz", ".mp4", ".mov"}:
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in PRIORITY_NAMES or path.name.startswith("Dockerfile")


def _sort_key(path: Path) -> tuple[int, int, str]:
    priority = 0 if path.name in PRIORITY_NAMES else 1
    depth = len(path.parts)
    return (priority, depth, str(path))


def create_repository_snapshot(repo_path: str | Path, *, max_bytes: int = 180_000, max_file_bytes: int = 24_000) -> RepositorySnapshot:
    repo = Path(repo_path).expanduser().resolve()
    if not repo.exists() or not repo.is_dir():
        raise FileNotFoundError(f"Repository path not found: {repo}")

    files = _candidate_files(repo)
    git_head = _git(repo, ["rev-parse", "--short", "HEAD"])
    git_status = _git(repo, ["status", "--short"]) or "clean"
    tree_lines = [str(path.relative_to(repo)) for path in files]

    sections = [
        f"# Repository snapshot\n\nPath: {repo}\nGit HEAD: {git_head or 'unknown'}\nGit status:\n```\n{git_status}\n```",
        "# File tree\n```\n" + "\n".join(tree_lines[:500]) + ("\n..." if len(tree_lines) > 500 else "") + "\n```",
    ]

    used = sum(len(section.encode("utf-8")) for section in sections)
    included = 0
    truncated = False
    for path in files:
        rel = path.relative_to(repo)
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        encoded = text.encode("utf-8")
        file_truncated = False
        if len(encoded) > max_file_bytes:
            text = encoded[:max_file_bytes].decode("utf-8", errors="replace")
            file_truncated = True
        section = f"# File: {rel}\n```\n{text}\n```"
        if file_truncated:
            section += "\n[File truncated for review snapshot]"
        section_bytes = len(section.encode("utf-8"))
        if used + section_bytes > max_bytes:
            truncated = True
            break
        sections.append(section)
        used += section_bytes
        included += 1

    return RepositorySnapshot(
        repo_path=str(repo),
        git_head=git_head,
        total_files_seen=len(files),
        files_included=included,
        bytes_included=used,
        truncated=truncated,
        content="\n\n---\n\n".join(sections),
    )
