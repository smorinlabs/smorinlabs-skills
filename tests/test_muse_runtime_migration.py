"""Offline security and publication checks for Claude Action helper."""
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

import pytest
import yaml

HELPER = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
spec = importlib.util.spec_from_file_location("muse_action_runtime", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class API:
    def __init__(self, pr=None, comments=None, fail=None, review_comments=None):
        self.pr, self.comments, self.fail = pr, comments or [], fail
        self.review_comments = review_comments or []
        self.calls = []
    def get(self, path):
        self.calls.append(("GET", path))
        if "/pulls/comments/" in path:
            return next(comment for comment in self.review_comments if str(comment["id"]) == path.rsplit("/", 1)[1])
        if "/pulls/" in path:
            return self.pr
        if path.startswith("users/"):
            return {"type": "User"}
        if path.endswith("/permission"):
            return {"permission": "write"}
        return None
    def pages(self, path):
        return list(self.review_comments if "/pulls/" in path else self.comments)
    def request(self, method, path, data=None):
        self.calls.append((method, path, data))
        if method == self.fail:
            raise ci.Refusal("test failure")


@pytest.fixture
def pr():
    return {"number": 5, "state": "open", "draft": False, "user": {"type": "User", "login": "author"},
            "head": {"ref": "branch", "sha": "a" * 40, "repo": {"full_name": "org/repo"}},
            "base": {"ref": "main", "sha": "b" * 40}}


@pytest.fixture
def repo():
    return {"full_name": "org/repo", "owner": {"type": "Organization", "login": "org"}, "default_branch": "main"}


def test_followup_requires_mention_human_and_pr(repo, pr):
    event = {"repository": repo, "action": "created", "issue": {"number": 5, "pull_request": {}},
             "comment": {"user": {"type": "User", "login": "member"}, "body": "@muse explain"}}
    # GitHub's pull_request marker is a nonempty object in real issue comments.
    event["issue"]["pull_request"] = {"url": "https://api.github.com/repos/org/repo/pulls/5"}
    api = API(pr)
    ci.authorize(event, "followup", "member", "runner", api, api, "org")
    assert event["_muse_pr"] == pr
    assert any("members/author" in c[1] for c in api.calls)
    for bad in ("@musebot hi", "not a mention", "x@muse"):
        event["comment"]["body"] = bad
        with pytest.raises(ci.Refusal):
            ci.authorize(event, "followup", "member", "runner", api, api, "org")
    event["comment"]["body"] = "@muse hi"
    event["comment"]["user"]["login"] = "other"
    with pytest.raises(ci.Refusal):
        ci.authorize(event, "followup", "member", "runner", api, api, "org")


def test_followup_refuses_fork_draft_or_issue(repo, pr):
    event = {"repository": repo, "action": "created", "issue": {"number": 5, "pull_request": {"url": "x"}},
             "comment": {"user": {"type": "User", "login": "member"}, "body": "@muse hi"}}
    api = API(pr)
    pr["draft"] = True
    with pytest.raises(ci.Refusal):
        ci.authorize(event, "followup", "member", "member", api, api, "org")
    pr["draft"] = False
    pr["head"]["repo"]["full_name"] = "other/fork"
    with pytest.raises(ci.Refusal):
        ci.authorize(event, "followup", "member", "member", api, api, "org")
    del event["issue"]["pull_request"]
    with pytest.raises(ci.Refusal):
        ci.authorize(event, "followup", "member", "member", api, api, "org")


def test_configuration_restricts_file_access(tmp_path):
    d = tmp_path / ".github/muse-ci"
    d.mkdir(parents=True)
    (d / "review-settings.json").write_text('{}')
    runtime = tmp_path.parent / "runtime"
    cfg = ci.configuration(tmp_path, "review", runtime)
    permissions = cfg["permissions"]
    assert all(permissions[key] is True for key in ("blockReadsOutsideWorkingDirectories",
               "blockWritesOutsideWorkingDirectories", "denyInsteadOfPrompting"))
    assert f"Read(//{str(tmp_path / '.git').lstrip('/')}/**)" in permissions["deny"]
    assert "Read(**/*.PEM)" in permissions["deny"]
    assert len(permissions["deny"]) < 4000


def test_summary_selects_new_bot_comment_and_preserves_on_failed_upsert():
    bot = {"login": "github-actions[bot]", "type": "Bot"}
    state = {"repository": "org/repo", "number": 5, "head": "a" * 40,
             "comment_ids": [1], "run_url": "https://github.com/org/repo/actions/runs/10"}
    comments = [{"id": 1, "user": bot, "body": "old"},
                {"id": 2, "user": bot, "body": "Done " + state["run_url"]}]
    api = API(comments=comments, fail="POST")
    with pytest.raises(ci.Refusal):
        ci.consolidate(api, state)
    assert not any(c[0] == "DELETE" for c in api.calls)
    api.fail = None
    ci.consolidate(api, state)
    assert [c[0] for c in api.calls[-2:]] == ["POST", "DELETE"]
    api.comments.append({"id": 3, "user": bot, "body": state["run_url"]})
    with pytest.raises(ci.Refusal, match="exactly one"):
        ci.consolidate(api, state)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def gitroot(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "file.txt").write_text("base\n")
    (tmp_path / "CLAUDE.md").write_text("base instruction\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_review_allows_exact_action_restoration_but_not_other_changes(gitroot):
    base = git(gitroot, "rev-parse", "HEAD")
    (gitroot / "CLAUDE.md").write_text("head instruction\n")
    git(gitroot, "commit", "-qam", "head")
    head = git(gitroot, "rev-parse", "HEAD")
    (gitroot / "CLAUDE.md").write_text("base instruction\n")
    snapshot = gitroot / ".claude-pr/CLAUDE.md"
    snapshot.parent.mkdir()
    snapshot.write_text("head instruction\n")
    ci.review_workspace(gitroot, {"head": head, "base": base})
    snapshot.write_text("tampered\n")
    with pytest.raises(ci.Refusal):
        ci.review_workspace(gitroot, {"head": head, "base": base})


def test_review_refuses_credential_files_and_unsafe_symlinks(gitroot):
    (gitroot / ".Env.local").write_text("credential")
    with pytest.raises(ci.Refusal):
        ci.validate_tree(gitroot, "review")
    (gitroot / ".Env.local").unlink()
    (gitroot / "link").symlink_to(".git/config")
    git(gitroot, "add", "link")
    with pytest.raises(ci.Refusal):
        ci.validate_tree(gitroot, "review")


def test_fix_refuses_sensitive_untracked_without_publishing(gitroot):
    base = git(gitroot, "rev-parse", "HEAD")
    git(gitroot, "checkout", "-qb", "muse/fix-10-1")
    (gitroot / ".env.local").write_text("secret")
    state = {"base": base, "branch": "muse/fix-10-1"}
    api = API()
    with pytest.raises(ci.Refusal):
        ci.publish_fix(gitroot, state, api)
    assert api.calls == []


def parse_actions_output(path):
    result = {}
    lines = iter(path.read_text().splitlines())
    for line in lines:
        key, delimiter = line.split("<<", 1)
        body = []
        for line in lines:
            if line == delimiter:
                break
            body.append(line)
        result[key] = "\n".join(body)
    return result


@pytest.mark.parametrize("mode,event_name", [("review", "pull_request"), ("followup", "issue_comment"),
                                             ("followup", "pull_request_review_comment")])
def test_prepare_review_then_finish_offline(tmp_path, monkeypatch, mode, event_name):
    root = tmp_path / "checkout"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    config = root / ".github/muse-ci"
    config.mkdir(parents=True)
    (config / "policy.json").write_text(json.dumps({"schema_version": 2, "model": ci.MODEL,
                                                    "organization": "org", "max_diff_bytes": 60000}))
    base_profile = {"permissions": {"allow": list(ci.READ_TOOLS), "deny": ["Bash", "Read(private/**)"]}}
    profile_file = config / "review-settings.json"
    profile_file.write_text(json.dumps(base_profile))
    profile_bytes = profile_file.read_bytes()
    (root / "app.txt").write_text("base\n")
    (root / "AGENTS.md").write_text("Trusted base guidance\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-qb", "feature")
    (root / "app.txt").write_text("changed\n")
    (root / "AGENTS.md").write_text("PR-modified instructions\n")
    git(root, "commit", "-qam", "change")
    head = git(root, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "origin", "HEAD:refs/heads/feature", f"{base}:refs/heads/main")
    git(root, "fetch", "-q", "origin", "main")
    git(root, "checkout", "-q", "--detach", base)
    repo = {"full_name": "org/repo", "owner": {"type": "Organization", "login": "org"}, "default_branch": "main"}
    pr = {"number": 1, "state": "open", "draft": False, "user": {"type": "User", "login": "author"},
          "head": {"ref": "feature", "sha": head, "repo": {"full_name": "org/repo"}},
          "base": {"ref": "main", "sha": base}}
    event = {"repository": repo, "pull_request": pr, "action": "opened"}
    if mode == "followup":
        event = {"repository": repo, "action": "created",
                 "issue": {"number": 1, "pull_request": {"url": "https://api.github.com/repos/org/repo/pulls/1"}},
                 "comment": {"id": 9, "user": {"type": "User", "login": "actor"}, "body": "@muse Explain this finding."}}
        if event_name == "pull_request_review_comment":
            del event["issue"]
            event["pull_request"] = pr
            event["comment"].update(in_reply_to_id=7, pull_request_url="https://api.github.com/repos/org/repo/pulls/1")
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))
    envfile, outfile = tmp_path / "env", tmp_path / "output"
    envfile.touch()
    outfile.touch()
    temp = tmp_path / "runner-temp"
    temp.mkdir()
    env = {"GITHUB_WORKSPACE": str(root), "GITHUB_EVENT_PATH": str(event_path),
           "GITHUB_EVENT_NAME": event_name,
           "GITHUB_REPOSITORY": "org/repo", "GITHUB_ACTOR": "actor", "MUSE_TRIGGERING_ACTOR": "actor",
           "MUSE_TRUSTED_BASE_SHA": base,
           "GITHUB_RUN_ID": "10", "RUNNER_TEMP": str(temp), "GITHUB_ENV": str(envfile),
           "GITHUB_OUTPUT": str(outfile), "GH_TOKEN": "fake"}
    api = API(pr)
    inline = event_name == "pull_request_review_comment"
    if inline:
        api.review_comments = [{"id": 7, "pull_request_url": "https://api.github.com/repos/org/repo/pulls/1"}, event["comment"]]
    monkeypatch.setattr(ci, "GitHub", lambda token: api)
    loaded_profiles = []
    loader = ci.load_configuration
    def capture_profile(*args):
        profile = loader(*args)
        loaded_profiles.append(profile)
        return profile
    monkeypatch.setattr(ci, "load_configuration", capture_profile)
    ci.prepare(mode, env)
    variables, output = parse_actions_output(envfile), parse_actions_output(outfile)
    assert Path(output["settings"]).is_absolute()
    assert head in output["prompt"]
    generated = json.loads(Path(output["settings"]).read_text())
    assert generated["permissions"]["allow"] == list(ci.READ_TOOLS)
    assert all(rule in generated["permissions"]["deny"] for rule in base_profile["permissions"]["deny"])
    assert ("mcp__github_inline_comment__create_inline_comment" in generated["permissions"]["deny"]) is inline
    assert loaded_profiles == [base_profile]
    assert profile_file.read_bytes() == profile_bytes
    trusted_prompt = output["prompt"].split('{"reviewed_head":', 1)[0]
    assert "Use ToolSearch to discover comment tools and their complete input schemas before calling them" in trusted_prompt
    assert "actual discovered tool names and fields; never guess" in trusted_prompt
    assert "Never post trial, test, placeholder, or schema-discovery comments" in trusted_prompt
    if inline:
        assert "Use the discovered update_claude_comment tool only on the existing response" in trusted_prompt
        assert "Do not create new inline findings, comments, or discussion threads" in trusted_prompt
        assert "do not call create_inline_comment" in trusted_prompt
        assert "For every inline finding call the inline comment tool" not in trusted_prompt
    else:
        assert "Post inline comments only for actionable findings or requested answers" in trusted_prompt
        assert "confirmed=true" in trusted_prompt
        assert "Do not create new inline findings" not in trusted_prompt
    assert "Reserve the final two turns for the final update_claude_comment call and its result" in trusted_prompt
    assert "Complete that final tool update before the turn limit so publication can be verified directly" in trusted_prompt
    assert "Trusted base guidance" in output["prompt"]
    assert "PR-modified instructions" in output["prompt"]  # The diff is explicitly untrusted data.
    guidance = output["prompt"].split("Trusted base AGENTS.md project guidance follows as JSON.")[-1]
    assert "Trusted base guidance" in guidance and "PR-modified instructions" not in guidance
    assert "HOME" not in variables
    assert Path(variables["MUSE_CI_STATE"]).is_file()
    assert git(root, "rev-parse", "HEAD") == head
    api.comments = [{"id": 5, "user": {"login": "github-actions[bot]", "type": "Bot"},
                     "html_url": "https://github.com/org/repo/pull/1#issuecomment-5",
                     "body": "Finished https://github.com/org/repo/actions/runs/10"}]
    response = api.comments[0]
    if inline:
        response.update(in_reply_to_id=7, html_url="https://github.com/org/repo/pull/1#discussion_r5")
        api.review_comments.append(response)
        api.comments = []
    execution = tmp_path / "execution.json"
    execution.write_text(json.dumps([
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "update_1",
            "name": "mcp__github_comment__update_claude_comment", "input": {"body": "Review complete"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "update_1",
            "content": json.dumps({"id": 5, "html_url": response["html_url"]})}]}},
        {"type": "result", "subtype": "success", "is_error": False},
    ]))
    env.update(variables, MUSE_ACTION_OUTCOME="success", MUSE_ACTION_CONCLUSION="success",
               MUSE_EXECUTION_FILE=str(execution))
    ci.finish(mode, env)
    assert [x[0] for x in api.calls if x[0] in ("POST", "PATCH", "DELETE")] == (
        ["POST", "DELETE"] if mode == "review" else [])


