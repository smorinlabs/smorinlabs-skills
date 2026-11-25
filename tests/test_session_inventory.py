"""Tests for the session-inventory CLI script (session-agent-list skill).

Run: uv run pytest tests/test_session_inventory.py -q

Builds fixture stores for Claude Code, Codex, Muse, and OpenCode under a fake
HOME, starts stand-in processes to exercise liveness detection, and drives the
script via subprocess against docs/session-inventory-cli.md (exit codes R6.1,
stdout/stderr split R7.1, JSON contract R7.2/R7.8).
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "session" / "skills" / "session-agent-list" / "scripts" / "session-inventory"

NOW = time.time()
HOUR = 3600


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def write_jsonl(path: Path, records, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def utc_lstart(pid: int) -> str:
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True,
                         text=True, env={**os.environ, "TZ": "UTC"}).stdout
    return " ".join(out.split())


def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


@pytest.fixture()
def procs():
    """Start stand-in processes; kill them all at teardown."""
    started = []

    def start(argv, cwd=None):
        """Start a process; stand-ins built by fake_tool signal readiness through
        READY_FILE once they run under their own name with locks held."""
        ready = Path(argv[0] + f".ready-{len(started)}")
        p = subprocess.Popen(argv, cwd=cwd, env={**os.environ, "READY_FILE": str(ready)})
        started.append(p)
        if argv[0].endswith(("/sleep", "sleep")):
            return p
        deadline = time.time() + 15
        while not ready.exists():
            assert time.time() < deadline, f"stand-in {argv[0]} never became ready"
            time.sleep(0.05)
        return p

    yield start
    for p in started:
        p.kill()
        p.wait()


def fake_tool(bindir: Path, name: str) -> Path:
    """An executable named after a tool that sleeps, optionally holding a file open."""
    bindir.mkdir(parents=True, exist_ok=True)
    exe = bindir / name
    exe.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys, time\n"
        "held = [open(a) for a in sys.argv[1:] if a.endswith('.lock')]\n"
        "open(os.environ['READY_FILE'], 'w').close()\n"
        "time.sleep(60)\n"
    )
    exe.chmod(0o755)
    return exe


# --- fixture stores -----------------------------------------------------------

def build_claude(home: Path):
    proj = home / ".claude" / "projects" / "-work-alpha"
    ids = {
        "renamed": "11111111-1111-4111-8111-111111111111",
        "plain": "22222222-2222-4222-8222-222222222222",
        "broken": "33333333-3333-4333-8333-333333333333",
    }
    write_jsonl(proj / f"{ids['renamed']}.jsonl", [
        {"type": "mode", "sessionId": ids["renamed"]},
        {"type": "user", "timestamp": iso(NOW - 3 * HOUR), "cwd": "/work/alpha",
         "gitBranch": "main", "sessionId": ids["renamed"]},
        {"type": "ai-title", "aiTitle": "old title", "sessionId": ids["renamed"]},
        {"type": "ai-title", "aiTitle": "Fix skill symlinks", "sessionId": ids["renamed"]},
        {"type": "custom-title", "customTitle": "symlink-fix", "sessionId": ids["renamed"]},
    ], mtime=NOW - 1 * HOUR)
    write_jsonl(proj / f"{ids['plain']}.jsonl", [
        {"type": "user", "timestamp": iso(NOW - 50 * HOUR), "cwd": "/work/my repo",
         "sessionId": ids["plain"]},
    ], mtime=NOW - 48 * HOUR)
    (proj / f"{ids['broken']}.jsonl").write_text("{not json\n\x00\x01garbage")
    # sidecar dir: must be ignored
    write_jsonl(proj / ids["renamed"] / "subagents" / "agent-x.jsonl",
                [{"type": "user", "timestamp": iso(NOW), "cwd": "/work/alpha"}])
    return ids


def build_codex(home: Path):
    root = home / ".codex"
    day = root / "sessions" / "2026" / "09" / "20"
    ids = {
        "user": "0a000000-0000-7000-8000-00000000000a",
        "fork": "0b000000-0000-7000-8000-00000000000b",
        "sub": "0c000000-0000-7000-8000-00000000000c",
        "guard": "0d000000-0000-7000-8000-00000000000d",
    }

    def meta(i, **extra):
        return [{"type": "session_meta", "payload": {
            "id": i, "timestamp": iso(NOW - 5 * HOUR), "cwd": "/work/beta",
            "thread_source": "user", "source": "cli", **extra}}]

    write_jsonl(day / f"rollout-2026-09-20T10-00-00-{ids['user']}.jsonl", meta(ids["user"]), NOW - 2 * HOUR)
    write_jsonl(day / f"rollout-2026-09-20T11-00-00-{ids['fork']}.jsonl",
                meta(ids["fork"], forked_from_id=ids["user"]), NOW - 2 * HOUR)
    write_jsonl(day / f"rollout-2026-09-20T12-00-00-{ids['sub']}.jsonl",
                meta(ids["sub"], thread_source="subagent",
                     source={"subagent": {"thread_spawn": {"parent_thread_id": ids["user"]}}}), NOW - 2 * HOUR)
    write_jsonl(day / f"rollout-2026-09-20T13-00-00-{ids['guard']}.jsonl",
                meta(ids["guard"], thread_source="guardian_review",
                     source={"subagent": {"other": "guardian"}}), NOW - 2 * HOUR)
    write_jsonl(root / "session_index.jsonl", [
        {"id": ids["user"], "thread_name": "Review README", "updated_at": iso(NOW)},
    ])
    locks = root / "thread-writer-locks"
    locks.mkdir(parents=True)
    for i in ids.values():
        (locks / f"{i}.lock").touch()
    return ids


MUSE_SCHEMA = """CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY, session_dir TEXT NOT NULL, session_log_path TEXT NOT NULL,
  workspace_root TEXT, git_branch TEXT, title TEXT NOT NULL, session_name TEXT,
  created_at_us INTEGER, updated_at_us INTEGER, status TEXT NOT NULL,
  msp_fork_source_session_id TEXT)"""


def build_muse(home: Path, host: str | None = None):
    data = home / ".local" / "share" / "muse"
    ids = {
        "named": "01a0ca24-4bbc-7ec1-bd58-21281a1af2bf",
        "stale": "01a0ca25-4bbc-7ec1-bd58-21281a1af2bf",
        "noworkspace": "01a0ca26-4bbc-7ec1-bd58-21281a1af2bf",
        "fork": "01a0ca27-4bbc-7ec1-bd58-21281a1af2bf",
    }
    data.mkdir(parents=True)
    db = sqlite3.connect(data / "session-index.db")
    db.execute(MUSE_SCHEMA)
    rows = [
        (ids["named"], "/work/gamma", "main", "Look at CI bottleneck", None, None, NOW - 1 * HOUR),
        (ids["stale"], "/work/gamma", None, "Old stale one", None, None, NOW - 30 * HOUR),
        (ids["noworkspace"], None, None, "New session", None, None, NOW - 4 * HOUR),
        (ids["fork"], "/work/gamma", None, "Forked", None, ids["named"], NOW - 2 * HOUR),
    ]
    for sid, ws, branch, title, name, fork, updated in rows:
        sdir = data / "sessions" / "2026" / "09" / "22" / sid
        sdir.mkdir(parents=True)
        (sdir / "session.jsonl").write_text("{}\n")
        (sdir / ".session.lock").write_text(f"pid={dead_pid()}\nhost={host or socket.gethostname()}\n")
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sid, str(sdir), str(sdir / "session.jsonl"), ws, branch, title, name,
             int((updated - HOUR) * 1e6), int(updated * 1e6), "valid", fork))
    db.commit()
    db.close()
    authority = home / "Library" / "Application Support" / "Muse" / "session-name-authority"
    authority.mkdir(parents=True)
    names = sqlite3.connect(authority / "session-names.db")
    names.execute("CREATE TABLE session_name_claims (normalized_name TEXT PRIMARY KEY, session_id TEXT NOT NULL,"
                  " kind TEXT NOT NULL, claim_revision INTEGER NOT NULL, created_sequence INTEGER NOT NULL)")
    names.execute("INSERT INTO session_name_claims VALUES ('old-name', ?, 'tombstone', 0, 1)", (ids["named"],))
    names.execute("INSERT INTO session_name_claims VALUES ('copper-umbra', ?, 'canonical', 1, 2)", (ids["named"],))
    names.commit()
    names.close()
    return ids, data


OPENCODE_SCHEMA = """CREATE TABLE session (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, parent_id TEXT, slug TEXT NOT NULL,
  directory TEXT NOT NULL, title TEXT NOT NULL, version TEXT NOT NULL,
  time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, time_archived INTEGER)"""


def build_opencode(home: Path):
    data = home / ".local" / "share" / "opencode"
    data.mkdir(parents=True)
    ids = {"top": "ses_top0000000000000000000", "child": "ses_child00000000000000000",
           "archived": "ses_arch000000000000000000"}
    db = sqlite3.connect(data / "opencode.db")
    db.execute(OPENCODE_SCHEMA)
    ms = lambda t: int(t * 1000)  # noqa: E731
    db.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?)",
               (ids["top"], "p1", None, "brave-otter", "/work/delta", "Find justfile recipes", "1",
                ms(NOW - 7 * HOUR), ms(NOW - 6 * HOUR), None))
    db.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?)",
               (ids["child"], "p1", ids["top"], "calm-fox", "/work/delta", "Explore (@explore subagent)", "1",
                ms(NOW - 7 * HOUR), ms(NOW - 6 * HOUR), None))
    db.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?)",
               (ids["archived"], "p1", None, "quiet-owl", "/work/delta", "Archived one", "1",
                ms(NOW - 90 * HOUR), ms(NOW - 80 * HOUR), ms(NOW - 70 * HOUR)))
    db.commit()
    db.close()
    return ids, data


AGY_SCHEMA = """CREATE TABLE conversation_summaries (
  conversation_id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  preview TEXT NOT NULL DEFAULT '',
  step_count INTEGER NOT NULL DEFAULT 0,
  last_modified_time DATETIME NOT NULL,
  workspace_uris TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  project_id TEXT NOT NULL DEFAULT '',
  agent_name TEXT NOT NULL DEFAULT '',
  parent_conversation_id TEXT NOT NULL DEFAULT '',
  nesting_depth INTEGER NOT NULL DEFAULT 0,
  last_user_input_time DATETIME NOT NULL
)"""


def build_agy(home: Path):
    root = home / ".gemini" / "antigravity-cli"
    root.mkdir(parents=True)
    ids = {
        "main": "2c8e9676-a98c-4595-b618-d4e53715f32b",
        "preview_only": "3d9f0787-b09d-4606-c729-e5f64826043c",
        "noworkspace": "4e001898-c10e-4717-d830-f6075937154d",
        "fork": "5f112909-d21f-4828-e941-07186048265e",
        "sub": "60223010-e320-4939-fa52-18297159376f",
    }
    db = sqlite3.connect(root / "conversation_summaries.db")
    db.execute(AGY_SCHEMA)
    # Mix ISO 8601 and Go time.Time string formats to exercise timestamp normalization
    rows = [
        (ids["main"], "Ship agy support", "fallback preview", 12,
         iso(NOW - 2 * HOUR), json.dumps(["file:///work/zeta", "file:///work/extra"]),
         "", 0, iso(NOW - 2 * HOUR)),
        (ids["preview_only"], "", "Preview becomes title", 4,
         time.strftime("%Y-%m-%d %H:%M:%S.123456789 +0000 UTC", time.gmtime(NOW - 40 * HOUR)),
         "file:///work/my%20agy%20repo",
         "", 0, iso(NOW - 40 * HOUR)),
        (ids["noworkspace"], "No workspace session", "", 1,
         iso(NOW - 5 * HOUR), "[]",
         "", 0, iso(NOW - 5 * HOUR)),
        (ids["fork"], "Forked agy session", "", 5,
         iso(NOW - 3 * HOUR), json.dumps(["file:///work/zeta"]),
         ids["main"], 0, iso(NOW - 3 * HOUR)),
        (ids["sub"], "Subagent task", "", 3,
         iso(NOW - 1 * HOUR), json.dumps(["file:///work/zeta"]),
         ids["main"], 1, iso(NOW - 1 * HOUR)),
    ]
    for sid, title, preview, steps, mod, ws, parent, depth, last_in in rows:
        db.execute(
            "INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, title, preview, steps, mod, ws, "IDLE", "cli", "default", "", parent, depth, last_in),
        )
    db.commit()
    db.close()

    # Transcripts: main, fork, and sub have transcript.jsonl with created_at; preview_only omits it
    for key, created_offset in (("main", 4 * HOUR), ("fork", 3.5 * HOUR), ("sub", 1.5 * HOUR)):
        tpath = root / "brain" / ids[key] / ".system_generated" / "logs" / "transcript.jsonl"
        write_jsonl(tpath, [
            {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT",
             "status": "DONE", "created_at": iso(NOW - created_offset), "content": "hello"},
        ], mtime=NOW - 1 * HOUR)
    return ids, root


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture()
def world(home):
    return {
        "claude": build_claude(home),
        "codex": build_codex(home),
        "muse": build_muse(home)[0],
        "opencode": build_opencode(home)[0],
        "agy": build_agy(home)[0],
    }


def run(home: Path, *args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("CODEX_HOME", "XDG_DATA_HOME")}
    env.update({"HOME": str(home), **(env_extra or {})})
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60)


def inventory(home: Path, *args, **kw):
    r = run(home, "list", "--json", *args, **kw)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def by_id(doc):
    return {s["id"]: s for s in doc["sessions"]}


# --- CLI basics (R4.1, R6.1, R7.9) ----------------------------------------------

def test_bare_invocation_prints_help_and_exits_zero(home):
    r = run(home)
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()


def test_version_goes_to_stdout(home):
    r = run(home, "--version")
    assert r.returncode == 0 and r.stdout.strip()


def test_output_flags_work_before_and_after_the_verb(home):
    # spec: --output/--json are global (PR #86 review, thread 4114456500)
    for argv in (["--json", "list"], ["list", "--json"], ["-o", "json", "list"], ["list", "-o", "json"]):
        r = run(home, *argv)
        assert r.returncode == 0, (argv, r.stderr)
        assert json.loads(r.stdout)["sessions"] == []
    assert not run(home, "list").stdout.lstrip().startswith("{")


def test_unknown_tool_is_usage_error(home):
    r = run(home, "list", "--tool", "grok")
    assert r.returncode == 2


def test_bad_since_is_usage_error(home):
    r = run(home, "list", "--since", "yesterday-ish")
    assert r.returncode == 2


def test_empty_home_is_success_with_absent_sources(home):
    doc = inventory(home)
    assert doc["sessions"] == []
    assert {v["status"] for v in doc["sources"].values()} == {"absent"}


# --- per-tool extraction ------------------------------------------------------

def test_claude_name_title_dir_and_resume(home, world):
    s = by_id(inventory(home, "--tool", "claude"))[world["claude"]["renamed"]]
    assert s["tool"] == "claude"
    assert s["name"] == "symlink-fix"
    assert s["title"] == "Fix skill symlinks"
    assert s["spawn_dir"] == "/work/alpha"
    assert s["branch"] == "main"
    assert s["created"].startswith(iso(NOW - 3 * HOUR)[:16])
    assert s["resume"] == f"cd /work/alpha && claude --resume {world['claude']['renamed']}"
    assert s["name_resumable"] is False and s["resume_by_name"] is None


def test_claude_resume_quotes_paths_with_spaces(home, world):
    s = by_id(inventory(home, "--tool", "claude"))[world["claude"]["plain"]]
    assert s["resume"] == f"cd '/work/my repo' && claude --resume {world['claude']['plain']}"


def test_claude_unreadable_is_listed_and_counted(home, world):
    doc = inventory(home, "--tool", "claude")
    s = by_id(doc)[world["claude"]["broken"]]
    assert s["unreadable"] is True
    assert doc["census"]["claude"]["unreadable"] == 1


def test_claude_sidecar_dirs_are_ignored(home, world):
    doc = inventory(home, "--tool", "claude")
    assert len(doc["sessions"]) == 3


def test_codex_names_forks_and_hidden_subagents(home, world):
    doc = inventory(home, "--tool", "codex")
    ids = world["codex"]
    got = by_id(doc)
    assert set(got) == {ids["user"], ids["fork"]}
    assert got[ids["user"]]["name"] == "Review README"
    assert got[ids["user"]]["name_resumable"] is True
    assert got[ids["user"]]["resume"] == f"codex resume {ids['user']}"
    assert got[ids["user"]]["resume_by_name"] == "codex resume 'Review README'"
    assert got[ids["fork"]]["lineage"] == {"kind": "fork", "parent_id": ids["user"]}
    assert doc["census"]["codex"]["hidden_subagents"] == 2


def test_codex_include_subagents_shows_them_with_lineage(home, world):
    ids = world["codex"]
    got = by_id(inventory(home, "--tool", "codex", "--include-subagents"))
    assert got[ids["sub"]]["lineage"] == {"kind": "subagent", "parent_id": ids["user"]}
    assert ids["guard"] in got


def test_codex_string_subagent_source_is_hidden(home, world):
    # real shape seen on 2026-09-22: {"subagent": "review"} (string, not object)
    rid = "0e000000-0000-7000-8000-00000000000e"
    write_jsonl(home / ".codex/sessions/2026/09/20" / f"rollout-2026-09-20T14-00-00-{rid}.jsonl",
                [{"type": "session_meta", "payload": {"id": rid, "timestamp": iso(NOW), "cwd": "/w",
                                                      "thread_source": "subagent",
                                                      "source": {"subagent": "review"}}}])
    doc = inventory(home, "--tool", "codex", "--include-subagents")
    assert by_id(doc)[rid]["lineage"] == {"kind": "subagent", "parent_id": None}
    assert doc["census"]["codex"]["hidden_subagents"] == 3


def test_codex_home_env_is_honored(home, world, tmp_path):
    moved = tmp_path / "elsewhere"
    (home / ".codex").rename(moved)
    got = by_id(inventory(home, "--tool", "codex", env_extra={"CODEX_HOME": str(moved)}))
    assert world["codex"]["user"] in got


def test_muse_name_resume_and_fork(home, world):
    ids = world["muse"]
    got = by_id(inventory(home, "--tool", "muse"))
    s = got[ids["named"]]
    assert s["name"] == "copper-umbra" and s["name_resumable"] is True
    assert s["title"] == "Look at CI bottleneck"
    assert s["resume"] == f"cd /work/gamma && muse resume {ids['named']}"
    assert s["resume_by_name"] == "cd /work/gamma && muse resume copper-umbra"
    assert got[ids["fork"]]["lineage"] == {"kind": "fork", "parent_id": ids["named"]}
    assert s["export_command"] == f"muse export --session {ids['named']}"


def test_muse_name_falls_back_to_index_column(home, world):
    ids = world["muse"]
    (home / "Library" / "Application Support" / "Muse" / "session-name-authority" / "session-names.db").unlink()
    db = sqlite3.connect(home / ".local/share/muse/session-index.db")
    db.execute("UPDATE sessions SET session_name = 'from-index' WHERE session_id = ?", (ids["fork"],))
    db.commit()
    db.close()
    got = by_id(inventory(home, "--tool", "muse"))
    assert got[ids["fork"]]["name"] == "from-index"
    assert got[ids["named"]]["name"] is None


def test_muse_missing_workspace_blocks_resume(home, world):
    s = by_id(inventory(home, "--tool", "muse"))[world["muse"]["noworkspace"]]
    assert s["resume"] is None and s["resume_blocked"] == "no_workspace"


def test_muse_schema_change_is_partial_failure(home, world):
    db = sqlite3.connect(home / ".local/share/muse/session-index.db")
    db.execute("ALTER TABLE sessions RENAME COLUMN workspace_root TO ws")
    db.commit()
    db.close()
    r = run(home, "list", "--json")
    assert r.returncode == 1
    doc = json.loads(r.stdout)
    assert doc["sources"]["muse"]["status"] == "error"
    assert world["codex"]["user"] in by_id(doc)          # other tools still listed
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "source_unreadable" and err["error"]["sources"] == ["muse"]


def test_muse_store_is_not_modified(home, world):
    db_path = home / ".local/share/muse/session-index.db"
    before = db_path.read_bytes()
    inventory(home, "--tool", "muse")
    assert db_path.read_bytes() == before


def test_xdg_data_home_is_honored(home, world, tmp_path):
    moved = tmp_path / "xdg"
    (home / ".local" / "share").rename(moved)
    doc = inventory(home, "--tool", "muse", "--tool", "opencode", env_extra={"XDG_DATA_HOME": str(moved)})
    assert world["muse"]["named"] in by_id(doc)
    assert world["opencode"]["top"] in by_id(doc)


def test_opencode_slug_children_archive_and_export(home, world):
    ids = world["opencode"]
    doc = inventory(home, "--tool", "opencode")
    got = by_id(doc)
    assert set(got) == {ids["top"], ids["archived"]}
    s = got[ids["top"]]
    assert s["name"] == "brave-otter" and s["name_resumable"] is False
    assert s["resume"] == f"cd /work/delta && opencode --session {ids['top']}"
    assert s["transcript"] is None
    assert s["export_command"] == f"opencode export {ids['top']}"
    assert got[ids["archived"]]["archived"] is True
    assert doc["census"]["opencode"]["hidden_subagents"] == 1


# Newer OpenCode releases write to `session_v2`, which keeps every `session` row;
# the old table stops receiving new ones.
OPENCODE_V2_SCHEMA = """CREATE TABLE session_v2 (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, workspace_id TEXT, parent_id TEXT, slug TEXT NOT NULL,
  directory TEXT NOT NULL, title TEXT, version TEXT NOT NULL,
  time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, time_archived INTEGER, time_idle INTEGER)"""


def test_opencode_session_v2_rows_are_listed(home):
    ids, data = build_opencode(home)
    ms = lambda t: int(t * 1000)  # noqa: E731
    new, new_child = "ses_new0000000000000000000", "ses_newkid000000000000000"
    untitled = "ses_untitled00000000000000"
    db = sqlite3.connect(data / "opencode.db")
    db.execute(OPENCODE_V2_SCHEMA)
    db.execute("INSERT INTO session_v2 (id, project_id, parent_id, slug, directory, title, version,"
               " time_created, time_updated, time_archived)"
               " SELECT id, project_id, parent_id, slug, directory, title, version,"
               " time_created, time_updated, time_archived FROM session")
    for sid, parent, slug in ((new, None, "swift-hawk"), (new_child, new, "tiny-wren")):
        db.execute("INSERT INTO session_v2 (id, project_id, parent_id, slug, directory, title, version,"
                   " time_created, time_updated) VALUES (?,?,?,?,?,?,?,?,?)",
                   (sid, "p1", parent, slug, "/work/echo", f"title {slug}", "2", ms(NOW - 2 * HOUR), ms(NOW - HOUR)))
    # session_v2.title is nullable; 6 of 17 rows on the reporting machine had none.
    db.execute("INSERT INTO session_v2 (id, project_id, slug, directory, title, version, time_created, time_updated)"
               " VALUES (?,?,?,?,?,?,?,?)",
               (untitled, "p1", "bare-moth", "/work/echo", None, "2", ms(NOW - 2 * HOUR), ms(NOW - HOUR)))
    db.commit()
    db.close()

    doc = inventory(home, "--tool", "opencode")
    got = by_id(doc)
    assert set(got) == {ids["top"], ids["archived"], new, untitled}
    assert got[untitled]["title"] is None and got[untitled]["name"] == "bare-moth"
    s = got[new]
    assert s["name"] == "swift-hawk" and s["title"] == "title swift-hawk"
    assert s["spawn_dir"] == "/work/echo"
    assert s["resume"] == f"cd /work/echo && opencode --session {new}"
    assert got[ids["archived"]]["archived"] is True
    assert doc["census"]["opencode"]["hidden_subagents"] == 2


def test_opencode_legacy_only_rows_are_listed_without_commands(home):
    # OpenCode stops importing `session` into `session_v2` once its migration is marked done, so a row
    # written to the old table afterwards exists only there. List it, but offer no v2 command for it.
    ids, data = build_opencode(home)
    ms = lambda t: int(t * 1000)  # noqa: E731
    new = "ses_new0000000000000000000"
    db = sqlite3.connect(data / "opencode.db")
    db.execute(OPENCODE_V2_SCHEMA)
    db.execute("INSERT INTO session_v2 (id, project_id, parent_id, slug, directory, title, version,"
               " time_created, time_updated, time_archived)"
               " SELECT id, project_id, parent_id, slug, directory, title, version,"
               " time_created, time_updated, time_archived FROM session WHERE id = ?", (ids["top"],))
    db.execute("INSERT INTO session_v2 (id, project_id, slug, directory, title, version, time_created, time_updated)"
               " VALUES (?,?,?,?,?,?,?,?)", (new, "p1", "swift-hawk", "/work/echo", "t", "2",
                                             ms(NOW - 2 * HOUR), ms(NOW - HOUR)))
    db.commit()
    db.close()

    doc = inventory(home, "--tool", "opencode")
    got = by_id(doc)
    assert set(got) == {ids["top"], ids["archived"], new}  # the legacy-only child stays hidden
    legacy = got[ids["archived"]]
    assert legacy["resume"] is None and legacy["resume_blocked"] == "legacy_only"
    assert legacy["export_command"] is None
    assert got[new]["resume"] == f"cd /work/echo && opencode --session {new}"
    assert got[ids["top"]]["resume_blocked"] is None
    assert doc["sources"]["opencode"]["legacy_only"] == 2  # archived + the hidden child
    assert doc["census"]["opencode"]["hidden_subagents"] == 1


def test_opencode_v2_fork_keeps_its_lineage_and_stays_listed(home):
    ids, data = build_opencode(home)
    ms = lambda t: int(t * 1000)  # noqa: E731
    fork = "ses_fork000000000000000000"
    db = sqlite3.connect(data / "opencode.db")
    db.execute(OPENCODE_V2_SCHEMA.replace("parent_id TEXT,", "parent_id TEXT, fork_session_id TEXT,"))
    db.execute("INSERT INTO session_v2 (id, project_id, parent_id, slug, directory, title, version,"
               " time_created, time_updated, time_archived)"
               " SELECT id, project_id, parent_id, slug, directory, title, version,"
               " time_created, time_updated, time_archived FROM session")
    db.execute("INSERT INTO session_v2 (id, project_id, fork_session_id, slug, directory, title, version,"
               " time_created, time_updated) VALUES (?,?,?,?,?,?,?,?,?)",
               (fork, "p1", ids["top"], "keen-lark", "/work/delta", "forked", "2", ms(NOW - 2 * HOUR), ms(NOW - HOUR)))
    db.commit()
    db.close()

    doc = inventory(home, "--tool", "opencode")
    got = by_id(doc)
    assert got[fork]["lineage"] == {"kind": "fork", "parent_id": ids["top"]}
    assert got[fork]["resume"] == f"cd /work/delta && opencode --session {fork}"
    assert got[ids["top"]]["lineage"] is None
    assert doc["census"]["opencode"]["hidden_subagents"] == 1
    assert doc["sources"]["opencode"]["legacy_only"] == 0


def test_agy_extraction_workspace_variants_lineage_and_subagents(home, world):
    ids = world["agy"]
    doc = inventory(home, "--tool", "agy")
    got = by_id(doc)
    assert set(got) == {ids["main"], ids["preview_only"], ids["noworkspace"], ids["fork"]}
    s = got[ids["main"]]
    assert s["tool"] == "agy"
    assert s["name"] is None and s["name_resumable"] is False
    assert s["title"] == "Ship agy support"
    assert s["spawn_dir"] == "/work/zeta"
    assert s["created"].startswith(iso(NOW - 4 * HOUR)[:16])
    assert s["updated"].startswith(iso(NOW - 2 * HOUR)[:16])
    assert s["transcript"].endswith(f"brain/{ids['main']}/.system_generated/logs/transcript.jsonl")
    assert s["resume"] == f"cd /work/zeta && agy --conversation {ids['main']}"
    assert s["lineage"] is None

    prev = got[ids["preview_only"]]
    assert prev["title"] == "Preview becomes title"
    assert prev["spawn_dir"] == "/work/my agy repo"
    assert prev["created"] is None  # missing transcript must never fall back to last_modified_time
    assert prev["transcript"] is None
    assert prev["resume"] == f"cd '/work/my agy repo' && agy --conversation {ids['preview_only']}"

    nows = got[ids["noworkspace"]]
    assert nows["resume"] is None and nows["resume_blocked"] == "no_workspace"

    assert got[ids["fork"]]["lineage"] == {"kind": "fork", "parent_id": ids["main"]}
    assert doc["census"]["agy"]["hidden_subagents"] == 1

    with_subs = by_id(inventory(home, "--tool", "agy", "--include-subagents"))
    assert with_subs[ids["sub"]]["lineage"] == {"kind": "subagent", "parent_id": ids["main"]}


def test_agy_store_is_not_modified_and_handles_minimal_schema(home, world):
    db_path = home / ".gemini" / "antigravity-cli" / "conversation_summaries.db"
    before = db_path.read_bytes()
    inventory(home, "--tool", "agy")
    assert db_path.read_bytes() == before

    # Minimal schema without optional preview / parent_conversation_id / nesting_depth columns
    db_path.unlink()
    db = sqlite3.connect(db_path)
    db.execute(
        "CREATE TABLE conversation_summaries ("
        "conversation_id TEXT PRIMARY KEY, title TEXT, last_modified_time TEXT, workspace_uris TEXT)"
    )
    db.execute(
        "INSERT INTO conversation_summaries VALUES (?,?,?,?)",
        ("minimal-1", "Minimal row", iso(NOW - HOUR), "file:///work/min1\nfile:///work/min2"),
    )
    db.execute(
        "INSERT INTO conversation_summaries VALUES (?,?,?,?)",
        ("minimal-2", "Comma row", iso(NOW - 2 * HOUR), "file:///work/comma1,file:///work/comma2"),
    )
    db.execute(
        "INSERT INTO conversation_summaries VALUES (?,?,?,?)",
        ("minimal-3", "Plain path", iso(NOW - 3 * HOUR), "/work/plain"),
    )
    db.commit()
    db.close()
    got = by_id(inventory(home, "--tool", "agy"))
    assert got["minimal-1"]["spawn_dir"] == "/work/min1"
    assert got["minimal-2"]["spawn_dir"] == "/work/comma1"
    assert got["minimal-3"]["spawn_dir"] == "/work/plain"


def test_agy_resume_quotes_shell_metacharacters_in_conversation_id(home, world):
    db_path = home / ".gemini" / "antigravity-cli" / "conversation_summaries.db"
    crafted = "target; touch /tmp/x"
    db = sqlite3.connect(db_path)
    db.execute(
        "INSERT INTO conversation_summaries "
        "(conversation_id, title, last_modified_time, workspace_uris, last_user_input_time) "
        "VALUES (?,?,?,?,?)",
        (crafted, "Crafted ID", iso(NOW - HOUR), '["file:///work/zeta"]', iso(NOW - HOUR)),
    )
    db.commit()
    db.close()
    got = by_id(inventory(home, "--tool", "agy"))
    assert got[crafted]["resume"] == "cd /work/zeta && agy --conversation 'target; touch /tmp/x'"


def test_agy_truncated_line1_reads_only_top_level_created_at(home, world):
    db_path = home / ".gemini" / "antigravity-cli" / "conversation_summaries.db"
    cases = {
        "agy-trunc-nested-before": (
            '{"metadata":{"created_at":"2020-01-01T00:00:00Z"},'
            '"created_at":"2026-11-24T01:02:03Z","content":"' + ("x" * 70000) + '"}'
        ),
        "agy-trunc-nested-only": (
            '{"metadata":{"created_at":"2020-01-01T00:00:00Z"},"content":"'
            + ("x" * 70000)
            + '","created_at":"2026-11-24T01:02:03Z"}'
        ),
        "agy-trunc-in-string": (
            '{"content":"\\"created_at\\":\\"2020-01-01T00:00:00Z\\"' + ("x" * 70000) + '"}'
        ),
        "agy-trunc-epoch": (
            '{"note":"{\\"created_at\\":\\"2020-01-01T00:00:00Z\\"}",'
            '"created_at":1764000000,"content":"' + ("x" * 70000) + '"}'
        ),
        # Pad so byte 65536 lands inside the numeric timestamp `1764000000`
        "agy-trunc-cut-epoch": (
            '{"pad":"'
            + ("p" * (65536 - len('{"pad":"","created_at":176400')))
            + '","created_at":1764000000,"content":"tail"}'
        ),
    }
    db = sqlite3.connect(db_path)
    for sid, line in cases.items():
        db.execute(
            "INSERT INTO conversation_summaries "
            "(conversation_id, title, last_modified_time, workspace_uris, last_user_input_time) "
            "VALUES (?,?,?,?,?)",
            (sid, sid, iso(NOW - HOUR), '["file:///work/zeta"]', iso(NOW - HOUR)),
        )
        tpath = home / ".gemini/antigravity-cli/brain" / sid / ".system_generated/logs/transcript.jsonl"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text(line + "\n", encoding="utf-8")
    db.commit()
    db.close()

    got = by_id(inventory(home, "--tool", "agy"))
    assert got["agy-trunc-nested-before"]["created"] == "2026-11-24T01:02:03Z"
    assert got["agy-trunc-nested-only"]["created"] is None
    assert got["agy-trunc-in-string"]["created"] is None
    assert got["agy-trunc-epoch"]["created"] == "2025-11-24T16:00:00Z"
    assert got["agy-trunc-cut-epoch"]["created"] is None


def test_agy_schema_error_is_partial_failure(home, world):
    db = sqlite3.connect(home / ".gemini/antigravity-cli/conversation_summaries.db")
    db.execute("DROP TABLE conversation_summaries")
    db.execute("CREATE TABLE conversation_summaries (conversation_id TEXT PRIMARY KEY)")
    db.commit()
    db.close()
    r = run(home, "list", "--json")
    assert r.returncode == 1
    doc = json.loads(r.stdout)
    assert doc["sources"]["agy"]["status"] == "error"
    assert world["claude"]["renamed"] in by_id(doc)
    err = json.loads(r.stderr.strip().splitlines()[-1])
    assert err["error"]["code"] == "source_unreadable" and err["error"]["sources"] == ["agy"]


# --- filters --------------------------------------------------------------------

def test_tool_filter_is_repeatable(home, world):
    doc = inventory(home, "--tool", "muse", "--tool", "opencode")
    assert {s["tool"] for s in doc["sessions"]} == {"muse", "opencode"}
    assert set(doc["census"]) == {"muse", "opencode"}


def test_since_filters_on_last_activity(home, world):
    doc = inventory(home, "--since", "3h")
    got = by_id(doc)
    assert world["claude"]["renamed"] in got           # 1h ago
    assert world["claude"]["plain"] not in got         # 48h ago
    assert world["muse"]["stale"] not in got           # 30h ago


def test_sort_is_newest_first_and_deterministic(home, world):
    doc = inventory(home)
    keys = [(s["updated"], s["tool"], s["id"]) for s in doc["sessions"]]
    # ISO-8601 Z strings sort lexically; stable sort gives updated desc, then tool, then id
    expected = sorted(sorted(keys, key=lambda k: (k[1], k[2])), key=lambda k: k[0], reverse=True)
    assert keys == expected


# --- liveness -------------------------------------------------------------------

def test_nothing_running_means_live_no(home, world):
    doc = inventory(home)
    assert {s["live"] for s in doc["sessions"]} <= {"no", "unknown"}
    assert inventory(home, "--live")["sessions"] == []


def test_claude_registry_live_and_blocks_resume(home, world, procs):
    p = procs(["sleep", "60"])
    sid = world["claude"]["renamed"]
    reg = home / ".claude" / "sessions"
    reg.mkdir(parents=True)
    (reg / f"{p.pid}.json").write_text(json.dumps({
        "pid": p.pid, "procStart": utc_lstart(p.pid), "sessionId": sid, "cwd": "/work/alpha",
        "status": "busy", "name": "alpha-7e", "tmux": "main:@1.%1"}))
    s = by_id(inventory(home, "--live"))[sid]
    assert s["live"] == "yes" and s["pid"] == p.pid and s["tmux"] == "main:@1.%1"
    assert s["resume"] is None and s["resume_blocked"] == "running"


def test_claude_reused_pid_is_not_live(home, world, procs):
    p = procs(["sleep", "60"])
    sid = world["claude"]["renamed"]
    reg = home / ".claude" / "sessions"
    reg.mkdir(parents=True)
    (reg / f"{p.pid}.json").write_text(json.dumps({
        "pid": p.pid, "procStart": "Mon Jan  1 00:00:00 2024", "sessionId": sid}))
    s = by_id(inventory(home))[sid]
    assert s["live"] == "no" and s["resume"] is not None


def test_codex_held_lock_is_live(home, world, procs):
    ids = world["codex"]
    lock = home / ".codex" / "thread-writer-locks" / f"{ids['user']}.lock"
    procs([str(fake_tool(home / "bin", "codex")), str(lock)])
    got = by_id(inventory(home, "--tool", "codex"))
    assert got[ids["user"]]["live"] == "yes"
    assert got[ids["user"]]["live_host"] == "cli"
    assert got[ids["fork"]]["live"] == "no"            # lock file exists but nobody holds it


def test_codex_lock_held_by_app_server_is_labeled(home, world, procs):
    ids = world["codex"]
    lock = home / ".codex" / "thread-writer-locks" / f"{ids['user']}.lock"
    procs([str(fake_tool(home / "bin", "codex")), "app-server", str(lock)])
    s = by_id(inventory(home, "--tool", "codex"))[ids["user"]]
    assert s["live"] == "yes" and s["live_host"] == "app-server"
    assert s["resume"] is None and s["resume_blocked"] == "running"


def test_muse_lock_with_live_muse_process_is_live(home, world, procs):
    ids = world["muse"]
    p = procs([str(fake_tool(home / "bin", "muse"))])
    lock = next((home / ".local/share/muse/sessions").rglob(f"{ids['named']}/.session.lock"))
    lock.write_text(f"pid={p.pid}\nhost={socket.gethostname()}\n")
    got = by_id(inventory(home, "--tool", "muse"))
    assert got[ids["named"]]["live"] == "yes"
    assert got[ids["stale"]]["live"] == "no"            # stale lock, dead pid


def test_muse_versioned_binary_counts_as_muse(home, world, procs):
    # the `muse` launcher runs a versioned binary, e.g. muse-bin-1.3.0-R3401.1
    ids = world["muse"]
    p = procs([str(fake_tool(home / "bin", "muse-bin-1.3.0-R3401.1")), "resume", "copper-umbra"])
    lock = next((home / ".local/share/muse/sessions").rglob(f"{ids['named']}/.session.lock"))
    lock.write_text(f"pid={p.pid}\nhost={socket.gethostname()}\n")
    assert by_id(inventory(home, "--tool", "muse"))[ids["named"]]["live"] == "yes"


def test_muse_lock_pid_owned_by_other_program_is_not_live(home, world, procs):
    ids = world["muse"]
    p = procs(["sleep", "60"])                           # alive, but not muse
    lock = next((home / ".local/share/muse/sessions").rglob(f"{ids['named']}/.session.lock"))
    lock.write_text(f"pid={p.pid}\nhost={socket.gethostname()}\n")
    assert by_id(inventory(home, "--tool", "muse"))[ids["named"]]["live"] == "no"


def test_muse_lock_from_other_host_is_unknown(home, world):
    ids = world["muse"]
    lock = next((home / ".local/share/muse/sessions").rglob(f"{ids['named']}/.session.lock"))
    lock.write_text("pid=1\nhost=some-other-machine\n")
    assert by_id(inventory(home, "--tool", "muse"))[ids["named"]]["live"] == "unknown"


def test_opencode_process_with_session_arg_is_live(home, world, procs):
    ids = world["opencode"]
    procs([str(fake_tool(home / "bin", "opencode")), "--session", ids["top"]])
    assert by_id(inventory(home, "--tool", "opencode"))[ids["top"]]["live"] == "yes"


def test_opencode_process_in_directory_surfaces_a_signal(home, world, procs, tmp_path):
    # policy-agnostic: whatever opencode_directory_liveness decides, a bare
    # `opencode` running in the directory must not leave the newest session "no"
    ids = world["opencode"]
    workdir = tmp_path / "delta"
    workdir.mkdir()
    db = sqlite3.connect(home / ".local/share/opencode/opencode.db")
    db.execute("UPDATE session SET directory = ?", (str(workdir.resolve()),))
    db.commit()
    db.close()
    procs([str(fake_tool(home / "bin", "opencode"))], cwd=workdir)
    got = by_id(inventory(home, "--tool", "opencode"))
    s = got[ids["top"]]
    assert s["live"] != "no" and "opencode pid" in s["live_basis"]


def test_opencode_directory_fallback_marks_only_newest_unknown(home, world, procs, tmp_path):
    # owner decision (PR #86): without --session, only the newest top-level
    # session in the process's directory is `unknown`; older ones stay `no`
    ids = world["opencode"]
    workdir = tmp_path / "delta"
    workdir.mkdir()
    db = sqlite3.connect(home / ".local/share/opencode/opencode.db")
    db.execute("UPDATE session SET directory = ?", (str(workdir.resolve()),))
    db.commit()
    db.close()
    procs([str(fake_tool(home / "bin", "opencode"))], cwd=workdir)
    got = by_id(inventory(home, "--tool", "opencode"))
    assert got[ids["top"]]["live"] == "unknown"
    assert got[ids["top"]]["resume"] is not None       # unknown never blocks resume
    assert got[ids["archived"]]["live"] == "no"
    # --live keeps possibly-running sessions (PR #86 review, thread 4114456485)
    live_ids = set(by_id(inventory(home, "--tool", "opencode", "--live")))
    assert live_ids == {ids["top"]}


def test_agy_process_with_conversation_arg_is_live(home, world, procs):
    ids = world["agy"]
    p = procs([str(fake_tool(home / "bin", "agy")), "--conversation", ids["main"]])
    got = by_id(inventory(home, "--tool", "agy"))
    s = got[ids["main"]]
    assert s["live"] == "yes" and s["live_host"] == "cli" and s["pid"] == p.pid
    assert s["resume"] is None and s["resume_blocked"] == "running"
    assert got[ids["fork"]]["live"] == "no"


def test_agy_process_with_resume_short_and_equals_args_is_live(home, world, procs):
    ids = world["agy"]
    procs([str(fake_tool(home / "bin", "agy")), f"--resume={ids['main']}"])
    procs([str(fake_tool(home / "bin", "agy")), "-r", ids["fork"]])
    got = by_id(inventory(home, "--tool", "agy"))
    assert got[ids["main"]]["live"] == "yes"
    assert got[ids["fork"]]["live"] == "yes"


def test_agy_non_tui_subcommands_and_print_mode_do_not_trigger_liveness(home, world, procs, tmp_path):
    ids = world["agy"]
    workdir = tmp_path / "zeta"
    workdir.mkdir()
    db = sqlite3.connect(home / ".gemini/antigravity-cli/conversation_summaries.db")
    db.execute("UPDATE conversation_summaries SET workspace_uris = ?",
               (json.dumps([workdir.resolve().as_uri()]),))
    db.commit()
    db.close()
    exe = str(fake_tool(home / "bin", "agy"))
    procs([exe, "acp", "--stdio"], cwd=workdir)
    procs([exe, "plugin", "validate", "."], cwd=workdir)
    procs([exe, "-p", "quick question"], cwd=workdir)
    got = by_id(inventory(home, "--tool", "agy"))
    assert got[ids["main"]]["live"] == "no"
    assert got[ids["fork"]]["live"] == "no"


def test_agy_print_and_value_flag_arguments_are_not_mistaken_for_conversation_id(home, world, procs, tmp_path):
    ids = world["agy"]
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    exe = str(fake_tool(home / "bin", "agy"))
    procs([exe, "-p", f"--conversation={ids['main']}"], cwd=other_dir)
    procs([exe, "--prompt-interactive", f"--conversation={ids['main']}"], cwd=other_dir)
    procs([exe, "-p", f"--conversation={ids['main']}", "--conversation", ids["fork"]], cwd=other_dir)
    got = by_id(inventory(home, "--tool", "agy"))
    assert got[ids["main"]]["live"] == "no"
    assert got[ids["fork"]]["live"] == "yes"


def test_agy_directory_fallback_marks_only_newest_unknown(home, world, procs, tmp_path):
    ids = world["agy"]
    workdir = tmp_path / "zeta"
    workdir.mkdir()
    db = sqlite3.connect(home / ".gemini/antigravity-cli/conversation_summaries.db")
    db.execute("UPDATE conversation_summaries SET workspace_uris = ?",
               (json.dumps([workdir.resolve().as_uri()]),))
    db.commit()
    db.close()
    procs([str(fake_tool(home / "bin", "agy"))], cwd=workdir)
    got = by_id(inventory(home, "--tool", "agy"))
    assert got[ids["main"]]["live"] == "unknown"
    assert "agy pid" in got[ids["main"]]["live_basis"]
    assert got[ids["main"]]["resume"] is not None  # unknown never blocks resume
    assert got[ids["fork"]]["live"] == "no"        # older session stays "no"
    live_ids = set(by_id(inventory(home, "--tool", "agy", "--live")))
    assert live_ids == {ids["main"]}


# --- text output ----------------------------------------------------------------

def test_text_output_lines_and_census(home, world):
    r = run(home, "list", "--tool", "muse")
    assert r.returncode == 0
    lines = r.stdout.strip().splitlines()
    assert any(l.startswith("muse\t" + world["muse"]["named"]) and "copper-umbra" in l for l in lines)
    assert any(l.startswith("# census muse") for l in lines)
