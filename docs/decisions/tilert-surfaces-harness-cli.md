# TileRT on harness, CLIs, and Speak (ATSB SPR-06)

**Status:** Substrate + docs (2026-06-23)  
**Depends on:** SPR-01 live Modal URL (OA-022) for end-to-end Codex validation

## Principle

TileRT stays **server-side** only. Harnesses and CLIs talk **OpenAI-compat HTTP**;
Antiek `dispatch()` owns production routing. Personal Codex wiring validates TPOT;
it does not prove DRW synthesis quality (see SPR-07).

## Codex / mimo2codex (milestone 1)

After OA-022 smoke:

```text
ANTIEK_TILERT_BASE_URL=https://<modal-web-host>
ANTIEK_TILERT_API_KEY=<ANTIEK_TILERT_MODAL_TOKEN>
```

Point **mimo2codex** generic upstream or `~/.codex` provider at
`$ANTIEK_TILERT_BASE_URL/v1` with Bearer auth, model id **`glm5`**.
Record one completion metadata line in operator notes when validating.

Reference: `infrastructure/modal/tilert_glm5/README.md` §5.

## RLM (milestone 2)

**Root** REPL iterations: `interactive` + driving roles → tier **`speed`** when
`brain=glm`. **Sub-LLM** chunk calls: stay **`flash`** — never bulk-route to
8×B200. See `docs/decisions/tilert-antiek-placement.md` §3.1.

## Caffenagent / Grok Build (milestone 3)

Primary coder path benefits from low TPOT when the operator opts in:

- Set gateway `ANTIEK_TILERT_*` on the machine running Antiek-backed tools.
- Cycle orchestrator does **not** embed TileRT; exec agents inherit env from the
  host running `dispatch()` or from Codex profile above.
- **Not** a substitute for SPR-01 prod gate on the Hetzner VM.

## Speak (milestone 4)

- **ASR / TTS:** MiMo ASR Modal, `transcription` / `tts` tiers — **not** TileRT `glm5`.
- **Interviewer LLM between utterances:** candidate for **`speed`** when
  `interfaces/research/api` read_voice / async interview paths use
  `dispatch_routing_kwargs(..., presence="engaged")` — measure round-trip SLA
  before promoting default.

## Conclave (explicit exclusion)

Parallel jurors need **throughput APIs**. One TileRT node is **serial**; conclave
stays on API providers. Optional single “speed juror” is experiment-only.