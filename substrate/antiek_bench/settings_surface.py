"""Settings-panel consumption shape for Antiek-bench leaderboard.

Pure adapter: turns a leaderboard snapshot into the JSON object a Settings
API/UI would return. Does not touch #440 budget projection or model inventory.
"""

from __future__ import annotations

from typing import Any

from .leaderboard import LeaderboardSnapshot, build_leaderboard, project_leaderboard_html
from .store import BenchStore  # BenchStore protocol / concrete stores


def settings_leaderboard_payload(
    week_id: str,
    *,
    store: BenchStore,
    include_html: bool = False,
) -> dict[str, Any]:
    """Public entry for Settings: structured leaderboard (+ optional HTML)."""
    snap = build_leaderboard(week_id, store=store)
    payload = snap.to_dict()
    payload["settings_panel"] = "antiek_bench_weekly"
    # Top model hint for decision-tree tab (advisory only — not auto-routing).
    if snap.models:
        top = snap.models[0]
        payload["recommended_model_id"] = top.model_id
        payload["recommended_mean_score"] = top.mean_score
    else:
        payload["recommended_model_id"] = None
        payload["recommended_mean_score"] = None
    if include_html:
        payload["html"] = project_leaderboard_html(snap)
    return payload


def leaderboard_from_snapshot(snapshot: LeaderboardSnapshot) -> dict[str, Any]:
    return snapshot.to_dict()


def settings_usage_summary_payload(
    *,
    store: BenchStore,
    include_html: bool = False,
) -> dict[str, Any]:
    """Public entry for Settings: weekly usage summary from recorded events.

    Calls shipped ``weekly_usage_summary`` — does not re-classify events or
    run live multi-provider benches.
    """
    from .usage_bridge import weekly_usage_summary

    summary = weekly_usage_summary(store=store)
    payload: dict[str, Any] = {
        "event_count": int(summary.get("event_count") or 0),
        "retention_limit": int(summary.get("retention_limit") or 0),
        "evicted_event_count": int(summary.get("evicted_event_count") or 0),
        "by_task_class": dict(summary.get("by_task_class") or {}),
        # Residual (ha): source breakdown (investigation_start vs session_flywheel).
        "by_source": dict(summary.get("by_source") or {}),
        # Residual (nx): known feed source legend (incl twin_chase / floating DR).
        "known_sources": list(summary.get("known_sources") or []),
        # Residual (ry): Write twin_seed aggregates (substrate SSOT for Settings).
        "write_seed_by_source": dict(summary.get("write_seed_by_source") or {}),
        "write_seed_source_count": int(summary.get("write_seed_source_count") or 0),
        "write_seed_event_count": int(summary.get("write_seed_event_count") or 0),
        "write_seed_known_count": int(summary.get("write_seed_known_count") or 0),
        # Residual (act): body honesty aggregates for recursive rewrite.
        "write_seed_with_body_count": int(
            summary.get("write_seed_with_body_count") or 0
        ),
        "write_seed_title_only_count": int(
            summary.get("write_seed_title_only_count") or 0
        ),
        "write_seed_body_unknown_count": int(
            summary.get("write_seed_body_unknown_count") or 0
        ),
        "view_format": "html",
        "settings_panel": "antiek_bench_usage_weekly",
        "source": "antiek_bench.usage_events",
        "notes": [],
    }
    if include_html:
        payload["html"] = project_usage_summary_html(payload)
    return payload


