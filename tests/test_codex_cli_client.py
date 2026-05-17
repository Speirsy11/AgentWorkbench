from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.llm_clients.codex_cli_client import CodexCLIChatModel
from tradingagents.llm_clients.factory import create_llm_client


def test_factory_creates_codex_cli_client():
    client = create_llm_client("codex", "gpt-5.1-codex")
    assert client.__class__.__name__ == "CodexCLIClient"


def test_codex_cli_invokes_exec_with_prompt_on_stdin(tmp_path: Path):
    log = tmp_path / "argv.txt"
    fake = tmp_path / "codex"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "prompt = sys.stdin.read()\n"
        f"pathlib.Path({str(log)!r}).write_text('ARGV\\n' + '\\n'.join(sys.argv[1:]) + '\\nPROMPT\\n' + prompt)\n"
        "print('codex response')\n"
    )
    fake.chmod(0o755)

    llm = CodexCLIChatModel("test-model", codex_command=str(fake), timeout=5)
    result = llm.invoke([
        SystemMessage(content="Be concise."),
        HumanMessage(content="Say hello."),
    ])

    assert result.content == "codex response"
    argv = log.read_text()
    assert "exec" in argv
    assert "--skip-git-repo-check" in argv
    assert "--model\ntest-model" in argv
    assert argv.split("PROMPT\n", 1)[1].startswith("System:\nBe concise.")
    assert "User:\nSay hello." in argv
    assert result.tool_calls == []
