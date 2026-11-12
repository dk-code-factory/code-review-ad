"""A $code-review-ad mention asks Claude to invoke the skill; other prompts pass through."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'claude/hooks/skill_mention.py'


def run(stdin):
    result = subprocess.run([sys.executable, str(HOOK)], input=stdin, text=True, capture_output=True, check=True)
    return result.stdout


@pytest.mark.parametrize('prompt', [
    'review pr 9 with $code-review-ad',
    '$code-review-ad 1234',
    'use $code-review-ad:code-review-ad on https://github.com/o/r/pull/1',
    'review ($code-review-ad).',
])
def test_mention_requests_skill_invocation(prompt):
    output = json.loads(run(json.dumps({'prompt': prompt})))['hookSpecificOutput']
    assert output['hookEventName'] == 'UserPromptSubmit'
    assert 'code-review-ad:code-review-ad' in output['additionalContext']
    assert 'Skill tool' in output['additionalContext']


@pytest.mark.parametrize('prompt', [
    'review pr 9 with code-review-ad',
    '/code-review-ad:code-review-ad 9',
    'use $code-review-ad-v2',
    'use $code-review-adx',
    'use $code-review-ad:other',
    'cost is a$code-review-ad',
])
def test_other_prompts_add_nothing(prompt):
    assert run(json.dumps({'prompt': prompt})) == ''


@pytest.mark.parametrize('stdin', ['', 'not json', '[]', '{"prompt": 3}'])
def test_malformed_input_is_ignored(stdin):
    assert run(stdin) == ''


def test_manifest_registers_hook():
    manifest = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())
    hooks = json.loads((ROOT / manifest['hooks']).read_text())['hooks']['UserPromptSubmit']
    assert hooks[0]['hooks'][0]['command'] == 'python3 "${CLAUDE_PLUGIN_ROOT}/claude/hooks/skill_mention.py"'