def project_usage_summary_html(summary: dict[str, Any]) -> str:
    """HTML-first human view of a usage summary (never PDF)."""
    # Residual (rx): Write twin_seed feed honesty in HTML projection
    # (parity Settings React chrome rt–rw).
    from substrate.antiek_bench.usage_bridge import TWIN_WRITE_SEED_USAGE_SOURCES
    from substrate.engagement_spine.project import project_to_html

    count = int(summary.get("event_count") or 0)
    retention_limit = int(summary.get("retention_limit") or 0)
    evicted = int(summary.get("evicted_event_count") or 0)
    by_class = summary.get("by_task_class") or {}
    by_source = summary.get("by_source") or {}
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Antiek-bench weekly usage"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Events retained: {count}/{retention_limit} · "
                        f"evicted over time: {evicted} · view: HTML"
                    ),
                }
            ],
        },
    ]
    if by_source:
        write_seed_bits: list[str] = []
        src_bits_parts: list[str] = []
        for src, n in sorted(by_source.items()):
            label = f"{src}={n}"
            if str(src) in TWIN_WRITE_SEED_USAGE_SOURCES:
                label = f"{label} [write seed]"
                write_seed_bits.append(str(src))
            src_bits_parts.append(label)
        src_bits = ", ".join(src_bits_parts)
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"By source: {src_bits}",
                    }
                ],
            }
        )
        if write_seed_bits:
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Write seed feeds: "
                                f"{len(write_seed_bits)} "
                                "(recursive note-taker → Write): "
                                + ", ".join(write_seed_bits)
                            ),
                        }
                    ],
                }
            )
    # Residual (act): body honesty for recursive suite rewrite quality.
    with_body = int(summary.get("write_seed_with_body_count") or 0)
    title_only = int(summary.get("write_seed_title_only_count") or 0)
    body_unknown = int(summary.get("write_seed_body_unknown_count") or 0)
    if with_body or title_only or body_unknown:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Write seed body honesty: "
                            f"with_body={with_body} · title_only={title_only} · "
                            f"unknown={body_unknown} "
                            "(title-only → failed outcome for suite rewrite)"
                        ),
                    }
                ],
            }
        )
    # Residual (nx): catalog of known feed sources (twin_chase, floating DR, …).
    known = summary.get("known_sources") or []
    if known:
        known_write = sum(
            1 for s in known if str(s) in TWIN_WRITE_SEED_USAGE_SOURCES
        )
        known_text = "Known feed sources: " + ", ".join(str(s) for s in known)
        if known_write:
            known_text += (
                f" · Write seed feeds: {known_write} "
                "(recursive note-taker → Write)"
            )
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": known_text,
                    }
                ],
            }
        )
    if not by_class:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "(no usage events yet — investigation starts, "
                            "floating DR / twin chase opens, engagement flywheel "
                            "deposits, marketplace host, and Midnight Oil feed "
                            "this summary)"
                        ),
                    }
                ],
            }
        )
    else:
        for task_class, bucket in sorted(by_class.items()):
            if not isinstance(bucket, dict):
                continue
            worked = int(bucket.get("worked") or 0)
            failed = int(bucket.get("failed") or 0)
            total = int(bucket.get("total") or 0)
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"{task_class}: total={total} worked={worked} failed={failed}"
                            ),
                        }
                    ],
                }
            )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id="antiek-bench-usage-summary",
        creator="antiek_bench",
    )


