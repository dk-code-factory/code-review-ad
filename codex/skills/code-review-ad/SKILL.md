---
name: code-review-ad
description: Review a GitHub pull request through independent Toolkit, Standards, and Spec passes, with a conditional Performance pass; report verified issues without editing code or suggesting fixes.
---

Use this Codex session and native subagents when available. Use the loaded skill location to resolve the plugin root; do not depend on the working directory.

Model and reasoning-effort settings belong to the host or runner. Do not set reviewer overrides in this skill.

Before work, read [the lifecycle procedure](../../../common/lifecycle.md), then run its entry command with `--host codex`. Retain its returned token and follow its structured action. Always run its completion command with that token in a finalization step, including on failure or interruption.

Native reviewers first describe code aspects, then run the bundled driver to assess those observations and collect any supported findings. The shared procedure defines the staged handoff.

Read [the shared procedure](../../../common/codex/procedure.md) and perform the requested workflow. Resolve paths beginning with `PLUGIN_ROOT/` against this plugin's root. Preserve the shared procedure's validation and publication guards.
