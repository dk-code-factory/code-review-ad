# Shared reporting criteria

Both hosts and every native reviewer apply these criteria during discovery and parent
reconciliation. Retain each host's own passes and verification methods.

Use simple, direct and concise language, no filler words.

| Category | Required evidence |
| --- | --- |
| Runtime/security bug | Changed execution path, concrete trigger and consequence, compared with base. |
| Test/build defect | Specific wrong behavior accepted by a claimed regression check, missing claimed stimulus, broken supported build, or assertion/failure/cleanup hazard. A passing happy path does not establish failure safety. |
| Diagnostic regression | Before/after visibility or error meaning under the same relevant configuration, including how callers otherwise learn of failure. |
| Factual documentation error | Source-backed contradiction of the exact assertion in its surrounding context, preserving subject, quantifier and conditions. A runtime failure is unnecessary. |
| Repository-rule violation | Exact applicable rule, its scope, violated predicate and any applicable exception. |
| Evidenced maintenance risk | Specific duplicated sites, coupled state, API obligations or a supported failure mode, with the demonstrated coordination invariant or maintenance consequence. Currently safe code can meet this threshold. |
| Unmet explicit acceptance criterion | Explicit promised condition and evidence of its violation within that condition. Distinguish unchanged pre-existing behavior from a newly introduced regression. |

Exclude matters of taste, alternative implementations and generic warnings about future edits.
A maintenance claim must identify the sites or paths that must remain coordinated and why;
do not overstate it as an existing runtime bug. Preserve every supported finding, including
low/nit severity. There is no finding quota. Keep distinct mechanisms and obligations separate;
merge equivalent assertions across passes. Truth and scope are separate: label directly related
pre-existing issues explicitly; unresolved applicability remains unresolved.

Keep an internal candidate ledger with stable reviewer-local IDs and evidence references.
Give every candidate one disposition: report with final finding reference, merge with the
equivalent finding, reject with evidence addressing the actual assertion, or unresolved with
the missing evidence. Preserve compound candidates as separate assertions when warranted.
Never silently discard a candidate or turn an unresolved check into a no-finding conclusion.
Ordinary reports retain the host's existing sections, concise findings and material coverage
limitations. Detailed ledgers and diagnostic artifacts are returned only when requested.
