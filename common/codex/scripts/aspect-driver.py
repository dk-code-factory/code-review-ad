#!/usr/bin/env python3
"""Print one role-specific deeper-look prompt for an ongoing native review."""
import argparse
import json
import re
import subprocess
import sys


PROMPTS = {
    "toolkit": "Look deeper for additional bugs and other supported issues beyond your first candidates. Challenge boundary inputs, failure and cleanup paths, ownership, and async ordering; check whether tests can pass while the claimed behavior is broken.",
    "standards": "Look deeper for additional repository-rule violations or evidenced maintenance risks. Check overlooked rule scope and exceptions, duplicated sites, and state or API obligations across callers. Support each concern with the exact applicable rule or demonstrated coordination invariant.",
    "spec": "Look deeper for additional gaps in the explicit promises. Challenge failure, completion, and alternate input paths; check whether tests distinguish the promised behavior. Stay within the stated conditions and do not invent requirements. If no meaningful specification exists, retain No spec available.",
    "performance": "Look deeper for additional performance regressions. Challenge scaling, repeated work, allocation, and contention under concrete input sizes or concurrency. Support the cost difference with source evidence and the repository's performance requirements.",
}


def git(*args):
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()


def drive(args):
    if not all(re.fullmatch(r"[a-f0-9]{40}", pin) for pin in (args.base, args.head)):
        raise ValueError("full base/head OIDs are required")
    if git("rev-parse", "HEAD") != args.head:
        raise ValueError("checkout HEAD differs from the pinned head")
    if git("merge-base", args.base, args.head) != args.base:
        raise ValueError("base must be the pinned merge-base")
    return {"schemaVersion": 1, "pass": args.role, "base": args.base, "head": args.head,
            "question": PROMPTS[args.role],
            "instruction": "Take this deeper look once in the same session, whether or not you found issues initially. Reuse inspected evidence; make only focused reads for new candidates or unresolved gaps. Preserve earlier supported findings and consider contrary evidence. There is no finding quota; no additional issues is valid. Return findings and coverage gaps to the parent after this follow-up."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass", dest="role", choices=PROMPTS, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(drive(args), ensure_ascii=False))
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"aspect-driver: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
