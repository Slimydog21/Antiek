# workspace/agent — seams other lanes consume (SPR-07)

Written 2026-10-08T01:10Z on `fix/ffx-kpa-spr-07-20261007` (repair of the
MiMo critic's REFUTED report at 900fd429a). CONTRACTS-adjacent: the frozen
contracts live in `../contracts/` and are consumed, never edited, here.

## 1. The project-seed seam (M8 → SPR-03's intake)

`interviewMode.ts` exports the ONE consumer path:

```ts
import { subscribeProjectSeed } from "../workspace/agent/interviewMode";
// in useProjectIntake (SPR-03, #3749):
useEffect(() => subscribeProjectSeed(applySeed), [applySeed]);
```

Contract: every subscribed consumer receives each confirmed seed exactly once,
as its own value copy (`{title, prompt, sources?}`). Seeds confirmed while no
intake is mounted are held in confirmation order (every one the pane said was
held) and handed to the FIRST subscriber, each once; a delivered seed is never
also held. A consumer that throws is a failed delivery: reported with
`console.error`, never propagated, and the other consumers still receive the
seed; a seed NO consumer took (none mounted, or every mounted one threw) stays
held, and a held seed a subscriber throws on stays held for the next one
(second repair, finding 3). `dispatchProjectSeed` returns `{delivered,
failed}`; the pane announces "Project seed handed to the intake" when
`delivered > 0`, "The project intake could not take the seed; it is held for
the next one" when only failures, else "No project intake is open yet; the
seed is held for it". The pane never calls `submitProject` (the intake owns
the paid POST). The earlier window `CustomEvent` transport is gone: one seam,
one consumer path.

## 2. The pane's tab on the frozen vocabulary (M1 / handoff F1)

A companion tab carrying `agentId` IS the agent pane (`companionStore.ts`
descriptor; `companionRegistry.metaFor` resolves it to `AgentPaneSurface`;
its id is `agent:pane:<agentId>`). Its `kind` is `"dialogue"`
(`agentTypes.AGENT_PANE_TAB_KIND`): `AgentTabKind` is consumed by the frozen
`contracts/tree.ts` (`AGENT_RUN_KIND_OF_TAB`, a Record over the closed union),
`contracts/adapters/preBackend.ts` (`runKind: AGENT_RUN_KIND_OF_TAB[t.kind]`)
and `contracts/tree.test.ts` T5 (registry keys == run-kind keys), so kind
`"agent"` cannot exist until the SPR-06 owner lands F1(a)–(d). The hour it
lands: flip `AGENT_PANE_TAB_KIND` to `"agent"`, add `"agent"` to
`AgentTabKind`, move `AGENT_PANE_META` under `AGENT_TAB_KINDS.agent`, and let
`openAgentPane` call `openAgentFromDocument({kind: "agent", …})`. Until F2,
the pre-backend adapter files the pane as session-global (its scope is
enforced in this browser only; the badge says so).

## 3. Status words (M3)

`statusWords.ts` is deterministic by turn index (`STATUS_WORDS[turnIndex %
5]`), nothing random: a test pins the word a turn shows by index. There is no
test flag and none is needed; the sprint page's "deterministic under a test
flag" describes the guarantee, not the mechanism.

## 4. The 8 s no-reply fallback (M8)

`turnLifecycle.ts`: `NO_REPLY_MS = 8000` by wall clock from `send()`. With no
visible token by then the lifecycle is `failed` with `reason: "no_reply"`
(copy: "Your agent couldn't get started" in the interview, "Your agent
couldn't answer" otherwise) and Retry is offered; Retry aborts the in-flight
request before sending once. The in-flight request is NOT aborted at 8 s: a
reply that lands later on the same request heals the fallback (the paid call
is never thrown away), and a reply landing after a Retry is dropped.

## 5. Reproducible test counts

`scripts/spr07_named_gates.sh` runs the named SPR-07 gate set under
`--maxWorkers=1` and prints one line per file with its pass/fail counts, so a
ledger claim such as "N/N" names the exact files it counted.
