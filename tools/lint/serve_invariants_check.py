#!/usr/bin/env python3
"""No-raw-body-read boundary lint — forbid a NEW SQL read of the materialized
body ``documents.raw_text`` outside the sanctioned serve gate (SPR-09 M2).

The invariant (master-spec §9.0; the SPR-01/02 serve gate). The full body of a
document lives in ``documents.raw_text``. The ONLY place that column may leave
storage to be SERVED is the serve gate ``substrate.books.serve.serve_full_text``
(wrapped by ``substrate.books.serve_guard.serve_full_text_guarded``), which
applies the content_class gate + the license-tier drift check + the link-back
invariant before a body is emitted. ``serve_guard_check.py`` already forbids a
direct *call* to ``serve_full_text`` outside the guard — but that would NOT catch
a brand-new endpoint that bypasses the gate entirely by issuing its OWN
``SELECT ... raw_text ... FROM documents`` and returning the body. THIS lint
closes that hole: a new SQL read of ``documents.raw_text`` outside the allowlist
goes red.

What is flagged. A SQL query string (resolved from an ``ast.Constant`` str OR a
``+``-concatenation of constant strings — see below) that reads the materialized
body from the ``documents`` table. Two read shapes count:

  1. EXPLICIT column read — ``SELECT`` + ``raw_text`` + ``documents`` all present
     (``SELECT raw_text FROM documents`` / ``SELECT d.raw_text FROM documents d``).
  2. STAR read of the documents table — ``SELECT * FROM documents`` (or
     ``SELECT * FROM main.documents`` / ``... FROM documents d``). A ``SELECT *``
     against ``documents`` pulls ``raw_text`` (the body column) out with the row
     even though the literal never names it — exactly the evasion a column-name-
     only scanner missed (round-2 tightening). The ``FROM documents`` is required
     so a ``SELECT *`` against some other table is not flagged.

INSERT / UPDATE of ``raw_text`` is NOT flagged (those WRITE the body — ingestion's
job — they do not serve it); the ``SELECT`` requirement excludes them.

``+``-concatenated literal SQL (``"SELECT raw_text " + "FROM documents ..."``) is
RECONSTRUCTED from its constant fragments before matching, so splitting the query
across string literals to dodge the single-literal match no longer evades (round-2
tightening). Python already merges IMPLICITLY-adjacent string literals into one
``ast.Constant``, so those were always caught; the ``+`` case is the new one.

Allowlist (the serve gate + the existing INTERNAL readers — none of which serves
the body OUT to a caller):

  * ``substrate/books/serve.py``               — the binding serve gate (the one
                                                  sanctioned body-emission path).
  * ``substrate/books/serve_guard.py``         — the guard wrapping it.
  * ``substrate/books/takedown.py``            — reads raw_text only to know what
                                                  to PURGE (then NULLs it); never
                                                  emits it.
  * ``substrate/research_bridge/extractor.py`` — internal extraction (chunking /
                                                  enrichment), not a serve-out.
  * ``substrate/research_bridge/versioning.py``— internal version snapshotting,
                                                  not a serve-out.
  * test files                                 — exercise the readers directly.

A NEW file (a careless future endpoint / worker / script) that issues its own
``SELECT raw_text FROM documents`` to serve a body makes CI go red here, forcing
it through ``serve_full_text_guarded``.

Modeled EXACTLY on ``tools/lint/serve_guard_check.py`` / ``boundary_check.py``:
same ``path:line`` output, same exit-code contract (0 = clean, 1 = violations),
same AST walk over the tree.

KNOWN, ACCEPTED LIMITATION: a body read whose table/column names are
INTERPOLATED at runtime (an f-string ``FROM {table}``, a ``.format()`` query, a
name read from a config/DB row) is not detected — the table/column tokens never
appear as static text, so no AST string lint can resolve them. This is the same
accepted-risk class as the other AST lints. The covered shapes are every
production form: a literal (or ``+``-concatenated literal) ``SELECT raw_text FROM
documents`` and ``SELECT * FROM documents``.

Exit 0 = clean; exit 1 = a violation, printed as ``path:line``.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# A SQL string that READS the materialized body. Shape 1 (explicit column):
# SELECT + raw_text + documents all present. Shape 2 (star read): SELECT * FROM
# documents — a star pulls raw_text out of the row without naming it. The
# ``FROM documents`` anchor (Shape 2) keeps a SELECT * against some OTHER table
# from flagging.
_SELECT_RE = re.compile(r"\bselect\b", re.IGNORECASE)
_RAW_TEXT_RE = re.compile(r"\braw_text\b", re.IGNORECASE)
_DOCUMENTS_RE = re.compile(r"\bdocuments\b", re.IGNORECASE)
# A SELECT * ... FROM [schema.]documents (the star body-read). ``\*`` may be
# followed by other things before FROM only in the explicit-column path; here we
# require the ``*`` projection then a FROM documents anchor.
_STAR_FROM_DOCUMENTS_RE = re.compile(
    r"\bselect\b\s*\*.*?\bfrom\b\s+(?:[a-z_][a-z0-9_]*\.)?documents\b",
    re.IGNORECASE | re.DOTALL,
)

# Allowlist: the serve gate + guard, and the existing internal readers that read
# raw_text but never SERVE it out to a caller.
_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "substrate/books/serve.py",
        "substrate/books/serve_guard.py",
        "substrate/books/takedown.py",
        "substrate/research_bridge/extractor.py",
        "substrate/research_bridge/versioning.py",
        # The standing corpus audit opens the DB READ-ONLY (connect_read, never
        # connect_write) and reads raw_text only to assert corpus invariants
        # (e.g. no servable doc with a NULL body); it never serves a body to a
        # client — an internal auditor, like the extractor/versioning above.
        "substrate/corpus_audit.py",
        # The Paul Graham incremental ingest driver (SPR-05) opens the DB
        # READ-ONLY and reads raw_text for two INTERNAL, non-serving purposes:
        # (1) recompute the stored body's content-hash for change-detection on a
        # re-run (this graph DB carries no content_hash column / events table, so
        # the body itself is the only source of the hash), and (2) assess
        # extraction quality (word count / markup-leakage) so a degraded essay is
        # flagged rather than silently stored. The body is never returned to a
        # caller or served — same internal-reader category as takedown /
        # extractor / versioning / corpus_audit above. It CANNOT serve a body
        # (no serve surface in the driver); serve_full_text_guarded remains the
        # only body-emission path. FOLLOW-UP (SPR-10/connector): persisting the
        # content-hash in documents.metadata would let change-detection read the
        # hash instead of the body, removing read (1) from this surface; the
        # quality read (2) inherently needs the body and stays an internal read.
        "acquisition/urls/paulgraham.py",
        # The personal-lane monitoring/puttering surface (SPR-09) reads raw_text
        # in _select_new_personal_items (SELECT ... d.raw_text ... WHERE
        # content_class='personal_reading') to populate FeedItem.body for the
        # OWNER's ambient feed. This is the personal_reading OWNER-PATH read, not
        # a public serve: the body leaves storage ONLY when putter_feed's
        # policy_tag is in search.PRIVILEGED_POLICY_TAGS (operator_only /
        # private_research) — `body = it.body if (with_body and owner_path) else
        # None` (monitor.py putter_feed) — exactly mirroring the search.py gate
        # the serve-guard enforces; on the public / attribution-eligible path the
        # body is None (test_putter_feed_withholds_body_on_public_path), and
        # refresh_monitor never puts a body in the event-log payload. The static
        # AST scanner cannot see that RUNTIME policy_tag gate, so the file is
        # allowlisted here. NOTE (vs the paulgraham entry above): this reader DOES
        # return the body — but only on the owner path, which is the documented
        # "personal_reading is readable in full ONLY on the owner path" invariant.
        # The SPR-10 corpus audit independently asserts no personal_reading row is
        # publicly servable/attributable, so a regression that widened this path
        # would be caught there too.
        "orchestration/monitoring/monitor.py",
        # SPR-01/02 (.antiek sidecar): _gather_anchors_and_audio reads raw_text in
        # `SELECT raw_text, metadata FROM documents WHERE document_id = ?` where the
        # document_id is a VOICE-NOTE id (an anchor's voice_note_id) — the OWNER's
        # own voice-note transcript, bundled into the owner's own signed .antiek
        # sidecar. This is owner-authored annotation content, not a third-party
        # servable body: it neither passes through nor needs the content_class /
        # license-tier / link-back serve gate, which governs licensed third-party
        # document bodies (books / arXiv), never the owner's own voice memos. Same
        # internal / owner-path category as monitor.py above; the sidecar carries
        # SIDECAR_CONTENT_CLASS and the .antiek _FORBIDDEN_SUBSTRATE_FIELDS gate
        # independently forbids chunks/embeddings/edges in the emitted container.
        "services/antiek_format/sidecar_writer.py",
        # Multimedia evidence registration reads private bodies only inside
        # owner-bound internal verification. The diagram authority hashes
        # source text to prove evidence identity; the knowledge registrar asks
        # DuckDB for SHA-256 digests to reject conflicting source/twin rows.
        # Neither module exposes a body or implements a serve surface.
        "substrate/multimedia/diagram_evidence_authority.py",
        "substrate/multimedia/knowledge_registration.py",
        # Corpus source-census (operator CLI): one read-only
        # `SELECT ... raw_text ... FROM documents` used to compute corpus
        # statistics (metadata / linkback / rights-tier / servable percentages).
        # Its docstring is explicit — "does not create the DB, call the network, or
        # write files"; it never returns a body to a caller. Same internal-auditor
        # category as substrate/corpus_audit.py above.
        "tools/source_census.py",
        # The test-residue quarantine tool (DOGFOOD SPR-04) opens the DB
        # READ-ONLY and reads only nodes/edges. Its `documents` references are
        # existence-check subqueries (SELECT document_id FROM documents), never
        # a raw_text body read, and the tool has no serve surface. The scanner's
        # STAR_FROM_DOCUMENTS_RE false-positives here: with re.DOTALL, `.*?`
        # stretches from `SELECT * FROM nodes` across the WHERE clause to match
        # the subquery's `FROM documents`, flagging a star body-read that does
        # not exist. TODO(scanner): tighten the regex to a same-level FROM
        # documents (no WHERE in between) so subqueries do not trip it; tracked
        # separately from this PR.
        "tools/quarantine_test_residue.py",
    }
)


def _is_body_read_sql(value: str) -> bool:
    """True iff ``value`` is a SQL string that READS the materialized body from
    ``documents`` — either the explicit column read (SELECT + raw_text +
    documents) OR the star read (SELECT * FROM documents, which pulls raw_text out
    with the row)."""
    if (
        _SELECT_RE.search(value)
        and _RAW_TEXT_RE.search(value)
        and _DOCUMENTS_RE.search(value)
    ):
        return True
    return bool(_STAR_FROM_DOCUMENTS_RE.search(value))


def _concat_constant_str(node: ast.AST) -> str | None:
    """Reconstruct a ``+``-concatenation of constant strings into one string, so a
    body read split across string literals to dodge the single-literal match is
    still resolved. Returns the joined string, or ``None`` if ``node`` is not a
    pure constant-string ``+`` tree (any non-constant operand makes it dynamic →
    out of scope, the accepted-limitation class)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _concat_constant_str(node.left)
        right = _concat_constant_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _is_test_file(rel: str) -> bool:
    parts = Path(rel).parts
    if parts and parts[0] == "tests":
        return True
    stem = Path(rel).name
    return stem.startswith("test_") or stem.endswith("_test.py")


