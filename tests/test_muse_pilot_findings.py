"""Offline regressions for late pilot findings."""
import importlib.util
import json
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
spec = importlib.util.spec_from_file_location("muse_pilot_findings", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


@pytest.mark.parametrize("mode", ["review", "followup"])
@pytest.mark.parametrize("outcome", ["failure", "cancelled"])
def test_failed_review_reports_advanced_head_without_publication(tmp_path, monkeypatch, mode, outcome):
    reviewed, current = "a" * 40, "b" * 40
    state = {"mode": mode, "repository": "org/repo", "number": 5, "head": reviewed, "default_branch": "main"}
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    summary = tmp_path / "summary"
    calls = []
    class API:
        def get(self, path):
            calls.append(("GET", path))
            return {"head": {"sha": current}, "base": {"ref": "main"}}
        def request(self, method, path, data=None):
            pytest.fail(f"Failed action attempted publication: {method} {path}")
    monkeypatch.setattr(ci, "GitHub", lambda token: API())
    env = {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state_path), "GH_TOKEN": "fake",
           "MUSE_ACTION_OUTCOME": outcome, "MUSE_ACTION_CONCLUSION": "failure", "GITHUB_STEP_SUMMARY": str(summary)}
    with pytest.raises(ci.Refusal):
        ci.finish(mode, env)
    assert calls == [("GET", "repos/org/repo/pulls/5")]
    body = summary.read_text()
    assert reviewed in body and current in body and "stale" in body.lower()


def test_failed_fix_never_queries_pull_request_or_publishes(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"mode": "fix"}))
    monkeypatch.setattr(ci, "GitHub", lambda token: pytest.fail("Failed fix should not contact GitHub"))
    with pytest.raises(ci.Refusal):
        ci.finish("fix", {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state_path),
                          "MUSE_ACTION_OUTCOME": "failure", "MUSE_ACTION_CONCLUSION": "failure", "GH_TOKEN": "fake"})


def test_only_tracked_safe_regular_data_fixtures_receive_literal_read_exceptions(tmp_path):
    import subprocess
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init", "-q")
    d = tmp_path / "tests/fixtures"
    d.mkdir(parents=True)
    for name in ("x.env.json", "x[1].env.json", "blocked.env.json", "x.env.local", ".env.local", "untracked.env.yaml"):
        (d / name).write_text("public fixture\n")
    (d / "alias.env.json").symlink_to("x.env.json")
    git("add", "--", *(f":(literal)tests/fixtures/{name}" for name in
                       ("x.env.json", "x[1].env.json", "blocked.env.json", "x.env.local", ".env.local", "alias.env.json")))
    source = {"permissions": {"deny": ["Read(tests/fixtures/blocked.env.json)"]}}
    profile = ci.configuration(tmp_path, "review", tmp_path.parent / "runtime", source=source, fixture_root=tmp_path)
    deny = profile["permissions"]["deny"]
    assert "Read(!/tests/fixtures/x.env.json)" in deny
    assert r"Read(!/tests/fixtures/x\[1\].env.json)" in deny
    assert not any("untracked.env.yaml" in rule or "alias.env.json" in rule or "x.env.local" in rule for rule in deny if rule.startswith("Read(!"))
    assert deny.index("Read(!/tests/fixtures/blocked.env.json)") < deny.index("Read(tests/fixtures/blocked.env.json)")
    assert source == {"permissions": {"deny": ["Read(tests/fixtures/blocked.env.json)"]}}


def git(root, *args):
    import subprocess
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def init_repo(root):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")


def outputs(path):
    result = {}
    lines = iter(path.read_text().splitlines())
    for line in lines:
        key, delimiter = line.split("<<", 1)
        values = []
        for value in lines:
            if value == delimiter:
                break
            values.append(value)
        result[key] = "\n".join(values)
    return result