@pytest.mark.parametrize("name,turns", [("pr-review", 24), ("followup", 24), ("fix-pr", 16)])
def test_workflow_turn_budget_preserves_job_timeout(name, turns):
    workflow = HELPER.parents[1] / f"workflows/muse-{name}.yml"
    document = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)
    job = next(iter(document["jobs"].values()))
    action = next(step for step in job["steps"] if step.get("id") == "muse")
    args = shlex.split(action["with"]["claude_args"])
    assert args.count("--max-turns") == 1
    assert int(args[args.index("--max-turns") + 1]) == turns
    assert int(job["timeout-minutes"]) == (15 if name == "fix-pr" else 10)


def test_fix_publication_creates_separate_branch_and_refuses_existing_remote(gitroot, tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(gitroot, "remote", "add", "origin", str(remote))
    base = git(gitroot, "rev-parse", "HEAD")
    git(gitroot, "checkout", "-qb", "muse/fix-10-1")
    (gitroot / "file.txt").write_text("new content\n")
    state = {"base": base, "branch": "muse/fix-10-1", "repository": "org/repo", "default_branch": "main",
             "request": "fix bug", "run_url": "https://github.com/org/repo/actions/runs/10"}
    api = API()
    ci.publish_fix(gitroot, state, api)
    assert api.calls[-1][0] == "POST" and api.calls[-1][2]["head"] == state["branch"]
    published = subprocess.check_output(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/muse/fix-10-1"], text=True).strip()
    assert published == git(gitroot, "rev-parse", "HEAD") and published != base
    # A rerun with the same branch name cannot update an existing remote branch.
    git(gitroot, "reset", "--hard", base)
    (gitroot / "file.txt").write_text("different\n")
    api.calls.clear()
    with pytest.raises(ci.Refusal, match="push"):
        ci.publish_fix(gitroot, state, api)
    assert not api.calls


def test_finish_rejects_mode_mismatch_before_api_or_publication(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"mode": "fix"}))
    env = {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state), "MUSE_ACTION_OUTCOME": "failure"}
    monkeypatch.setattr(ci, "GitHub", lambda token: pytest.fail("API must not be reached"))
    with pytest.raises(ci.Refusal, match="Action failed"):
        ci.finish("review", env)


