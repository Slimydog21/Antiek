# Prime Agent dispatch bills the call ceiling, never a definite zero

**Date:** 2026-09-24
**Status:** DECIDED — the conservative state is already produced by the wave-4 C06 router rule; this record names it, adds the explicit provider flag, and states the reconsider-if
**Owner:** Antiek — merge train (Antiek Nudge), follow-up to audit wave 4 finding C06
**Surfaces:**
`substrate/dispatch/providers/prime_agent.py` (`RawProviderResponse.raw_usage={}`; `normalize_usage` — no token counts);
`substrate/dispatch/router.py` (the C06 rule: a paid 200 with no usage or `reported=False` bills the ceiling — one input token per prompt byte plus the effective output budget at the base tier price, cache writes at 1.25× only where the adapter bills them);
`substrate/dispatch/base.py` (`NormalizedUsage.reported`, `cache_unknown`, `optional_count`);
`runtime/prime_agent/process.py` (the subprocess receipt: state, detail, duration_ms, stdout/stderr — no usage field).
**Builds on:** audit wave 4 C06 (PR #3415, "unreported usage is billed at ceiling"); SPR-01 Prime Agent connect (PR #3399); the owner-BYOT reserve-before-spend ledger (PR #720), whose reservation bound is the same ceiling.
**Closes:** `audit-wave4-open-calls.md` §4 ("What a Prime Agent dispatch costs on the books"), whose resolved direction of 2026-09-23 this record makes the declared adapter contract.

## What is true today

The Prime Agent binary reports no token counts. Its dispatch adapter
returns an empty `raw_usage` and its `normalize_usage` returns zeros; the
process receipt carries state, detail, duration and captured output only.
So a Prime Agent call reaches the router with nothing to meter.

Two accounting options were considered and both are wrong:

- **A 0-priced tier** would be a false statement of cost. Prime Agent runs
  on metered provider keys (DeepSeek, Kimi) that the operator pays for;
  the tokens exist, only the count is missing.
- **Real counts** are impossible today: no channel from the binary to the
  receipt carries them, and inventing them from prompt length would be a
  fabricated measurement presented as a reading.

## Decision

Every Prime Agent dispatch is billed at the **call ceiling**: one input
token per prompt byte plus the effective `max_tokens` output budget, priced
at the base tier for the routed model. This is the bound the owner-BYOT
ledger reserves before any spend, so the ledger never settles an unmetered
response at a definite zero and never under-reserves relative to what the
provider could charge. The receipt records `reported=False`, which is the
honest state: the cost is an upper bound, not a reading.

The C06 router rule already produces this outcome for Prime Agent because
the adapter's `raw_usage` is empty. That is a fact about the adapter's
current shape, not a declared contract, so this record also makes the
adapter declare it: `normalize_usage` returns `reported=False`. A later
adapter change that populates `raw_usage` with anything but real counts
must not silently flip the router back to trusting zeros.

Consequences the operator should expect:

- Prime Agent usage panels and balance projections show ceiling costs,
  which overstate real spend. Overstating is the intended direction.
- A usage cap set on a Prime Agent key trips earlier than the true spend
  would trip it. Raise the cap rather than lower the ceiling.

## Reconsider if

- The Prime Agent binary starts emitting token usage on its receipt (a
  usage record on the process receipt, or a usage line in its stdout
  protocol). Then the adapter forwards real counts with `reported=True`,
  and the ceiling rule stops applying to it automatically.
- The providers behind Prime Agent expose per-call usage through an API the
  substrate can query after the fact. A reconciliation pass could then
  replace the ceiling with the reading, keeping the receipt's original
  `reported=False` for audit. Note that the owner-BYOT ledger has no such
  path today: `substrate/byot_usage/ledger.py` only accumulates
  `used_cents` (`settle_operation` refuses any row that is not
  `settlement_pending`, and both mutation paths add, never adjust), so an
  after-the-fact reading needs a new, audited adjustment mutation on the
  ledger before it can replace anything.

Never `reported=True` with zeros. A zero that looks like a reading is the
one state this record forbids.
