#!/usr/bin/env python3
"""Ask Claude to invoke the review skill when a prompt mentions $code-review-ad."""
import json
import re
import sys

SKILL = 'code-review-ad:code-review-ad'
MENTION = re.compile(r'(?<![\w$])\$code-review-ad(?::code-review-ad)?(?![\w:-])')


def context(prompt):
    if not isinstance(prompt, str) or not MENTION.search(prompt):
        return None
    return (f'The user referenced the {SKILL} skill with a $code-review-ad mention. '
            f'Invoke {SKILL} with the Skill tool before doing anything else, '
            'passing the review target from the prompt as its arguments.')


def main():
    try:
        prompt = json.load(sys.stdin).get('prompt')
    except (ValueError, AttributeError):
        return 0
    text = context(prompt)
    if text:
        json.dump({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': text}}, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())
