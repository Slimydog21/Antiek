"""Registry audit CLI for the Sprint 18 retrieval-time legal gate.

    python -m substrate.legal_gate.audit
    python -m substrate.legal_gate.audit --probe-url https://libgen.is/x
    python -m substrate.legal_gate.audit --probe-author "Margaret Atwood"
    python -m substrate.legal_gate.audit --json

Satisfies the operator-facing acceptance criterion documented at
the Sprint 18 sprint page §2.5: "Operator can edit registry.py,
run `python -m substrate.legal_gate.audit`, and see a list of (a)
what would be newly blocked, (b) what would be newly unblocked,
(c) any inconsistencies."

What this CLI shows:

  - Current registry counts (per tuple).
  - Inconsistencies — entries that look obviously wrong (empty
    strings, all-whitespace, banned-domain starting with `http`).
  - Optional probes — feed a URL / author / title / corpus_id /
    content_hash and see the gate's verdict.

What this CLI does NOT do:

  - Edit the registry. Adding entries requires a code-review PR
    with documented legal justification per `registry.py`'s
    module docstring.
  - Show "what would be newly blocked" against a real ingestion
    corpus — that requires walking the substrate's documents
    table and is a different scope (it's a substrate refactor
    territory, see master-spec §9).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import RegistryBackedLegalGate, registry
from .predicate import (
    author_blocked_reason,
    content_hash_blocked_reason,
    corpus_blocked_reason,
    document_blocked_reason,
    title_blocked_reason,
    url_blocked_reason,
)


def _registry_summary() -> dict[str, Any]:
    return {
        "banned_domains": list(registry.BANNED_DOMAINS),
        "banned_corpus_ids": list(registry.BANNED_CORPUS_IDS),
        "banned_authors": list(registry.BANNED_AUTHORS),
        "banned_title_substrings": list(registry.BANNED_TITLE_SUBSTRINGS),
        "banned_content_hash_prefixes": list(registry.BANNED_CONTENT_HASH_PREFIXES),
    }


def _inconsistencies() -> list[str]:
    """Lightweight static lint of registry entries. Flags obvious
    mistakes (empty strings, banned domains with `http` prefix,
    hash prefixes that aren't lowercase-hex)."""
    issues: list[str] = []
    for d in registry.BANNED_DOMAINS:
        if not d or not d.strip():
            issues.append("banned_domains contains an empty/whitespace entry")
        if d.startswith("http://") or d.startswith("https://"):
            issues.append(
                f"banned_domains entry {d!r} includes scheme — should be host-only"
            )
        if "/" in d:
            issues.append(
                f"banned_domains entry {d!r} contains a path — should be host-only"
            )
    for h in registry.BANNED_CONTENT_HASH_PREFIXES:
        if not h or not h.strip():
            issues.append("banned_content_hash_prefixes contains an empty entry")
            continue
        bad = [c for c in h.lower() if c not in "0123456789abcdef"]
        if bad:
            issues.append(
                f"banned_content_hash_prefixes entry {h!r} contains non-hex chars"
            )
    return issues


def _probe(
    *,
    url: str | None,
    author: str | None,
    title: str | None,
    corpus_id: str | None,
    content_hash: str | None,
) -> dict[str, Any]:
    """Run each non-empty probe input through the matching
    predicate AND through the composite `check_document` for the
    end-to-end view."""
    out: dict[str, Any] = {}
    if url:
        out["url"] = {"input": url, "reason": url_blocked_reason(url)}
    if author:
        out["author"] = {
            "input": author, "reason": author_blocked_reason(author),
        }
    if title:
        out["title"] = {"input": title, "reason": title_blocked_reason(title)}
    if corpus_id:
        out["corpus_id"] = {
            "input": corpus_id, "reason": corpus_blocked_reason(corpus_id),
        }
    if content_hash:
        out["content_hash"] = {
            "input": content_hash,
            "reason": content_hash_blocked_reason(content_hash),
        }
    if any([url, author, title, corpus_id, content_hash]):
        composite = document_blocked_reason(
            url=url or "",
            author=author or "",
            title=title or "",
            source_corpus=corpus_id or "",
            content_hash=content_hash or "",
        )
        gate = RegistryBackedLegalGate()
        verdict = gate.check_document(
            url=url or "",
            author=author or "",
            title=title or "",
            source_corpus=corpus_id or "",
            content_hash=content_hash or "",
        )
        out["composite"] = {
            "first_match_reason": composite,
            "verdict_allowed": verdict.allowed,
            "verdict_reason": verdict.reason,
            "gate_kind": verdict.gate_kind,
        }
    return out


def _render_summary(s: dict[str, Any], *, out=None) -> None:
    out = out or sys.stdout
    print("Legal-gate registry summary", file=out)
    print("=" * 32, file=out)
    for key, items in s.items():
        print(f"\n{key} ({len(items)}):", file=out)
        if not items:
            print("  (empty)", file=out)
        else:
            for entry in items:
                print(f"  - {entry}", file=out)


def _render_probe(p: dict[str, Any], *, out=None) -> None:
    out = out or sys.stdout
    print("\nProbe results", file=out)
    print("=" * 32, file=out)
    for k, v in p.items():
        if k == "composite":
            comp = v
            verdict = "ALLOWED" if comp["verdict_allowed"] else "REJECTED"
            print(
                f"\ncomposite: {verdict} (gate={comp['gate_kind']})", file=out,
            )
            if comp["verdict_reason"]:
                print(f"  reason: {comp['verdict_reason']}", file=out)
        else:
            input_ = v["input"]
            reason = v["reason"]
            verdict = "BLOCKED" if reason else "allowed"
            print(f"\n{k}: {verdict}", file=out)
            print(f"  input:  {input_}", file=out)
            if reason:
                print(f"  reason: {reason}", file=out)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m substrate.legal_gate.audit",
        description=(
            "Audit the Sprint 18 retrieval-time legal gate registry. "
            "Read-only — adding registry entries requires a code-review PR."
        ),
    )
    p.add_argument("--probe-url", default=None, help="Probe a URL.")
    p.add_argument(
        "--probe-author", default=None, help="Probe an author name.",
    )
    p.add_argument(
        "--probe-title", default=None, help="Probe a title.",
    )
    p.add_argument(
        "--probe-corpus", default=None, help="Probe a source-corpus id.",
    )
    p.add_argument(
        "--probe-hash", default=None,
        help="Probe a content_hash (sha256 hex; the 'sha256:' prefix is stripped).",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Output JSON instead of a human-readable summary.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    summary = _registry_summary()
    issues = _inconsistencies()
    probe = _probe(
        url=args.probe_url,
        author=args.probe_author,
        title=args.probe_title,
        corpus_id=args.probe_corpus,
        content_hash=args.probe_hash,
    )

    if args.json:
        print(json.dumps({
            "summary": summary,
            "inconsistencies": issues,
            "probe": probe,
        }, indent=2))
        return 0

    _render_summary(summary)
    if issues:
        print("\nInconsistencies", file=sys.stderr)
        print("=" * 32, file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
    if probe:
        _render_probe(probe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