def test_finish_followup_rejects_unproven_response_and_stale_head(tmp_path, monkeypatch):
    head = "a" * 40
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"mode": "followup", "repository": "org/repo", "number": 1, "head": head,
                                 "default_branch": "main", "checkout_sha": "b" * 40}))
    env = {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state), "MUSE_ACTION_OUTCOME": "success",
           "MUSE_ACTION_CONCLUSION": "success",
           "GH_TOKEN": "fake"}
    api = API({"head": {"sha": head}, "base": {"ref": "main"}})
    monkeypatch.setattr(ci, "GitHub", lambda token: api)
    monkeypatch.setattr(ci, "review_workspace", lambda root, state: None)
    monkeypatch.setattr(ci, "restore_revision", lambda root, state: "b" * 40)
    with pytest.raises(ci.Refusal, match="execution"):
        ci.finish("followup", env)
    assert all(call[0] == "GET" for call in api.calls)
    api.pr["head"]["sha"] = "b" * 40
    with pytest.raises(ci.Refusal, match="stale"):
        ci.finish("followup", env)
    assert all(call[0] == "GET" for call in api.calls)


def test_modified_authorization_rerun_and_head_refused(repo, pr):
    event = {"repository": repo, "pull_request": json.loads(json.dumps(pr))}
    class DenyRerun(API):
        def get(self, path):
            if path.endswith("/collaborators/rerunner/permission"):
                return {"permission": "read"}
            return super().get(path)
    api = DenyRerun(pr)
    with pytest.raises(ci.Refusal, match="write access"):
        ci.authorize(event, "review", "actor", "rerunner", api, api, "org")
    api = API(pr)
    pr["head"]["sha"] = "c" * 40
    with pytest.raises(ci.Refusal, match="PR changed"):
        ci.authorize(event, "review", "actor", "actor", api, api, "org")