def test_followup_can_compare_old_pr_base_using_new_trusted_checkout(tmp_path, monkeypatch):
    import subprocess
    root = tmp_path / "repo"
    root.mkdir()
    init_repo(root)
    config = root / ".github/muse-ci"
    config.mkdir(parents=True)
    (config / "policy.json").write_text(json.dumps({"schema_version": 2, "model": ci.MODEL, "organization": "org"}))
    (config / "review-settings.json").write_text('{"permissions": {"deny": []}}')
    (root / "AGENTS.md").write_text("Original guidance\n")
    (root / "app.txt").write_text("base\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    comparison_base = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-qb", "feature")
    (root / "app.txt").write_text("PR change\n")
    git(root, "commit", "-qam", "feature")
    head = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    (root / "AGENTS.md").write_text("Trusted latest guidance\n")
    git(root, "commit", "-qam", "advance base")
    trusted = git(root, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "origin", "main", "feature")
    git(root, "fetch", "-q", "origin", "main")
    git(root, "checkout", "-q", "--detach", trusted)
    repo = {"full_name": "org/repo", "owner": {"type": "Organization", "login": "org"}, "default_branch": "main"}
    pr = {"number": 5, "state": "open", "draft": False, "user": {"type": "User", "login": "author"},
          "head": {"ref": "feature", "sha": head, "repo": {"full_name": "org/repo"}},
          "base": {"ref": "main", "sha": comparison_base}}
    event = {"repository": repo, "action": "created", "issue": {"number": 5, "pull_request": {"url": "x"}},
             "comment": {"user": {"type": "User", "login": "member"}, "body": "@muse please explain"}}
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event))
    envfile, outfile, runner = tmp_path / "env", tmp_path / "out", tmp_path / "runner"
    runner.mkdir()
    class API:
        def get(self, path):
            if "/pulls/" in path: return pr
            if path.startswith("users/"): return {"type": "User"}
            if path.endswith("/permission"): return {"permission": "write"}
            return None
        def pages(self, path): return []
    monkeypatch.setattr(ci, "GitHub", lambda token: API())
    env = {"GITHUB_WORKSPACE": str(root), "GITHUB_EVENT_PATH": str(event_file), "GITHUB_EVENT_NAME": "issue_comment",
           "GITHUB_REPOSITORY": "org/repo", "GITHUB_ACTOR": "member", "MUSE_TRIGGERING_ACTOR": "member",
           "MUSE_TRUSTED_BASE_SHA": trusted, "GITHUB_RUN_ID": "10", "RUNNER_TEMP": str(runner),
           "GITHUB_ENV": str(envfile), "GITHUB_OUTPUT": str(outfile), "GH_TOKEN": "fake"}
    ci.prepare("followup", env)
    variables, output = outputs(envfile), outputs(outfile)
    state = json.loads(Path(variables["MUSE_CI_STATE"]).read_text())
    assert state["base"] == comparison_base and state["checkout_sha"] == trusted
    assert "Trusted latest guidance" in output["prompt"] and "PR change" in output["prompt"]
    assert git(root, "rev-parse", "HEAD") == head


def test_action_restoration_accepts_forward_main_only_and_rejects_unrelated_writes(tmp_path):
    init_repo(tmp_path)
    config = tmp_path / ".claude/settings.json"
    config.parent.mkdir()
    config.write_text("base\n")
    (tmp_path / "app.txt").write_text("base\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    base = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", "-qb", "feature")
    config.write_text("pr version\n")
    git(tmp_path, "commit", "-qam", "feature")
    head = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "checkout", "-q", "main")
    config.write_text("trusted version\n")
    git(tmp_path, "commit", "-qam", "trusted")
    trusted = git(tmp_path, "rev-parse", "HEAD")
    config.write_text("forward version\n")
    git(tmp_path, "commit", "-qam", "forward")
    forward = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", forward)
    git(tmp_path, "checkout", "-q", "feature")
    # The pinned Action snapshots the PR version, then restores origin/main.
    snapshot = tmp_path / ".claude-pr/.claude/settings.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("pr version\n")
    config.write_text("forward version\n")
    state = {"base": base, "checkout_sha": trusted, "head": head, "default_branch": "main"}
    state["restore_base"] = ci.restore_revision(tmp_path, state)
    assert state["restore_base"] == forward
    ci.review_workspace(tmp_path, state)
    (tmp_path / "app.txt").write_text("unrelated write\n")
    with pytest.raises(ci.Refusal):
        ci.review_workspace(tmp_path, state)
    (tmp_path / "app.txt").write_text("base\n")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", base)
    with pytest.raises(ci.Refusal):
        ci.restore_revision(tmp_path, state)


def test_failed_review_retains_failure_if_head_refresh_unavailable(tmp_path, monkeypatch):
    state_path, summary = tmp_path / "state.json", tmp_path / "summary"
    state_path.write_text(json.dumps({"mode": "review", "repository": "org/repo", "number": 5, "head": "a" * 40, "default_branch": "main"}))
    class Offline:
        def get(self, path): raise ci.Refusal("API unavailable")
        def request(self, method, path, data=None): pytest.fail("No publication after failure")
    monkeypatch.setattr(ci, "GitHub", lambda token: Offline())
    env = {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state_path), "GH_TOKEN": "fake",
           "MUSE_ACTION_OUTCOME": "failure", "MUSE_ACTION_CONCLUSION": "failure", "GITHUB_STEP_SUMMARY": str(summary)}
    with pytest.raises(ci.Refusal, match="Action failed"):
        ci.finish("review", env)
    assert "a" * 40 in summary.read_text()
    assert "unavailable" in summary.read_text().lower() or "could not" in summary.read_text().lower()


