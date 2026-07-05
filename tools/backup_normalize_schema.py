"""Normalize the malformed ``schema.sql`` DuckDB ``EXPORT DATABASE`` emits.

Context (see ``specs/antiek-data-durability/`` + ``tests/test_backup_restore_roundtrip.py``):
DuckDB's ``EXPORT DATABASE`` cannot round-trip a **self-referential foreign key**.
It drops the FK but leaves a stray comma in the emitted ``schema.sql`` — either an
empty constraint slot (``, ,``) or a trailing comma before the table's closing
paren (``, )``). ``IMPORT DATABASE`` then raises ``syntax error at or near ","`` on
the real Antiek schema (``edges.superseded_by``, ``deliverable_sections.
parent_section_id``), so the documented disaster-recovery restore (``runbooks/
disaster-recovery.md`` → ``IMPORT DATABASE``) is non-functional.

``normalize_exported_schema_sql`` fixes that malformed DDL at the backup layer
(called by ``infrastructure/ansible/templates/backup.sh.j2`` right after the
EXPORT). The two self-ref FKs are still dropped on the restored DB (a DuckDB
limitation, not fixable here) — they are advisory soft-pointers and are *already*
silently lost on any restore today; this normalizer makes the restore actually
run instead of crashing.

Why this is safe (provably correctness-preserving)
--------------------------------------------------
A comma immediately followed by another comma (``, ,``) or by a closing paren
(``, )``) is **never valid SQL** inside a ``CREATE TABLE`` column/constraint
list. The normalizer only ever removes such definitively-malformed commas; it
never alters valid DDL. It is depth- and string-aware: only commas at paren
depth 1 inside a ``CREATE TABLE`` (the column/constraint list — not inside a
nested ``CHECK``/``DEFAULT``/``IN``, and not inside a string literal) are
considered, so a comma that is legitimately part of an expression or literal is
never touched. Idempotent: a second pass is a no-op.
"""

from __future__ import annotations

_CREATE_RE = "CREATE TABLE"


def normalize_exported_schema_sql(sql: str) -> str:
    """Return ``sql`` with the DuckDB self-ref-FK stray commas removed.

    Operates per ``CREATE TABLE`` statement (the only construct the malformation
    appears in). Within each, a comma at paren-depth 1 (the column/constraint
    list), outside string literals, is dropped when the next non-space token is
    another comma (empty constraint slot) or ``)`` (trailing comma at table
    close). Everything else — including all commas inside nested ``CHECK``/
    ``DEFAULT`` expressions or string literals — is passed through unchanged.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        # Find the next CREATE TABLE; pass through anything before/around it
        # (sequences, indexes, views, comments) byte-for-byte.
        ct = sql.find(_CREATE_RE, i)
        if ct == -1:
            out.append(sql[i:])
            break
        out.append(sql[i:ct])
        # Statement body runs from ct to the statement terminator. DuckDB EXPORT
        # uses ';;'; fall back to ')' of the table if no terminator is present.
        stmt_start = ct
        term = sql.find(";;", stmt_start)
        stmt_end = (term + 2) if term != -1 else _table_close(sql, stmt_start)
        out.append(_normalize_one_create_table(sql[stmt_start:stmt_end]))
        i = stmt_end
    return "".join(out)


def _table_close(sql: str, start: int) -> int:
    """Index just past the ``)`` that closes the CREATE TABLE starting at *start*."""
    depth = 0
    in_str = False
    j = start
    while j < len(sql):
        ch = sql[j]
        if in_str:
            if ch == "'":
                in_str = False
        elif ch == "'":
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(sql)


def _normalize_one_create_table(stmt: str) -> str:
    """Normalize one CREATE TABLE statement (depth- + string-aware)."""
    out: list[str] = []
    depth = 0
    in_str = False
    j = 0
    n = len(stmt)
    while j < n:
        ch = stmt[j]
        if in_str:
            out.append(ch)
            if ch == "'":
                in_str = False
            j += 1
            continue
        if ch == "'":
            in_str = True
            out.append(ch)
            j += 1
            continue
        if ch == "(":
            depth += 1
            out.append(ch)
            j += 1
            continue
        if ch == ")":
            depth -= 1
            out.append(ch)
            j += 1
            continue
        if ch == "," and depth == 1:
            # Look ahead past whitespace: if the next token is ',' (empty slot)
            # or ')' (trailing comma at table close), drop this comma.
            k = j + 1
            while k < n and stmt[k] in " \t\r\n":
                k += 1
            if k < n and stmt[k] in ",)":
                j += 1  # drop the comma
                continue
        out.append(ch)
        j += 1
    return "".join(out)
