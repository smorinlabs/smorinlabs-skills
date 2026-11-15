"""Offline checks for deliberate migration of generated OpenCode Muse installs."""
import importlib.util
import json
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup"
spec = importlib.util.spec_from_file_location("muse_migration_installer", SKILL / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def templates(tmp_path, monkeypatch):
    root = tmp_path / "templates"
    for name in installer.TEMPLATE_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"model":"muse-spark-1.3-contributor"}\n' if name.endswith("policy.json") else
                        f"new {name} __MUSE_ORG__ muse-spark-1.3-contributor\n")
    (root / "AGENTS.muse.md").write_text(installer.MARKER + "\nnew security\n" + installer.END_MARKER + "\n")
    monkeypatch.setattr(installer, "TEMPLATES", root)
    return root


def legacy(root, version=0, model="muse-spark-1.3", fixes=True):
    snapshots = json.loads(installer.LEGACY.read_text())
    for name, versions in snapshots.items():
        if name == "AGENTS.muse.md":
            name = "AGENTS.md"
        if not fixes and (name.endswith("opencode-fix-pr.yml") or name.endswith("/fix.json")):
            continue
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(installer.render(versions[min(version, len(versions)-1)], "example-org", model))
    (root / "opencode.json").write_text('{"provider":{"unrelated":true}}\n')
    (root / ".opencode/muse-ci/custom.json").write_text("keep\n")


@pytest.mark.parametrize("version", range(4))
def test_migrate_exact_legacy_variants_and_preserve_other_files(tmp_path, templates, version):
    legacy(tmp_path, version)
    before = (tmp_path / "opencode.json").read_bytes()
    with pytest.raises(installer.Conflict, match="--migrate-opencode"):
        installer.plan(tmp_path, "example-org")
    changes = installer.plan(tmp_path, "example-org", migrate_opencode=True)
    assert changes[".github/workflows/opencode-pr-review.yml"] is None
    assert ".github/workflows/muse-fix-pr.yml" in changes
    assert "muse-spark-1.3\"" in changes[installer.NEW_POLICY]
    assert (tmp_path / ".github/workflows/opencode-pr-review.yml").exists()
    installer.apply(tmp_path, changes)
    assert (tmp_path / "opencode.json").read_bytes() == before
    assert (tmp_path / ".opencode/muse-ci/custom.json").read_text() == "keep\n"
    assert installer.plan(tmp_path, "example-org", migrate_opencode=True) == {}
    assert installer.plan(tmp_path, "example-org") == {}


@pytest.mark.parametrize("name", [".github/workflows/opencode-pr-review.yml", ".github/scripts/muse_ci.py",
                                  ".opencode/muse-ci/policy.json", "AGENTS.md"])
def test_refuses_modified_legacy_before_any_write(tmp_path, templates, name):
    legacy(tmp_path)
    path = tmp_path / name
    original = path.read_text()
    path.write_text(original.replace(installer.END_MARKER, "custom\n" + installer.END_MARKER)
                    if name == "AGENTS.md" else original + "custom\n")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and "templates" not in p.parts}
    with pytest.raises(installer.Conflict):
        installer.plan(tmp_path, "example-org", migrate_opencode=True)
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and "templates" not in p.parts}
    assert before == after


def test_owner_block_is_migrated_without_disturbing_other_rules(tmp_path, templates):
    legacy(tmp_path, fixes=False)
    name = ".github/CODEOWNERS"
    lines = [installer.OWNERS_MARKER, "# CODEOWNERS is not enforcement on its own; branch rules must require review."]
    lines += [f"{p} @example-org/team" for p in (*installer.OLD_OWNED_PATHS, "/" + name)]
    path = tmp_path / name
    path.write_text("/other @someone\n\n" + "\n".join(lines) + "\n")
    changes = installer.plan(tmp_path, "example-org", codeowner="@example-org/team", migrate_opencode=True)
    installer.apply(tmp_path, changes)
    assert path.read_text().startswith("/other @someone\n\n")
    assert "/.github/workflows/muse-*.yml @example-org/team" in path.read_text()
    assert installer.plan(tmp_path, "example-org", codeowner="@example-org/team") == {}


def test_conflicting_models_need_explicit_choice(tmp_path, templates):
    legacy(tmp_path, fixes=False)
    path = tmp_path / installer.NEW_POLICY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"model":"muse-wonder-1.0"}\n')
    with pytest.raises(installer.Conflict, match="models conflict"):
        installer.plan(tmp_path, "example-org", migrate_opencode=True)
    # An explicit choice does not authorize overwriting an existing differing new policy.
    with pytest.raises(installer.Conflict, match="Existing .github/muse-ci/policy.json differs"):
        installer.plan(tmp_path, "example-org", model="muse-spark-1.3", migrate_opencode=True)


