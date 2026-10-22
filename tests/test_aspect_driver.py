"""Exercise deeper-look prompts against real pinned Git objects."""
import json
from pathlib import Path
import subprocess
import sys

import pytest


DRIVER = Path(__file__).resolve().parents[1] / "common/codex/scripts/aspect-driver.py"


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (tmp_path / "code.py").write_text("value = 1\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "code.py").write_text("value = 2\n")
    git("commit", "-qam", "head")
    return tmp_path, base, git("rev-parse", "HEAD")


def run(repo, role="toolkit"):
    directory, base, head = repo
    return subprocess.run([sys.executable, str(DRIVER), "--pass", role,
                           "--base", base, "--head", head],
                          cwd=directory, capture_output=True, text=True)


@pytest.mark.parametrize("role", ["toolkit", "standards", "spec", "performance"])
def test_returns_role_prompt_without_editing_checkout(repo, role):
    result = run(repo, role)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["pass"] == role
    assert (value["base"], value["head"]) == repo[1:]
    assert value["question"] and value["instruction"]
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=repo[0]) == b""


@pytest.mark.parametrize("pin", ["HEAD", "abc", "f" * 40])
def test_rejects_invalid_or_missing_base(repo, pin):
    directory, base, head = repo
    result = run((directory, pin, head))
    assert result.returncode == 1
    assert not result.stdout


def test_rejects_moved_checkout(repo):
    directory, base, head = repo
    assert run((directory, base, base)).returncode == 1


def test_rejects_non_ancestor_base(repo):
    directory, base, head = repo
    other = subprocess.check_output(
        ["git", "commit-tree", f"{base}^{{tree}}", "-p", base, "-m", "alternate"],
        cwd=directory, text=True).strip()
    result = run((directory, other, head))
    assert result.returncode == 1
    assert "base must be the pinned merge-base" in result.stderr
