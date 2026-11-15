"""Private execution contents become fixed-name, locally computed tool counts."""
import importlib.util
import json
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
spec = importlib.util.spec_from_file_location("muse_tool_evidence", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
CANARY = "PRIVATE_CANARY_DO_NOT_LOG"


def call(name="WebFetch", identifier="call_one", **extra):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": name, "id": identifier,
         "input": {"url": CANARY, "prompt": CANARY}, **extra}]}}


def returned(identifier="call_one", **extra):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": identifier,
         "content": CANARY, **extra}]}}


def write_execution(tmp_path, messages):
    path = tmp_path / "execution.json"
    path.write_text(json.dumps(messages))
    return str(path)


def test_counts_results_without_logging_content_arguments_ids_or_unknown_names(tmp_path, capsys):
    messages = [call(identifier=CANARY), returned(CANARY),
                call("WebSearch", "search"), returned("search", is_error=True),
                call(CANARY, "unknown"), returned("unknown"),
                {"type": "assistant", "message": {"content": [{"type": "text", "text": CANARY}]}}]
    ci.emit_tool_evidence(write_execution(tmp_path, messages))
    lines = capsys.readouterr().out.splitlines()
    assert "not semantic correctness" in lines[0]
    assert CANARY not in "\n".join(lines)
    rows = [json.loads(line) for line in lines[1:]]
    assert [row["tool"] for row in rows] == list(ci.READ_TOOLS)
    assert all(type(value) is int for row in rows for key, value in row.items() if key != "tool")
    assert rows[ci.READ_TOOLS.index("WebFetch")] == {
        "tool": "WebFetch", "invocations": 1, "reported_success": 1, "reported_error": 0, "unmatched": 0}
    assert rows[ci.READ_TOOLS.index("WebSearch")]["reported_error"] == 1


@pytest.mark.parametrize("case", ["missing", "result_before_call", "duplicate_call", "duplicate_result",
                                  "unknown_collision", "bad_id", "bad_input", "bad_error", "missing_content"])
def test_ambiguous_or_malformed_pair_is_unmatched(case):
    first, result = call(), returned()
    messages = [first, result]
    if case == "missing": messages = [first]
    elif case == "result_before_call": messages.reverse()
    elif case == "duplicate_call": messages.insert(1, call())
    elif case == "duplicate_result": messages.append(returned())
    elif case == "unknown_collision": messages.insert(1, call(CANARY))
    elif case == "bad_id": first["message"]["content"][0]["id"] = {}
    elif case == "bad_input": first["message"]["content"][0]["input"] = CANARY
    elif case == "bad_error": result["message"]["content"][0]["is_error"] = "false"
    else: del result["message"]["content"][0]["content"]
    counts = ci.tool_evidence(messages)["WebFetch"]
    assert counts == {"invocations": 2 if case == "duplicate_call" else 1,
                      "reported_success": 0, "reported_error": 0,
                      "unmatched": 2 if case == "duplicate_call" else 1}


def test_nonmatching_results_and_malformed_envelopes_do_not_create_success():
    messages = [None, {"message": None}, {"message": {"content": CANARY}},
                call(), returned("other"), {"type": "user", "message": {"content": [None]}}]
    assert ci.tool_evidence(messages)["WebFetch"]["unmatched"] == 1


@pytest.mark.parametrize("kind", ["missing", "invalid_json", "empty", "object", "symlink", "oversized"])
def test_unavailable_diagnostic_never_exposes_error_or_file_content(tmp_path, capsys, kind):
    path = tmp_path / CANARY
    if kind == "invalid_json": path.write_text(CANARY)
    elif kind == "empty": path.write_text("[]")
    elif kind == "object": path.write_text(json.dumps({"secret": CANARY}))
    elif kind == "symlink": path.symlink_to(write_execution(tmp_path, [call()]))
    elif kind == "oversized":
        with path.open("wb") as file: file.truncate(20_000_001)
    ci.emit_tool_evidence(str(path))
    assert capsys.readouterr().out == "Muse tool evidence unavailable; execution diagnostics could not be verified.\n"


def finish_environment(tmp_path, outcome, execution):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"mode": "review", "repository": "org/repo", "number": 1,
                                 "head": "a" * 40, "default_branch": "main", "checkout_sha": "b" * 40}))
    return {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state),
            "MUSE_ACTION_OUTCOME": outcome, "MUSE_ACTION_CONCLUSION": outcome,
            "MUSE_EXECUTION_FILE": execution}


def test_failed_finish_emits_counts_but_still_refuses_publication(tmp_path, monkeypatch, capsys):
    execution = write_execution(tmp_path, [call(), returned(),
        {"type": "result", "subtype": "error_during_execution", "is_error": True}])
    class API:
        def __init__(self, token): pass
        def get(self, path): return {"head": {"sha": "a" * 40}, "base": {"ref": "main"}}
    monkeypatch.setattr(ci, "GitHub", API)
    monkeypatch.setattr(ci, "consolidate", lambda *args: pytest.fail("must not publish"))
    with pytest.raises(ci.Refusal, match="Action failed"):
        ci.finish("review", finish_environment(tmp_path, "failure", execution))
    assert '"reported_success": 1' in capsys.readouterr().out


@pytest.mark.parametrize("messages", [None, [], [{"type": "result", "subtype": "success", "is_error": False}]])
def test_diagnostics_do_not_bypass_existing_success_publication_refusals(tmp_path, monkeypatch, messages):
    execution = "" if messages is None else write_execution(tmp_path, messages)
    class API:
        def __init__(self, token): pass
        def get(self, path): return {"head": {"sha": "a" * 40}, "base": {"ref": "main"}}
    monkeypatch.setattr(ci, "GitHub", API)
    monkeypatch.setattr(ci, "restore_revision", lambda *args: "b" * 40)
    monkeypatch.setattr(ci, "review_workspace", lambda *args: None)
    monkeypatch.setattr(ci, "consolidate", lambda *args: pytest.fail("must not publish"))
    with pytest.raises(ci.Refusal):
        ci.finish("review", finish_environment(tmp_path, "success", execution))
