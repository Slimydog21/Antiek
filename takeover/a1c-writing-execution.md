# A1c Writing execution

Date: 2026-09-27. Base: `68ddf0b9db4579eca8851d1efbd0c895f12a5d36`. Worktree: `/Users/slimydog/Antiek/worktrees/cockpit-a1c-takeover-20260927`. Branch: `fix/cockpit-a1c-takeover-20260927`.

## Scope

Owned `modes/Write/Outline.tsx` and its tests for critic M5 and M6. Root subsequently extended ownership to `modes/Write/Editor/InlineComplete.ts` and its tests after a related late-completion race was found. Other agents own workspace, pane and Escape changes. No backend, shared editor host, model-provider wiring, push or merge changes.

Sources: the final A1c brief in `~/.claude/projects/-Users-slimydog/236c36bd-045d-4b26-8fab-350d18d9d3ca/workflows/wf_8592428a-237.json` and `~/.claude/jobs/236c36bd/tmp/a1b/a1c/critic3.json`, findings M5/M6.

## Changes

- A section editor becomes read-only immediately when generation starts, with a visible explanation. It becomes editable after generation settles. A synchronous guard prevents duplicate generation. Applying a previously requested FloatMenu edit while generating is refused with an explanation.
- Section prose saves use a serial promise queue. While one request is in flight, later queued edits coalesce to the latest text. Each request uses the last confirmed prose as its baseline. An older response cannot mark a newer pending edit saved or replace that edit's local prose.
- Generation flushes pending text and waits for any save already in flight, including saves whose debounce has fired. Failed persistence stops generation and retains the editable draft. Existing no-prose generation remains supported.
- Leaving the piece before the 800ms debounce expires flushes the latest edit through the same queue. The queue continues after the component unmounts.
- Inline completion checks that its editor is live and editable before requesting and before applying a result. It also checks the immutable document and selection still match the request. Responses for changed documents or cursor positions are discarded. Old editors remain locked until React commits a generated replacement, closing the same-microtask completion race.

## Verification

Red first, before implementation:

- New Outline behavior tests: **6 failed, 1 passed**, 20 existing tests excluded. Failures reproduced editing during generation, concurrent saves, overlapping unmount flush, generation preceding an in-flight save, and generation proceeding after a save error. The existing unmount flush already passed; its explicit regression test was retained without claiming a new fix to that behavior alone. Log: `/tmp/a1c-writing-red.log`.
- Real TipTap inline-completion tests against the old implementation: **6 failed, 9 passed**. Failures reproduced requests from unavailable editors and stale insertion after readonly, edits, cursor movement or document replacement. The destroyed-editor test was later adjusted to observe command access rather than call getText after destruction, because TipTap releases its schema. Log: `/tmp/a1c-inline-red.log`.

Final focused command from the worktree root:

```sh
NODE_OPTIONS='--no-experimental-webstorage --no-network-family-autoselection' \
  npm --prefix apps/reading run test -- --no-color \
  src/modes/Write/Outline.test.tsx \
  src/modes/Write/Outline.applyEdit.test.tsx \
  src/workspace/cockpitSweepV2.write.test.tsx \
  src/modes/Write/Editor/InlineComplete.test.ts --maxWorkers=2
```

**4 files, 49 tests passed.** Includes the final integration test resolving generation and an older inline completion together, then advancing the debounce to prove no stale PATCH follows. It exercises the real TipTap editor while mocking only API calls. Log: `/tmp/a1c-writing-focused.log`.

`npx tsc -b` passed after the final test addition. Log: `/tmp/a1c-writing-tsc.log`. `git diff --check` passed on the owned files.

React Doctor was run twice with `npx react-doctor@latest --verbose --scope changed`. It compares the whole rescue branch to origin/main, not just this patch. Score stayed **62/100**; reported issues fell from 64 to 63 after fixing an introduced Promise ref-initializer warning. Remaining Outline reports concern the existing large component, prop-sync effect and render-time persistRef/handleGenerateRef assignments, already present at base. No new InlineComplete diagnostic was reported. Exit 1 reflects existing diagnostics; no clean-doctor claim is made. Logs: `/tmp/a1c-writing-react-doctor.log`, `/tmp/a1c-writing-react-doctor-final.log`.

## Limits

- This is focused local behavior/type proof, not the full A1c suite, rendered matrix, exact-head independent review, main landing or production acceptance. Root coordinates those after all owned changes are integrated.
- Save ordering covers a mounted section and its pending unmount flush. It does not add backend compare-and-set for competing browser sessions or guarantee request delivery if the browser process exits.
- Empty edits retain the existing API non-empty policy; this patch does not introduce deletion of all section prose.
- The existing save-error UI still exposes its historical error text. Its redesign belongs to the already-recorded honest-failures pass, not M5/M6.
- Other A1c findings, per-mode agent tabs, and the backend document-id dependency remain outside this change.
