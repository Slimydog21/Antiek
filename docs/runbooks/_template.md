# Runbook template

**Owner:** _name or alias_
**Last verified:** _YYYY-MM-DD_

## Symptom

> The thing an engineer types into the search bar at 2am. User-language,
> not vendor-jargon. Lead with what the engineer SEES.

## Likely cause

One paragraph. The single most common reason this symptom appears.
If there are two equally likely causes, list both — but resist the
urge to list five; runbooks branch quickly and become useless.

## Quick diagnostics

Commands the engineer runs, in order. Each command should be
copy-pasteable. Include expected output so the engineer knows whether
the diagnostic is informative.

```bash
# Confirm the symptom is real, not a flake.
<command 1>

# Narrow it to subsystem.
<command 2>
```

## Root-cause path

Step-by-step reasoning from symptom to fix. This is the "why" section —
without it, the engineer learns a magic incantation instead of intuition.

1. _Observation A means …_
2. _Therefore B is happening …_
3. _Which means the fix targets C …_

## Mitigation

The exact action to take. Code change, config flip, restart, escalate.
If escalation: name who to ping and what minimal info to bring.

## Reference

- Code path: `path/to/file.py:NNN`
- Decision record: `docs/decisions/<relevant>.md`
- Upstream doc: <URL>
- Past incident: <postmortem path / link>

## Worked example

A paste of a real (or representative) log/error snippet followed by a
step-by-step trace through this runbook. This is the test that the
runbook actually works on a real symptom.

```
<paste of log / stack trace / error message>
```

_Trace: applying this runbook to the paste above…_