@pytest.mark.parametrize("suffix", ["json", "yaml", "yml", "toml", "snap", "JSON"])
def test_each_data_fixture_suffix_gets_exact_exception(tmp_path, suffix):
    git(tmp_path, "init", "-q")
    directory = tmp_path / "fixtures"
    directory.mkdir()
    name = f"fixtures/x.env.{suffix}"
    (tmp_path / name).write_text("public data\n")
    git(tmp_path, "add", "--", name)
    rules = ci.data_fixture_read_rules(tmp_path)
    assert f"Read(!/{name})" in rules


@pytest.mark.parametrize("mode", ["review", "followup"])
def test_retargeted_pr_refuses_before_publication(tmp_path, monkeypatch, mode):
    head = "a" * 40
    state = {"mode": mode, "repository": "org/repo", "number": 5, "head": head, "default_branch": "main"}
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    class API:
        def get(self, path): return {"head": {"sha": head}, "base": {"ref": "release"}}
        def request(self, method, path, data=None): pytest.fail("Retargeted PR must not publish")
    monkeypatch.setattr(ci, "GitHub", lambda token: API())
    monkeypatch.setattr(ci, "restore_revision", lambda *args: pytest.fail("Retarget must refuse before restoring"))
    env = {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state_path), "GH_TOKEN": "fake",
           "MUSE_ACTION_OUTCOME": "success", "MUSE_ACTION_CONCLUSION": "success"}
    with pytest.raises(ci.Refusal):
        ci.finish(mode, env)


def test_failed_review_at_same_head_never_publishes(tmp_path, monkeypatch):
    head = "a" * 40
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"mode": "review", "repository": "org/repo", "number": 5,
                                      "head": head, "default_branch": "main"}))
    calls = []
    class API:
        def get(self, path):
            calls.append(("GET", path))
            return {"head": {"sha": head}, "base": {"ref": "main"}}
        def request(self, method, path, data=None):
            pytest.fail(f"Failed action attempted publication: {method} {path}")
    monkeypatch.setattr(ci, "GitHub", lambda token: API())
    with pytest.raises(ci.Refusal, match="Action failed"):
        ci.finish("review", {"GITHUB_WORKSPACE": str(tmp_path), "MUSE_CI_STATE": str(state_path),
                             "GH_TOKEN": "fake", "MUSE_ACTION_OUTCOME": "failure",
                             "MUSE_ACTION_CONCLUSION": "failure"})
    assert calls == [("GET", "repos/org/repo/pulls/5")]


@pytest.mark.parametrize("extra", [
    {"env": {"ANTHROPIC_AUTH_TOKEN": "public-placeholder"}},
    {"apiKeyHelper": "echo public-placeholder"},
    {"unknownSetting": True},
])
def test_permission_profiles_reject_unsupported_fields_in_both_entry_points(tmp_path, extra):
    profile = {"permissions": {"deny": []}, **extra}
    settings = tmp_path / ".github/muse-ci/review-settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps(profile))
    with pytest.raises(ci.Refusal, match="unsupported fields"):
        ci.load_configuration(tmp_path, "review")
    with pytest.raises(ci.Refusal, match="unsupported fields"):
        ci.configuration(tmp_path, "review", tmp_path / "runtime", source=profile)


def test_permission_profile_preserves_custom_rules_and_isolation_fields(tmp_path):
    source = {"permissions": {"allow": ["Read", "Grep"], "deny": ["Read(private.txt)"]},
              "disableAllHooks": True, "autoMemoryEnabled": False, "claudeMdExcludes": ["**"]}
    settings = tmp_path / ".github/muse-ci/review-settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps(source))
    assert ci.load_configuration(tmp_path, "review") == source
    result = ci.configuration(tmp_path, "review", tmp_path / "runtime", source=source)
    assert result["permissions"]["allow"] == ["Read", "Grep"]
    assert result["permissions"]["deny"][-1] == "Read(private.txt)"
    assert result["disableAllHooks"] is True and result["autoMemoryEnabled"] is False
    assert result["claudeMdExcludes"] == ["**"]
    assert source["permissions"]["deny"] == ["Read(private.txt)"]
