# Declared typing status — honest framing (2026-09-26)

**Status:** settled fact, recorded to stop a recurring misreading
**Author:** caffenagent master (session `ses_-ffe5f234a8f65ffeHyZ21E9k5`)
**Supersedes:** the informal claim "mypy strict clean on 745 backend files"

## Why this document exists

Grading passes have repeatedly described Antiek's typing as "mypy strict clean on
745 backend files." That sentence is a **subset framing**, and it has been read
as a typing verdict. It is not one. Recording the real numbers here so no future
grader has to re-derive them or repeat the imprecise form.

## Measured facts (reproduce from `tools/lints/baselines/declared_mypy.json`)

```sh
python3 -c "
import json, collections
d = json.load(open('tools/lints/baselines/declared_mypy.json'))
v = d['violations']
paths = collections.Counter(x['path'] for x in v)
kinds = collections.Counter(x['kind'] for x in v)
print('total violations:', len(v))
print('files with baselined violations:', len(paths))
print('kinds:', kinds.most_common(8))
print('top files:', paths.most_common(5))
"
```

Output at 2026-09-26:

| Fact | Value |
|---|---|
| Baselined mypy violations | **1684** |
| Files carrying baselined violations | **308** |
| Baseline generated | 2026-06-02 |
| Largest single file | `interfaces/research/api/app.py` — **77** violations |

Violation kinds (top 8):

| Kind | Count |
|---|---:|
| `type-arg` | 504 |
| `no-untyped-def` | 262 |
| `unused-ignore` | 244 |
| `import-not-found` | 126 |
| `no-any-return` | 125 |
| `no-untyped-call` | 112 |
| `arg-type` | 98 |
| `attr-defined` | 92 |

## What "strict" actually means here

`pyproject.toml` sets `strict = true`. That is real and it is the right default.
But the gate that runs in CI is **`mypy --strict` against a violation baseline**,
not `mypy --strict` clean. The baseline is what keeps the check useful without
forcing a 1684-violation burn-down before anything can merge.

So the accurate statements are:

- ✅ "Declared typing is strict (`strict = true` in `pyproject.toml`)."
- ✅ "CI runs `mypy --strict` against a 1684-violation baseline spanning 308 files."
- ✅ "N files in the declared scope carry zero baselined violations." (measure N
  before quoting it — the "745" figure has drifted and was never tied to a
  reproduction command.)
- ❌ "mypy strict clean on 745 backend files." — sounds like a verdict, is a
  subset, and the count is not currently reproducible from a documented command.

## Known exemptions

`substrate/cli/*` is exempt via `ignore_errors = true` in `pyproject.toml`. That
exemption is separate from the baseline and is not counted in the 1684.

## Burn-down order (if anyone asks what to fix first)

1. `no-untyped-def` (262) and `no-any-return` (125) — these are the kinds that
   actually hide runtime type errors. 387 of the 1684.
2. `unused-ignore` (244) — noise in the signal; cheap to clear.
3. `interfaces/research/api/app.py` (77) — the largest single file, and also a
   7,934-line god module. Splitting it reduces both violations and reader load.

`type-arg` (504) is the largest bucket but the least dangerous; it is mostly
`dict` / `list` without parameters. Do not start there.

## Effect on grading

A Code score that quotes "745 mypy-clean" as evidence of typing quality is
**unsound** and should be re-derived from the numbers in this document. The
independent re-grade of 2026-09-26 priced this correctly (Code 87, not 96).
