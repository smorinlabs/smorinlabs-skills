"""Review-only checkout alias support; unsafe targets fail before model use."""
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

HELPER = Path(__file__).resolve().parents[1] / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
spec = importlib.util.spec_from_file_location("muse_symlink_runtime", HELPER)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    git(root, "init", "-q")
    (root / "normal.txt").write_text("ordinary source\n")
    return root


def stage(root):
    git(root, "add", ".")


@pytest.mark.parametrize("mode", ["review", "followup"])
def test_existing_skill_directory_alias_and_file_chain_are_supported(checkout, mode):
    target = checkout / ".claude/skills/new-python-project"
    target.mkdir(parents=True)
    (target / "README.md").write_text("Project skill instructions are data in CI.\n")
    alias = checkout / ".agents/skills/new-python-project"
    alias.parent.mkdir(parents=True)
    alias.symlink_to("../../.claude/skills/new-python-project", target_is_directory=True)
    (checkout / "file-chain").symlink_to("normal-alias")
    (checkout / "normal-alias").symlink_to("normal.txt")
    stage(checkout)
    ci.validate_tree(checkout, mode)
    assert alias.is_symlink() and alias.resolve() == target


def test_fix_refuses_even_benign_alias(checkout):
    (checkout / "alias").symlink_to("normal.txt")
    stage(checkout)
    with pytest.raises(ci.Refusal, match="fixes.*symlinks"):
        ci.validate_tree(checkout, "fix")


@pytest.mark.parametrize("target", ["../outside.txt", ".git/config", "missing.txt"])
def test_escape_git_and_dangling_targets_refuse(checkout, target):
    (checkout.parent / "outside.txt").write_text("fake credential\n")
    (checkout / "alias").symlink_to(target)
    stage(checkout)
    with pytest.raises(ci.Refusal):
        ci.validate_tree(checkout, "review")


def test_escape_then_return_is_not_allowed(checkout):
    outside = checkout.parent / "outside"
    outside.mkdir()
    (outside / "back").symlink_to(checkout / "normal.txt")
    (checkout / "alias").symlink_to(outside / "back")
    stage(checkout)
    with pytest.raises(ci.Refusal, match="escapes"):
        ci.validate_tree(checkout, "review")


@pytest.mark.parametrize("shape", ["chain_cycle", "directory_cycle"])
def test_cycles_refuse(checkout, shape):
    if shape == "chain_cycle":
        (checkout / "a").symlink_to("b")
        (checkout / "b").symlink_to("a")
    else:
        (checkout / "data").mkdir()
        (checkout / "data/back").symlink_to(".")
        (checkout / "alias").symlink_to("data")
    stage(checkout)
    with pytest.raises(ci.Refusal, match="cycle"):
        ci.validate_tree(checkout, "review")


@pytest.mark.parametrize("credential", [".aws/config", ".ssh/config", ".config/gh/hosts.yml", "nested/key.PeM"])
def test_directory_alias_cannot_expose_credential_tree(checkout, credential):
    target = checkout / "data"
    secret = target / credential
    secret.parent.mkdir(parents=True)
    secret.write_text("fake sensitive content\n")
    (checkout / "alias").symlink_to("data")
    # Keep target untracked to prove directory inspection covers more than the index.
    git(checkout, "add", "alias", "normal.txt")
    with pytest.raises(ci.Refusal, match="credential"):
        ci.validate_tree(checkout, "review")


def test_nested_directory_alias_escape_refuses(checkout):
    (checkout / "data").mkdir()
    (checkout / "data/back").symlink_to(checkout.parent)
    (checkout / "alias").symlink_to("data")
    stage(checkout)
    with pytest.raises(ci.Refusal, match="escapes"):
        ci.validate_tree(checkout, "followup")


def test_untracked_alias_uses_same_bounds(checkout):
    stage(checkout)
    alias = checkout / "alias"
    alias.symlink_to("normal.txt")
    ci.validate_tree(checkout, "review")
    alias.unlink()
    alias.symlink_to(".git/config")
    with pytest.raises(ci.Refusal, match="credential"):
        ci.validate_tree(checkout, "review")


def test_directory_inspection_has_a_shared_path_budget(checkout, monkeypatch):
    target = checkout / "data"
    target.mkdir()
    for index in range(5):
        (target / f"file{index}.txt").write_text("data\n")
    (checkout / "alias").symlink_to("data")
    stage(checkout)
    monkeypatch.setattr(ci, "MAX_SYMLINK_NODES", 3)
    with pytest.raises(ci.Refusal, match="path limit"):
        ci.validate_tree(checkout, "review")


def test_excessive_chain_refuses(checkout, monkeypatch):
    for index in range(5):
        (checkout / f"alias{index}").symlink_to(f"alias{index + 1}" if index < 4 else "normal.txt")
    stage(checkout)
    monkeypatch.setattr(ci, "MAX_SYMLINK_HOPS", 3)
    with pytest.raises(ci.Refusal, match="excessive"):
        ci.validate_tree(checkout, "review")


def test_nonregular_target_refuses_without_opening_it(checkout):
    os.mkfifo(checkout / "pipe")
    (checkout / "alias").symlink_to("pipe")
    git(checkout, "add", "alias", "normal.txt")
    with pytest.raises(ci.Refusal, match="not a regular"):
        ci.validate_tree(checkout, "review")


def test_excessively_deep_target_tree_refuses(checkout):
    target = checkout / "data"
    target.mkdir()
    current = target
    for _ in range(65):
        current = current / "nested"
        current.mkdir()
    (checkout / "alias").symlink_to("data")
    git(checkout, "add", "alias", "normal.txt")
    with pytest.raises(ci.Refusal, match="depth limit"):
        ci.validate_tree(checkout, "review")


@pytest.mark.parametrize("mode", ["review", "followup", "fix"])
def test_submodule_remains_unsupported(checkout, mode):
    git(checkout, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "add", ".")
    git(checkout, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "base")
    head = git(checkout, "rev-parse", "HEAD")
    git(checkout, "update-index", "--add", "--cacheinfo", f"160000,{head},nested")
    with pytest.raises(ci.Refusal, match="submodules"):
        ci.validate_tree(checkout, mode)
