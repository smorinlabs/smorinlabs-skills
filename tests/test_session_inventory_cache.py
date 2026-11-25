"""Parsed metadata caching must never cache process liveness or lose index rows."""

import importlib.machinery
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[1] / "plugins/session/skills/session-agent-list"
          / "scripts/session-inventory")
loader = importlib.machinery.SourceFileLoader("session_inventory_cached", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
inventory = importlib.util.module_from_spec(spec)
loader.exec_module(inventory)

SID = "11111111-1111-4111-8111-111111111111"


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def claude_file(home):
    return write_lines(home / ".claude/projects/example" / f"{SID}.jsonl", [
        {"type": "user", "cwd": "/work/example", "gitBranch": "main",
         "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "custom-title", "customTitle": "First title"},
        {"type": "ai-title", "aiTitle": "Example task"},
    ])


def codex_file(home):
    return write_lines(home / ".codex/sessions/2026/01/01" / f"rollout-{SID}.jsonl", [
        {"type": "session_meta", "payload": {"id": SID, "cwd": "/work/example",
         "timestamp": "2026-01-01T00:00:00Z", "source": "cli"}},
    ])


@pytest.fixture
def roots(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(inventory, "claude_registry", lambda _: {})
    monkeypatch.setattr(inventory, "codex_held_locks", lambda _: {})
    return home, tmp_path / "cache"


def test_unchanged_metadata_skips_file_reads_and_json_parsing(roots, monkeypatch):
    home, cache_dir = roots
    claude_file(home)
    codex_file(home)
    write_lines(home / ".codex/session_index.jsonl", [{"id": SID, "thread_name": "Named"}])
    first = inventory.MetadataCache(cache_dir)
    claude, _ = inventory.scan_claude(home, first)
    codex, _, _ = inventory.scan_codex(home, {}, first)
    first.save()
    second = inventory.MetadataCache(cache_dir)

    def reject_parse(_):
        raise AssertionError("unchanged metadata was parsed again")

    monkeypatch.setattr(second, "parse", reject_parse)
    assert inventory.scan_claude(home, second)[0] == claude
    assert inventory.scan_codex(home, {}, second)[0] == codex
    assert second.stats["hits"] == 3
    assert second.stats["parsed_records"] == second.stats["bytes_read"] == 0


def test_claude_append_updates_title_and_retries_partial_record(roots):
    home, cache_dir = roots
    path = claude_file(home)
    cache = inventory.MetadataCache(cache_dir)
    inventory.scan_claude(home, cache)
    cache.save()
    with path.open("ab") as fh:
        fh.write(b'{"type":"custom-title","customTitle":"New')
    partial = inventory.MetadataCache(cache_dir)
    assert inventory.scan_claude(home, partial)[0][0]["name"] == "First title"
    partial.save()
    with path.open("ab") as fh:
        fh.write(b' title"}\n')
    updated = inventory.MetadataCache(cache_dir)
    assert inventory.scan_claude(home, updated)[0][0]["name"] == "New title"
    assert updated.stats["parsed_files"] == 1


def test_codex_nonmetadata_append_reuses_parsed_head(roots):
    home, cache_dir = roots
    path = codex_file(home)
    first = inventory.MetadataCache(cache_dir)
    inventory.scan_codex(home, {}, first)
    first.save()
    with path.open("ab") as fh:
        fh.write(b'{"type":"response_item","payload":{"role":"assistant"}}\n')
    second = inventory.MetadataCache(cache_dir)
    assert inventory.scan_codex(home, {}, second)[0][0]["spawn_dir"] == "/work/example"
    assert second.stats["misses"] == 1
    assert second.stats["sections_reused"] == 1
    assert second.stats["parsed_files"] == second.stats["parsed_records"] == 0


def test_names_cursor_parses_append_only_and_keeps_partial_line(roots):
    home, cache_dir = roots
    root = home / ".codex"
    path = write_lines(root / "session_index.jsonl", [{"id": SID, "thread_name": "First"}])
    first = inventory.MetadataCache(cache_dir)
    assert inventory.codex_names(root, first) == {SID: "First"}
    first.save()
    with path.open("ab") as fh:
        fh.write(b'{"id":"second","thread_name":"Sec')
    partial = inventory.MetadataCache(cache_dir)
    assert inventory.codex_names(root, partial) == {SID: "First"}
    partial.save()
    with path.open("ab") as fh:
        fh.write(b'ond"}\n')
    second = inventory.MetadataCache(cache_dir)
    assert inventory.codex_names(root, second) == {SID: "First", "second": "Second"}
    assert second.stats["parsed_records"] == 1
    assert second.stats["index_appends"] == 1


def test_valid_unterminated_index_row_is_provisional_until_next_append(roots):
    home, cache_dir = roots
    root = home / ".codex"
    path = write_lines(root / "session_index.jsonl", [{"id": SID, "thread_name": "First"}])
    with path.open("a") as fh:
        fh.write('{"id":"second","thread_name":"Second"}')
    first = inventory.MetadataCache(cache_dir)
    assert inventory.codex_names(root, first)["second"] == "Second"
    first.save()
    # Appending malformed text changes that formerly valid unterminated line.
    with path.open("a") as fh:
        fh.write('garbage\n')
    second = inventory.MetadataCache(cache_dir)
    assert inventory.codex_names(root, second) == {SID: "First"}


@pytest.mark.parametrize("change", ["truncate", "replace", "rewrite_and_grow"])
def test_names_cursor_rejects_changed_prefix_and_removed_records(roots, change):
    home, cache_dir = roots
    root = home / ".codex"
    path = write_lines(root / "session_index.jsonl", [
        {"id": SID, "thread_name": "Old"}, {"id": "deleted", "thread_name": "Removed"}])
    first = inventory.MetadataCache(cache_dir)
    inventory.codex_names(root, first)
    first.save()
    value = "New" + (" long replacement" * 30 if change == "rewrite_and_grow" else "")
    if change == "replace":
        path.unlink()
    write_lines(path, [{"id": SID, "thread_name": value}])
    second = inventory.MetadataCache(cache_dir)
    assert inventory.codex_names(root, second) == {SID: value}
    assert second.stats["parsed_records"] == 1


def test_transcript_replacement_and_same_size_edit_invalidate(roots):
    home, cache_dir = roots
    path = claude_file(home)
    first = inventory.MetadataCache(cache_dir)
    inventory.scan_claude(home, first)
    first.save()
    original = path.stat()
    path.write_text(path.read_text().replace("First title", "Other title"))
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    second = inventory.MetadataCache(cache_dir)
    assert inventory.scan_claude(home, second)[0][0]["name"] == "Other title"
    second.save()
    path.unlink()
    write_lines(path, [{"cwd": "/work/replaced", "timestamp": "2026-01-01T00:00:00Z"}])
    third = inventory.MetadataCache(cache_dir)
    assert inventory.scan_claude(home, third)[0][0]["spawn_dir"] == "/work/replaced"


def test_cached_metadata_still_refreshes_claude_and_codex_liveness(roots, monkeypatch):
    home, cache_dir = roots
    claude_file(home)
    codex_file(home)
    first = inventory.MetadataCache(cache_dir)
    inventory.scan_claude(home, first)
    inventory.scan_codex(home, {}, first)
    first.save()
    monkeypatch.setattr(inventory, "claude_registry", lambda _: {SID: {"pid": 100, "name": "Registry"}})
    monkeypatch.setattr(inventory, "codex_held_locks", lambda _: {SID: 200})
    second = inventory.MetadataCache(cache_dir)
    claude = inventory.scan_claude(home, second)[0][0]
    codex = inventory.scan_codex(home, {200: ["codex", "app-server"]}, second)[0][0]
    assert claude["live"] == codex["live"] == "yes"
    assert claude["resume"] is codex["resume"] is None
    assert claude["pid"] == 100 and codex["pid"] == 200
    assert codex["live_host"] == "app-server"
    assert second.stats["parsed_records"] == 0


@pytest.mark.parametrize("damage", ["json", "version", "entry"])
def test_cache_corruption_or_version_change_falls_back_to_source(roots, damage):
    home, cache_dir = roots
    claude_file(home)
    first = inventory.MetadataCache(cache_dir)
    expected = inventory.scan_claude(home, first)[0]
    first.save()
    if damage == "json":
        first.path.write_text('{"entries":')
    else:
        doc = json.loads(first.path.read_text())
        if damage == "version":
            doc["parser_version"] = 999
        else:
            next(iter(doc["entries"].values()))["value"]["spawn_dir"] = "/incorrect"
        first.path.write_text(json.dumps(doc))
    second = inventory.MetadataCache(cache_dir)
    assert inventory.scan_claude(home, second)[0] == expected
    assert second.report()["status"] == "degraded"
    assert second.stats["parsed_records"] > 0


def test_force_refresh_reparses_and_default_cli_has_no_cache_field(roots):
    home, cache_dir = roots
    claude_file(home)
    first = inventory.MetadataCache(cache_dir)
    inventory.scan_claude(home, first)
    first.save()
    forced = inventory.MetadataCache(cache_dir, refresh=True)
    inventory.scan_claude(home, forced)
    assert forced.stats["hits"] == 0 and forced.stats["parsed_files"] == 1
    result = subprocess.run([sys.executable, str(SCRIPT), "list", "--json", "--tool", "claude"],
                            capture_output=True, text=True, check=True)
    assert set(json.loads(result.stdout)) == {"sessions", "census", "sources"}


def test_refresh_requires_cache_directory(roots):
    result = subprocess.run([sys.executable, str(SCRIPT), "list", "--refresh-cache"],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "--refresh-cache requires --cache-dir" in result.stderr


def test_cache_write_failure_does_not_discard_current_source_data(roots):
    home, cache_dir = roots
    claude_file(home)
    cache_dir.write_text("not a directory")
    cache = inventory.MetadataCache(cache_dir)
    assert inventory.scan_claude(home, cache)[0][0]["name"] == "First title"
    cache.save()
    assert cache.report()["status"] == "degraded"


def test_source_write_during_collection_is_not_saved_under_later_fingerprint(roots):
    home, cache_dir = roots
    path = home / "moving.jsonl"
    path.write_text('{"value":"before"}\n')
    first = inventory.MetadataCache(cache_dir)

    def racing_loader(previous, entry):
        value = first.parse(path.read_bytes())
        path.write_text('{"value":"after"}\n')
        return value

    assert first.read(path, "test", racing_loader) == {"value": "before"}
    assert first.stats["raced_files"] == 1
    first.save()
    second = inventory.MetadataCache(cache_dir)
    assert second.read(path, "test", lambda *_: second.parse(path.read_bytes())) == {"value": "after"}
    assert second.stats["hits"] == 0


def test_deleted_source_after_read_preserves_metadata_and_evicts_cache(roots):
    home, cache_dir = roots
    path = home / "deleted-after-read.jsonl"
    path.write_text('{"value":"old"}\n')
    cache = inventory.MetadataCache(cache_dir)
    cache.read(path, "test", lambda *_: cache.parse(path.read_bytes()))
    assert cache.entries
    path.write_text('{"value":"new observation"}\n')

    def deleting_loader(previous, entry):
        value = cache.parse(path.read_bytes())
        path.unlink()
        return value

    assert cache.read(path, "test", deleting_loader) == {"value": "new observation"}
    assert cache.stats["raced_files"] == 1
    assert cache.entries == {}


def agy_store(home: Path, sid: str = SID) -> Path:
    root = home / ".gemini" / "antigravity-cli"
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "conversation_summaries.db")
    db.execute(
        "CREATE TABLE conversation_summaries ("
        "conversation_id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', "
        "preview TEXT NOT NULL DEFAULT '', last_modified_time DATETIME NOT NULL, "
        "workspace_uris TEXT NOT NULL, parent_conversation_id TEXT NOT NULL DEFAULT '', "
        "nesting_depth INTEGER NOT NULL DEFAULT 0)"
    )
    db.execute(
        "INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?)",
        (sid, "Cached agy session", "", "2026-11-25T04:00:00Z", '["file:///work/example"]', "", 0),
    )
    db.commit()
    db.close()
    tpath = root / "brain" / sid / ".system_generated" / "logs" / "transcript.jsonl"
    return write_lines(tpath, [
        {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT",
         "created_at": "2026-11-25T03:02:49Z", "content": "hello"},
    ])


def test_agy_created_cache_hits_and_append_reuses_head_section(roots, monkeypatch):
    home, cache_dir = roots
    tpath = agy_store(home)
    first = inventory.MetadataCache(cache_dir)
    recs, src, hidden = inventory.scan_agy(home, {}, first)
    assert src["status"] == "ok" and hidden == 0
    assert recs[0]["created"] == "2026-11-25T03:02:49Z"
    assert first.stats["parsed_files"] == 1
    first.save()

    second = inventory.MetadataCache(cache_dir)
    monkeypatch.setattr(second, "parse", lambda _: (_ for _ in ()).throw(AssertionError("reparsed")))
    recs2, _, _ = inventory.scan_agy(home, {}, second)
    assert recs2 == recs
    assert second.stats["hits"] == 1
    assert second.stats["bytes_read"] == second.stats["parsed_records"] == 0

    # Appending turn 1 changes stat signature, but line 1 hash matches -> section reused without parsing!
    with tpath.open("ab") as fh:
        fh.write(b'{"step_index":1,"source":"MODEL","type":"PLANNER_RESPONSE","status":"DONE","content":"hi"}\n')
    third = inventory.MetadataCache(cache_dir)
    monkeypatch.setattr(third, "parse", lambda _: (_ for _ in ()).throw(AssertionError("reparsed head")))
    recs3, _, _ = inventory.scan_agy(home, {}, third)
    assert recs3[0]["created"] == "2026-11-25T03:02:49Z"
    assert third.stats["misses"] == 1 and third.stats["sections_reused"] == 1
    assert third.stats["parsed_records"] == 0
    third.save()

    # Liveness is never cached: passing a live agy process flips live to yes on warm cache
    fourth = inventory.MetadataCache(cache_dir)
    recs4, _, _ = inventory.scan_agy(home, {4321: ["agy", "--conversation", SID]}, fourth)
    assert recs4[0]["live"] == "yes" and recs4[0]["pid"] == 4321 and recs4[0]["resume"] is None
    assert fourth.stats["hits"] == 1


def test_agy_3tier_liveness_unit_in_sandbox(roots, monkeypatch):
    home, _ = roots
    agy_store(home, SID)
    db = sqlite3.connect(home / ".gemini/antigravity-cli/conversation_summaries.db")
    older = "22222222-2222-4222-8222-222222222222"
    db.execute(
        "INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?)",
        (older, "Older", "", "2026-11-25T01:00:00Z", '["file:///work/example"]', "", 0),
    )
    db.commit()
    db.close()

    monkeypatch.setattr(inventory, "process_cwd", lambda pid: "/work/example" if pid == 77 else None)
    # Tier 2 bare agy: only newest is unknown; non-TUI subcommands & -p print mode ignored
    procs = {
        77: ["/opt/local/bin/agy", "-c"],
        88: ["agy", "acp", "--stdio"],
        89: ["agy", "-p", "hi"],
    }
    recs, _, _ = inventory.scan_agy(home, procs)
    by = {r["id"]: r for r in recs}
    assert by[SID]["live"] == "unknown" and by[SID]["resume"] is not None
    assert by[older]["live"] == "no"

    # Tier 1 explicit --conversation / --resume / -r overrides to live=yes and blocks resume
    recs2, _, _ = inventory.scan_agy(home, {99: ["agy", "--resume", older]})
    by2 = {r["id"]: r for r in recs2}
    assert by2[older]["live"] == "yes" and by2[older]["pid"] == 99 and by2[older]["resume_blocked"] == "running"
    assert by2[SID]["live"] == "no"
