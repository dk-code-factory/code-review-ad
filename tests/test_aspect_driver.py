"""Exercise deeper-look prompts against real pinned Git objects."""
from pathlib import Path
import json
import subprocess
import sys

import pytest


DRIVER = Path(__file__).resolve().parents[1] / "common/codex/scripts/aspect-driver.py"


@pytest.fixture
def repo(tmp_path, request):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    object_format = getattr(request, "param", "sha1")
    git("init", "-q", f"--object-format={object_format}")
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


def test_returns_distinct_role_prompts_without_editing_checkout(repo):
    prompts = []
    for role in ("toolkit", "standards", "spec", "performance"):
        result = run(repo, role)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip()
        prompts.append(result.stdout)
    assert len(set(prompts)) == len(prompts)
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=repo[0]) == b""


@pytest.mark.parametrize("repo", ["sha256"], indirect=True)
def test_accepts_sha256_pins_from_inventory(repo):
    directory, base, head = repo
    inventory = subprocess.run(
        ["node", str(DRIVER.with_name("prepare-review.js")), "--base", base,
         "--head", head, "--json"],
        cwd=directory, capture_output=True, text=True, check=True,
    )
    pins = json.loads(inventory.stdout)
    assert len(pins["mergeBase"]) == len(pins["head"]) == 64
    result = run((directory, pins["mergeBase"], pins["head"]))
    assert result.returncode == 0, result.stderr
    assert "Look deeper" in result.stdout


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
