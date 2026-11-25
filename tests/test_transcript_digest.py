"""tests/test_transcript_digest.py"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins/session/skills/session-recap/scripts/transcript_digest.py"
)

# Checked once, loudly. A missing script exits 2 with its message on stderr,
# which is indistinguishable from the NO_TRANSCRIPT case below and otherwise
# surfaces as an assertion against an empty stdout.
assert SCRIPT.is_file(), f"transcript_digest.py not found at {SCRIPT}"


def run(*args, env_extra=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_CODE_SESSION_ID", "ANTIGRAVITY_CONVERSATION_ID", "ANTIGRAVITY_APP_DATA_DIR")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)


def rec(role, text, ts, cwd="/r/a", branch="main", side=False):
    return {
        "type": role,
        "isSidechain": side,
        "timestamp": ts,
        "cwd": cwd,
        "gitBranch": branch,
        "message": {"role": role, "content": text},
    }


def write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_scope_view(tmp_path):
    f = tmp_path / "t.jsonl"
    write_jsonl(
        f,
        [
            rec("user", "start", "2026-07-22T10:00:00Z"),
            rec("assistant", "[tool: Bash]", "2026-07-22T10:05:00Z"),
            rec("user", "moved", "2026-07-22T11:00:00Z", cwd="/r/b", branch="feat/x"),
            rec("user", "side noise", "2026-07-22T11:01:00Z", cwd="/r/side", side=True),
            rec("assistant", "no branch info", "2026-07-22T11:30:00Z", cwd="/r/c", branch=None),
            rec("user", "back to a", "2026-07-22T12:00:00Z"),
            {"type": "worktree-state", "worktreeSession": {}, "sessionId": "s"},
            {"type": "relocated", "relocatedCwd": "/r/b", "sessionId": "s"},
        ],
    )
    out = run("--scope", str(f)).stdout
    assert "/r/a" in out and "main" in out
    assert "/r/b" in out and "feat/x" in out
    assert "/r/side" not in out  # sidechain excluded
    assert "/r/c" not in out  # missing gitBranch: skipped for scope purposes
    assert "worktree-state events: 1" in out
    assert "relocations: 1" in out
    # a -> b -> a: a's span (first->last seen) must extend past b's first-seen,
    # while transcript-order (first-seen) placement is unaffected.
    assert "[07-22 10:00 → 07-22 12:00] /r/a · main" in out
    assert "[07-22 11:00] /r/b · feat/x" in out
    assert "None" not in out  # missing-field pairs never render as "None · None"


def test_days_view(tmp_path):
    f = tmp_path / "t.jsonl"
    write_jsonl(
        f,
        [
            rec("user", "day one a", "2026-07-22T10:00:00Z"),
            rec("assistant", "reply", "2026-07-22T10:10:00Z"),
            rec("user", "day two", "2026-07-23T09:00:00Z"),
        ],
    )
    out = run("--days", str(f)).stdout
    assert "2026-07-22" in out and "2026-07-23" in out
    assert "2 turns" in out and "1 turns" in out


def test_find_view_case_insensitive(tmp_path):
    f = tmp_path / "t.jsonl"
    write_jsonl(
        f,
        [
            rec(
                "user", "yes, add a hits/blocked Counter to the middleware", "2026-07-22T21:14:00Z"
            ),
            rec("assistant", "unrelated", "2026-07-22T21:15:00Z"),
        ],
    )
    out = run("--find", "counter", str(f)).stdout
    assert "hits/blocked Counter" in out
    assert "user" in out and "07-22 21:14" in out
    assert "(1)" in out  # match count in header


def test_default_digest_excludes_sidechain(tmp_path):
    f = tmp_path / "t.jsonl"
    write_jsonl(
        f,
        [
            rec("user", "real", "2026-07-22T10:00:00Z"),
            rec("user", "noise", "2026-07-22T10:01:00Z", side=True),
        ],
    )
    out = run(str(f)).stdout
    assert "total_turns: 1" in out


def test_no_transcript_missing_file(tmp_path):
    missing = tmp_path / "does-not-exist.jsonl"
    result = run(str(missing))
    assert result.returncode == 2
    assert "NO_TRANSCRIPT" in result.stderr


def test_malformed_line_tolerance(tmp_path):
    f = tmp_path / "t.jsonl"
    lines = [
        json.dumps(rec("user", "before the garbage", "2026-07-22T10:00:00Z")),
        "{not valid json,,,",
        json.dumps(rec("user", "after the garbage", "2026-07-22T10:05:00Z")),
    ]
    f.write_text("\n".join(lines) + "\n")
    result = run(str(f))
    assert result.returncode == 0
    assert "total_turns: 2" in result.stdout


def test_prompts_only_view(tmp_path):
    f = tmp_path / "t.jsonl"
    write_jsonl(
        f,
        [
            rec("user", "please add a retry wrapper to the login flow", "2026-07-22T10:00:00Z"),
            rec("user", "[tool result]", "2026-07-22T10:01:00Z"),
        ],
    )
    out = run("--prompts-only", str(f)).stdout
    assert "please add a retry wrapper to the login flow" in out
    assert "[tool result]" not in out


def agy_records():
    return [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-11-25T10:00:00Z",
            "content": "<USER_REQUEST>\nImplement ENG-42 per docs/spec.md\n</USER_REQUEST>\n"
                       "<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-25\n</ADDITIONAL_METADATA>",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-11-25T10:02:00Z",
            "content": "Checking the spec first.",
            "tool_calls": [{"name": "read_file", "args": {"Path": '"docs/spec.md"'}}],
        },
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-11-25T10:02:05Z",
            "content": "Created At: ...\nCompleted At: ...\nSpec contents",
        },
        {
            "step_index": 3,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-11-25T10:05:00Z",
            "content": "Done implementing ENG-42.",
        },
    ]


def test_agy_transcript_digest_direct_and_scope(tmp_path):
    f = tmp_path / "transcript.jsonl"
    write_jsonl(f, agy_records())
    res = run(str(f))
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "total_turns: 3" in out  # USER_INPUT + 2 PLANNER_RESPONSE (GENERIC omitted)
    assert "Implement ENG-42 per docs/spec.md" in out
    assert "<ADDITIONAL_METADATA>" not in out
    assert "ENG-42" in out and "docs/spec.md" in out
    assert "[tool: read_file]" in out

    scope_out = run("--scope", str(f)).stdout
    assert "Antigravity transcripts do not record per-turn cwd/gitBranch" in scope_out

    prompts_out = run("--prompts-only", str(f)).stdout
    assert "Implement ENG-42 per docs/spec.md" in prompts_out


def test_agy_auto_detect_env_and_db_title_and_full_find(tmp_path):
    app_dir = tmp_path / "antigravity-cli"
    cid = "2c8e9676-a98c-4595-b618-d4e53715f32b"
    logs = app_dir / "brain" / cid / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    write_jsonl(logs / "transcript.jsonl", agy_records())
    full_recs = agy_records()
    full_recs[3]["content"] = "Done implementing ENG-42 with secret-full-only-needle."
    write_jsonl(logs / "transcript_full.jsonl", full_recs)

    db = sqlite3.connect(app_dir / "conversation_summaries.db")
    db.execute("CREATE TABLE conversation_summaries (conversation_id TEXT PRIMARY KEY, title TEXT, preview TEXT)")
    db.execute("INSERT INTO conversation_summaries VALUES (?, ?, ?)", (cid, "Add Antigravity support", ""))
    db.commit()
    db.close()

    env = {"ANTIGRAVITY_CONVERSATION_ID": cid, "ANTIGRAVITY_APP_DATA_DIR": str(app_dir)}
    res = run(env_extra=env)
    assert res.returncode == 0, res.stderr
    assert "title: Add Antigravity support" in res.stdout
    assert "Implement ENG-42 per docs/spec.md" in res.stdout

    find_res = run("--find", "secret-full-only-needle", env_extra=env)
    assert find_res.returncode == 0
    assert "(1)" in find_res.stdout and "secret-full-only-needle" in find_res.stdout
