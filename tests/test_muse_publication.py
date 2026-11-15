"""Publication proof and inline-thread repair for the pinned Claude Action."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

HELPER = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
spec = importlib.util.spec_from_file_location("muse_publication", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

RUN = "https://github.com/org/repo/actions/runs/10"
PR = "https://api.github.com/repos/org/repo/pulls/5"
BOT = {"login": "github-actions[bot]", "type": "Bot"}


def comment(identifier=20, inline=False, body=None, root=7):
    return {"id": identifier, "html_url": f"https://github.com/org/repo/pull/5#{'discussion_r' if inline else 'issuecomment-'}{identifier}",
            "body": body if body is not None else f"The completed answer. [View job run]({RUN})",
            "user": BOT, "pull_request_url": PR, **({"in_reply_to_id": root} if inline else {})}


def state(inline=False):
    result = {"repository": "org/repo", "number": 5, "head": "a" * 40,
              "comment_ids": [1], "run_url": RUN}
    if inline:
        result.update(thread_root_id=7, review_comment_ids=[7, 8])
    return result


def execution(path, update=None, failed=False):
    update = update or comment()
    messages = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "call_1",
          "name": "mcp__github_comment__update_claude_comment", "input": {"body": update["body"]}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "call_1",
          "is_error": failed, "content": [{"type": "text", "text": json.dumps({
              "id": update["id"], "html_url": update["html_url"], "updated_at": "2026-11-14T01:00:00Z"})}]}]}},
        {"type": "result", "subtype": "success", "is_error": False},
    ]
    path.write_text(json.dumps(messages))
    return messages


class API:
    def __init__(self, top=None, inline=None, objects=None, fail_post=False):
        self.top, self.inline, self.objects = top or [], inline or [], objects or {}
        self.calls, self.fail_post = [], fail_post

    def pages(self, path):
        self.calls.append(("PAGES", path))
        return self.inline if "/pulls/" in path else self.top

    def get(self, path):
        self.calls.append(("GET", path))
        return self.objects[path]

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "POST":
            if self.fail_post:
                raise ci.Refusal("Posting failed")
            return {"id": 30}


def test_correlates_successful_mcp_result_and_id(tmp_path):
    path = tmp_path / "execution.json"
    messages = execution(path)
    assert ci.successful_comment_update(str(path))["id"] == 20
    # SDK tool results may encode the MCP text content as a string.
    messages[1]["message"]["content"][0]["content"] = json.dumps({"id": 20, "html_url": comment()["html_url"]})
    path.write_text(json.dumps(messages))
    assert ci.successful_comment_update(str(path))["id"] == 20


@pytest.mark.parametrize("invalid", ["no_tool", "tool_error", "wrong_call", "wrong_tool", "bad_result", "no_result"])
def test_initial_progress_or_unproven_update_is_refused(tmp_path, invalid):
    path = tmp_path / "execution.json"
    messages = execution(path, failed=invalid == "tool_error")
    if invalid == "no_tool":
        messages = messages[-1:]
    elif invalid == "wrong_call":
        messages[1]["message"]["content"][0]["tool_use_id"] = "unrelated"
    elif invalid == "wrong_tool":
        messages[0]["message"]["content"][0]["name"] = "mcp__github_inline_comment__create_inline_comment"
    elif invalid == "bad_result":
        messages[-1]["is_error"] = True
    elif invalid == "no_result":
        messages.pop()
    path.write_text(json.dumps(messages))
    with pytest.raises(ci.Refusal):
        ci.successful_comment_update(str(path))


@pytest.mark.parametrize("final_failure", ["tool_error", "missing_result", "empty_body"])
def test_failed_final_update_cannot_promote_earlier_progress(tmp_path, final_failure):
    path = tmp_path / "execution.json"
    messages = execution(path)
    final_call = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "final_call",
        "name": "mcp__github_comment__update_claude_comment", "input": {
            "body": "" if final_failure == "empty_body" else "Final answer"}}]}}
    tail = [final_call]
    if final_failure != "missing_result":
        tail.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "final_call",
            "is_error": True, "content": "Error posting final answer"}]}})
    messages[-1:-1] = tail
    path.write_text(json.dumps(messages))
    with pytest.raises(ci.Refusal, match="No successful"):
        ci.successful_comment_update(str(path))


def test_publication_readback_matches_id_url_bot_newness_and_exact_run():
    answer = comment()
    api = API(top=[answer])
    assert ci.completed_response(api, state(), answer) == (answer, False)
    for replacement in (
        {**answer, "user": {"login": "member", "type": "User"}},
        {**answer, "id": 1},
        {**answer, "html_url": "https://github.com/other/repo/pull/5#issuecomment-20"},
        {**answer, "body": f"Answer {RUN}0"},
        {**answer, "body": "An untouched initial comment without a run link"},
    ):
        with pytest.raises(ci.Refusal):
            ci.completed_response(API(top=[replacement]), state(), answer)


def test_id_namespaces_do_not_confuse_issue_comment_and_review_reply():
    top, reply = comment(), comment(inline=True)
    api = API(top=[top], inline=[reply])
    assert ci.completed_response(api, state(True), reply) == (reply, True)


def test_resolves_child_trigger_root_without_replacing_member_metadata():
    trigger = {"id": 8, "body": "@muse explain", "user": {"login": "member", "type": "User"},
               "in_reply_to_id": 7, "pull_request_url": PR}
    root = {"id": 7, "pull_request_url": PR}
    api = API(objects={"repos/org/repo/pulls/comments/8": trigger,
                       "repos/org/repo/pulls/comments/7": root})
    before = json.loads(json.dumps(trigger))
    assert ci.review_thread_root(api, "org/repo", 5, trigger) == 7
    assert trigger == before
    root["pull_request_url"] = PR + "0"
    with pytest.raises(ci.Refusal, match="root"):
        ci.review_thread_root(api, "org/repo", 5, trigger)


def test_native_reply_stays_in_thread_and_wrong_thread_fails():
    api = API()
    ci.finish_followup(api, state(True), comment(inline=True), True)
    assert not api.calls
    with pytest.raises(ci.Refusal, match="wrong inline"):
        ci.finish_followup(api, state(True), comment(inline=True, root=99), True)
    assert not api.calls


def test_child_reply_fallback_moves_only_after_verified_thread_post():
    answer = comment()
    reply = comment(30, inline=True, body=answer["body"])
    api = API(objects={"repos/org/repo/pulls/comments/30": reply})
    ci.finish_followup(api, state(True), answer, False)
    assert api.calls == [
        ("POST", "repos/org/repo/pulls/5/comments/7/replies", {"body": answer["body"]}),
        ("GET", "repos/org/repo/pulls/comments/30"),
        ("DELETE", "repos/org/repo/issues/comments/20", None),
    ]


@pytest.mark.parametrize("failure", ["post", "wrong_root", "changed_body", "wrong_pr"])
def test_fallback_survives_failed_relocation(failure):
    answer = comment()
    reply = comment(30, inline=True, root=99 if failure == "wrong_root" else 7)
    if failure == "changed_body":
        reply["body"] = "unexpected"
    elif failure == "wrong_pr":
        reply["pull_request_url"] = PR + "0"
    api = API(objects={"repos/org/repo/pulls/comments/30": reply}, fail_post=failure == "post")
    with pytest.raises(ci.Refusal):
        ci.finish_followup(api, state(True), answer, False)
    assert not any(call[0] == "DELETE" for call in api.calls)


def test_finish_requires_action_conclusion_before_api(tmp_path, monkeypatch):
    recorded = tmp_path / "state.json"
    recorded.write_text(json.dumps({"mode": "fix"}))
    env = {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(recorded), "MUSE_ACTION_OUTCOME": "success"}
    monkeypatch.setattr(ci, "GitHub", lambda token: pytest.fail("No API access without action success"))
    with pytest.raises(ci.Refusal, match="Action failed"):
        ci.finish("fix", env)


def test_finish_cannot_accept_zero_followup_publication(tmp_path, monkeypatch):
    recorded, log = tmp_path / "state.json", tmp_path / "execution.json"
    recorded.write_text(json.dumps({"mode": "followup", **state()}))
    log.write_text(json.dumps([{"type": "result", "subtype": "success", "is_error": False}]))
    env = {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(recorded), "MUSE_ACTION_OUTCOME": "success",
           "MUSE_ACTION_CONCLUSION": "success", "MUSE_EXECUTION_FILE": str(log), "GH_TOKEN": "fake"}
    api = API(objects={"repos/org/repo/pulls/5": {"head": {"sha": "a" * 40}}})
    monkeypatch.setattr(ci, "GitHub", lambda token: api)
    monkeypatch.setattr(ci, "review_workspace", lambda *unused: None)
    with pytest.raises(ci.Refusal, match="No successful"):
        ci.finish("followup", env)
    assert not any(call[0] in ("POST", "PATCH", "DELETE") for call in api.calls)


def test_prepare_exposes_only_the_ci_log_directory_outside_checkout(tmp_path, monkeypatch):
    root, runtime = tmp_path / "checkout'quoted", tmp_path / "runner'temp"
    root.mkdir()
    runtime.mkdir()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    git("init", "-q", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    config = root / ".github/muse-ci"
    config.mkdir(parents=True)
    (config / "policy.json").write_text(json.dumps({"schema_version": 2, "model": ci.MODEL, "organization": "org"}))
    (config / "fix-settings.json").write_text('{}')
    (root / "app.txt").write_text("tracked\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"ref": "main", "repository": {"full_name": "org/repo", "default_branch": "main",
        "owner": {"type": "Organization", "login": "org"}}, "inputs": {"request": "Fix app"}}))
    envfile, output = tmp_path / "env", tmp_path / "output"
    api = API(objects={"users/member": {"type": "User"}, "orgs/org/members/member": None,
                       "repos/org/repo/collaborators/member/permission": {"permission": "write"}})
    monkeypatch.setattr(ci, "GitHub", lambda token: api)
    ci.prepare("fix", {"GITHUB_WORKSPACE": str(root), "GITHUB_EVENT_PATH": str(event),
        "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": "org/repo", "GITHUB_SHA": base,
        "GITHUB_ACTOR": "member", "MUSE_TRIGGERING_ACTOR": "member", "RUNNER_TEMP": str(runtime),
        "GITHUB_ENV": str(envfile), "GITHUB_OUTPUT": str(output), "GITHUB_RUN_ID": "10", "GH_TOKEN": "fake"})
    fields = {}
    lines = iter(output.read_text().splitlines())
    for line in lines:
        name, delimiter = line.split("<<", 1)
        values = []
        for value in lines:
            if value == delimiter:
                break
            values.append(value)
        fields[name] = "\n".join(values)
    assert "mcp_config" not in fields
    assert Path(fields["ci_logs"]) == runtime / "github-ci-logs"
    assert Path(fields["ci_logs"]).is_dir()
    permissions = json.loads(Path(fields["settings"]).read_text())["permissions"]
    own_runtime = Path(fields["settings"]).parent
    def rule(path):
        return f"Read(//{str(path.resolve()).lstrip('/')}/**)"
    assert rule(own_runtime) in permissions["deny"]
    assert rule(runtime) not in permissions["deny"]
    assert rule(Path(fields["ci_logs"])) not in permissions["deny"]
    assert permissions["blockReadsOutsideWorkingDirectories"] is True


def test_fallback_without_upstream_run_link_is_correlated_then_repaired(tmp_path):
    # Pinned MCP replaces the entire comment body; its fallback finalizer can
    # fail to read an issue comment using the PR-review-comment namespace.
    answer = comment(body="The completed answer.")
    path = tmp_path / "execution.json"
    execution(path, update=answer)
    verified_update = ci.successful_comment_update(str(path))
    reply_body = answer["body"] + f"\n\n[View job run]({RUN})"
    api = API(top=[answer], objects={"repos/org/repo/pulls/comments/30": comment(30, inline=True, body=reply_body)})
    found, inline = ci.completed_response(api, state(True), verified_update)
    assert (found, inline) == (answer, False)
    ci.finish_followup(api, state(True), found, inline)
    assert api.calls[-3:] == [
        ("POST", "repos/org/repo/pulls/5/comments/7/replies", {"body": reply_body}),
        ("GET", "repos/org/repo/pulls/comments/30"),
        ("DELETE", "repos/org/repo/issues/comments/20", None),
    ]
    # The exception applies only to the verified new issue-comment fallback.
    with pytest.raises(ci.Refusal):
        ci.completed_response(API(top=[answer]), state(), verified_update)
    old = {**answer, "id": 1}
    with pytest.raises(ci.Refusal):
        ci.completed_response(API(top=[old]), state(True), {**verified_update, "id": 1})
    member = {**answer, "user": {"login": "member", "type": "User"}}
    with pytest.raises(ci.Refusal):
        ci.completed_response(API(top=[member]), state(True), verified_update)
    wrong = comment(inline=True, body="The completed answer.")
    with pytest.raises(ci.Refusal):
        ci.completed_response(API(inline=[wrong]), state(True), wrong)


@pytest.mark.parametrize("name", [".claude/link", ".husky/link", ".mcp.json", ".claude.json", ".gitmodules",
                                  ".ripgreprc", "CLAUDE.md", "CLAUDE.local.md"])
def test_review_refuses_links_in_action_restored_paths_before_model(tmp_path, name):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init", "-q")
    (tmp_path / "target").write_text("content\n")
    link = tmp_path / name
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(os.path.relpath(tmp_path / "target", link.parent))
    # Git rejects adding a symlink named .gitmodules; validate that untracked case.
    git("add", "target", *([] if name == ".gitmodules" else [name]))
    with pytest.raises(ci.Refusal, match="Action-restored path"):
        ci.validate_tree(tmp_path, "review")


def test_review_accepts_safe_link_from_agents_into_claude(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init", "-q")
    dest = tmp_path / ".claude/skills/new-python-project"
    dest.mkdir(parents=True)
    (dest / "README.md").write_text("project\n")
    link = tmp_path / ".agents/skills/new-python-project"
    link.parent.mkdir(parents=True)
    link.symlink_to("../../.claude/skills/new-python-project", target_is_directory=True)
    git("add", ".")
    ci.validate_tree(tmp_path, "review")
