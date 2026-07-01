# Design-it-twice: the graph-write interface (AOD SPR-06)

**Date:** 2026-07-01 · **Status:** proposal (verdict-only; no code changes here) ·
**Lens:** Ousterhout, *A Philosophy of Software Design*, Ch. 11 ("design it twice")

## Why this interface

SPR-01's ranking puts `substrate/graph/ops.py` at `top_unfenced[0]` — the
shallowest load-bearing *and* hottest unfenced module (ratio 0.333, churn 3, 14
public `insert_*` functions). SPR-02's `leaks.json` independently implicates the
same module: `substrate.graph.ops._maybe_json` and `._exists` are imported by
three `acquisition/*` callers (private-name leaks). Two independent measuring
instruments point at one interface, so it is the one worth designing twice before
SPR-04 deepens it.

### What's actually shallow about it

Every `insert_*` function repeats the same **caller-side ceremony**:

```python
def insert_document(con: LockedConnection, *, document_id, source_tier,
                    document_type, source_uri=None, title=None, author=None,
                    published_at=None, investigation_id=None, raw_text=None,
                    metadata=None, content_class=None, ip_holder_id=None,
                    on_conflict="error", events_dir=None) -> str: ...
```

- The caller threads a `LockedConnection` into *every* call and the body
  re-asserts the write lock (`_assert_write_locked(con)`) *every time*.
- `insert_document` alone exposes 15 parameters — the interface is nearly as wide
  as the row it writes.
- Id-derivation (content-addressed vs supplied), `on_conflict`, and JSON coercion
  (`_maybe_json`) are decisions the caller keeps re-making — and, per SPR-02,
  reaching into private helpers to make.

The implementation is not trivial (real SQL + id + conflict logic), but the
*interface* is wide and ceremonious. That is the Ousterhout-shallow signature the
metric caught: a caller must learn 14 functions × wide signatures + the lock
protocol to write to the graph.

---

## Design A — unified `write(con, record)` with typed records

One public verb over a union of typed record dataclasses:

```python
@dataclass(frozen=True)
class DocumentRecord: document_id: str; source_tier: int; document_type: str; ...
@dataclass(frozen=True)
class ChunkRecord: document_id: str; chunk_index: int; text: str; ...
GraphRecord = DocumentRecord | ChunkRecord | NodeRecord | EdgeRecord | ...

def write(con: LockedConnection, record: GraphRecord, *, on_conflict="error") -> str: ...
```

- **Public symbols collapse** from 14 functions to 1 function + N record types
  (data, not behavior). The widest signatures become self-documenting typed data.
- `on_conflict` / id-derivation / JSON coercion move *into* `write` and the record
  constructors — decided once, not at every call site.
- **Cost:** a big discriminated union; adding a node kind = a new record type + a
  `write` branch. The record *fields* are still interface the caller learns — the
  surface is partly *relocated* into the record types rather than hidden. It reads
  as deep to SPR-01's metric (dataclass fields aren't counted), but that is partly
  a metric artifact, not fully real depth.

## Design B — a `GraphWriter` facade bound to a locked connection

Absorb the connection + lock ceremony into a stateful facade constructed once:

```python
class GraphWriter:
    def __init__(self, con: LockedConnection) -> None:
        _assert_write_locked(con); self._con = con
    def document(self, *, document_id, source_tier, document_type, ...) -> str: ...
    def chunk(self, *, document_id, chunk_index, text, ...) -> str: ...
    def edge(self, *, ...) -> str: ...
```

- The **lock discipline is asserted once** (in `__init__`), not re-threaded through
  every call — the single-writer invariant becomes a property of *holding a
  writer*, which is stronger and less error-prone than "remember to pass the
  locked con."
- The write vocabulary coheres under one abstraction — exactly the *class-cohesion*
  insight SPR-01's own metric encodes (a class is one learnable abstraction; its
  methods a vocabulary). A caller learns "get a writer, call `.document(...)`."
- The facade is the natural home for the cross-cutting concerns callers currently
  open-code or leak for: JSON coercion (`_maybe_json` → a private method or a
  public `.write_json_field`), existence checks (`_exists`), and any future typed
  event emission — which **closes the SPR-02 leaks** as a side effect.
- **Cost:** still N methods (interface breadth similar to N functions, just
  grouped); the facade is stateful (holds `con`), so its lifetime must not outlive
  the lock — a real but bounded constraint, and one the type system can guard.

---

## Verdict — chosen: **B (GraphWriter facade), grafting A's typed record for the widest inserts**

B absorbs the *most repeated caller-side ceremony* — the `LockedConnection` +
`_assert_write_locked` dance that recurs at every one of graph/ops's call sites —
which is the actual shallowness the metric flagged. It coheres the write
vocabulary under one abstraction (consistent with the class-cohesion discount
SPR-01 itself uses), and it gives the `_maybe_json`/`_exists` leaks a legitimate
home, turning the SPR-02 finding into a fix rather than a standing smell. A grabs
a smaller ceremony (id/conflict) and mostly *relocates* field surface into record
types.

The graft: for the two or three inserts with the widest signatures
(`document` at 15 params foremost), accept an optional typed record
(`writer.document(record=DocumentRecord(...))`) so the widest interface becomes
self-documenting data — A's best idea, scoped to where it pays.

### Why not A alone
A's discriminated-union `write(con, record)` still threads `con` through every
call and re-asserts the lock, so it does not remove the ceremony the metric
actually penalized; it trades 14 verbs for 1 verb + N nouns, but the *nouns* carry
the same field surface. It reads deep to the proxy partly because the proxy does
not count dataclass fields — a place where the metric's own documented limitation
would flatter the design. Choosing on the metric's blind spot would be exactly the
overfitting the SPR-01 calibration warned against.

### Reconsider-if
- If a future requirement makes writes *cross-connection* or batched, the stateful
  facade's lifetime constraint gets awkward — revisit A's stateless `write(record)`.
- If the node/edge kinds proliferate past ~a dozen, the typed-record union (A)
  becomes the better scaling shape and B's method list bloats.

### For SPR-04 (the implementation that follows)
Deepen behind a `GraphWriter`, **behavior-preserving + test-locked**: characterize
the current `insert_*` outputs green-before, introduce the facade, migrate call
sites, keep the free functions as thin deprecated shims until every caller moves,
and close the `_maybe_json`/`_exists` leaks by making them writer internals. Public
`insert_*` symbol count goes down; the module does strictly more.
