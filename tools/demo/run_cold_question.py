"""Operator-runnable demo: POST a cold question to a running Antiek
server and poll until the Loop 1 orchestrator terminates.

Sprint 8 day 4. The first real-LLM end-to-end exercise of the full
substrate. Requires:

- ``uvicorn interfaces.research.api.app:app --reload`` (or equivalent)
  running on ``--base-url`` (default ``http://localhost:8000``).
- ``DEEPSEEK_API_KEY`` or ``OPENROUTER_API_KEY`` in env so the
  dispatch router can serve every role (decomposer, evidence_retriever,
  parameter_extractor, connector, synthesizer, knowledge_extractor).
- An ``ANTIEK_RESEARCH_DIR`` writable directory for per-investigation
  research artifacts and the eventual ``MASTER.md``.
- An ``ANTIEK_KNOWLEDGE_SKILLS_DIR`` with at least one
  ``<domain>-knowledge/SKILL.md`` template so Phase 8 has somewhere to
  patch.

Usage:

    python -m tools.demo.run_cold_question \\
        --question "What's the load-bearing constraint on scaling \\
                    diffraction-limited photonic interconnects to 1 TB/s?" \\
        --topic-slug photonic-interconnects \\
        --base-url http://localhost:8000

The script POSTs ``/investigations``, then polls
``GET /investigations/{id}`` every 2 seconds. On terminal status
(``completed`` or ``failed``), prints:

- Final phase + last_delivered_action_type
- Terminal payload summary (thesis_summary / MASTER.md path /
  domains_patched OR failure reason)
- A trajectory summary by event-type counts so the operator can
  spot anomalies (e.g. CONSTRAINT_REVISION_TRIGGERED firing 3x
  means the constraint loop hit max_iterations).

Two suggested cold questions from the Sprint 8 day 4 brief:

    "What's the load-bearing constraint on scaling diffraction-
     limited photonic interconnects to 1 TB/s aggregate bandwidth?"

    "How would a Series B deep-tech investor evaluate a startup
     claiming GaN substrate cost parity with silicon by 2027?"

Exit codes: 0 on completed, 1 on failed, 2 on transport/timeout
errors.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import httpx


def _post_investigation(
    base_url: str, *,
    question: str,
    context: str,
    topic_slug: str | None,
    max_sub_questions: int,
    investigation_id: str | None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """POST /investigations. Returns the response body on 202."""
    body: dict[str, Any] = {
        "question": question,
        "context": context,
        "max_sub_questions": max_sub_questions,
    }
    if topic_slug:
        body["topic_slug"] = topic_slug
    if investigation_id:
        body["investigation_id"] = investigation_id
    r = httpx.post(
        f"{base_url}/investigations", json=body, timeout=timeout,
    )
    if r.status_code != 202:
        raise RuntimeError(
            f"POST /investigations returned {r.status_code}: {r.text}"
        )
    return r.json()


def _get_status(
    base_url: str, investigation_id: str, *, timeout: float = 5.0,
) -> dict[str, Any]:
    r = httpx.get(
        f"{base_url}/investigations/{investigation_id}", timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"GET /investigations/{investigation_id} returned {r.status_code}: {r.text}"
        )
    return r.json()


def _get_trajectory(
    base_url: str, investigation_id: str, *, timeout: float = 10.0,
) -> list[dict[str, Any]]:
    r = httpx.get(
        f"{base_url}/trajectory/{investigation_id}", timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"GET /trajectory returned {r.status_code}: {r.text}"
        )
    return r.json().get("events", [])


def _summarize_trajectory(events: list[dict[str, Any]]) -> dict[str, int]:
    """Count events by action_type for a quick anomaly scan."""
    counts: dict[str, int] = {}
    for e in events:
        at = e.get("action_type", "(unknown)")
        counts[at] = counts.get(at, 0) + 1
    return dict(sorted(counts.items()))


def _print_terminal(status: dict[str, Any]) -> None:
    """Pretty-print the terminal payload."""
    s = status["status"]
    print(f"\n=== Investigation {status['investigation_id']} → {s.upper()} ===")
    print(f"Last phase entered: {status.get('current_phase')}")
    print(f"Last delivered: {status.get('last_delivered_action_type')}")
    tp = status.get("terminal_payload") or {}
    if s == "completed":
        print(f"\nThesis summary:\n  {tp.get('thesis_summary', '(none)')}\n")
        print(f"Recommendation: {tp.get('implicit_recommendation')}")
        print(f"Constraint loop: {tp.get('constraint_loop_status')}"
              f" ({tp.get('constraint_loop_iterations')} iter)")
        print(f"MASTER.md: {tp.get('master_md_path')}")
        print(f"Domains patched: {tp.get('domains_patched')}")
        print(f"Phases verified: {tp.get('total_phases_verified')}")
    elif s == "failed":
        print(f"Failed at phase: {tp.get('phase')}")
        print(f"Last completed phase: {tp.get('last_completed_phase')}")
        print(f"\nReason:\n  {tp.get('reason')}")


def run(
    *,
    base_url: str,
    question: str,
    context: str,
    topic_slug: str | None,
    max_sub_questions: int,
    investigation_id: str | None,
    poll_interval: float,
    timeout_seconds: float,
    print_trajectory: bool,
) -> int:
    """Returns exit code: 0 completed, 1 failed, 2 timeout/transport."""
    try:
        post_resp = _post_investigation(
            base_url, question=question, context=context,
            topic_slug=topic_slug,
            max_sub_questions=max_sub_questions,
            investigation_id=investigation_id,
        )
    except Exception as e:
        print(f"POST failed: {e}", file=sys.stderr)
        return 2

    inv_id = post_resp["investigation_id"]
    print(f"Started investigation {inv_id} (start_event_id="
          f"{post_resp['start_event_id']})")
    print(f"Polling every {poll_interval}s; timeout {timeout_seconds}s …")

    deadline = time.monotonic() + timeout_seconds
    last_status_str: str | None = None
    while time.monotonic() < deadline:
        try:
            status = _get_status(base_url, inv_id)
        except Exception as e:
            print(f"GET failed (will retry): {e}", file=sys.stderr)
            time.sleep(poll_interval)
            continue

        cur = (
            f"phase={status.get('current_phase')} "
            f"last_delivered={status.get('last_delivered_action_type')}"
        )
        if cur != last_status_str:
            print(f"  [{status['status']}] {cur}")
            last_status_str = cur

        if status["status"] in ("completed", "failed"):
            _print_terminal(status)
            if print_trajectory:
                events = _get_trajectory(base_url, inv_id)
                print(
                    "\nTrajectory event counts:\n"
                    + json.dumps(_summarize_trajectory(events), indent=2)
                )
            return 0 if status["status"] == "completed" else 1

        time.sleep(poll_interval)

    print(
        f"Timed out after {timeout_seconds}s waiting for terminal status.",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Run a cold question through the Antiek Loop 1 orchestrator "
            "and report the terminal verdict + trajectory summary."
        ),
    )
    p.add_argument(
        "--question", required=True,
        help="The cold research question to investigate.",
    )
    p.add_argument(
        "--context", default="",
        help="Optional domain framing prepended to the Decomposer prompt.",
    )
    p.add_argument(
        "--topic-slug", default=None,
        help=(
            "Slug for the MASTER.md output dir; auto-derived from the "
            "question when omitted."
        ),
    )
    p.add_argument(
        "--max-sub-questions", type=int, default=8,
        help="Cap on parallel evidence_retrieve dispatches (default 8).",
    )
    p.add_argument(
        "--investigation-id", default=None,
        help="Stable id for backtest correlation; auto-generated when omitted.",
    )
    p.add_argument(
        "--base-url", default="http://localhost:8000",
        help="Antiek server base URL (default http://localhost:8000).",
    )
    p.add_argument(
        "--poll-interval", type=float, default=2.0,
        help="Seconds between status polls (default 2.0).",
    )
    p.add_argument(
        "--timeout-seconds", type=float, default=600.0,
        help=(
            "Overall timeout before giving up on the run (default 600s = "
            "10 minutes; typical Loop 1 run is 60-300s)."
        ),
    )
    p.add_argument(
        "--no-trajectory", action="store_true",
        help="Skip the trajectory event-count summary at end.",
    )
    args = p.parse_args(argv)

    return run(
        base_url=args.base_url,
        question=args.question,
        context=args.context,
        topic_slug=args.topic_slug,
        max_sub_questions=args.max_sub_questions,
        investigation_id=args.investigation_id,
        poll_interval=args.poll_interval,
        timeout_seconds=args.timeout_seconds,
        print_trajectory=not args.no_trajectory,
    )


if __name__ == "__main__":
    sys.exit(main())
