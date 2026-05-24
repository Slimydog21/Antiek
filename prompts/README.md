# prompts/ — agent prompt retention

Every commit message that carries a `Co-Authored-By: Claude` trailer also
carries a `Prompt-Hash: <sha256>` trailer. The matching file lives here at
`prompts/<sha256>.md`. The hash is the sha256 of the agent's prompt with
leading/trailing whitespace stripped — identical prompts dedupe.

The point: Hashimoto's interview lens — *"reading the prompt is actually
if it's a bunch of code generated, the pull request is meaningless"* —
applied to Antiek's git history. The diff tells you WHAT changed; the
prompt tells you WHY. Together they make agent commits as debuggable as
operator commits.

## File shape

Each `prompts/<hash>.md` is YAML front-matter plus the prompt verbatim:

```markdown
---
captured_at: 2026-05-24T18:42:07Z
agent: claude
branch: hashimoto-eng/e6-provenance
commit_template: true
---

<the prompt text the operator gave the agent, normalised>
```

## Append-only

Files in this directory must not be deleted. The CI test
`tests/test_prompts_append_only.py` enforces this on every push by walking
git history for deletions under `prompts/`. If a prompt genuinely needs
to be redacted (secrets pasted in, etc.), do it in a dedicated commit
with operator sign-off in the message; the test will surface the
deletion as a finding rather than silently allowing it.

## Filling the directory

The `.githooks/commit-msg` hook writes the prompt file automatically when
the commit-time environment variable `ANTIEK_AGENT_PROMPT` is set. Agent
harnesses that produce commits export the prompt verbatim before
invoking `git commit`. The hook computes the hash, persists the file
(if not already present), and appends the trailer to the commit message.

For commits authored before SPR-E6 landed, the directory is empty by
design — no backfilling, since the prompts are not reconstructible.

## Reading the prompts back

```
./.venv/bin/python -m tools.agent_commits list --since=7d
./.venv/bin/python -m tools.agent_commits show <git-sha-or-prompt-hash>
```

See `tools/agent_commits/README.md` for the full CLI surface.

## Spec

`~/specs/antiek-hashimoto-engineering/sprint-e6-provenance.html`
