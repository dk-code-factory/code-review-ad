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