def test_fresh_install_preserves_opencode_jsonc_and_repeats(tmp_path, templates):
    (tmp_path / "opencode.jsonc").write_text("// user's config\n")
    changes = installer.plan(tmp_path, "example-org")
    installer.apply(tmp_path, changes)
    assert (tmp_path / "opencode.jsonc").read_text() == "// user's config\n"
    assert installer.plan(tmp_path, "example-org") == {}


def test_cli_preview_lists_deletions_without_mutating(tmp_path, templates, monkeypatch, capsys):
    legacy(tmp_path, fixes=False)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    class Probe:
        returncode = 0
        stdout = str(tmp_path)
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **kw: Probe())
    monkeypatch.setattr(installer.sys, "argv", ["install.py", str(tmp_path), "--organization", "example-org",
                                               "--no-codeowner", "--migrate-opencode"])
    assert installer.main() == 0
    output = capsys.readouterr().out
    assert "delete .github/workflows/opencode-pr-review.yml" in output
    assert "model: muse-spark-1.3" in output
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("shape", ["missing_start", "missing_end", "reversed", "duplicate_start", "duplicate_end"])
def test_apply_refuses_malformed_instruction_markers_before_any_write(tmp_path, templates, monkeypatch, shape):
    legacy(tmp_path, fixes=False)
    instructions = tmp_path / "AGENTS.md"
    body = instructions.read_text()
    if shape == "missing_start":
        body = body.replace(installer.MARKER, "", 1)
    elif shape == "missing_end":
        body = body.replace(installer.END_MARKER, "", 1)
    elif shape == "reversed":
        body = body.replace(installer.MARKER, "__REVIEW_MARKER_SWAP__", 1).replace(
            installer.END_MARKER, installer.MARKER, 1).replace("__REVIEW_MARKER_SWAP__", installer.END_MARKER, 1)
    elif shape == "duplicate_start":
        body += installer.MARKER + "\n"
    else:
        body += installer.END_MARKER + "\n"
    instructions.write_text(body)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    class Probe:
        returncode = 0
        stdout = str(tmp_path)
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **kw: Probe())
    monkeypatch.setattr(installer.sys, "argv", ["install.py", str(tmp_path), "--organization", "example-org",
                                               "--no-codeowner", "--migrate-opencode", "--apply"])
    assert installer.main() == 1
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_unmarked_project_instructions_are_preserved_and_repeat(tmp_path, templates):
    instructions = tmp_path / "AGENTS.md"
    guidance = "# Project instructions\nKeep the documented development workflow.\n"
    instructions.write_text(guidance)
    installer.apply(tmp_path, installer.plan(tmp_path, "example-org"))
    assert instructions.read_text().startswith(guidance)
    assert instructions.read_text().count(installer.MARKER) == 1
    assert instructions.read_text().count(installer.END_MARKER) == 1
    assert installer.plan(tmp_path, "example-org") == {}


@pytest.mark.parametrize("generation", ["legacy", "new"])
def test_managed_ownership_moves_after_later_rules_and_repeats(tmp_path, templates, generation):
    owner = "@example-org/team"
    location = ".github/CODEOWNERS"
    if generation == "legacy":
        legacy(tmp_path, fixes=False)
        paths = (*installer.OLD_OWNED_PATHS, "/" + location)
        block = "\n".join([installer.OWNERS_MARKER,
            "# CODEOWNERS is not enforcement on its own; branch rules must require review.",
            *(f"{path} {owner}" for path in paths)]) + "\n"
    else:
        installer.apply(tmp_path, installer.plan(tmp_path, "example-org", codeowner=owner))
        block = (tmp_path / location).read_text()
    before = "/unrelated/ @another-team\n\n"
    after = "\n# Keep these repository-wide rules.\n* @default-team\n/docs/ @docs-team\n"
    target = tmp_path / location
    target.write_text(before + block + after)
    original = target.read_bytes()
    changes = installer.plan(tmp_path, "example-org", codeowner=owner, migrate_opencode=generation == "legacy")
    # Preview is read-only and shows the code-owner file as an intentional update.
    assert target.read_bytes() == original
    rendered = changes[location]
    assert rendered.startswith(before + after)
    assert rendered.index("* @default-team") < rendered.index(installer.OWNERS_MARKER)
    assert rendered.index("/docs/ @docs-team") < rendered.index(installer.OWNERS_MARKER)
    assert rendered.count(installer.OWNERS_MARKER) == 1
    assert rendered.endswith(f"/{location} {owner}\n")
    assert f"/.github/workflows/muse-*.yml {owner}\n" in rendered
    installer.apply(tmp_path, changes)
    assert installer.plan(tmp_path, "example-org", codeowner=owner) == {}


