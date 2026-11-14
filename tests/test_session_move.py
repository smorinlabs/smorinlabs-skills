"""Tests for the session-move helper (plugins/session/skills/session-move/scripts/session-move).

Run: uv run pytest tests/test_session_move.py -q
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins" / "session" / "skills"
SCRIPT = SKILLS / "session-move" / "scripts" / "session-move"
SPINOFF = SKILLS / "session-spinoff" / "scripts" / "spinoff-plan"


def load_module(name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


sm = load_module("session_move", SCRIPT)

SESSIONS = [
    {"session_id": "session:aaa", "label": "skills"},
    {"session_id": "session:bbb", "label": "audit"},
    {"session_id": "session:ccc", "label": "dup"},
    {"session_id": "session:ddd", "label": "dup"},
]


def facts(**over) -> dict:
    base = {"self": False, "panes": 1, "source_host": "h1", "server_host": "h1",
            "agent": "claude", "foreground": "claude", "conversation_id": "conv-1",
            "identity_note": "", "status": "idle", "quiet_seconds": None}
    return {**base, **over}


def plan(**over) -> dict:
    base = {
        "self": False, "agent": "claude", "pid": 4242, "conversation_id": "conv-1",
        "cwd": "/work/repo", "transcript": None, "resume_argv": ["claude", "--resume", "conv-1"],
        "source": {"session_id": "session:aaa", "window_id": "window:w1",
                   "label": "security-review", "label_auto": False, "host_id": "h1"},
        "destination": {"exists": True, "session_id": "session:bbb", "label": "audit", "near": []},
    }
    return {**base, **over}


# ── P73-TS01: one launch recipe everywhere ───────────────────────────────


def test_wrapper_is_the_same_literal_session_spinoff_uses():
    spinoff = load_module("spinoff_plan_for_move", SPINOFF)
    assert sm.SHELL_FALLBACK == '"$@"; exec "$0" -il'
    assert sm.SHELL_FALLBACK == spinoff.SHELL_FALLBACK


def test_the_shell_that_runs_the_wrapper_is_chosen_as_session_spinoff_chooses_it():
    spinoff = load_module("spinoff_plan_for_move", SPINOFF)
    assert sm.POSIX_SHELLS == spinoff.POSIX_SHELLS
    for env_shell in ("/bin/zsh", "/opt/homebrew/bin/bash", "/bin/ksh",
                      "/opt/homebrew/bin/fish", "/bin/tcsh", "", None):
        assert sm.launch_shell(env_shell) == spinoff.launch_shell(env_shell)


# ── P73-TS02: what can move ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "argv0, expected",
    [("claude", "claude"), ("/opt/homebrew/bin/codex", "codex"), ("-muse", "muse"),
     ("/opt/tools/bin/muse-bin-1.4.20-R8619.1", "muse"), ("/bin/zsh", None), ("", None)],
)
def test_detect_agent(argv0, expected):
    assert sm.detect_agent({"foreground": {"argv0": argv0}}) == expected


def test_a_movable_window_has_no_refusals():
    assert sm.refusals(facts()) == []


@pytest.mark.parametrize(
    "over, needle",
    [
        ({"source_host": "h2"}, "different computer"),
        ({"source_host": None}, "cannot confirm"),
        ({"panes": 2}, "2 panes"),
        ({"agent": None, "foreground": "/bin/zsh"}, "not running Claude Code, Codex, or Muse"),
        ({"conversation_id": None, "identity_note": "no inventory row for pid 7"}, "cannot tell which"),
        ({"status": "busy"}, "status: busy"),
        ({"status": "shell"}, "background shell"),
        ({"agent": "codex", "status": None, "quiet_seconds": 2.0}, "2s ago"),
    ],
)
def test_refusals_name_the_reason(over, needle):
    out = sm.refusals(facts(**over))
    assert len(out) == 1 and needle in out[0]


def test_an_agent_moving_its_own_window_is_busy_by_definition():
    assert sm.refusals(facts(self=True, status="busy")) == []


def test_a_quiet_codex_window_can_move():
    assert sm.refusals(facts(agent="codex", status=None, quiet_seconds=30.0)) == []


ROWS = [
    {"id": "muse-1", "pid": 9356, "live": "yes", "spawn_dir": "/work/a"},
    {"id": "codex-1", "pid": 8630, "live": "yes", "spawn_dir": "/work/b"},  # the app-server's PID
    {"id": "codex-2", "pid": 8630, "live": "yes", "spawn_dir": "/work/c"},
    {"id": "codex-3", "pid": 8630, "live": "yes", "spawn_dir": "/work/c"},
    {"id": "old", "pid": None, "live": "no", "spawn_dir": "/work/b"},
]


def test_conversation_by_pid_then_by_the_one_live_conversation_in_the_directory():
    assert sm.match_conversation(ROWS, 9356, "/work/a")[0]["id"] == "muse-1"
    assert sm.match_conversation(ROWS, 9345, "/work/b")[0]["id"] == "codex-1"


def test_several_live_conversations_in_one_directory_need_a_choice():
    row, note = sm.match_conversation(ROWS, 9345, "/work/c")
    assert row is None and "codex-2, codex-3" in note and "--conversation" in note
    assert sm.match_conversation(ROWS, 9345, "/work/c", "codex-3")[0]["id"] == "codex-3"
    assert sm.match_conversation(ROWS, 9345, "/work/none")[0] is None


# ── P73-TS03: destination ────────────────────────────────────────────────


def test_destination_by_label_and_by_id():
    by_label = sm.resolve_destination(SESSIONS, "audit", "session:aaa")
    by_id = sm.resolve_destination(SESSIONS, "session:bbb", "session:aaa")
    assert by_label == by_id == {"exists": True, "session_id": "session:bbb",
                                 "label": "audit", "near": []}


def test_a_missing_destination_is_created_and_near_matches_are_reported():
    assert sm.resolve_destination(SESSIONS, "fresh", "session:aaa") == {
        "exists": False, "session_id": None, "label": "fresh", "near": []}
    assert sm.resolve_destination(SESSIONS, "AUDIT", "session:aaa")["near"] == ["audit"]


@pytest.mark.parametrize(
    "to, needle",
    [("skills", "already in that session"), ("dup", "2 sessions"), ("session:zzz", "no session")],
)
def test_destination_refusals(to, needle):
    with pytest.raises(sm.MoveRefusal, match=needle):
        sm.resolve_destination(SESSIONS, to, "session:aaa")


# ── P73-TS04: the destination window ─────────────────────────────────────


def launch(p: dict, monkeypatch) -> list[str]:
    monkeypatch.setenv("SHELL", "/bin/zsh")
    return sm.build_launch(p, "/py", "/skill/session-move", "/tmp/r.release")


HANDOFF = ["/py", "/skill/session-move", "handoff", "--agent", "claude", "--old-pid", "4242",
           "--old-session", "session:aaa", "--old-window", "window:w1",
           "--release-file", "/tmp/r.release"]
WRAPPED = ["-c", "/work/repo", "--shell=none", "--json", "--",
           "/bin/zsh", "-ilc", '"$@"; exec "$0" -il', "/bin/zsh"]


def test_existing_session_keeps_the_window_name_and_directory(monkeypatch):
    assert launch(plan(), monkeypatch) == [
        "rex", "window", "new", "-s", "session:bbb", "security-review", "--focus=false",
        *WRAPPED, *HANDOFF, "--", "claude", "--resume", "conv-1"]


def test_a_non_bourne_shell_never_receives_the_wrapper(monkeypatch):
    # fish and tcsh reject '"$@"; exec "$0" -il', so /bin/zsh runs it instead (P73-TS08).
    monkeypatch.setenv("SHELL", "/opt/homebrew/bin/fish")
    assert sm.build_launch(plan(), "/py", "/skill/session-move", "/tmp/r.release") == [
        "rex", "window", "new", "-s", "session:bbb", "security-review", "--focus=false",
        *WRAPPED, *HANDOFF, "--", "claude", "--resume", "conv-1"]


def test_new_session_names_its_first_window(monkeypatch):
    p = plan(destination={"exists": False, "session_id": None, "label": "fresh", "near": []})
    assert launch(p, monkeypatch) == [
        "rex", "new", "fresh", "--window", "security-review",
        *WRAPPED, *HANDOFF, "--", "claude", "--resume", "conv-1"]


def test_an_auto_generated_name_is_not_copied(monkeypatch):
    assert sm.is_auto_label("Window afa79287") and not sm.is_auto_label("security-review")
    src = {**plan()["source"], "label": "Window afa79287", "label_auto": True}
    assert launch(plan(source=src), monkeypatch)[:6] == [
        "rex", "window", "new", "-s", "session:bbb", "--focus=false"]


def test_self_move_follows_and_codex_passes_its_transcript(monkeypatch):
    p = plan(self=True, agent="codex", transcript="/t/rollout.jsonl",
             resume_argv=["codex", "resume", "conv-1"])
    argv = launch(p, monkeypatch)
    tail = argv[argv.index("--release-file"):]
    assert tail == ["--release-file", "/tmp/r.release", "--transcript", "/t/rollout.jsonl",
                    "--follow", "--", "codex", "resume", "conv-1"]


@pytest.mark.parametrize(
    "agent, expected",
    [("claude", ["claude", "--resume", "x"]), ("codex", ["codex", "resume", "x"]),
     ("muse", ["muse", "resume", "x"])],
)
def test_the_same_agent_resumes_the_same_conversation(agent, expected):
    assert sm.resume_argv(agent, "x") == expected


# ── P73-TS05: the handoff never leaves two copies running ────────────────


class FakePorts:
    """The outside world for run_handoff: a clock, the old agent, and Rex."""

    def __init__(self, *, released_at=0.0, status="idle", idle_at=0.0, alive=True,
                 dies_on_close=True, quiet_at=None):
        self.t = 0.0
        self.released_at, self.status_final, self.idle_at = released_at, status, idle_at
        self.is_alive, self.dies_on_close, self.quiet_at = alive, dies_on_close, quiet_at
        self.closed, self.execed, self.followed, self.said = [], None, False, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds

    def alive(self, pid):
        return self.is_alive

    def exists(self, path):
        return self.released_at is not None and self.t >= self.released_at

    def claude_status(self, pid):
        return self.status_final if self.t >= self.idle_at else "busy"

    def mtime_age(self, path):
        return None if self.quiet_at is None else max(0.0, self.t - self.quiet_at)

    def close_window(self, session, window):
        self.closed.append((session, window))
        if self.dies_on_close:
            self.is_alive = False

    def follow(self):
        self.followed = True

    def say(self, text):
        self.said.append(text)

    def exec(self, argv):
        self.execed = argv
        return 0


def cfg(**over) -> dict:
    base = {"agent": "claude", "old_pid": 4242, "old_session": "session:aaa",
            "old_window": "window:w1", "release_file": "/tmp/r.release", "transcript": None,
            "follow": False, "resume_argv": ["claude", "--resume", "conv-1"]}
    return {**base, **over}


def test_released_and_idle_closes_the_old_window_then_resumes():
    ports = FakePorts(released_at=2.0, idle_at=5.0)
    assert sm.run_handoff(cfg(follow=True), ports) == 0
    assert ports.closed == [("session:aaa", "window:w1")]
    assert ports.execed == ["claude", "--resume", "conv-1"] and ports.followed
    assert ports.t >= 5.0  # it waited for the old agent's turn to end


def test_a_background_shell_status_counts_as_turn_ended():
    ports = FakePorts(status="shell")
    assert sm.run_handoff(cfg(), ports) == 0 and ports.execed


def test_never_released_changes_nothing():
    ports = FakePorts(released_at=None)
    assert sm.run_handoff(cfg(), ports) == 1
    assert ports.closed == [] and ports.execed is None


def test_old_agent_gone_before_release_does_not_resume_by_surprise():
    ports = FakePorts(released_at=None, alive=False)
    assert sm.run_handoff(cfg(), ports) == 1
    assert ports.execed is None and "claude --resume conv-1" in ports.said[-1]


def test_a_busy_old_agent_is_left_alone():
    ports = FakePorts(status="busy")
    assert sm.run_handoff(cfg(), ports) == 1
    assert ports.closed == [] and ports.execed is None


def test_an_old_agent_that_will_not_exit_blocks_the_resume():
    ports = FakePorts(dies_on_close=False)
    assert sm.run_handoff(cfg(), ports) == 1
    assert ports.closed and ports.execed is None and "two copies" in ports.said[-1]


def test_codex_waits_for_a_quiet_transcript():
    ports = FakePorts(quiet_at=10.0)
    assert sm.run_handoff(cfg(agent="codex", transcript="/t/rollout.jsonl",
                              resume_argv=["codex", "resume", "conv-1"]), ports) == 0
    assert ports.t >= 10.0 + sm.QUIET_SECONDS and ports.execed == ["codex", "resume", "conv-1"]


def test_jump_command_names_the_app_when_one_is_known():
    assert sm.jump_command("session:s", "window:w") == [
        "rex", "do", "session.select", "session_id=session:s", "window_id=window:w"]
    assert sm.jump_command("session:s", "window:w", "client:c")[:3] == ["rex", "-C", "client:c"]


# ── P73-TS06: the result check ───────────────────────────────────────────


@pytest.mark.parametrize(
    "process, observed_id, expected",
    [
        ({"foreground": {"argv0": "claude", "pid": 9}}, "conv-1",
         {"resumed": True, "same_conversation": True}),
        ({"foreground": {"argv0": "claude", "pid": 9}}, "other",
         {"resumed": True, "same_conversation": False}),
        ({"foreground": {"argv0": "python3", "pid": 9}}, None,
         {"resumed": False, "same_conversation": None}),
        ({"foreground": {"argv0": "claude", "pid": 10}}, "conv-1",
         {"resumed": False, "same_conversation": None}),
    ],
)
def test_check_resumed(process, observed_id, expected):
    armed = {"agent": "claude", "handoff_pid": 9, "conversation_id": "conv-1"}
    assert sm.check_resumed(armed, process, observed_id) == expected
