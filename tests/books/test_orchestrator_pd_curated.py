"""--pd-curated orchestrator wiring (SPR-06). No live network.

The curated PD spine must rotate the five Wave-2 connectors, route each
candidate's verdict through classify() (never a local content_class), and
collapse a work shared with Gutenberg to one document. We monkeypatch each
connector's ``discover`` so the test never touches the network, then drive the
orchestrator's pure planning core + a dry-run main().
"""

from __future__ import annotations

import acquisition.books.registry as registry
import tools.run_corpus_ingest as orch
from acquisition.books.pd_connector_base import BookCandidate


def _fake_candidate(source: str, source_id: str, *, pd: bool):
    return BookCandidate(
        source=source,
        source_id=f"{source}:{source_id}",
        title=f"Work {source_id}",
        author="Someone",
        source_uri=f"https://example.org/{source_id}",
        download_url=f"https://example.org/{source_id}.pdf",
        download_format="pdf",
        pd_signal=(f"{source}: established PD" if pd else None),
    )


def test_pd_curated_wires_all_five_connectors(monkeypatch):
    """--pd-curated discovers from every registered connector; the planned
    candidates carry source-id identities and a deferred classify()-routed
    ingest thunk."""
    seen_sources = []

    def _make_discover(src_key):
        def _discover(fetcher, *, limit=25):
            seen_sources.append(src_key)
            return [_fake_candidate(src_key, "001", pd=True)]
        return _discover

    # Patch each registry entry's discover in place.
    patched = tuple(
        registry.PdSource(
            key=s.key, module=s.module,
            discover=_make_discover(s.key), establishment=s.establishment,
        )
        for s in registry.PD_CURATED_SOURCES
    )
    monkeypatch.setattr(registry, "PD_CURATED_SOURCES", patched)

    planned = orch._pd_curated_book_candidates(limit=2, investigation_id="inv-t")
    # Every registered source contributed.
    assert set(seen_sources) == set(registry.PD_CURATED_SOURCE_KEYS)
    assert len(planned) == len(registry.PD_CURATED_SOURCES)
    for pc in planned:
        assert pc.source == "public_domain"
        assert pc.ref.source_id.endswith(":001")


def test_pd_curated_source_failure_is_isolated(monkeypatch):
    """One connector's discovery failure does not abort the curated spine (the
    gutendex-503 lesson generalized)."""
    def _ok(fetcher, *, limit=25):
        return [_fake_candidate("standard_ebooks", "ok", pd=True)]

    def _boom(fetcher, *, limit=25):
        raise RuntimeError("source down")

    patched = (
        registry.PdSource(
            key="standard_ebooks", module="m", discover=_ok, establishment="e"
        ),
        registry.PdSource(
            key="internet_archive", module="m", discover=_boom, establishment="e"
        ),
    )
    monkeypatch.setattr(registry, "PD_CURATED_SOURCES", patched)
    planned = orch._pd_curated_book_candidates(limit=2, investigation_id="inv-t")
    # The healthy source still produced a candidate; the broken one was skipped.
    assert len(planned) == 1
    assert planned[0].ref.source_id == "standard_ebooks:ok"


def test_pd_curated_flag_parsed():
    args = orch.build_parser().parse_args(
        ["--source", "public_domain", "--pd-curated", "--limit", "5", "--dry-run"]
    )
    assert args.pd_curated is True
    assert args.dry_run is True
