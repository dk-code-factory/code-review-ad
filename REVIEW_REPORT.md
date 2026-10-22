# Ten-pass correctness review

Ten sequential review-and-fix iterations, each performed by a separate agent
(`review_01` through `review_10`). Later passes worked against the accumulated
fixes, and the final pass reviewed the combined diff. Findings were fixed only
when supported by a concrete failure or contract mismatch.

| Pass | Area reviewed | Result |
| --- | --- | --- |
| 1 | Frozen Git inventory | Fixed added and modified submodules crashing source extraction when gitlink commits are unavailable locally. |
| 2 | Deeper-look driver | Accepted full SHA-256 commit IDs already supported by the inventory helper. |
| 3 | Updater installation identity | Prevented local checkouts from borrowing another Codex installation's identity, and excluded local marketplaces from automatic updates. |
| 4 | Pending update lifecycle | Rechecked full installation identity at completion and preserved requests for distinct installations, including legacy state records. |
| 5 | Release validation | Rejected stale Claude marketplace versions and invalid stable versions with leading zeroes. |
| 6 | Updater failure paths | Preserved lifecycle tracking across host/configuration/version errors, allowed completion with invalid settings, and refreshed invalid or future-dated release caches. |
| 7 | Inventory configuration and paths | Included gitlinks despite submodule-ignore settings and retained full source evidence when invoked from repository subdirectories. |
| 8 | Scoped updates and locking | Ran and verified Claude project/local updates in their registered project; retried Windows lock contention beyond the native API's short retry window. |
| 9 | Codex update verification | Required installed status and the original scope before reporting success, and ignored uninstalled duplicate rows. |
| 10 | Combined diff and runtime contracts | Aligned updater stable-version validation with release tools; invalid leading-zero and Unicode-digit tags cannot schedule installations. |

The submodule regressions and SHA-256 integration regression were observed failing
before their fixes. Other focused regressions cover identity changes, distinct
installations, configuration and host failures, cache corruption, project scope,
Git settings, and invalid release identities.

Final validation:

- `python3 scripts/check.py`: valid, synchronized version 1.0.7.
- `python3 scripts/test.py`: 77 passed (baseline: 23 passed).
- `git diff --check`: passed.

Runtime Python remains standard-library-only. Windows lock contention was tested
with a simulated `msvcrt` adapter on Linux; native Windows execution remains
unverified. Host commands and GitHub release responses use controlled fixtures;
no live plugin installation was performed.
