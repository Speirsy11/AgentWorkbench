"""LangChain-compatible client backed by the local Codex CLI.

This provider is intended for users who have authenticated the Codex CLI with
their OpenAI account/subscription and do not want to provide an API key to
TradingAgents. It shells out to ``codex exec`` for each LLM invocation.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable

from .base_client import BaseLLMClient


_DEFAULT_TIMEOUT_SECONDS = 300


def _message_role(message: BaseMessage) -> str:
    msg_type = getattr(message, "type", "message")
    return {
        "system": "System",
        "human": "User",
        "ai": "Assistant",
        "tool": "Tool",
    }.get(msg_type, msg_type.title())


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def _input_to_prompt(input_: Any) -> str:
    """Render common LangChain input shapes into a plain prompt."""
    if hasattr(input_, "to_messages"):
        input_ = input_.to_messages()

    if isinstance(input_, list):
        rendered: list[str] = []
        for message in input_:
            if isinstance(message, BaseMessage):
                content = _stringify_content(message.content).strip()
                if content:
                    rendered.append(f"{_message_role(message)}:\n{content}")
            else:
                text = str(message).strip()
                if text:
                    rendered.append(text)
        return "\n\n".join(rendered)

    return str(input_)


class CodexCLIChatModel(Runnable[Any, AIMessage]):
    """Small Runnable adapter that invokes ``codex exec`` headlessly."""

    def __init__(
        self,
        model: str,
        *,
        codex_command: str = "codex",
        timeout: int = _DEFAULT_TIMEOUT_SECONDS,
        extra_args: Optional[list[str]] = None,
    ):
        self.model = model
        self.codex_command = codex_command
        self.timeout = timeout
        self.extra_args = extra_args or []

    def bind_tools(self, tools: Any, **kwargs: Any) -> "CodexCLIChatModel":
        # Codex CLI does not expose LangChain tool-calling semantics. Returning
        # self lets analyst agents produce a best-effort report without tool
        # calls instead of failing at graph construction time.
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Codex CLI provider does not support structured output")

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> AIMessage:
        prompt = _input_to_prompt(input)
        command = [
            self.codex_command,
            "exec",
            "--skip-git-repo-check",
            "--color",
            "never",
            *self.extra_args,
            "-",
        ]
        if self.model not in {"default", "codex-default", ""}:
            command[-1:-1] = ["--model", self.model]
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Codex CLI executable not found. Install/authenticate Codex CLI, "
                "or set TRADINGAGENTS_CODEX_COMMAND to its path."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Codex CLI timed out after {self.timeout}s while running headlessly."
            ) from exc

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise RuntimeError(
                f"Codex CLI exited with status {completed.returncode}: {stderr}"
            )

        return AIMessage(content=completed.stdout.strip())


class CodexCLIClient(BaseLLMClient):
    """Client that uses an authenticated local Codex CLI instead of an API key."""

    def get_llm(self) -> Any:
        command = self.kwargs.get("codex_command") or os.getenv(
            "TRADINGAGENTS_CODEX_COMMAND", "codex"
        )
        timeout = int(
            self.kwargs.get("timeout")
            or os.getenv("TRADINGAGENTS_CODEX_TIMEOUT", _DEFAULT_TIMEOUT_SECONDS)
        )
        extra = shlex.split(os.getenv("TRADINGAGENTS_CODEX_EXTRA_ARGS", ""))

        # Fail early with a clear message before the graph starts doing work.
        if shutil.which(command) is None:
            raise RuntimeError(
                "Codex CLI executable not found. Install/authenticate Codex CLI, "
                "or set TRADINGAGENTS_CODEX_COMMAND to its path."
            )

        return CodexCLIChatModel(
            self.model,
            codex_command=command,
            timeout=timeout,
            extra_args=extra,
        )

    def validate_model(self) -> bool:
        return True
