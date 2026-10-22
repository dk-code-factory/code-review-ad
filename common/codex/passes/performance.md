# Performance pass

Find concrete performance regressions in the selected hot paths immediately.

Inspect changed code and relevant call sites for PR-introduced runtime, memory, I/O, or contention regressions. Prioritize paths exercised per request, item, or retry; derive the work or allocation from the changed operation and a realistic input or concurrency level. Compare base and head, and report only a concrete, consequential regression at a changed line. Do not run benchmarks or expand into general correctness, style, or spec review. Return `No findings` when no performance-sensitive change warrants a finding.