@pytest.mark.parametrize("settings", [[], {"permissions": []}, {"permissions": {"deny": "Read(*)"}},
                                       {"permissions": {"deny": [17]}}])
def test_invalid_settings_refuse_cleanly(tmp_path, settings):
    config = tmp_path / ".github/muse-ci"
    config.mkdir(parents=True)
    (config / "review-settings.json").write_text(json.dumps(settings))
    with pytest.raises(ci.Refusal, match="settings"):
        ci.configuration(tmp_path, "review", tmp_path.parent / "runtime")


def test_actual_packaged_profiles_are_valid(tmp_path):
    template_root = HELPER.parents[2]
    policy = json.loads((template_root / ".github/muse-ci/policy.json").read_text())
    assert policy["schema_version"] == 2 and policy["model"] == ci.MODEL
    for mode in ("review", "followup", "fix"):
        permissions = ci.configuration(template_root, mode, tmp_path / "runtime")["permissions"]
        assert permissions["blockReadsOutsideWorkingDirectories"]
        assert permissions["blockWritesOutsideWorkingDirectories"]
        assert permissions["denyInsteadOfPrompting"]
        assert "Read(//proc/**)" in permissions["deny"]
        if mode == "fix":
            assert "Edit(.husky/**)" in permissions["deny"]
            assert "Edit(.claude-pr/**)" in permissions["deny"]


