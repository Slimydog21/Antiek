"""A decision record must not cite a repo path that does not exist.

Of 531 repo-path citations across the decision records and CLAUDE.md, 17 point
at nothing. Most are harmless drift. Four are not, because the citation is the
evidence for a claim the document makes about enforcement:

    usability-keystone.md      "INSTALLED ... + verify-live WIRED", citing
                               tests/test_usability_keystone.py and
                               infrastructure/runbooks/usability-keystone-
                               verify-live.md — neither exists, and
                               `grep keystone` over deploy.yml returns zero.
    convergence-owner.md       "LIVE in this repo ... the planted-duplicate
                               proof (tests/test_uniqueness_registry.py)" —
                               does not exist.
    reachability-gate.md       tests/test_reachability_runner.py — does not
                               exist (already corrected separately).

A missing tool file is a typo. A missing *self-test*, cited as the thing that
would notice a gate being demoted, is the gate's own tripwire being absent —
which is why nobody noticed. That pattern recurs across four records, always
with the same shape: the tool is real, the proof is not.

The register below is a NO-GROWTH list: every entry carries why the path is
absent, a new dangling citation fails, and `test_register_entries_are_still_
absent` fails when a registered path appears, so entries must LEAVE when the
work lands rather than accumulating.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Paths cited by a decision record that legitimately do not exist yet.
# Each entry states WHY. Entries must leave when the path appears.
KNOWN_ABSENT: dict[str, str] = {
    # wrestle-evolution-spec-2026-05-23.md declares its own status as
    # "Code complete on `wrestle-evolution/integration` branch; push to
    # origin/main pending operator review" — so these are branch-only by
    # design, not drift.
    "services/library/raw_bytes_store.py": "wrestle-evolution: unmerged branch",
    "services/library/thumbnails.py": "wrestle-evolution: unmerged branch",
    "services/voice/audio_store.py": "wrestle-evolution: unmerged branch",
    "substrate/behavior/sessions.py": "wrestle-evolution: unmerged branch",
    "substrate/behavior/PRIVACY.md": "wrestle-evolution: unmerged branch",
    # are-wave-2-tooling-additive.md documents these as OPTIONAL: both lints
    # handle absence deliberately (no_raise_in_substrate_writers.py:166-169,
    # unannotated_bypass.py:208-215) and the doc says so.
    "tools/lints/raise_allowlist.toml": "optional; lint handles absence by design",
    "tools/lints/bypass_patterns.toml": "optional; lint handles absence by design",
    # Gates whose CI step and self-test were never committed. Registered
    # rather than silently deleted, because the absence IS the finding.
    # See the corrected Status lines in each record.
    #
    # tests/test_usability_keystone.py LEFT this register on 2026-09-20: the
    # probe it names was written, run for the first time, found a live 500
    # (GET /chunks/{id}), and now has a real test. The register shrank
    # because the work landed — which is the only way an entry should go.
    "infrastructure/runbooks/usability-keystone-verify-live.md": "never written — see usability-keystone.md",
    "tests/test_uniqueness_registry.py": "gate never wired — see convergence-owner.md",
    "tests/test_reachability_runner.py": "gate never wired — see reachability-gate.md",
    # Renamed or removed since the record was written; the record's argument
    # does not depend on the path resolving.
    "acquisition/openaccess/rogue.py": "stale name, pre-dates the connector split",
    "substrate/graph/rogue_tool.py": "stale name, pre-dates the connector split",
    "substrate/graph_handle.py": "stale name",
    "substrate/invariants.py": "now a package, substrate/invariants/",
    "tests/test_first_light_e2e.py": "stale name",
}

_PREFIXES = (
    "tests/", "tools/", "infrastructure/", "substrate/", "interfaces/",
    "runtime/", "benchmarks/", ".github/", "apps/", "orchestration/",
    "acquisition/", "services/",
)
_CITATION = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|ts|tsx|yml|yaml|json|toml|sh))`")


def _cited_paths() -> dict[str, str]:
    """Repo-path citation -> the first document citing it."""
    docs = sorted((_ROOT / "docs" / "decisions").glob("*.md"))
    claude = _ROOT / "CLAUDE.md"
    if claude.exists():
        docs.append(claude)
    assert len(docs) > 50, f"only {len(docs)} docs found — check is vacuous"
    out: dict[str, str] = {}
    for doc in docs:
        for hit in _CITATION.findall(doc.read_text(encoding="utf-8", errors="ignore")):
            if hit.startswith(_PREFIXES):
                out.setdefault(hit, doc.name)
    assert len(out) > 200, f"only {len(out)} citations extracted — check is vacuous"
    return out


def test_no_new_dangling_citation() -> None:
    dangling = {
        path: doc
        for path, doc in _cited_paths().items()
        if not (_ROOT / path).exists() and path not in KNOWN_ABSENT
    }
    assert not dangling, (
        "decision records cite repo paths that do not exist:\n  "
        + "\n  ".join(f"{p}  (cited by {d})" for p, d in sorted(dangling.items()))
        + "\nFix the citation, or add it to KNOWN_ABSENT with the reason."
    )


def test_register_entries_are_still_absent() -> None:
    """The register must shrink. A present path is a stale entry."""
    present = sorted(p for p in KNOWN_ABSENT if (_ROOT / p).exists())
    assert not present, (
        "these registered paths now exist — remove them from KNOWN_ABSENT so "
        f"they are covered by the check above: {present}"
    )