def settings_suite_proposal_payload(
    *,
    store: BenchStore,
    registry: Any = None,
    include_html: bool = False,
) -> dict[str, Any]:
    """Public entry for Settings: suite rewrite *proposal* from recorded usage.

    Calls shipped ``propose_from_recorded_usage`` / ``propose_suite_delta``.
    Status is always ``proposed`` on this path — never auto-promotes active suite.

    Honest empty: zero usage events → no fabricated proposal (notes only).
    """
    from .suite import active_suite
    from .usage_bridge import list_usage_events, propose_from_recorded_usage

    events = list_usage_events(store=store)
    active = active_suite(registry=registry)
    active_version = active.suite_version
    base: dict[str, Any] = {
        "has_proposal": False,
        "proposal_id": None,
        "status": None,
        "base_suite_version": active_version,
        "proposed_suite_version": None,
        "active_suite_version": active_version,
        "active_suite_unchanged": True,
        "auto_promoted": False,
        "rationale": None,
        "added_item_ids": [],
        # Residual (acy/adp): body honesty matrix (0 when empty).
        "title_only_write_seed_count": 0,
        "with_body_write_seed_count": 0,
        "body_unknown_write_seed_count": 0,
        "event_count": len(events),
        "view_format": "html",
        "settings_panel": "antiek_bench_suite_proposal",
        "source": "antiek_bench.propose_from_recorded_usage",
        "notes": [],
    }
    if not events:
        base["notes"] = [
            "No usage events recorded; suite proposal requires non-empty "
            "usage history. Active suite is unchanged."
        ]
        if include_html:
            base["html"] = project_suite_proposal_html(base)
        return base

    proposal = propose_from_recorded_usage(store=store, registry=registry)
    after = active_suite(registry=registry)
    prop_dict = proposal.to_dict() if hasattr(proposal, "to_dict") else dict(proposal)
    status = str(prop_dict.get("status") or getattr(proposal, "status", "proposed"))
    payload: dict[str, Any] = {
        "has_proposal": True,
        "proposal_id": str(
            prop_dict.get("proposal_id") or getattr(proposal, "proposal_id", "")
        ),
        "status": status,
        "base_suite_version": str(
            prop_dict.get("base_suite_version")
            or getattr(proposal, "base_suite_version", active_version)
        ),
        "proposed_suite_version": str(
            prop_dict.get("proposed_suite_version")
            or getattr(proposal, "proposed_suite_version", "")
        ),
        "active_suite_version": after.suite_version,
        "active_suite_unchanged": after.suite_version == active_version,
        "auto_promoted": False,
        "rationale": str(
            prop_dict.get("rationale") or getattr(proposal, "rationale", "") or ""
        ),
        "added_item_ids": list(
            prop_dict.get("added_item_ids")
            or getattr(proposal, "added_item_ids", ())
            or []
        ),
        "seed_policy_version": str(prop_dict.get("seed_policy_version") or ""),
        "reviewed_seed_count": int(prop_dict.get("reviewed_seed_count") or 0),
        "generic_seed_count": int(prop_dict.get("generic_seed_count") or 0),
        "redacted_event_count": int(prop_dict.get("redacted_event_count") or 0),
        "dropped_event_count": int(prop_dict.get("dropped_event_count") or 0),
        # Residual (acy/adp): body honesty matrix for recursive rewrite Settings chrome.
        "title_only_write_seed_count": int(
            prop_dict.get("title_only_write_seed_count")
            or getattr(proposal, "title_only_write_seed_count", 0)
            or 0
        ),
        "with_body_write_seed_count": int(
            prop_dict.get("with_body_write_seed_count")
            or getattr(proposal, "with_body_write_seed_count", 0)
            or 0
        ),
        "body_unknown_write_seed_count": int(
            prop_dict.get("body_unknown_write_seed_count")
            or getattr(proposal, "body_unknown_write_seed_count", 0)
            or 0
        ),
        "event_count": len(events),
        "view_format": "html",
        "settings_panel": "antiek_bench_suite_proposal",
        "source": "antiek_bench.propose_from_recorded_usage",
        "notes": [
            "Proposal status is proposed only — approve_and_promote is a separate operator gate.",
        ],
    }
    if status != "proposed":
        payload["notes"].append(
            f"Unexpected proposal status {status!r}; product path must not auto-promote."
        )
    if not payload["active_suite_unchanged"]:
        payload["notes"].append(
            "WARNING: active suite version changed during propose — promote must stay gated."
        )
    if include_html:
        payload["html"] = project_suite_proposal_html(payload)
    return payload


def settings_approve_suite_proposal_payload(
    proposal_id: str,
    *,
    store: BenchStore,
    registry: Any = None,
    approve: bool = True,
    include_html: bool = False,
) -> dict[str, Any]:
    """Explicit operator gate: approve/reject + promote only when approve=True.

    Calls shipped ``approve_and_promote``. Never implicit from GET propose path.
    """
    from .rewrite import (
        ProposalIntegrityError,
        ProposalStateError,
        StaleSuiteProposalError,
        approve_and_promote,
    )
    from .suite import active_suite

    pid = str(proposal_id or "").strip()
    if not pid:
        raise ValueError("proposal_id is required")

    before = active_suite(registry=registry)
    before_version = before.suite_version
    row = store.get_proposal(pid)
    if row is None:
        payload: dict[str, Any] = {
            "ok": False,
            "proposal_id": pid,
            "status": None,
            "approved": False,
            "promoted": False,
            "active_suite_version": before_version,
            "active_suite_before": before_version,
            "proposed_suite_version": None,
            "view_format": "html",
            "settings_panel": "antiek_bench_suite_approve",
            "source": "antiek_bench.approve_and_promote",
            "notes": [f"Unknown proposal_id: {pid}"],
        }
        if include_html:
            payload["html"] = project_suite_proposal_html(
                {
                    "has_proposal": False,
                    "auto_promoted": False,
                    "proposal_id": pid,
                    "status": None,
                    "rationale": payload["notes"][0],
                }
            )
        return payload

    try:
        suite = approve_and_promote(
            pid, store=store, registry=registry, approve=approve
        )
    except (ProposalIntegrityError, ProposalStateError) as exc:
        after = active_suite(registry=registry)
        updated = store.get_proposal(pid) or row
        stale = isinstance(exc, StaleSuiteProposalError)
        payload = {
            "ok": False,
            "proposal_id": pid,
            "status": str(updated.get("status") or ("stale" if stale else "invalid")),
            "approved": False,
            "promoted": False,
            "active_suite_version": after.suite_version,
            "active_suite_before": before_version,
            "proposed_suite_version": updated.get("proposed_suite_version"),
            "view_format": "html",
            "settings_panel": "antiek_bench_suite_approve",
            "source": "antiek_bench.approve_and_promote",
            "notes": [str(exc)],
        }
        if include_html:
            payload["html"] = project_suite_proposal_html(
                {
                    "has_proposal": True,
                    "proposal_id": pid,
                    "status": payload["status"],
                    "base_suite_version": updated.get("base_suite_version"),
                    "proposed_suite_version": payload["proposed_suite_version"],
                    "active_suite_version": after.suite_version,
                    "auto_promoted": False,
                    "rationale": payload["notes"][0],
                }
            )
        return payload
    after = active_suite(registry=registry)
    updated = store.get_proposal(pid) or {}
    status = str(updated.get("status") or ("approved" if approve else "rejected"))
    promoted = bool(approve) and after.suite_version != before_version
    replayed_approval = bool(approve) and str(row.get("status")) == "approved"
    payload = {
        "ok": True,
        "proposal_id": pid,
        "status": status,
        "approved": status == "approved",
        "promoted": promoted,
        "active_suite_version": after.suite_version,
        "active_suite_before": before_version,
        "proposed_suite_version": str(
            updated.get("proposed_suite_version") or suite.suite_version
        ),
        "view_format": "html",
        "settings_panel": "antiek_bench_suite_approve",
        "source": "antiek_bench.approve_and_promote",
        "notes": [
            (
                f"Approved and promoted suite {after.suite_version}"
                if promoted
                else f"Approval already recorded; active suite remains {after.suite_version}"
                if status == "approved" or replayed_approval
                else f"Rejected proposal {pid}; active suite remains {after.suite_version}"
            )
        ],
    }
    if include_html:
        payload["html"] = project_suite_proposal_html(
            {
                "has_proposal": True,
                "proposal_id": pid,
                "status": status,
                "base_suite_version": before_version,
                "proposed_suite_version": payload["proposed_suite_version"],
                "active_suite_version": after.suite_version,
                "auto_promoted": False,
                "rationale": payload["notes"][0],
                "added_item_ids": list(updated.get("added_item_ids") or []),
            }
        )
    return payload


