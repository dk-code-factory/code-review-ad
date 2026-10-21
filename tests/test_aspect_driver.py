"""Exercise staged collection against real pinned Git objects without source edits."""
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


def run(repo, phase, **inputs):
    directory, base, head = repo
    args = [sys.executable, str(DRIVER), "--phase", phase, "--pass", "toolkit",
            "--base", base, "--head", head]
    for key, value in inputs.items():
        args.extend(["--" + key, json.dumps(value)])
    return subprocess.run(args, cwd=directory, capture_output=True, text=True)


def seen(**updates):
    return {"summary": "The assigned value changes.", "evidence": [
        {"path": "code.py", "line": 1, "observation": "Value is now two."}],
        "gaps": [], **updates}


def finding(**updates):
    return {"id": "t1", "category": "runtime", "claim": "Example claim",
            "path": "code.py", "line": 1, "trigger": "Example input",
            "consequence": "Example consequence", "baseHead": "One becomes two",
            "contraryEvidence": "No alternate assignment", **updates}


def test_stages_collect_without_editing_checkout(repo):
    assert run(repo, "inspect").returncode == 0
    assessment = run(repo, "assess", observations=seen())
    assert assessment.returncode == 0, assessment.stderr
    assessed = json.loads(assessment.stdout)
    assert assessed["observations"] == seen()
    collected = run(repo, "collect", observations=seen(), findings=[finding()])
    assert collected.returncode == 0, collected.stderr
    value = json.loads(collected.stdout)
    assert value["findings"] == [finding()]
    assert value["observationSha256"] == assessed["observationSha256"]
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=repo[0]) == b""


def test_no_findings_preserves_unexamined_scope(repo):
    result = run(repo, "collect", observations=seen(gaps=["Shutdown not inspected"]), findings=[])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["coverageGaps"] == ["Shutdown not inspected"]


@pytest.mark.parametrize("update", [{"path": "../code.py"}, {"path": "missing.py"},
                                   {"line": 200}, {"line": True}, {"claim": ""}])
def test_rejects_invalid_claims_and_citations(repo, update):
    assert run(repo, "collect", observations=seen(), findings=[finding(**update)]).returncode == 1


def test_does_not_assess_without_observations(repo):
    assert run(repo, "assess").returncode == 1
    assert run(repo, "assess", observations=seen(evidence=[])).returncode == 1


def test_rejects_duplicate_ids_and_moved_checkout(repo):
    assert run(repo, "collect", observations=seen(), findings=[finding(), finding()]).returncode == 1
    directory, base, head = repo
    assert run((directory, base, base), "inspect").returncode == 1
