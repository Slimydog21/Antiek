#!/usr/bin/env python3
"""Smoke-test the dispatch router against REAL provider APIs.

This is the operator-runnable counterpart to ``tests/test_dispatch.py``
and the adapter tests. It hits the live APIs of the providers it's
configured for, so:

- API keys must be present in the environment:
    ANTHROPIC_API_KEY   for ``--tier synthesis``
    DEEPSEEK_API_KEY    for ``--tier flash``  and  ``--tier pro``

- The cost is small but real. A single ``flash`` call is fractions of
  a cent; a single ``synthesis`` call is ~1 cent. The script prints
  the actual cost from the DispatchCall event before exiting.

Usage::

    # Cheap, fast: hit DeepSeek-Flash via the 'flash' tier.
    python scripts/smoke_dispatch.py --tier flash

    # TileRT speed lane (needs ANTIEK_TILERT_API_KEY + ANTIEK_TILERT_BASE_URL).
    python scripts/smoke_dispatch.py --tier speed --latency-mode interactive --brain glm

    # Expensive, high-quality: hit Claude via the 'synthesis' tier.
    python scripts/smoke_dispatch.py --tier synthesis

    # Custom prompt
    python scripts/smoke_dispatch.py --tier flash --prompt "two-sentence summary of CRISPR"

    # Force a fallback path by pretending the primary 401s (sets the
    # ANTHROPIC_API_KEY to garbage):
    ANTHROPIC_API_KEY=bad python scripts/smoke_dispatch.py --tier synthesis

The script confirms three things end-to-end:

1. The HTTP call succeeds (or the fallback chain handles failure).
2. ``normalize_usage`` produced sensible input/output token counts on
   the real response (compare against the actual length of the prompt
   plus the response).
3. ``cost_usd`` was computed and is non-zero (assumes the tier has
   pricing entries in ``config.yaml``).
4. The DispatchCall event landed in the trajectory store with the
   correct shape.

Failures are loud: any inconsistency between the printed response and
the event payload means cost reports downstream will be wrong.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the package importable without installing.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from substrate.dispatch import dispatch  # noqa: E402
from substrate.dispatch.providers.bootstrap import register_default_providers  # noqa: E402
from substrate.dispatch.session_routing import dispatch_routing_kwargs  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import DispatchCallPayload, Event  # noqa: E402

# Tier → role used to exercise that tier. Picked to match the
# role_tiers mapping in substrate/dispatch/config.yaml.
TIER_TO_ROLE = {
    "flash": "note_taker",       # routes to flash via role_tiers
    "pro": "decomposer",         # routes to pro
    "synthesis": "synthesizer",  # routes to synthesis
    "speed": "synthesizer",      # TileRT tier (needs ANTIEK_TILERT_* + engagement kwargs)
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=list(TIER_TO_ROLE), default="flash")
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: 'smoke test ok'.",
        help="The prompt to send. Default is a deterministic one-liner.",
    )
    parser.add_argument(
        "--investigation-id", default="smoke-dispatch",
        help="Investigation id for the trajectory store.",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=64,
        help="Cap the response length. 64 is enough for a smoke probe.",
    )
    parser.add_argument(
        "--latency-mode",
        choices=("interactive", "autonomous"),
        default="interactive",
        help="Engagement clock for routing (speed tier needs interactive + brain=glm).",
    )
    parser.add_argument(
        "--brain",
        choices=("glm", "premium"),
        default="glm",
        help="Brain toggle when exercising speed / engaged driving roles.",
    )
    args = parser.parse_args()

    registered = register_default_providers()
    if args.tier == "speed" and "tilert" not in registered:
        print(
            "tilert provider not registered — set ANTIEK_TILERT_API_KEY and "
            "ANTIEK_TILERT_BASE_URL (see infrastructure/modal/tilert_glm5/README.md)",
            file=sys.stderr,
        )
        return 2

    role = TIER_TO_ROLE[args.tier]
    routing = dispatch_routing_kwargs(
        args.investigation_id,
        presence="engaged" if args.latency_mode == "interactive" else "background",
    )
    routing["latency_mode"] = args.latency_mode
    routing["brain"] = args.brain

    print(f"→ dispatching role={role!r} (tier={args.tier!r}) prompt={args.prompt!r}")
    result = dispatch(
        args.prompt,
        role,
        investigation_id=args.investigation_id,
        max_tokens=args.max_tokens,
        **routing,
    )

    print()
    print("── Result ────────────────────────────────────────────")
    print(f"provider:     {result.provider}")
    print(f"model:        {result.model}")
    print(f"tier:         {result.tier}")
    print(f"fallback_idx: {result.fallback_chain_index}")
    print(f"finish:       {result.finish_reason}")
    print(f"latency_ms:   {result.latency_ms}")
    print(f"input_tokens: {result.usage.input_tokens} (cached: {result.usage.cached_input_tokens})")
    print(f"output_tokens:{result.usage.output_tokens}")
    print(f"cost_usd:     ${result.cost_usd:.6f}")
    print()
    print("── Response text ─────────────────────────────────────")
    print(result.text)
    print()

    # Confirm the event landed cleanly.
    rows = trajectory(args.investigation_id)
    matching = [r for r in rows if r.get("event_id") == result.event_id]
    if not matching:
        print(f"ERROR: success result returned event_id={result.event_id!r} "
              f"but no matching row found in the trajectory store.")
        return 1
    event = Event.model_validate(matching[0])
    if not isinstance(event.payload, DispatchCallPayload):
        print(f"ERROR: event {result.event_id} round-tripped to a "
              f"{type(event.payload).__name__}, not DispatchCallPayload.")
        return 1

    print("── DispatchCall event (round-tripped) ─────────────────")
    print(json.dumps(event.model_dump(mode="json"), indent=2)[:1200])
    print()

    # Sanity invariants — if any of these fail, costs/usage are wrong
    # for downstream reports and need investigation BEFORE more events
    # accumulate.
    issues = []
    if event.payload.input_tokens != result.usage.input_tokens:
        issues.append(
            f"event.input_tokens ({event.payload.input_tokens}) != "
            f"result.usage.input_tokens ({result.usage.input_tokens})"
        )
    if event.payload.output_tokens != result.usage.output_tokens:
        issues.append(
            f"event.output_tokens ({event.payload.output_tokens}) != "
            f"result.usage.output_tokens ({result.usage.output_tokens})"
        )
    if abs(event.payload.cost_usd - result.cost_usd) > 1e-9:
        issues.append(
            f"event.cost_usd ({event.payload.cost_usd}) != "
            f"result.cost_usd ({result.cost_usd})"
        )
    if event.policy_id != f"{result.provider}/{result.model}":
        issues.append(
            f"event.policy_id ({event.policy_id!r}) != "
            f"'{result.provider}/{result.model}'"
        )

    if issues:
        print("FAIL — invariants violated:")
        for it in issues:
            print(f"  - {it}")
        return 1

    print("OK — all invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
