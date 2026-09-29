# Reviewer child brief: template and contract

Copy into `rlm.spawn(...)`. Self-contained on purpose: a child shares none of the parent's
context, and children cannot spawn further children (depth is 1).

```
You are reviewing a change against a supplied rubric. You did not write this code and you are
not asked whether it is good - you are asked which rubric rules it breaks.

FILES YOU NEED (read them; they are on disk because they are too big for a message)
- preview JSON:  <abs path>/preview.json
- rule JSON:     <abs path>/rules.json

STEP 1 - build your checklist. From preview.json, list every reviewable_files entry as
"(path, status)". The same path can appear twice with different statuses; they are separate
items. This list is your coverage contract.

STEP 2 - read the rubric from rules.json for the group that covers your files. Note its
blocking/non-blocking split and its "do not report" lines; the carve-outs are part of the
rubric, not suggestions.

STEP 3 - get each diff yourself; do not trust a summary:
  workspace tracked:    git diff HEAD -- <path>
  workspace untracked:  read the whole file
  range:                git diff <merge_base>..<to> -- <path>
  commit:               git show <commit> -- <path>

STEP 4 - answer in exactly this form:

  RULE GROUP APPLIED: <group_id, source, pattern>

  COVERAGE
  reviewed: <n>   skipped: <n>   total: <n>   coverage_rate: <n/n>
  - <path> (<status>) - reviewed | skipped: <concrete reason>

  BLOCKING
  - <path>:<line> - <rule broken> - <what is wrong> - <why it is wrong>

  NON-BLOCKING
  - <path>:<line> - <rule section> - <what to improve>

  NOT REPORTED, DELIBERATELY
  - <carve-out you applied> - <the code you checked it against>

  VERDICT: <BLOCKING FINDINGS: n | CLEAN>

RULES FOR YOU
- Precision over recall: stay silent unless you are sure. A false alarm costs more reviewer
  trust than a missed minor issue. Discard likely false positives silently.
- Every finding needs a path and line you actually read in a diff.
- If the rubric does not cover something you saw, put it under NON-BLOCKING and say the rubric
  did not cover it. Never promote it to BLOCKING.
- Do not stop at the first high-severity issue. Finish the checklist.
- Report only. Fix nothing. Do not edit the repository.

OUT:   <absolute path for your report>
ACCEPT: the file exists and contains both the "RULE GROUP APPLIED:" and "coverage_rate:" lines
RETURN: reply "done: <OUT>" plus the VERDICT and coverage_rate lines only.
```

## Comment schema, when the review must be machine-readable

Upstream's contract for a review comment (use these field names if a downstream consumer reads
the output): `path` (required), `content` (required), `start_line`, `end_line`,
`category` in {bug, security, performance, maintainability, test, style, documentation, other},
`severity` in {critical, high, medium, low}. Map the rubric's blocking/non-blocking split into
those severities explicitly rather than inventing a scale.

## Why each constraint exists

- **Rubric verbatim** - paraphrasing drops the carve-outs, and the carve-outs are what separate
  a review from a list of style opinions.
- **Checklist identity `(path, status)`** - workspace mode can report one path twice; a
  path-only checklist silently loses an item.
- **COVERAGE block** - delegation disables OCR's diff-size ceiling, so the child is the only
  thing standing between a large PR and a partial review. Numbers make the gap visible.
- **RULE GROUP APPLIED** - a cheap mechanical check that the child read the rubric at all.
- **NOT REPORTED, DELIBERATELY** - turns silence into evidence; without it you cannot tell a
  disciplined reviewer from a lazy one.
- **No fixes** - a reviewer that edits is no longer a reviewer, and the parent loses the
  ability to gate on the finding.