def _is_lint_scanner(rel: str) -> bool:
    """The lint scanners in ``tools/lint/`` DESCRIBE the SQL pattern they hunt
    for in their own prose/docstrings, so they must not scan themselves (or each
    other) — that is documentation, not a body read."""
    parts = Path(rel).parts
    return len(parts) >= 2 and parts[0] == "tools" and parts[1] == "lint"


def find_violations(root: Path = _REPO) -> list[str]:
    """Return ``path:line: message`` strings for every new SQL read of
    ``documents.raw_text`` outside the allowlist + test files."""
    out: list[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root).as_posix()
        if rel in _ALLOWED_FILES or _is_test_file(rel) or _is_lint_scanner(rel):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        seen_lines: set[int] = set()  # de-dup so a matched concat + its child
        # constant fragment don't both report on the same line.
        for node in ast.walk(tree):
            candidate: str | None = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                candidate = node.value
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                candidate = _concat_constant_str(node)
            if candidate is None or not _is_body_read_sql(candidate):
                continue
            if node.lineno in seen_lines:
                continue
            seen_lines.add(node.lineno)
            out.append(
                f"{rel}:{node.lineno}: SQL read of documents.raw_text "
                f"(the materialized body) outside the serve gate — a body "
                f"may leave storage ONLY through serve_full_text_guarded "
                f"(substrate/books/serve_guard.py), which applies the "
                f"content_class gate + license-tier + link-back checks"
            )
    return out


def main() -> int:
    violations = find_violations()
    if violations:
        print("Serve-invariant (raw_text body read) violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nThe materialized body documents.raw_text may be SELECTed and served "
            "ONLY through the serve gate (serve_full_text / serve_full_text_guarded). "
            "A new SQL read of raw_text from documents bypasses the content_class + "
            "license-tier + link-back gates and risks serving a non-T1 / "
            "un-attributed body. Allowlist: the serve gate + guard, the internal "
            "readers (takedown, extractor, versioning), and test files."
        )
        return 1
    print(
        "OK: no SQL read of documents.raw_text outside the serve gate + allowlist."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
