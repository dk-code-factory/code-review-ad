"""Frozen Git inventory uses Git objects and preserves the reviewed checkout."""
import json
from pathlib import Path
import subprocess
import pytest
HELPER=Path(__file__).resolve().parents[1]/'common/codex/scripts/prepare-review.js'


def test_inventory_pins_objects_and_leaves_local_changes_alone(tmp_path):
    def git(*args):return subprocess.check_output(['git',*args],cwd=tmp_path,text=True).strip()
    git('init','-q');git('config','user.name','Test');git('config','user.email','test@example.test')
    (tmp_path/'x.py').write_text('def value():\n    return 1\n')
    git('add','.');git('commit','-qm','Initial');base=git('rev-parse','HEAD')
    (tmp_path/'x.py').write_text('# Return the retained value\ndef value():\n    return 2\n')
    git('add','.');git('commit','-qm','Change value');head=git('rev-parse','HEAD')
    (tmp_path/'x.py').write_text('local work\n')
    before=git('status','--porcelain')
    result=subprocess.run(['node',str(HELPER),'--repo',str(tmp_path),'--base',base,'--head',head,'--json'],text=True,capture_output=True,check=True)
    data=json.loads(result.stdout)
    assert data['base']==base and data['head']==head and data['mergeBase']==base
    assert data['files'][0]['path']=='x.py'
    assert any('Return the retained value' in c['text'] for c in data['comments'])
    assert git('status','--porcelain')==before and (tmp_path/'x.py').read_text()=='local work\n'
    failed=subprocess.run(['node',str(HELPER),'--repo',str(tmp_path),'--base','HEAD~1','--head',head],text=True,capture_output=True)
    assert failed.returncode and 'full commit' in failed.stderr


@pytest.mark.parametrize("initial_submodule", [False, True])
@pytest.mark.parametrize("ignore_submodules", [False, True])
def test_inventory_keeps_submodules_with_unavailable_commit_objects(tmp_path, initial_submodule, ignore_submodules):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, text=True).strip()

    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.test')
    (tmp_path / 'source.py').write_text('value = 1\n')
    git('add', '.')
    if initial_submodule:
        git('update-index', '--add', '--cacheinfo', '160000', '1' * 40, 'dependency')
    git('commit', '-qm', 'Initial')
    base = git('rev-parse', 'HEAD')
    git('update-index', '--add', '--cacheinfo', '160000', '2' * 40, 'dependency')
    git('commit', '-qm', 'Update dependency')
    head = git('rev-parse', 'HEAD')
    if ignore_submodules:
        git('config', 'diff.ignoreSubmodules', 'all')

    result = subprocess.run(
        ['node', str(HELPER), '--repo', str(tmp_path), '--base', base, '--head', head, '--json'],
        text=True, capture_output=True, check=True,
    )
    data = json.loads(result.stdout)
    assert data['files'] == [{'status': 'M' if initial_submodule else 'A', 'path': 'dependency'}]
    assert data['commits'][0]['files'] == ['dependency']
    assert data['comments'] == []
    assert data['nearby'] == []
    assert data['risks'] == []


def test_inventory_from_subdirectory_uses_repository_relative_paths(tmp_path):
    # Preserve trailing whitespace in the root returned by Git as well.
    repo = tmp_path / 'repository \n'
    subdir = repo / 'nested'
    subdir.mkdir(parents=True)

    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()

    git('init', '-q')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.test')
    for source in [repo / 'outside.py', subdir / 'inside.py']:
        source.write_text('value = 1\n')
    git('add', '.')
    git('commit', '-qm', 'Initial')
    base = git('rev-parse', 'HEAD')
    for source in [repo / 'outside.py', subdir / 'inside.py']:
        source.write_text('# Retain the value\nsleep(1)\n')
    git('add', '.')
    git('commit', '-qm', 'Change both files')
    head = git('rev-parse', 'HEAD')
    git('config', 'diff.relative', 'true')

    def inventory(directory):
        result = subprocess.run(
            ['node', str(HELPER), '--repo', str(directory), '--base', base, '--head', head, '--json'],
            text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    data = inventory(subdir)
    assert data == inventory(repo)
    assert {row['path'] for row in data['comments']} == {'outside.py', 'nested/inside.py'}
    assert {row['path'] for row in data['risks']} == {'outside.py', 'nested/inside.py'}
