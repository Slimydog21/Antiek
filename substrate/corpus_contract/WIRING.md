# WIRING.md — frozen-file needs for SPR-06

This document records where the research loop should consume the corpus
contract via the protocol, and which frozen files need wiring (documented
here, not edited).

## Where the research loop should consume corpora

The deep-research loop (``docs/deep_research_doctrine.md``, PR #716)
consumes any corpus through the two-verb protocol:

```python
from substrate.corpus_contract import CorpusAdapter, CorpusHit, CorpusDocument, FetchResult
```

A research iteration calls ``adapter.search(query)`` to get an immutable
tuple of ranked hits (descending score, ascending opaque id for ties)
with snippets (context economy: doctrine I-2), then calls
``adapter.fetch(hit.id)`` for each hit it wants to synthesize.  The loop
never needs a third verb — if it measurably needs link-graph traversal to
match recall, that is doctrine-falsifying evidence to record (W6).

## Frozen-file wiring needs (not edited — additive new-files-only)

### `substrate/engagement_spine/__init__.py`

**What the owner must wire:** re-export the twin-notes adapter so consumers
can do ``from substrate.engagement_spine import TwinNotesCorpusAdapter``.

**Why:** SPR-05 reads twin notes through the corpus contract.  The adapter
lives in ``substrate/corpus_contract/adapters/twin_notes.py`` but the
engagement spine's public surface is where twin-note consumers already
import from.

### `substrate/marketplace_host/__init__.py`

**What the owner must wire:** re-export the hosted-documents adapter so
consumers can do ``from substrate.marketplace_host import HostedDocsCorpusAdapter``.

**Why:** SPR-07/08's acquisition outputs become corpora behind the corpus
contract.  The adapter lives in
``substrate/corpus_contract/adapters/hosted_docs.py`` but the marketplace
host's public surface is where hosted-document consumers already import from.

### `runtime/research_loop.py` (or equivalent)

**What the owner must wire:** the research loop's corpus iteration should
accept ``CorpusAdapter`` (the protocol), not concrete store handles.  Each
corpus (twin notes, hosted docs, future web corpora from SPR-07/08) provides
an adapter; the loop calls ``search`` then ``fetch`` uniformly.

**Why:** one uniform mechanism instead of N integrations — the doctrine's
core claim.

## Doctrine invariants carried by this sprint

- **I-2:** search returns snippets; full docs only via fetch.  Enforced by
  ``CorpusHit.snippet`` (context-economy span) and ``CorpusDocument.content``
  (full text).
- **I-8:** read-only by construction.  Enforced by ``TwinNoteReader`` and
  ``HostedDocReader`` protocols having no write methods, and
  ``assert_read_only`` in the conformance kit.
- **Rights/provenance:** every fetch carries the fetched unit's
  ``origin_ref`` and a non-empty ``license_class``. Hosted documents preserve
  the stored rights class; operator twin notes are ``operator_private``.
- **Public surface:** adapters expose exactly ``search`` and ``fetch``. The
  conformance kit challenges randomized multi-document corpora, coherent hit
  fetches, deterministic replay, snippet bounds, and exact ranking.
- **W6 falsification hook:** if the twin-notes adapter reveals recall needs
  graph traversal (follow ``supported_by`` edges), record that as
  doctrine-falsifying evidence.  Noted in the handoff packet.
