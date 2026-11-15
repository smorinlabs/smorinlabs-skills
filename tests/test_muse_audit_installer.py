"""Audit-triage cutover preserves reviews and refuses modified legacy files."""
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup"
spec = importlib.util.spec_from_file_location("muse_audit_installer", SKILL / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def seed(root, variant=0, activation="MUSE_CI_ENABLED", model="muse-spark-1.3-contributor"):
    snapshots = json.loads(installer.TRIAGE_LEGACY.read_text())
    for name, bodies in snapshots.items():
        bodies = [body for body in bodies if isinstance(body, str)]
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(installer.triage_render(bodies[min(variant, len(bodies)-1)], "example-org", model, activation))
    for name, text in {
        "AGENTS.md": "# Project instructions\nKeep project work.\n",
        "opencode.json": '{"unrelated":true}\n',
        ".opencode/muse-ci/custom.json": "keep unrelated local configuration\n",
        ".github/workflows/muse-pr-review.yml": "preserve existing reviews\n",
        ".github/scripts/muse_ci.py": "preserve existing review helper\n",
        ".github/muse-ci/policy.json": '{"model":"muse-wonder-1.0"}\n',
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("variant", range(3))
@pytest.mark.parametrize("activation", installer.TRIAGE_SWITCHES)
def test_cutover_preserves_review_and_unrelated_files(tmp_path, variant, activation):
    seed(tmp_path, variant, activation)
    before = files(tmp_path)
    with pytest.raises(installer.Conflict, match="--migrate-opencode"):
        installer.triage_plan(tmp_path, "example-org")
    changes = installer.triage_plan(tmp_path, "example-org", migrate_opencode=True, codeowner="@example-org/owners")
    assert files(tmp_path) == before  # preview is read-only
    assert changes[".github/scripts/audit_triage.py"] is None
    assert changes[installer.TRIAGE_OLD_POLICY] is None
    assert "opencode run" not in changes[".github/workflows/audit-triage.yml"]
    assert "anthropics/claude-code-action@" in changes[".github/workflows/audit-triage.yml"]
    assert f"vars.{activation}" in changes[".github/workflows/audit-triage.yml"]
    installer.apply(tmp_path, changes)
    for name in before.keys() - changes.keys():
        assert (tmp_path / name).read_bytes() == before[name]
    assert (tmp_path / "AGENTS.md").read_bytes().startswith(before["AGENTS.md"])
    policy = json.loads((tmp_path / installer.TRIAGE_POLICY).read_text())
    assert policy["activation_variable"] == activation
    assert policy["organization"] == "example-org"
    assert installer.triage_plan(tmp_path, "example-org", codeowner="@example-org/owners") == {}
    assert installer.triage_plan(tmp_path, "example-org", migrate_opencode=True, codeowner="@example-org/owners") == {}


@pytest.mark.parametrize("model", installer.MODELS)
def test_preserves_established_model_and_runtime_copy(tmp_path, model):
    seed(tmp_path, model=model)
    changes = installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)
    policy = json.loads(changes[installer.TRIAGE_POLICY])
    assert policy["model"] == model
    assert f"The selected model is {installer.MODELS[model]} ({model})." in changes[".github/muse-audit-triage/NOTICE"]
    assert changes[".github/muse-audit-triage/runtime.py"] == installer.render(
        (installer.TEMPLATES / ".github/scripts/muse_ci.py").read_text(), "example-org", model
    )
    installer.apply(tmp_path, changes)
    assert installer.triage_plan(tmp_path, "example-org") == {}


@pytest.mark.parametrize("path", list(json.loads(installer.TRIAGE_LEGACY.read_text())))
def test_modified_legacy_refused_without_writes(tmp_path, path):
    seed(tmp_path)
    item = tmp_path / path
    item.write_text(item.read_text() + "\nchanged locally\n")
    before = files(tmp_path)
    with pytest.raises((installer.Conflict, ValueError)):
        installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)
    assert files(tmp_path) == before


@pytest.mark.parametrize("path", [".github/scripts/muse_audit_triage.py", ".github/muse-audit-triage/triage-settings.json"])
def test_unrecognized_destination_refused(tmp_path, path):
    seed(tmp_path)
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("user-owned data\n")
    before = files(tmp_path)
    with pytest.raises(installer.Conflict, match="preserve it"):
        installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)
    assert files(tmp_path) == before


def test_no_fresh_automatic_repair_install(tmp_path):
    with pytest.raises(installer.Conflict, match="existing reviewed installation"):
        installer.triage_plan(tmp_path, "example-org")


