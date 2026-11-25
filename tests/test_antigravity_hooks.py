"""Tests for Antigravity SessionStart hooks in project-harness and factor-harness."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK_PLUGINS = ("project-harness", "factor-harness")


def _clean_env(**extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_PLUGIN_ROOT", "CURSOR_PLUGIN_ROOT", "COPILOT_CLI", "ANTIGRAVITY_AGENT")
    }
    env.update(extra)
    return env


@pytest.mark.parametrize("plugin", HOOK_PLUGINS)
def test_antigravity_hooks_json_matches_source_and_contract(plugin: str) -> None:
    pdir = ROOT / "plugins" / plugin
    src = json.loads((pdir / "hooks" / "antigravity-hooks.json").read_text())
    rendered = json.loads((pdir / "hooks.json").read_text())
    assert rendered == src

    assert len(rendered) == 1
    group_name, group = next(iter(rendered.items()))
    assert group_name == f"{plugin}-session-start"
    handlers = group["SessionStart"]
    assert isinstance(handlers, list) and len(handlers) == 1
    cmd = handlers[0]["command"]
    assert cmd.startswith("./hooks/")
    assert "${" not in cmd  # Antigravity plugin hooks use cwd=<plugin-root>, not ${PLUGIN_ROOT}


@pytest.mark.parametrize("plugin", HOOK_PLUGINS)
def test_antigravity_session_start_hook_executes_from_plugin_root(plugin: str) -> None:
    pdir = ROOT / "plugins" / plugin
    rendered = json.loads((pdir / "hooks.json").read_text())
    cmd = next(iter(rendered.values()))["SessionStart"][0]["command"]

    proc = subprocess.run(
        ["sh", "-c", cmd],
        cwd=pdir,
        input='{"conversationId": "test-conv", "workspacePaths": ["/work/demo"]}',
        capture_output=True,
        text=True,
        env=_clean_env(),
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    steps = payload["injectSteps"]
    assert isinstance(steps, list) and len(steps) == 1
    msg = steps[0]["systemMessage"]["systemMessage"]
    assert f"using-{plugin}" in msg
    assert "<EXTREMELY_IMPORTANT>" in msg


@pytest.mark.parametrize("plugin", HOOK_PLUGINS)
def test_session_start_preserves_claude_cursor_and_env_antigravity_formats(plugin: str) -> None:
    script = ROOT / "plugins" / plugin / "hooks" / "session-start"

    agy_env = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=_clean_env(ANTIGRAVITY_AGENT="1"),
        timeout=15,
    )
    assert agy_env.returncode == 0, agy_env.stderr
    assert "injectSteps" in json.loads(agy_env.stdout)

    claude_env = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=_clean_env(CLAUDE_PLUGIN_ROOT=str(ROOT / "plugins" / plugin)),
        timeout=15,
    )
    assert claude_env.returncode == 0, claude_env.stderr
    claude_doc = json.loads(claude_env.stdout)
    assert claude_doc["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "additionalContext" in claude_doc["hookSpecificOutput"]

    cursor_env = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=_clean_env(CURSOR_PLUGIN_ROOT=str(ROOT / "plugins" / plugin)),
        timeout=15,
    )
    assert cursor_env.returncode == 0, cursor_env.stderr
    assert "additional_context" in json.loads(cursor_env.stdout)
