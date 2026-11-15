#!/usr/bin/env python3
"""Plan or apply Muse CI files to a local Git worktree; never changes GitHub."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SKILL = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL / "templates"
LEGACY = SKILL / "references/legacy/snapshots.json"
MARKER = "<!-- muse-github-setup:security:start -->"
END_MARKER = "<!-- muse-github-setup:security:end -->"
OWNERS_MARKER = "# Muse CI security-sensitive configuration (muse-github-setup)."
OWNERS_FILES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
OWNED_PATHS = ("/.github/workflows/muse-*.yml", "/.github/scripts/muse_ci.py",
               "/.github/muse-ci/", "/AGENTS.md")
OLD_OWNED_PATHS = ("/.github/workflows/opencode-*.yml", "/.github/scripts/muse_ci.py",
                   "/.opencode/muse-ci/", "/opencode.json", "/AGENTS.md")
TEMPLATE_FILES = (
    ".github/scripts/muse_ci.py", ".github/workflows/muse-pr-review.yml",
    ".github/workflows/muse-followup.yml", ".github/workflows/muse-fix-pr.yml",
    ".github/muse-ci/policy.json", ".github/muse-ci/review-settings.json",
    ".github/muse-ci/fix-settings.json", ".github/muse-ci/NOTICE",
)
OPTIONAL = {".github/workflows/muse-fix-pr.yml", ".github/muse-ci/fix-settings.json"}
OLD_POLICY = ".opencode/muse-ci/policy.json"
NEW_POLICY = ".github/muse-ci/policy.json"
DEFAULT_MODEL = "muse-spark-1.3-contributor"
MODELS = {
    "muse-spark-1.3-contributor": "Muse Spark 1.3 Contributor",
    "muse-spark-1.3": "Muse Spark 1.3 Standard",
    "muse-wonder-1.0": "Muse Wonder 1.0",
}


class Conflict(ValueError):
    pass


def destination(root: Path, name: str) -> Path:
    result = root / name
    current = result
    while current != root:
        if current.is_symlink():
            raise Conflict(f"Refusing a symlink at {current.relative_to(root)}")
        current = current.parent
    return result


def with_model(body: str, model: str) -> str:
    return body.replace(MODELS[DEFAULT_MODEL], MODELS[model]).replace(DEFAULT_MODEL, model)


def render(body: str, organization: str, model: str) -> str:
    return with_model(body.replace("__MUSE_ORG__", organization), model)


def policy_model(root: Path, name: str) -> str | None:
    path = destination(root, name)
    if not path.exists():
        return None
    try:
        model = json.loads(path.read_text())["model"]
        model = model.removeprefix("model_api/")
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise Conflict(f"Cannot determine model from {name}; reconcile its policy") from error
    if model not in MODELS:
        raise Conflict(f"Unknown model in {name}; reconcile its policy")
    return model


def owners_change(root: Path, codeowner: str, migrate: bool = False) -> dict[str, str]:
    login = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    if not re.fullmatch(rf"@{login}(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?", codeowner):
        raise Conflict("codeowner must be the owner's @login or @organization/team")
    existing = [name for name in OWNERS_FILES if destination(root, name).exists()]
    if len(existing) > 1:
        raise Conflict(f"Several CODEOWNERS files exist ({', '.join(existing)}); GitHub reads only the first")
    name = existing[0] if existing else OWNERS_FILES[0]
    current = destination(root, name).read_text() if existing else ""
    def block(paths: tuple[str, ...]) -> str:
        return "\n".join([OWNERS_MARKER, "# CODEOWNERS is not enforcement on its own; branch rules must require review.",
                           *(f"{path} {codeowner}" for path in paths)]) + "\n"
    new = block((*OWNED_PATHS, "/" + name))
    def replace_block(existing: str) -> dict[str, str]:
        before, after = current.split(existing, 1)
        if any(line.strip() and not line.lstrip().startswith("#") for line in after.splitlines()):
            # CODEOWNERS uses the last matching rule. Keep unrelated rows in
            # order, then make the explicitly requested managed ownership win.
            remaining = before + after
            separator = ""
            if remaining and not remaining.endswith("\n\n"):
                separator = "\n" if remaining.endswith("\n") else "\n\n"
            return {name: remaining + separator + new}
        return {} if existing == new else {name: before + new + after}
    if OWNERS_MARKER in current:
        if current.count(OWNERS_MARKER) != 1:
            raise Conflict(f"Existing Muse block in {name} differs; reconcile its owners explicitly")
        if new in current:
            return replace_block(new)
        if migrate:
            # Early installer versions did not include the CODEOWNERS file itself.
            for paths in ((*OLD_OWNED_PATHS, "/" + name), OLD_OWNED_PATHS):
                old = block(paths)
                if old in current:
                    return replace_block(old)
        raise Conflict(f"Existing Muse block in {name} differs; reconcile its owners explicitly")
    return {name: current.rstrip() + ("\n\n" if current else "") + new}


def plan(root: Path, organization: str, with_fixes: bool = False, model: str | None = None,
         codeowner: str | None = None, migrate_opencode: bool = False) -> dict[str, str | None]:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", organization):
        raise Conflict("organization must be the actual GitHub organization login")
    if model is not None and model not in MODELS:
        raise Conflict(f"model must be one of: {', '.join(MODELS)}")
    snapshots = json.loads(LEGACY.read_text())
    old_names = [name for name in snapshots if name != "AGENTS.muse.md"]
    # The helper has the same destination in both generations; it alone is not proof of a legacy install.
    legacy_present = any(destination(root, n).exists() for n in old_names if n != ".github/scripts/muse_ci.py")
    if legacy_present and not migrate_opencode:
        raise Conflict("Legacy OpenCode Muse files exist; use --migrate-opencode after reviewing the cutover")
    legacy_model = policy_model(root, OLD_POLICY) if legacy_present else None
    installed_model = policy_model(root, NEW_POLICY)
    if legacy_present and legacy_model is None:
        raise Conflict("Legacy policy is missing; cannot preserve its model")
    if model is None and legacy_model and installed_model and legacy_model != installed_model:
        raise Conflict("Legacy and new policy models conflict; select --model explicitly after review")
    selected = model or legacy_model or installed_model or DEFAULT_MODEL
    # Preserve the optional fix workflow across migration and repeated installs.
    with_fixes = (with_fixes or destination(root, ".github/workflows/opencode-fix-pr.yml").exists()
                  or destination(root, ".github/workflows/muse-fix-pr.yml").exists())
    changes: dict[str, str | None] = {}
    recognized: set[str] = set()
    if legacy_present:
        for name in old_names:
            target = destination(root, name)
            if not target.exists():
                continue
            current = target.read_text()
            # Legacy files are validated against their original model, not the selected replacement.
            if not any(current == render(body, organization, legacy_model) for body in snapshots[name]):
                raise Conflict(f"Existing legacy {name} differs; preserve it and prepare a reviewed reconciliation")
            recognized.add(name)
            if name != ".github/scripts/muse_ci.py":
                changes[name] = None
    for name in TEMPLATE_FILES:
        if not with_fixes and name in OPTIONAL:
            continue
        body = render((TEMPLATES / name).read_text(), organization, selected)
        target = destination(root, name)
        if target.exists() and target.read_text() != body and name not in recognized:
            raise Conflict(f"Existing {name} differs; preserve it and prepare a reviewed update")
        if not target.exists() or target.read_text() != body:
            changes[name] = body
    instructions = destination(root, "AGENTS.md")
    current = instructions.read_text() if instructions.exists() else ""
    security = (TEMPLATES / "AGENTS.muse.md").read_text()
    marker_counts = current.count(MARKER), current.count(END_MARKER)
    if marker_counts != (0, 0):
        if marker_counts != (1, 1) or current.index(END_MARKER) < current.index(MARKER):
            raise Conflict("Existing Muse AGENTS.md section differs; preserve its project-specific edits")
        start = current.index(MARKER)
        end = current.index(END_MARKER, start) + len(END_MARKER)
        existing_block = current[start:end]
        if existing_block != security.strip():
            if not migrate_opencode or not any(existing_block == old.strip() for old in snapshots["AGENTS.muse.md"]):
                raise Conflict("Existing Muse AGENTS.md section differs; preserve its project-specific edits")
            changes["AGENTS.md"] = current[:start] + security.strip() + current[end:]
    else:
        changes["AGENTS.md"] = current.rstrip() + ("\n\n" if current else "") + security
    if codeowner is not None:
        changes.update(owners_change(root, codeowner, migrate_opencode))
    return changes


def apply(root: Path, changes: dict[str, str | None]) -> None:
    # Validate all destination paths before making any changes.
    for name in changes:
        destination(root, name)
    for name, content in changes.items():
        target = destination(root, name)
        if content is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".muse-install-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(content)
            if target.exists():
                os.chmod(temporary, target.stat().st_mode & 0o777)
            else:
                os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worktree", type=Path)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--with-fixes", action="store_true", help="Include the manual new-PR workflow")
    parser.add_argument("--model", choices=MODELS, help="Muse model; omitted preserves an existing policy model")
    parser.add_argument("--migrate-opencode", action="store_true", help="Plan removal of recognized legacy Muse files")
    owners = parser.add_mutually_exclusive_group(required=True)
    owners.add_argument("--codeowner", help="Owner's @login or @organization/team for the Muse CODEOWNERS block")
    owners.add_argument("--no-codeowner", action="store_true", help="Leave CODEOWNERS unchanged")
    parser.add_argument("--apply", action="store_true", help="Write the listed files; default only prints a plan")
    args = parser.parse_args()
    root = args.worktree.resolve()
    try:
        probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if probe.returncode or Path(probe.stdout.strip()).resolve() != root:
            raise Conflict("worktree must name the Git repository root")
        selected = args.model or policy_model(root, OLD_POLICY) or policy_model(root, NEW_POLICY) or DEFAULT_MODEL
        changes = plan(root, args.organization, args.with_fixes, args.model, args.codeowner, args.migrate_opencode)
        for name, content in changes.items():
            print(("delete " if content is None else "update " if (root / name).exists() else "create ") + name)
        print(f"model: {selected}")
        if args.apply:
            apply(root, changes)
        print(f"{'Applied' if args.apply else 'Planned'} {len(changes)} file changes. No GitHub settings or workflow runs were changed.")
    except (OSError, ValueError) as error:
        print(f"Muse setup stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
