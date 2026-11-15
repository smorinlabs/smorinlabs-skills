"""Guarded publication of terminal SDK text when no MCP update was attempted."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
spec = importlib.util.spec_from_file_location("muse_final_response", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
RUN = "https://github.com/org/repo/actions/runs/10"
BOT = {"login": "github-actions[bot]", "type": "Bot"}


def state(mode="review", inline=False):
    value = {"mode": mode, "repository": "org/repo", "number": 5, "head": "a" * 40,
             "comment_ids": [1], "run_url": RUN, "default_branch": "main", "checkout_sha": "b" * 40}
    if inline: value.update(thread_root_id=7, review_comment_ids=[7, 8])
    return value


def comment(identifier=20, inline=False):
    return {"id": identifier, "html_url": f"https://github.com/org/repo/pull/5#{'discussion_r' if inline else 'issuecomment-'}{identifier}",
            "body": f"I'll analyze. [View job run]({RUN})", "user": copy.deepcopy(BOT),
            **({"pull_request_url": "https://api.github.com/repos/org/repo/pulls/5", "in_reply_to_id": 7} if inline else
               {"issue_url": "https://api.github.com/repos/org/repo/issues/5"})}


class API:
    def __init__(self, top=None, inline=None, corrupt=None):
        self.top, self.inline, self.corrupt = top or [], inline or [], corrupt or {}
        self.calls = []
    def pages(self, path):
        return copy.deepcopy(self.inline if "/pulls/" in path else self.top)
    def get(self, path):
        self.calls.append(("GET", path))
        if path.endswith("/pulls/5"):
            return {"head": {"sha": "a" * 40}, "base": {"ref": "main"}}
        found = next(c for c in self.inline + self.top if c["id"] == int(path.rsplit("/", 1)[1]))
        return {**copy.deepcopy(found), **self.corrupt}
    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if method == "PATCH":
            found = next(c for c in self.inline + self.top if c["id"] == int(path.rsplit("/", 1)[1]))
            found["body"] = data["body"]
        elif method == "POST":
            self.top.append({**comment(100), "body": data["body"]})
        elif method == "DELETE":
            self.top[:] = [c for c in self.top if c["id"] != int(path.rsplit("/", 1)[1])]


def execution(tmp_path, result="The completed answer.", prefix=None, **extra):
    path = tmp_path / "execution.json"
    path.write_text(json.dumps([*(prefix or []),
        {"type": "result", "subtype": "success", "is_error": False, "result": result, **extra}]))
    return str(path)


@pytest.mark.parametrize("mode,inline", [("review", False), ("followup", False), ("followup", True)])
def test_finish_publishes_sdk_text_then_uses_existing_finalization(tmp_path, monkeypatch, capsys, mode, inline):
    prepared = state(mode, inline)
    candidate = comment(inline=inline)
    old = {**comment(1), "body": ci.SUMMARY_MARKER + "\nOld summary."}
    api = API(top=[old] if inline else [old, candidate], inline=[candidate] if inline else [])
    path = execution(tmp_path)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(prepared))
    monkeypatch.setattr(ci, "GitHub", lambda token: api)
    monkeypatch.setattr(ci, "restore_revision", lambda *args: "b" * 40)
    monkeypatch.setattr(ci, "review_workspace", lambda *args: None)
    ci.finish(mode, {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state_path),
                     "MUSE_EXECUTION_FILE": path, "MUSE_ACTION_OUTCOME": "success", "MUSE_ACTION_CONCLUSION": "success"})
    body = "The completed answer.\n\n[View job run](" + RUN + ")"
    assert api.calls[1:3] == [
        ("PATCH", f"repos/org/repo/{'pulls' if inline else 'issues'}/comments/20", {"body": body}),
        ("GET", f"repos/org/repo/{'pulls' if inline else 'issues'}/comments/20")]
    if mode == "review":
        assert [c["id"] for c in api.top] == [1]
        assert body in api.top[0]["body"] and "Reviewed commit" in api.top[0]["body"]
    else:
        assert candidate["body"] == body
        assert not any(call[0] in ("POST", "DELETE") for call in api.calls)
    output = capsys.readouterr().out
    assert "Published final SDK response after no tracking-comment tool invocation" in output
    assert "The completed answer" not in output


def test_inline_fallback_requires_run_link_even_when_top_level(tmp_path):
    candidate = comment()
    api = API(top=[candidate])
    actual, inline = ci.published_response(api, state("followup", True), execution(tmp_path))
    assert not inline and actual["id"] == candidate["id"]
    candidate["body"] = "Unbound fallback"
    api.calls.clear()
    with pytest.raises(ci.Refusal, match="exactly one"):
        ci.published_response(api, state("followup", True), execution(tmp_path))
    assert api.calls == []


@pytest.mark.parametrize("failure", ["failed", "empty", "malformed", "missing_result"])
def test_any_updater_attempt_preserves_strict_refusal_without_sdk_fallback(tmp_path, failure):
    invocation = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "u",
        "name": "mcp__github_comment__update_claude_comment",
        "input": {"body": "" if failure == "empty" else "Attempted answer"}}]}}
    prefix = [invocation]
    if failure != "missing_result":
        prefix.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u",
            "is_error": failure == "failed", "content": "malformed" if failure == "malformed" else
            json.dumps({"id": 20, "html_url": comment()["html_url"]})}]}})
    api = API(top=[comment()])
    with pytest.raises(ci.Refusal):
        ci.published_response(api, state(), execution(tmp_path, prefix=prefix))
    assert api.calls == []


def test_successful_updater_keeps_original_proof_path_without_fallback_patch(tmp_path):
    candidate = comment()
    invocation = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "u",
        "name": "mcp__github_comment__update_claude_comment", "input": {"body": "Answer"}}]}}
    result = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u",
        "content": json.dumps({"id": 20, "html_url": candidate["html_url"]})}]}}
    api = API(top=[candidate])
    actual, inline = ci.published_response(api, state(), execution(tmp_path, prefix=[invocation, result]))
    assert actual == candidate and not inline and api.calls == []


@pytest.mark.parametrize("text", [None, "", " \n", 123, {}, "é" * 30_001])
def test_invalid_or_oversized_final_text_never_mutates_comment(tmp_path, text):
    api = API(top=[comment()])
    with pytest.raises(ci.Refusal, match="bounded final SDK"):
        ci.published_response(api, state(), execution(tmp_path, result=text))
    assert api.calls == []


@pytest.mark.parametrize("extra", [{"subtype": "error_max_turns"}, {"is_error": True}, {"type": "assistant"}])
def test_unsuccessful_terminal_message_never_publishes(tmp_path, extra):
    api = API(top=[comment()])
    with pytest.raises(ci.Refusal, match="did not finish successfully"):
        ci.published_response(api, state(), execution(tmp_path, **extra))
    assert api.calls == []


@pytest.mark.parametrize("invalid", ["wrong_run", "preexisting", "human", "multiple", "wrong_url", "wrong_context", "wrong_thread"])
def test_tracking_comment_identity_and_uniqueness_fail_closed(tmp_path, invalid):
    inline = invalid == "wrong_thread"
    candidate = comment(inline=inline)
    api = API(inline=[candidate] if inline else [], top=[] if inline else [candidate])
    if invalid == "wrong_run": candidate["body"] = RUN + "123"
    elif invalid == "preexisting": candidate["id"] = 1
    elif invalid == "human": candidate["user"] = {"login": "member", "type": "User"}
    elif invalid == "multiple": api.top.append(comment(21))
    elif invalid == "wrong_url": candidate["html_url"] = "https://github.com/org/other/pull/5#issuecomment-20"
    elif invalid == "wrong_context": candidate["issue_url"] = "https://api.github.com/repos/org/repo/issues/6"
    else: candidate["in_reply_to_id"] = 99
    with pytest.raises(ci.Refusal):
        ci.published_response(api, state("followup" if inline else "review", inline), execution(tmp_path))
    assert api.calls == []


@pytest.mark.parametrize("corrupt", [{"body": "Not saved"}, {"id": 99}, {"html_url": "wrong"},
                                     {"user": {"login": "member", "type": "User"}}, {"issue_url": "wrong"}])
def test_failed_publication_readback_never_claims_completion_or_consolidates(tmp_path, capsys, corrupt):
    api = API(top=[comment()], corrupt=corrupt)
    with pytest.raises(ci.Refusal, match="readback failed"):
        ci.published_response(api, state(), execution(tmp_path))
    assert [call[0] for call in api.calls] == ["PATCH", "GET"]
    assert "Published final SDK response" not in capsys.readouterr().out


def test_inline_readback_must_still_belong_to_original_root(tmp_path):
    api = API(inline=[comment(inline=True)], corrupt={"in_reply_to_id": 99})
    with pytest.raises(ci.Refusal, match="readback failed"):
        ci.published_response(api, state("followup", True), execution(tmp_path))
    assert [call[0] for call in api.calls] == ["PATCH", "GET"]


def test_final_text_utf8_bound_accepts_exactly_sixty_thousand_bytes(tmp_path):
    api = API(top=[comment()])
    text = "é" * 30_000
    actual, inline = ci.published_response(api, state(), execution(tmp_path, result=text))
    assert not inline and actual["body"].startswith(text + "\n\n")


def test_missing_or_malformed_execution_file_never_publishes(tmp_path):
    api = API(top=[comment()])
    with pytest.raises(ci.Refusal, match="Missing action execution"):
        ci.published_response(api, state(), "")
    path = tmp_path / "execution.json"
    for text in ("not json", "[]", '[{"type":"assistant","message":null},{"type":"result","subtype":"success","is_error":false,"result":"Answer"}]'):
        path.write_text(text)
        with pytest.raises((ci.Refusal, ValueError)):
            ci.published_response(api, state(), str(path))
    assert api.calls == []
