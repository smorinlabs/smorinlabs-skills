"""Behavioral contracts for snapshots, updates, adapters, imports, and offline HTML."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/session/skills/session-map/scripts"
sys.path.insert(0, str(SCRIPTS))
from session_map import state
from session_map import collect as collectors
from session_map.cli import main
from session_map.migrate import import_prototype
from session_map.projects import parse_plan, collect_projects
from session_map.render import render


def baseline():
    data = state.new_map({"sources": [], "roots": [], "herdr_sessions": []})
    fresh = {"locations": {"loc:a": {"id": "loc:a", "source_id": "test", "title": "Implementation",
        "cwd": "/work/demo", "project_ids": ["project:a"], "evidence": "Working on P01-T01",
        "navigation": {"command": "rex select exact-id", "validated_at": "earlier"}}},
        "projects": {"project:a": {"id": "project:a", "source_id": "test", "title": "Demo",
                                    "session_ids": ["loc:a"], "plan_ids": []}}}
    return state.reconcile(data, fresh, {"test": {"status": "ok"}}, {}, full=True)


def assessments(data):
    return {"generation_id": data["generation_id"], "assessments": [
        {"id": key, "evidence_hash": row["evidence_hash"], "status": "Working", "summary": "Implementation active",
         "next_action": "Finish P01-T01", "rationale": "Current terminal evidence", "closure": "keep",
         "project_ids": ["project:a"], "owner_ids": ["loc:a"], "evidence_ids": ["loc:a", "project:a"]}
        for key, row in state.entities(data).items()]}


def observed(data):
    return {kind: {key: copy.deepcopy(row) for key, row in data[kind].items()} for kind in state.KINDS}


def test_no_change_retains_assessment_and_ignores_navigation_check_time():
    data = baseline()
    data = state.apply_assessments(data, assessments(data))
    fresh = observed(data)
    fresh["locations"]["loc:a"]["navigation"]["validated_at"] = "later"
    updated = state.reconcile(data, fresh, {"test": {"status": "ok"}}, {})
    assert updated["changes"]["changed"] == []
    assert updated["changes"]["reassess"] == []
    assert updated["locations"]["loc:a"]["assessment"] == data["locations"]["loc:a"]["assessment"]


def test_changed_session_invalidates_project_dependency():
    data = baseline()
    data = state.apply_assessments(data, assessments(data))
    fresh = observed(data)
    fresh["locations"]["loc:a"]["evidence"] = "Implementation handed off for review"
    updated = state.reconcile(data, fresh, {"test": {"status": "ok"}}, {})
    assert set(updated["changes"]["reassess"]) == {"loc:a", "project:a"}
    assert updated["projects"]["project:a"]["assessment"]["freshness"] == "stale"


@pytest.mark.parametrize("status,complete,presence", [("error", False, "stale"), ("partial", False, "stale"),
    ("ok", True, "not_observed"), ("absent", False, "stale")])
def test_source_failure_and_successful_disappearance_are_distinct(status, complete, presence):
    data = baseline()
    updated = state.reconcile(data, {}, {"test": {"status": status, "complete": complete}}, {})
    row = updated["locations"]["loc:a"]
    assert row["presence"] == presence
    assert row["evidence"] == data["locations"]["loc:a"]["evidence"]
    assert row["navigation"] is None
    assert not row.get("assessment", {})


def test_uncovered_source_is_not_removed_by_scoped_update():
    data = baseline()
    updated = state.reconcile(data, {}, {}, {}, scope={"project": "different"})
    assert updated["locations"]["loc:a"]["presence"] == "observed"
    assert updated["locations"]["loc:a"]["observed_at"] == data["locations"]["loc:a"]["observed_at"]


def test_failed_pane_capture_preserves_previous_evidence():
    data = baseline()
    fresh = {"locations": {"loc:a": {"id": "loc:a", "source_id": "test", "error": "timeout", "evidence": ""}}}
    updated = state.reconcile(data, fresh, {"test": {"status": "partial", "complete": False}}, {})
    assert updated["locations"]["loc:a"]["evidence"] == "Working on P01-T01"
    assert updated["locations"]["loc:a"]["presence"] == "stale"


def test_stale_assessment_batch_rejected_without_mutation():
    data = baseline()
    payload = assessments(data)
    payload["assessments"][1]["evidence_hash"] = "outdated"
    with pytest.raises(ValueError, match="changed"):
        state.apply_assessments(data, payload)
    assert data["locations"]["loc:a"]["assessment"] is None
    payload["generation_id"] = "old"
    with pytest.raises(ValueError, match="generation"):
        state.apply_assessments(data, payload)


def test_annotation_survives_full_and_invalidates_related_assessments():
    data = baseline()
    data = state.apply_assessments(data, assessments(data))
    data = state.annotate(data, "loc:a", {"title": "Owner session", "notes": "Keep this session"}, data["generation_id"])
    assert data["projects"]["project:a"]["assessment_needed"]
    fresh = observed(data)
    updated = state.reconcile(data, fresh, {"test": {"status": "ok"}}, {}, full=True)
    assert updated["locations"]["loc:a"]["overrides"]["notes"] == "Keep this session"
    assert updated["locations"]["loc:a"]["title"] == "Implementation"


def test_saved_render_has_no_collector_calls(tmp_path, monkeypatch, capsys):
    data = baseline()
    state.save(tmp_path, data)
    import session_map.cli as cli
    monkeypatch.setattr(cli, "collect", lambda *a, **kw: pytest.fail("render performed discovery"))
    before = (tmp_path / "inventory.json").read_bytes()
    assert main(["render", "--map-dir", str(tmp_path), "--no-open"]) == 0
    assert (tmp_path / "inventory.json").read_bytes() == before
    assert json.loads(capsys.readouterr().out)["generation_id"] == data["generation_id"]
    assert data["generation_id"] in (tmp_path / "index.html").read_text()


def test_atomic_render_preserves_previous_html_on_failure(tmp_path, monkeypatch):
    data = baseline()
    render(data, tmp_path)
    previous = (tmp_path / "index.html").read_bytes()
    import session_map.render as module
    monkeypatch.setattr(module, "atomic", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        render(data, tmp_path)
    assert (tmp_path / "index.html").read_bytes() == previous


def test_html_escapes_script_closure_and_preserves_exact_commands(tmp_path):
    data = baseline()
    data["locations"]["loc:a"]["evidence"] = '</script><script>alert("owned")</script>&'
    data["locations"]["loc:a"]["navigation"]["command"] = "'/path with spaces/rex' select 'full-id'"
    html = render(data, tmp_path).read_text()
    embedded = html.split('<script id="inventory" type="application/json">', 1)[1].split('</script>', 1)[0]
    parsed = json.loads(embedded)
    assert '</script><script>alert' not in html
    assert parsed["locations"]["loc:a"]["evidence"] == data["locations"]["loc:a"]["evidence"]
    assert parsed["locations"]["loc:a"]["navigation"]["command"] == "'/path with spaces/rex' select 'full-id'"


def test_map_lock_excludes_second_writer_and_releases(tmp_path):
    with state.locked(tmp_path):
        with pytest.raises(ValueError, match="writer lock"):
            with state.locked(tmp_path):
                pass
    with state.locked(tmp_path):
        pass


def test_unknown_schema_never_overwritten(tmp_path):
    path = tmp_path / "inventory.json"
    path.write_text('{"schema_version": 999}')
    original = path.read_bytes()
    assert main(["full", "--map-dir", str(tmp_path), "--no-open"]) == 2
    assert path.read_bytes() == original


def test_snapshot_generation_cannot_escape_output_directory(tmp_path):
    data = baseline()
    data["generation_id"] = "../../escaped"
    (tmp_path / "inventory.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="UUID"):
        state.save(tmp_path, baseline())
    assert not (tmp_path.parent / "escaped.json").exists()


def test_missing_native_collector_marks_existing_tool_records_unavailable(tmp_path, monkeypatch):
    data = baseline()
    data["sources"]["native:codex"] = {"status": "ok"}
    monkeypatch.setattr(collectors, "resolve_inventory", lambda: None)
    _, sources = collectors.native(data, tmp_path, False, {})
    assert sources["native:codex"]["status"] == "unavailable"


def test_plan_counts_scope_conflicts_and_examples():
    text = '''## [x] Project P01: Example
- [x] [P01-T01] Implement
- [ ] [P01-TS01] Verify
- [~] [P01-T02] In progress
- [-] [P01-T03] Retired
- [>] [P01-T04] Successor
- [ ] P01-T01 contradictory duplicate
- [ ] Manual acceptance
```markdown
- [ ] P01-T99 example only
```
## [ ] Project P02: Next
- [ ] P02-T01 Another project
'''
    result = parse_plan(Path('/work/PROJECTS.md'), text)
    first = result["phases"][0]
    assert first["counts"] == {"complete": 0, "open": 1, "in_progress": 1, "retired": 1,
        "redirected": 1, "unknown": 0, "conflict": 1, "total": 5, "implementation": 4, "tests": 1}
    assert first["conflict"]
    assert len(first["acceptance"]) == 1
    assert result["phases"][1]["tasks"][0]["id"] == "P02-T01"


def test_plan_cache_reuses_unchanged_body_and_refreshes_changed(tmp_path):
    path = tmp_path / "PROJECTS.md"
    path.write_text('## [ ] P01: Demo\n- [ ] P01-T01 Work\n')
    data = state.new_map({"roots": [str(tmp_path)], "sources": []})
    metrics = {"plans_parsed": 0, "plan_cache_hits": 0}
    projects, plans, src = collect_projects(data["config"], [], data, True, None, metrics)
    data = state.reconcile(data, {"projects": projects, "plans": plans}, src, metrics)
    assert metrics["plans_parsed"] == 1
    metrics = {"plans_parsed": 0, "plan_cache_hits": 0}
    collect_projects(data["config"], [], data, False, None, metrics)
    assert metrics == {"plans_parsed": 0, "plan_cache_hits": 1}
    path.write_text(path.read_text().replace('[ ] P01-T01','[x] P01-T01'))
    metrics = {"plans_parsed": 0, "plan_cache_hits": 0}
    _, changed, _ = collect_projects(data["config"], [], data, False, None, metrics)
    assert metrics["plans_parsed"] == 1
    assert next(iter(changed.values()))["phases"][0]["counts"]["complete"] == 1


def test_transcript_tail_cache_and_partial_records(tmp_path):
    path = tmp_path / "conversation.jsonl"
    lines = [json.dumps({"type": "user", "message": {"content": "start"}})]
    lines.extend(json.dumps({"type": "tool_result", "text": "padding" * 1000}) for _ in range(10))
    lines.append(json.dumps({"type": "assistant", "message": {"content": "last action"}}))
    path.write_text('\n'.join(lines)+'\n{"incomplete":')
    metrics = {"excerpt_cache_hits": 0, "excerpts_parsed": 0}
    first = collectors.text_excerpt(str(path), None, False, metrics)
    assert "last action" in first["text"]
    second = collectors.text_excerpt(str(path), first, False, metrics)
    assert second == first
    assert metrics == {"excerpt_cache_hits": 1, "excerpts_parsed": 1}


def test_import_preserves_data_but_disables_unverified_commands():
    raw = {"projects": [{"id": "demo", "name": "Demo", "locations": [], "plans": []}],
        "sessions": [{"id": "R9", "manager": "Rex", "agent": "Codex", "workspace_id": "session:exact",
            "window_id": "window:exact", "pane_id": "block:exact", "native_id": "native-full",
            "title": "Implementation", "project": "demo", "status": "Working",
            "command": "do not trust this command", "evidence": "Work in progress"}]}
    data = import_prototype(raw, {"roots": [], "sources": []})
    row = next(iter(data["locations"].values()))
    assert row["id"] != "R9"
    assert row["navigation"] is None
    assert row["assessment"]["freshness"] == "stale"
    assert row["evidence"] == "Work in progress"
    state.validate(data)


def test_native_helper_resolution_uses_shipped_sibling():
    assert collectors.resolve_inventory() == ROOT / 'plugins/session/skills/session-agent-list/scripts/session-inventory'


def test_assessed_inactive_conversation_gets_changed_excerpt(tmp_path, monkeypatch):
    data = state.new_map({"roots": [], "sources": ["native"]})
    row = {"id": "conversation:a", "native_id": "fixture", "source_id": "native:codex",
           "title": "Implementation", "live": "no", "evidence": "Old excerpt", "transcript": "/fixture/log"}
    data["conversations"][row["id"]] = {**row, "assessment": {"summary": "Previously reviewed"}}
    monkeypatch.setattr(collectors, "native", lambda *a: ({row["id"]: dict(row)}, {"native:codex": {"status": "ok"}}))
    monkeypatch.setattr(collectors, "text_excerpt", lambda *a: {"text": "New completed work", "basis": "fixture"})
    monkeypatch.setattr(collectors, "collect_projects", lambda *a: ({}, {}, {}))
    fresh, _, _ = collectors.collect(data, tmp_path)
    assert fresh["conversations"][row["id"]]["evidence"] == "New completed work"


def test_cli_full_update_render_with_fake_collect(tmp_path, monkeypatch, capsys):
    import session_map.cli as cli
    def fake_collect(data, directory, **kwargs):
        return {"locations": {"loc:a": {"id": "loc:a", "source_id": "fixture", "title": "Demo",
                                       "evidence": "Ready for review"}}}, {"fixture": {"status": "ok"}}, {}
    monkeypatch.setattr(cli, "collect", fake_collect)
    for mode in ("full", "update", "render"):
        assert main([mode, "--map-dir", str(tmp_path), "--no-open"]) == 0
        assert json.loads(capsys.readouterr().out)["mode"] == mode
    assert len(state.load(tmp_path)["locations"]) == 1
    assert len(list((tmp_path/'snapshots').glob('*.json'))) == 1