def project_suite_proposal_html(payload: dict[str, Any]) -> str:
    """HTML-first human view of a suite proposal (never PDF)."""
    from substrate.engagement_spine.project import project_to_html

    has = bool(payload.get("has_proposal"))
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Antiek-bench suite proposal"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Status: proposal only (not auto-active) · view: HTML · "
                        f"auto_promoted={payload.get('auto_promoted')}"
                    ),
                }
            ],
        },
    ]
    if not has:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "(no proposal — record usage events via engagement flywheel first)"
                        ),
                    }
                ],
            }
        )
    else:
        for label, key in (
            ("Proposal id", "proposal_id"),
            ("Status", "status"),
            ("Base suite", "base_suite_version"),
            ("Proposed suite", "proposed_suite_version"),
            ("Active suite", "active_suite_version"),
            ("Usage seed policy", "seed_policy_version"),
            ("Rationale", "rationale"),
        ):
            val = payload.get(key)
            if val is None or val == "":
                continue
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": f"{label}: {val}"},
                    ],
                }
            )
        # Residual (acy/adp): full body honesty matrix in HTML view.
        title_only_n = int(payload.get("title_only_write_seed_count") or 0)
        with_body_n = int(payload.get("with_body_write_seed_count") or 0)
        body_unknown_n = int(payload.get("body_unknown_write_seed_count") or 0)
        if title_only_n or with_body_n or body_unknown_n:
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Body honesty matrix: with_body={with_body_n} · "
                                f"title_only={title_only_n} · unknown={body_unknown_n}"
                                + (
                                    f" · title-only Write seeds (has_body=false): "
                                    f"{title_only_n} → suite rewrite"
                                    if title_only_n
                                    else ""
                                )
                            ),
                        }
                    ],
                }
            )
        reviewed_n = int(payload.get("reviewed_seed_count") or 0)
        generic_n = int(payload.get("generic_seed_count") or 0)
        redacted_n = int(payload.get("redacted_event_count") or 0)
        dropped_n = int(payload.get("dropped_event_count") or 0)
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Usage seeds: reviewed={reviewed_n} · generic={generic_n} · "
                            f"redacted={redacted_n} · dropped={dropped_n}"
                        ),
                    }
                ],
            }
        )
        added = payload.get("added_item_ids") or []
        if added:
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Added items: {', '.join(str(x) for x in added)}",
                        }
                    ],
                }
            )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id="antiek-bench-suite-proposal",
        creator="antiek_bench",
    )
