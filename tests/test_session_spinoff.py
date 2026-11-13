"""Tests for the session-spinoff helper (plugins/session/skills/session-spinoff/scripts/spinoff-plan).

Run: uv run pytest tests/test_session_spinoff.py -q
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "session" / "skills" / "session-spinoff" / "scripts" / "spinoff-plan"


def load_module():
    loader = importlib.machinery.SourceFileLoader("spinoff_plan", str(SCRIPT))
    spec = importlib.util.spec_from_loader("spinoff_plan", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


sp = load_module()


# ── P66-TS01: argument gate ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "argv, expected",
    [
        ([], {"idea": "", "placement": "ask", "session": None, "name": None,
              "repo": None, "agent": None, "dry_run": False}),
        (["fix", "the", "worktree", "bug"], {"idea": "fix the worktree bug", "placement": "ask"}),
        (["--new"], {"placement": "new"}),
        (["--session", "flox-cli-prs"], {"placement": "session", "session": "flox-cli-prs"}),
        (["--name", "fix-repo-finder"], {"placement": "new", "name": "fix-repo-finder"}),
        (["--new", "--name", "x"], {"placement": "new", "name": "x"}),
        (["--repo", "shelf", "--codex"], {"repo": "shelf", "agent": "codex"}),
        (["--muse", "idea", "--dry-run"], {"agent": "muse", "idea": "idea", "dry_run": True}),
        (["--claude"], {"agent": "claude"}),
    ],
)
def test_parse_args_accepts(argv, expected):
    got = sp.parse_args(argv)
    for key, value in expected.items():
        assert got[key] == value, (key, got)


@pytest.mark.parametrize(
    "argv, fragment",
    [
        (["--new", "--session", "s"], "--new"),
        (["--name", "n", "--session", "s"], "--name"),
        (["--claude", "--codex"], "agent"),
        (["--codex", "--codex"], "agent"),
        (["--branch", "b"], "unknown"),
        (["--session"], "needs a value"),
        (["--name"], "needs a value"),
        (["--repo"], "needs a value"),
        (["--session", "--new"], "needs a value"),
    ],
)
def test_parse_args_refuses(argv, fragment):
    with pytest.raises(sp.SpinoffArgError) as exc:
        sp.parse_args(argv)
    assert fragment in str(exc.value)


def test_cli_args_verb_refusal_exits_2():
    proc = subprocess.run([sys.executable, str(SCRIPT), "args", "--", "--new", "--session", "s"],
                          capture_output=True, text=True)
    assert proc.returncode == 2
    assert "--new" in proc.stderr


def test_slugify():
    assert sp.slugify("Fix: repo-finder mis-reports Worktrees!") == "fix-repo-finder-mis-reports-worktrees"
    assert len(sp.slugify("a " * 100, max_len=40)) <= 40
    assert not sp.slugify("a " * 100, max_len=40).endswith("-")


def test_detect_agent():
    assert sp.detect_agent({"foreground": {"argv0": "claude"}}) == "claude"
    assert sp.detect_agent({"foreground": {"argv0": "/opt/homebrew/bin/codex"}}) == "codex"
    assert sp.detect_agent({"foreground": {"argv0": "muse"}}) == "muse"
    assert sp.detect_agent({"foreground": {"argv0": "zsh"}}) is None
    assert sp.detect_agent({}) is None


# ── P66-TS02: classification (tiers from facts; the LLM orders within a tier) ──

TARGET = "/code/shelf/.git"


def tab(cwd, repo_dir, agent=None):
    return {"cwd": cwd, "repo_dir": repo_dir, "agent": agent}


def session(sid, label, tabs):
    return {"session_id": sid, "label": label,
            "windows": [{"window_id": f"w-{sid}", "label": "t", "tabs": tabs}]}


def test_classify_repo_match_is_tier_1():
    sessions = [
        session("s1", "hailwire-design", [tab("/code/hailwire", "/code/hailwire/.git", "claude")]),
        session("s2", "shelf-tags", [tab("/code/shelf-wt", TARGET, "codex")]),
        session("s3", "misc", []),
    ]
    out = sp.classify_sessions(sessions, TARGET)
    assert [s["session_id"] for s in out] == ["s2", "s1", "s3"]
    assert [s["tier"] for s in out] == [1, 2, 2]
    assert out[0]["repo_tabs"] == 1
    assert out[0]["agents"] == ["codex"]
    assert "1 tab in this repo" in out[0]["facts"]


def test_classify_more_repo_tabs_first_within_tier_1():
    sessions = [
        session("s1", "a", [tab("/x", TARGET)]),
        {"session_id": "s2", "label": "b", "windows": [
            {"window_id": "w1", "tabs": [tab("/x", TARGET)]},
            {"window_id": "w2", "tabs": [tab("/y", TARGET)]},
        ]},
    ]
    out = sp.classify_sessions(sessions, TARGET)
    assert [s["session_id"] for s in out] == ["s2", "s1"]
    assert "2 tabs in this repo" in out[0]["facts"]


def test_classify_keeps_rex_order_in_tier_2_and_every_session():
    sessions = [session(f"s{i}", f"l{i}", []) for i in range(5)]
    out = sp.classify_sessions(sessions, TARGET)
    assert [s["session_id"] for s in out] == [f"s{i}" for i in range(5)]
    assert all(s["tier"] == 2 for s in out)


# ── P66-TS03: command builder ────────────────────────────────────────────

BASE_PLAN = {
    "repo": "/code/shelf",
    "default_branch": "main",
    "branch": "feat/shelf-tags",
    "worktree": "/code/shelf-shelf-tags",
    "agent": "codex",
    "brief": "Add tags to shelf.\nDone when: tags round-trip.",
    "tab_label": "shelf-tags",
    "client": "client:abc",
}


def test_commands_new_session():
    plan = {**BASE_PLAN, "placement": "new", "name": "shelf-tags"}
    cmds = sp.build_commands(plan)
    assert cmds["worktree"][:4] == ["git", "-C", "/code/shelf", "fetch"]
    assert cmds["worktree_add"] == ["git", "-C", "/code/shelf", "worktree", "add", "-b",
                                    "feat/shelf-tags", "/code/shelf-shelf-tags", "origin/main"]
    launch = cmds["launch"]
    assert launch[:3] == ["rex", "new", "shelf-tags"]
    assert launch[launch.index("-c") + 1] == "/code/shelf-shelf-tags"
    assert launch[launch.index("--") + 1:] == ["codex", BASE_PLAN["brief"]]
    assert "--json" in launch


def test_commands_existing_session():
    plan = {**BASE_PLAN, "placement": "session", "session": "session:xyz"}
    launch = sp.build_commands(plan)["launch"]
    assert launch[:5] == ["rex", "window", "new", "-s", "session:xyz"]
    assert launch[5] == "shelf-tags"
    assert launch[launch.index("--") + 1:] == ["codex", BASE_PLAN["brief"]]


def test_jump_command():
    jump = sp.jump_command("client:abc", "session:xyz", "window:123")
    assert jump == ["rex", "-C", "client:abc", "do", "session.select",
                    "session_id=session:xyz", "window_id=window:123"]


def test_cli_commands_verb_is_pure(tmp_path):
    """`commands` only prints; it never runs git or rex (what --dry-run relies on)."""
    plan = {**BASE_PLAN, "placement": "new", "name": "shelf-tags", "repo": str(tmp_path)}
    proc = subprocess.run([sys.executable, str(SCRIPT), "commands"], input=json.dumps(plan),
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["launch"][:2] == ["rex", "new"]
    assert "shell" in out and "rex new" in out["shell"]["launch"]
    assert list(tmp_path.iterdir()) == []


# ── review fixes (skill-reviewer, 2026-11-13) ────────────────────────────


def test_default_branch_with_origin_prefix_is_stripped():
    plan = {**BASE_PLAN, "placement": "new", "name": "n", "default_branch": "origin/main"}
    assert sp.build_commands(plan)["worktree_add"][-1] == "origin/main"


def test_relative_worktree_resolves_against_repo():
    plan = {**BASE_PLAN, "placement": "new", "name": "n", "worktree": "../shelf-tags"}
    cmds = sp.build_commands(plan)
    assert cmds["worktree_add"][-2] == "/code/shelf-tags"
    assert cmds["launch"][cmds["launch"].index("-c") + 1] == "/code/shelf-tags"


@pytest.mark.parametrize("drop", ["name", "repo", "agent", "branch"])
def test_commands_missing_key_exits_2(drop):
    plan = {**BASE_PLAN, "placement": "new", "name": "n"}
    del plan[drop]
    proc = subprocess.run([sys.executable, str(SCRIPT), "commands"], input=json.dumps(plan),
                          capture_output=True, text=True)
    assert proc.returncode == 2 and drop in proc.stderr


def test_session_placement_needs_session():
    plan = {**BASE_PLAN, "placement": "session"}
    with pytest.raises(sp.SpinoffArgError):
        sp.build_commands(plan)


def test_brief_file_carries_multiline_quoted_text(tmp_path):
    brief = 'Fix "worktree" detection.\nError: can\'t parse {"kind": 1}\n'
    f = tmp_path / "brief.md"
    f.write_text(brief)
    plan = {k: v for k, v in BASE_PLAN.items() if k != "brief"}
    plan.update(placement="new", name="n")
    proc = subprocess.run([sys.executable, str(SCRIPT), "commands", "--brief-file", str(f)],
                          input=json.dumps(plan), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    launch = json.loads(proc.stdout)["launch"]
    assert launch[-1] == brief


def test_commands_bad_json_exits_2():
    proc = subprocess.run([sys.executable, str(SCRIPT), "commands"], input="{not json",
                          capture_output=True, text=True)
    assert proc.returncode == 2


# ── smoke-test finding: idea text that mentions flags ────────────────────


def test_unknown_dashword_inside_idea_is_idea_text():
    got = sp.parse_args(["--new", "--claude", "add", "a", "--version", "flag", "--dry-run"])
    assert got["idea"] == "add a --version flag"
    assert got["dry_run"] is True and got["placement"] == "new"


def test_unknown_flag_before_idea_is_still_refused():
    with pytest.raises(sp.SpinoffArgError):
        sp.parse_args(["--verbose", "fix", "it"])


def test_bare_double_dash_ends_flags():
    got = sp.parse_args(["--codex", "--", "document", "--new", "and", "--session"])
    assert got["agent"] == "codex"
    assert got["placement"] == "ask"
    assert got["idea"] == "document --new and --session"


def test_cli_args_verb_keeps_inner_double_dash():
    proc = subprocess.run([sys.executable, str(SCRIPT), "args", "--", "--muse", "--", "x", "--new"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["idea"] == "x --new" and out["agent"] == "muse"


# ── P66-TS06: directories (session dirs shown, launch dir chosen and verified) ──


def test_classify_lists_each_sessions_dirs_once():
    sessions = [session("s1", "a", [tab("/code/shelf", TARGET), tab("/code/shelf", TARGET),
                                    tab("/code/other", "/code/other/.git"), tab(None, None)])]
    out = sp.classify_sessions(sessions, TARGET)
    assert out[0]["dirs"] == ["/code/shelf", "/code/other"]


def test_launch_dir_defaults_to_worktree():
    plan = {**BASE_PLAN, "placement": "new", "name": "n"}
    launch = sp.build_commands(plan)["launch"]
    assert launch[launch.index("-c") + 1] == "/code/shelf-shelf-tags"


@pytest.mark.parametrize("launch_dir, expected", [
    ("packages/api", "/code/shelf-shelf-tags/packages/api"),   # subdir, relative to the worktree
    ("/code", "/code"),                                          # parent, for multi-repo ideas
])
def test_launch_dir_subdir_or_parent(launch_dir, expected):
    plan = {**BASE_PLAN, "placement": "new", "name": "n", "launch_dir": launch_dir}
    cmds = sp.build_commands(plan)
    assert cmds["launch"][cmds["launch"].index("-c") + 1] == expected
    assert cmds["launch_dir"] == expected


def test_launch_dir_outside_worktree_line_is_refused():
    plan = {**BASE_PLAN, "placement": "new", "name": "n", "launch_dir": "/elsewhere/repo"}
    with pytest.raises(sp.SpinoffArgError) as exc:
        sp.build_commands(plan)
    assert "launch_dir" in str(exc.value)


def test_check_launch_matches_cwd_and_agent():
    proc = {"foreground": {"argv0": "codex", "cwd": "/code/shelf-shelf-tags"}}
    got = sp.check_launch(proc, "/code/shelf-shelf-tags", "codex")
    assert got == {"ok": True, "cwd": "/code/shelf-shelf-tags", "agent": "codex",
                   "cwd_ok": True, "agent_ok": True}


def test_check_launch_flags_wrong_dir_and_agent():
    proc = {"foreground": {"argv0": "zsh", "cwd": "/tmp/x"}}
    got = sp.check_launch(proc, "/code/shelf-shelf-tags", "codex")
    assert got["ok"] is False and got["cwd_ok"] is False and got["agent_ok"] is False


# ── P66-TS07: transcript evidence + label fact (sessions started in a parent dir) ──


def fake_root_of(path):
    if path.startswith("/code/shelf"):          # /code/shelf and /code/shelf-wt are one repo
        return TARGET
    if path.startswith("/code/other"):
        return "/code/other/.git"
    return None


def test_repo_hits_collapses_worktrees_and_ignores_non_repo_paths():
    text = ('{"file_path": "/code/shelf/a.py"} git -C /code/shelf-wt status '
            '"/code/other/x" /code/shelf/b.py /nowhere/z')
    hits = sp.repo_hits(text, "/code", fake_root_of)
    assert hits == {TARGET: 3, "/code/other/.git": 1}


def test_transcript_hits_put_a_parent_started_tab_in_tier_1():
    s = session("s1", "rslpb-p02-merge", [{**tab("/code", None, "claude"), "touched": {TARGET: 5}}])
    out = sp.classify_sessions([s], TARGET)
    assert out[0]["tier"] == 1
    assert "agent touched this repo 5× recently" in out[0]["facts"]


def test_transcript_hits_below_threshold_stay_tier_2_but_are_shown():
    s = session("s1", "x", [{**tab("/code", None, "claude"), "touched": {TARGET: 2}}])
    out = sp.classify_sessions([s], TARGET)
    assert out[0]["tier"] == 2
    assert "agent touched this repo 2× recently" in out[0]["facts"]


def test_tier_1_orders_started_in_repo_then_hits():
    started = session("a", "a", [tab("/code/shelf", TARGET)])
    busy = session("b", "b", [{**tab("/code", None, "codex"), "touched": {TARGET: 40}}])
    light = session("c", "c", [{**tab("/code", None, "codex"), "touched": {TARGET: 4}}])
    out = sp.classify_sessions([light, busy, started], TARGET)
    assert [s["session_id"] for s in out] == ["a", "b", "c"]


@pytest.mark.parametrize("label, repo, expected", [
    ("review-shelf-p27", "shelf", True),
    ("shelf", "shelf", True),
    ("bookshelf-ideas", "shelf", False),
    ("T8-muse-lost-sessions", "lost-sessions", True),
    ("lost-and-found-sessions", "lost-sessions", False),
    ("anything", "", False),
])
def test_label_names_repo(label, repo, expected):
    assert sp.label_names_repo(label, repo) is expected


def test_label_fact_never_sets_the_tier():
    out = sp.classify_sessions([session("s1", "review-shelf-p27", [])], TARGET)
    assert out[0]["tier"] == 2
    assert "label names this repo" in out[0]["facts"]


# ── PR #103 review (CodeRabbit) ──────────────────────────────────────────


def test_repo_tabs_counts_windows_not_panes():
    s = {"session_id": "s1", "label": "x", "windows": [
        {"window_id": "w1", "tabs": [tab("/code/shelf", TARGET)] * 4},   # one tab split into 4 panes
        {"window_id": "w2", "tabs": [tab("/code/shelf", TARGET)]},
    ]}
    out = sp.classify_sessions([s], TARGET)
    assert out[0]["repo_tabs"] == 2
    assert "2 tabs in this repo" in out[0]["facts"]


def test_existing_session_launch_keeps_focus():
    plan = {**BASE_PLAN, "placement": "session", "session": "session:xyz"}
    assert "--focus=false" in sp.build_commands(plan)["launch"]


def test_snapshot_refuses_when_rex_listing_fails(monkeypatch):
    monkeypatch.setattr(sp, "git_common_dir", lambda path: TARGET)
    monkeypatch.setattr(sp, "_run_json", lambda argv: None)
    with pytest.raises(sp.SpinoffArgError) as exc:
        sp.snapshot("/code/shelf")
    assert "rex ls" in str(exc.value)
