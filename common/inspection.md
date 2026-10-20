# Inspection and coverage

Inspect the changed-file list and relevant PR/commit metadata broadly before deep candidate
verification. Make an initial pass over every changed file, including tests and documentation;
record unexamined files or ranges. Then focus source reads and counterexamples on candidates
and applicable checks. Inventory leads do not replace independent inspection.

Use focused reads with explicit paths or line ranges. Batch independent reads when useful,
but keep briefs/checks separate from diff output; do not combine all instructions and a full
patch into one large response. Split large files and patches into retrievable ranges. Check
both outer tool responses and nested results for display limits, omitted rows, truncation or
execution failures. Retrieve every missing range needed by a check before marking it inspected.
A successful exit code alone does not establish that all output was displayed. A literal use
of the word "truncated" in source is not evidence of tool truncation.

Track changed-file/range coverage and candidate dispositions internally. If omitted content
cannot be retrieved or a check cannot finish, preserve the gap and disclose material limits in
the ordinary report. Neither tool truncation nor a failed command counts as checked coverage.
During a requested diagnostic run, attach candidate IDs, source/tool evidence references,
parent dispositions, final-finding mappings and unresolved coverage to the requested versioned
artifact. Use visible tool results and reviewer outputs; do not disclose private reasoning.