@pytest.mark.parametrize("legacy", [False, True])
def test_real_installer_templates_render_and_repeat(tmp_path, legacy):
    installer_path = HELPER.parents[3] / "scripts/install.py"
    install_spec = importlib.util.spec_from_file_location("actual_muse_installer", installer_path)
    installer = importlib.util.module_from_spec(install_spec)
    install_spec.loader.exec_module(installer)
    if legacy:
        snapshots = json.loads(installer.LEGACY.read_text())
        for name, variants in snapshots.items():
            if name == "AGENTS.muse.md":
                name = "AGENTS.md"
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(installer.render(variants[0], "org", "muse-spark-1.3"))
        (tmp_path / "opencode.json").write_text('{"preserve":true}\n')
    changes = installer.plan(tmp_path, "org", migrate_opencode=legacy, codeowner="@org/team")
    installer.apply(tmp_path, changes)
    policy = json.loads((tmp_path / installer.NEW_POLICY).read_text())
    expected = "muse-spark-1.3" if legacy else installer.DEFAULT_MODEL
    assert policy["model"] == expected
    assert installer.plan(tmp_path, "org", codeowner="@org/team") == {}
    if legacy:
        assert not (tmp_path / ".github/workflows/opencode-pr-review.yml").exists()
        assert (tmp_path / "opencode.json").read_text() == '{"preserve":true}\n'
        assert (tmp_path / ".github/workflows/muse-fix-pr.yml").exists()


def test_status_paths_preserves_leading_whitespace(gitroot):
    base = git(gitroot, "rev-parse", "HEAD")
    (gitroot / " leading.txt").write_text("data\n")
    assert ci.status_paths(gitroot, base) == [" leading.txt"]
