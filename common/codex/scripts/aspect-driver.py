#!/usr/bin/env python3
"""Read-only, two-stage source inspection and finding collection for native agents."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ASPECTS = {
    "toolkit": [
        "Describe inputs, outputs, error propagation, and public type/API behavior.",
        "Trace ownership, state transitions, callbacks, waits, retries, and shutdown.",
        "Describe test stimuli, assertions, deadlines, and cleanup paths.",
        "Relate factual comments and documentation to the implementation.",
        "Map changed branches and repeated logic to their callers and tests.",
    ],
    "standards": [
        "Identify documented repository rules and their artifact-specific scope.",
        "Compare changed setup, teardown, helpers, and declarations with nearby conventions.",
        "Describe duplicated sites and state or API obligations that require coordination.",
        "Map commit contents, messages, attribution, and validation claims to the changes.",
    ],
    "spec": [
        "Identify explicit promises in the PR description and supplied specification.",
        "Map those promises to base/head behavior, including completion and failure ordering.",
        "Describe how changed tests stimulate the promised behavior.",
    ],
    "performance": [
        "Describe work, allocation, I/O, and contention in changed hot paths.",
        "Compare base/head costs for concrete inputs and concurrency levels.",
    ],
}
ROOT = Path(__file__).resolve().parents[3]


def git(*args):
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()


def citation(row, head):
    path, line = row.get("path"), row.get("line")
    if (not isinstance(path, str) or not path or "\\" in path
            or PurePosixPath(path).is_absolute() or ".." in path.split("/")):
        raise ValueError("citation needs a repository-relative path")
    if type(line) is not int or line < 1:
        raise ValueError("citation needs a positive integer line")
    if line > len(git("show", f"{head}:{path}").splitlines()):
        raise ValueError("citation line is outside the pinned head file")


def observations(value, head):
    if not isinstance(value, dict) or not isinstance(value.get("summary"), str) or not value["summary"].strip():
        raise ValueError("observations need a nonempty factual summary")
    evidence, gaps = value.get("evidence"), value.get("gaps")
    if not isinstance(evidence, list) or not isinstance(gaps, list) or any(not isinstance(g, str) or not g.strip() for g in gaps):
        raise ValueError("observations need evidence and explicit gap lists")
    if not evidence and not gaps:
        raise ValueError("supply source evidence or disclose the unexamined scope")
    for row in evidence:
        citation(row, head)
        if not isinstance(row.get("observation"), str) or not row["observation"].strip():
            raise ValueError("each source citation needs a factual observation")
    return value


def drive(args):
    if not all(re.fullmatch(r"[a-f0-9]{40}", pin) for pin in (args.base, args.head)):
        raise ValueError("full base/head OIDs are required")
    if git("rev-parse", "HEAD") != args.head:
        raise ValueError("checkout HEAD differs from the pinned head")
    if git("merge-base", args.base, args.head) != args.base:
        raise ValueError("base must be the pinned merge-base")
    common = {"schemaVersion": 1, "pass": args.role, "base": args.base, "head": args.head}
    if args.phase == "inspect":
        return {**common, "phase": "inspect", "aspects": ASPECTS[args.role],
                "instruction": "Look at these aspects across every changed file and relevant metadata. Describe what the code does, with source citations, and record unexamined scope. Then run this driver with --phase assess and --observations JSON containing summary, evidence [{path,line,observation}], and gaps. Stay in this same native agent session."}
    seen = observations(json.loads(args.observations or "null"), args.head)
    digest = hashlib.sha256(json.dumps(seen, sort_keys=True).encode()).hexdigest()
    common.update(observations=seen, observationSha256=digest)
    if args.phase == "assess":
        return {**common, "phase": "assess",
                "question": "Having looked at those aspects, do you see any problems there? No problems is a valid answer. Assess the observed behavior against the applicable contracts and consider contrary evidence; investigate a concern further only as needed to support its actual assertion.",
                "readNow": [str(ROOT / "common" / "reporting.md"),
                            str(ROOT / "common" / "codex" / "passes" / f"{args.role}.md")],
                "checks": args.check,
                "instruction": "Apply the supplied pass brief and applicable check references now. Collect supported findings with --phase collect, the same --observations, and --findings JSON. Each finding needs id, category, claim, path, line, trigger, consequence, baseHead, and contraryEvidence. An empty array is valid. Preserve material coverage gaps; do not create files, run tests/builds, delegate, or publish."}
    findings = json.loads(args.findings or "null")
    if not isinstance(findings, list):
        raise ValueError("findings must be a JSON array; use [] for no findings")
    ids = set()
    for row in findings:
        if not isinstance(row, dict):
            raise ValueError("each finding must be an object")
        for field in ("id", "category", "claim", "trigger", "consequence", "baseHead", "contraryEvidence"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"finding needs nonempty {field}")
        if row["id"] in ids:
            raise ValueError("finding IDs must be unique within a pass")
        ids.add(row["id"])
        citation(row, args.head)
    return {**common, "phase": "collected", "findings": findings,
            "coverageGaps": seen["gaps"],
            "instruction": "Return these findings and coverage gaps to the parent for its existing independent verification. Collection validates structure and citations, not semantic truth."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("inspect", "assess", "collect"), required=True)
    parser.add_argument("--pass", dest="role", choices=ASPECTS, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--observations")
    parser.add_argument("--findings")
    parser.add_argument("--check", action="append", default=[])
    args = parser.parse_args()
    try:
        print(json.dumps(drive(args), ensure_ascii=False))
    except (ValueError, TypeError, AttributeError, subprocess.CalledProcessError) as exc:
        print(f"aspect-driver: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
