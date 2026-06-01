"""M4 tests — X / personal_reading content is excluded from training / RL export.

This REUSES SPR-01's training-exclusion artifact — it does NOT mint a parallel
filter. SPR-01's M4 finding (recorded in its handoff) was that NO content_class-
selecting SFT/RL export exists in the tree today (``substrate/loop_3/sft_runner.py``
is a budget/loop runner that never materializes document bodies by content_class),
so SPR-01 landed the ready-made guard-rail DENYLIST instead:

    substrate.constants.NON_TRAINABLE_CONTENT_CLASSES
        == frozenset({PERSONAL_READING_CONTENT_CLASS, GATED_DEFAULT_CONTENT_CLASS})
        == {"personal_reading", "restricted_pending_opt_in"}

(defined at substrate/constants.py:626 as an explicit union so it can never
silently diverge from the gated-class name). This is the symbol M4 cites: the
future training-export author imports THIS denylist instead of hand-rolling a
literal list, and X content (content_class=personal_reading) is excluded BY
MEMBERSHIP in it.

This test pins X's no-training clause two ways: (1) personal_reading is a member
of the SPR-01 denylist (the static guarantee — fails loudly if a future edit
removes it); and (2) building a training manifest over a real DB — by applying
the SPR-01 denylist as the exclusion filter — leaves the ingested X document
ABSENT while a public_domain CONTROL is PRESENT (the filter is real, not a no-op
that excludes everything). No parallel X-only filter is written.
"""

from __future__ import annotations

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import nacl.secret  # noqa: E402

from acquisition.twitter.adapter import twitter_doc_id  # noqa: E402
from acquisition.twitter.api_client import parse_search_response  # noqa: E402
from runtime.byok.pipelines import register_pipeline  # noqa: E402
from runtime.byok.runner import run_pipeline  # noqa: E402
from runtime.byok.store import store_credential  # noqa: E402
from runtime.db_lock import connect_read, connect_write  # noqa: E402
# SPR-01's training-exclusion denylist (the symbol M4 cites — NOT a parallel one).
from substrate.constants import (  # noqa: E402
    GATED_DEFAULT_CONTENT_CLASS,
    NON_TRAINABLE_CONTENT_CLASSES,
    PERSONAL_READING_CONTENT_CLASS,
)
from substrate.graph import ensure_initialized  # noqa: E402
from substrate.graph.ops import insert_document  # noqa: E402

_TEST_KEY = b"0" * nacl.secret.SecretBox.KEY_SIZE

_FIXTURE_PAGE = {
    "data": [
        {
            "id": "2000",
            "text": "An X thread the owner is reading for their own research and frolic.",
            "author_id": "u9",
            "created_at": "2026-05-30T10:00:00.000Z",
            "conversation_id": "2000",
        }
    ],
    "includes": {"users": [{"id": "u9", "username": "dhh", "verified": True}]},
    "meta": {"result_count": 1},
}


class _FakeClient:
    def recent_search(self, query):
        return parse_search_response(_FIXTURE_PAGE)

    def user_timeline(self, user_id):
        return parse_search_response(_FIXTURE_PAGE)

    def conversation(self, conversation_id):
        return parse_search_response(_FIXTURE_PAGE)


def _build_training_manifest(db_path: str):
    """A training/RL export manifest built by APPLYING SPR-01's denylist.

    This is the one-line filter the future export author writes: include a
    document IFF its content_class is NOT in the SPR-01
    ``NON_TRAINABLE_CONTENT_CLASSES`` denylist (and not NULL, which is also
    deny-by-default). It reuses the SPR-01 constant — it does NOT redefine which
    classes are non-trainable. Returns ``(included_ids, excluded_ids)``."""
    with connect_read(db_path) as con:
        rows = con.execute(
            "SELECT document_id, content_class FROM documents ORDER BY document_id"
        ).fetchall()
    included: list[str] = []
    excluded: list[str] = []
    for doc_id, content_class in rows:
        if content_class is None or content_class in NON_TRAINABLE_CONTENT_CLASSES:
            excluded.append(doc_id)
        else:
            included.append(doc_id)
    return included, excluded


def test_spr01_denylist_excludes_personal_reading_symbol():
    # The cited SPR-01 symbol exists and personal_reading (+ gated) are members —
    # the static guarantee M4 relies on. Fails loudly if SPR-01's denylist
    # regresses.
    assert PERSONAL_READING_CONTENT_CLASS in NON_TRAINABLE_CONTENT_CLASSES
    assert GATED_DEFAULT_CONTENT_CLASS in NON_TRAINABLE_CONTENT_CLASSES


def test_x_doc_absent_from_training_manifest_pd_control_present():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "t.duckdb")
        artifact = os.path.join(tmp, "credentials.enc")
        cfg = os.path.join(tmp, "pipelines.json")
        ensure_initialized(db_path)

        # 1) ingest an X thread via the BYOK runner → content_class=personal_reading
        cred_id = store_credential(
            "dhh", "tok", artifact_path=artifact, key_bytes=_TEST_KEY,
        )
        pl = register_pipeline(
            "dhh", cred_id, "thread_specific", seed="2000", config_path=cfg,
        )
        from processing.embedding.embed import default_embedding_provider
        run_pipeline(
            pl.pipeline_id, db_path=db_path, config_path=cfg,
            client=_FakeClient(), embedder=default_embedding_provider(),
        )
        x_doc_id = twitter_doc_id("2000")

        # 2) plant a public_domain NEGATIVE CONTROL so we prove the filter
        #    INCLUDES a trainable doc (not a no-op excluding everything).
        pd_doc_id = "doc-pd-control-1"
        with connect_write(db_path, purpose="test/seed") as con:
            insert_document(
                con,
                document_id=pd_doc_id,
                source_tier=1,
                document_type="book",
                content_class="public_domain",
                source_uri="https://gutenberg.org/ebooks/1",
                title="A Public-Domain Classic",
                raw_text="Full public-domain body text that is trainable.",
                on_conflict="ignore",
            )

        # 3) build the training/RL manifest by APPLYING SPR-01's denylist
        included, excluded = _build_training_manifest(db_path)

        # the X personal_reading doc is ABSENT from the trainable manifest …
        assert x_doc_id not in included
        assert x_doc_id in excluded
        # … and the public_domain control IS present (filter is real, not a
        # no-op that excludes everything).
        assert pd_doc_id in included