def previous_managed(root, model, fixes, baseline=0):
    snapshots = json.loads(installer.MANAGED.read_text())
    for name, versions in snapshots.items():
        if not fixes and name in installer.OPTIONAL:
            continue
        target = root / ("AGENTS.md" if name == "AGENTS.muse.md" else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = installer.render(versions[min(baseline, len(versions) - 1)], "example-org", model)
        if name == "AGENTS.muse.md":
            text = "# Existing project guidance\n\n" + text + "\nKeep this trailing guidance.\n"
        target.write_text(text)


@pytest.mark.parametrize("model", sorted(installer.MODELS))
@pytest.mark.parametrize("fixes", [False, True])
@pytest.mark.parametrize("baseline", [0, 1, 2], ids=["0.5.0", "0.5.1", "0.5.2"])
def test_known_claude_install_updates_preserving_model_fixes_and_unrelated_files(tmp_path, templates, model, fixes, baseline):
    previous_managed(tmp_path, model, fixes, baseline)
    unrelated = tmp_path / "opencode.json"
    unrelated.write_text('{"keep":true}\n')
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    changes = installer.plan(tmp_path, "example-org")
    assert changes and all(content is not None for content in changes.values())
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert json.loads(changes[installer.NEW_POLICY])["model"] == model
    assert (".github/workflows/muse-fix-pr.yml" in changes) is fixes
    installer.apply(tmp_path, changes)
    assert unrelated.read_text() == '{"keep":true}\n'
    assert (tmp_path / "AGENTS.md").read_text().startswith("# Existing project guidance\n\n")
    assert (tmp_path / "AGENTS.md").read_text().endswith("\nKeep this trailing guidance.\n")
    assert installer.plan(tmp_path, "example-org") == {}


@pytest.mark.parametrize("name", [".github/scripts/muse_ci.py", ".github/workflows/muse-followup.yml", "AGENTS.md"])
def test_changed_claude_install_refuses_update_without_writes(tmp_path, templates, name):
    previous_managed(tmp_path, "muse-spark-1.3", False)
    target = tmp_path / name
    current = target.read_text()
    target.write_text(current.replace(installer.END_MARKER, "Local change.\n" + installer.END_MARKER)
                      if name == "AGENTS.md" else current + "Local change.\n")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(installer.Conflict, match="differs"):
        installer.plan(tmp_path, "example-org")
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("generation", ["legacy", "previous", "current"])
@pytest.mark.parametrize("kind", ["helper", "policy", "instructions"])
def test_crlf_modified_generated_files_refuse_before_writes(tmp_path, templates, generation, kind):
    if generation == "legacy":
        legacy(tmp_path, fixes=False)
    elif generation == "previous":
        previous_managed(tmp_path, "muse-spark-1.3", False)
    else:
        installer.apply(tmp_path, installer.plan(tmp_path, "example-org"))
    name = {"helper": ".github/scripts/muse_ci.py", "instructions": "AGENTS.md",
            "policy": installer.OLD_POLICY if generation == "legacy" else installer.NEW_POLICY}[kind]
    target = tmp_path / name
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(installer.Conflict, match="differs"):
        installer.plan(tmp_path, "example-org", migrate_opencode=generation == "legacy")
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_update_preserves_instruction_surroundings_byte_for_byte(tmp_path, templates):
    previous_managed(tmp_path, "muse-spark-1.3", False)
    target = tmp_path / "AGENTS.md"
    previous = json.loads(installer.MANAGED.read_text())["AGENTS.muse.md"][0].strip().encode()
    prefix, suffix = b"# Project\r\nTrailing spaces.  \r\n\r\n", b"\r\n\r\nKeep this.  \r\n"
    target.write_bytes(prefix + previous + suffix)
    changes = installer.plan(tmp_path, "example-org")
    installer.apply(tmp_path, changes)
    current = (templates / "AGENTS.muse.md").read_bytes().strip()
    assert target.read_bytes() == prefix + current + suffix
    assert installer.plan(tmp_path, "example-org") == {}


def test_append_preserves_unmarked_instruction_bytes(tmp_path, templates):
    target = tmp_path / "AGENTS.md"
    original = b"# Project\r\nKeep trailing spaces.  \r\n\r\n"
    target.write_bytes(original)
    installer.apply(tmp_path, installer.plan(tmp_path, "example-org"))
    assert target.read_bytes().startswith(original)
    assert installer.plan(tmp_path, "example-org") == {}