def test_owner_and_activation_mismatch_refused(tmp_path):
    seed(tmp_path)
    with pytest.raises(installer.Conflict, match="organization differs"):
        installer.triage_plan(tmp_path, "other-org", migrate_opencode=True)
    workflow = tmp_path / ".github/workflows/audit-triage.yml"
    workflow.write_text(workflow.read_text().replace("vars.MUSE_CI_ENABLED", "vars.UNKNOWN_ENABLED"))
    with pytest.raises(installer.Conflict, match="activation variable"):
        installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)


def test_symlink_refused_before_plan(tmp_path):
    seed(tmp_path)
    target = tmp_path / ".github/scripts/muse_audit_triage.py"
    target.symlink_to(tmp_path / "AGENTS.md")
    with pytest.raises(installer.Conflict, match="symlink"):
        installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)


def test_codeowners_keeps_review_block_and_last_match_precedence(tmp_path):
    seed(tmp_path)
    path = tmp_path / ".github/CODEOWNERS"
    old = "# existing review ownership\n/.github/workflows/muse-*.yml @review-owners\n* @project-owner\n"
    path.write_text(old)
    installer.apply(tmp_path, installer.triage_plan(tmp_path, "example-org", migrate_opencode=True, codeowner="@triage-owner"))
    assert path.read_text().startswith(old)
    path.write_text(path.read_text() + "* @later-owner\n")
    installer.apply(tmp_path, installer.triage_plan(tmp_path, "example-org", codeowner="@triage-owner"))
    assert path.read_text().index("* @later-owner") < path.read_text().index(installer.TRIAGE_OWNERS)
    assert installer.triage_plan(tmp_path, "example-org", codeowner="@triage-owner") == {}


def test_missing_legacy_file_and_partial_cutover_refused(tmp_path):
    seed(tmp_path)
    (tmp_path / ".github/scripts/audit_triage.py").unlink()
    with pytest.raises(installer.Conflict, match="legacy"):
        installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)


def test_model_change_is_explicit_and_idempotent(tmp_path):
    seed(tmp_path)
    installer.apply(tmp_path, installer.triage_plan(tmp_path, "example-org", migrate_opencode=True))
    installer.apply(tmp_path, installer.triage_plan(tmp_path, "example-org", model="muse-spark-1.3"))
    assert json.loads((tmp_path / installer.TRIAGE_POLICY).read_text())["model"] == "muse-spark-1.3"
    assert installer.triage_plan(tmp_path, "example-org") == {}


@pytest.mark.parametrize("name", [".github/workflows/audit-triage.yml", ".github/scripts/audit_triage.py"])
def test_crlf_modified_legacy_is_not_an_exact_snapshot(tmp_path, name):
    seed(tmp_path)
    path = tmp_path / name
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(installer.Conflict, match="legacy"):
        installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)


def test_instruction_and_ownership_surrounding_bytes_preserved(tmp_path):
    seed(tmp_path)
    instructions = tmp_path / "AGENTS.md"
    old_instructions = b"# User instructions\r\nKeep this.  \r\n\r\n"
    instructions.write_bytes(old_instructions)
    owners = tmp_path / ".github/CODEOWNERS"
    old_owners = b"* @project-owner\r\n\r\n"
    owners.write_bytes(old_owners)
    installer.apply(tmp_path, installer.triage_plan(tmp_path, "example-org", migrate_opencode=True, codeowner="@triage-owner"))
    assert instructions.read_bytes().startswith(old_instructions)
    assert owners.read_bytes().startswith(old_owners)
    assert installer.triage_plan(tmp_path, "example-org", codeowner="@triage-owner") == {}


def test_private_variant_digest_recognizes_exact_bytes_without_shipping_content(tmp_path, monkeypatch):
    seed(tmp_path, activation="MUSE_AUDIT_TRIAGE_ENABLED", model="muse-spark-1.3")
    path = tmp_path / ".github/scripts/audit_triage.py"
    path.write_bytes(path.read_bytes() + b"\n# synthetic private customization\n")
    canonical = path.read_text().replace("example-org", "__MUSE_ORG__").replace(
        "Muse Spark 1.3 Standard", "Muse Spark 1.3 Contributor"
    ).replace("muse-spark-1.3", installer.DEFAULT_MODEL)
    snapshots = json.loads(installer.TRIAGE_LEGACY.read_text())
    snapshots[".github/scripts/audit_triage.py"] = [{"sha256": hashlib.sha256(canonical.encode()).hexdigest()}]
    registry = tmp_path / "private-digests.json"
    registry.write_text(json.dumps(snapshots))
    monkeypatch.setattr(installer, "TRIAGE_LEGACY", registry)
    assert installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)[".github/scripts/audit_triage.py"] is None
    path.write_bytes(path.read_bytes() + b"# changed\n")
    with pytest.raises(installer.Conflict, match="legacy"):
        installer.triage_plan(tmp_path, "example-org", migrate_opencode=True)
