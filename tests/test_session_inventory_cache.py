"""Parsed metadata caching must never cache process liveness or lose index rows."""

import importlib.machinery
import importlib.util
import json
import os
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
