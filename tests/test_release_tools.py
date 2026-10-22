"""Validate release identities before CI and publication consume them."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def release_tree(tmp_path):
    def write(path, value):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))

    for host in ("codex", "claude"):
        write(f".{host}-plugin/plugin.json", {
            "name": "example", "version": "1.2.3", "skills": f"./{host}/skills/",
        })
        skill = tmp_path / host / "skills/example/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("name: example\ndescription: lifecycle test\n")
    for path in (".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json"):
        write(path, {"name": "example", "plugins": [{"name": "example", "version": "1.2.3"}]})
    (tmp_path / "scripts").mkdir()
    for name in ("check.py", "version.py"):
        shutil.copyfile(ROOT / "scripts" / name, tmp_path / "scripts" / name)
    return tmp_path


def run(tree, script, *args):
    return subprocess.run([sys.executable, str(tree / "scripts" / script), *args],
                          capture_output=True, text=True)


def test_checker_rejects_stale_marketplace_version(release_tree):
    assert run(release_tree, "check.py").returncode == 0
    catalog_path = release_tree / ".claude-plugin/marketplace.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["plugins"][0]["version"] = "1.2.2"
    catalog_path.write_text(json.dumps(catalog))
    result = run(release_tree, "check.py")
    assert result.returncode == 1
    assert "marketplace version must match" in result.stderr


@pytest.mark.parametrize("version", ["01.2.3", "1.02.3", "1.2.03"])
def test_release_tools_reject_leading_zeroes(release_tree, version):
    before = {path: path.read_bytes() for path in release_tree.rglob("*.json")}
    result = run(release_tree, "version.py", version)
    assert result.returncode != 0
    assert {path: path.read_bytes() for path in before} == before
    for path in before:
        value = json.loads(path.read_text())
        if "version" in value:
            value["version"] = version
        else:
            value["plugins"][0]["version"] = version
        path.write_text(json.dumps(value))
    result = run(release_tree, "check.py")
    assert result.returncode == 1
    assert "Stable semantic version required" in result.stderr


@pytest.mark.parametrize("version", ["0.0.0", "1.10.0", "20.0.31"])
def test_version_command_updates_all_release_versions(release_tree, version):
    result = run(release_tree, "version.py", version)
    assert result.returncode == 0, result.stderr
    result = run(release_tree, "check.py")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["version"] == version
