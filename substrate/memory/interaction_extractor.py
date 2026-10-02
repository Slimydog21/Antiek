"""Conservative first-person fact extraction from a completed thought-partner turn.

WHY RULES AND NOT A MODEL. The store never deletes. A fact written here is a
permanent, owner-scoped row that the owner has to notice and correct by hand,
and the reconciler treats a wrong restatement as a SUPERSEDE rather than a
retraction. A producer that guesses is therefore worse than no producer, which
is why extraction is a short allow-list of explicit first-person declaratives
about the speaker, anchored at clause start, and everything else is ignored.
Recall is low on purpose; precision is the bar. A second dispatch per turn to
have a model propose facts would add cost and a provider dependency to every
conversation and would not raise precision, so it is not attempted here.

WHAT IS READ. Only the owner's prompt. The model's reply is never a source of
facts about the owner, and a clause that addresses the assistant ("I prefer
that you answer briefly") is a steering instruction, not a stable fact, so
second-person objects are refused along with questions, deictic objects ("this",
"that") and anything longer than a short noun phrase.

WHAT IS WRITTEN. Every candidate goes through ``route_memory_update`` against
the exact-key timeline; only ADD, UPDATE and SUPERSEDE verdicts reach the
store, and a NOOP writes nothing. Provenance always carries
``{"source": "thought_partner", ...}`` plus the clause it came from and the
investigation id when the turn had one, which is what the ``MemoryItem``
validator requires and what the memory panel shows.

DARK BY DEFAULT. Nothing here runs unless ``INTERACTION_MEMORY_FLAG`` is set.
Turning it on means conversation content starts being distilled into a
durable store; that is a privacy posture decision for the operator, not for
this module.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import datetime

from pydantic import JsonValue

from runtime.db_lock import LockedConnection
from substrate.graph.ops import content_addressed_id

from . import store
from ._text import lexical_tokens
from .models import MemoryDecision, MemoryItem
from .router import load_memory_timeline, route_memory_update

INTERACTION_MEMORY_FLAG = "ANTIEK_ACCOUNT_MEMORY_WRITEBACK"
EXTRACTOR_VERSION = "first_person_rules_v1"
# The owner speaking about themselves. Owner scoping is the row's
# owner_user_id; the subject is what the memory panel renders.
OWNER_SUBJECT = "owner"

# Rules extract; the reconciler still decides. 0.8 says "a rule matched", not
# "a model was sure", and it is stamped on the edge for anyone ranking by it.
_RULE_CONFIDENCE = 0.8
_MAX_OBJECT_CHARS = 80
_MAX_OBJECT_WORDS = 10
_MAX_EXCERPT_CHARS = 200

# (pattern, predicate, negated). Anchored at clause start; first match wins.
_RULES: tuple[tuple[re.Pattern[str], str, bool], ...] = (
    (re.compile(r"^i (?:don't|do not|no longer) use (?P<object>.+)$", re.I), "uses", True),
    (re.compile(r"^i (?:don't|do not|no longer) prefer (?P<object>.+)$", re.I), "prefers", True),
    (re.compile(r"^i(?:'m| am) (?:no longer|not) (?:using|on) (?P<object>.+)$", re.I), "uses", True),
    (re.compile(r"^i prefer (?P<object>.+)$", re.I), "prefers", False),
    (re.compile(r"^i (?:always |usually |mostly )?use (?P<object>.+)$", re.I), "uses", False),
    (re.compile(r"^i work (?:at|for) (?P<object>.+)$", re.I), "works_at", False),
    (re.compile(r"^i(?:'m| am) based in (?P<object>.+)$", re.I), "lives_in", False),
    (re.compile(r"^i live in (?P<object>.+)$", re.I), "lives_in", False),
    (re.compile(r"^(?:my name is|call me) (?P<object>.+)$", re.I), "name", False),
)

_SENTENCE_SPLIT = re.compile(r"[.!?;\n]+")
# "..., and I live in Berlin" starts a new first-person clause.
_CLAUSE_SPLIT = re.compile(r",?\s+(?:and|but|so)\s+(?=i\b|i'm\b|i am\b|my\b)", re.I)
_LEADING_FILLER = re.compile(r"^(?:and|but|so|also|well|ok|okay|yes|no|actually|honestly)[,\s]+", re.I)
_EXPLANATION_CUT = re.compile(r"\s+(?:because|since)\s+.*$", re.I)
_TRAILING_FILLER = re.compile(
    r"\s+(?:anymore|any more|now|these days|nowadays|at the moment|though)$", re.I
)
_SECOND_PERSON = frozenset({"you", "your", "yours", "yourself"})
_DEICTIC_STARTS = frozenset({"this", "that", "these", "those", "it", "them", "here", "there"})


def interaction_memory_enabled() -> bool:
    """Whether the conversation write-back is switched on for this process."""
    return os.environ.get(INTERACTION_MEMORY_FLAG, "").strip().lower() in ("1", "true", "yes")


def extract_memory_candidates(
    *,
    owner_user_id: str,
    prompt: str,
    valid_from: datetime,
    investigation_id: str | None = None,
) -> list[MemoryItem]:
    """Propose candidate memories from one owner prompt. Pure; never writes.

    One candidate per ``(subject, predicate)`` key, the last mention winning,
    so a turn that changes its mind mid-sentence cannot hand the reconciler two
    candidates with the same ``valid_from`` for one key.
    """
    by_key: dict[tuple[str, str], MemoryItem] = {}
    for clause in _clauses(prompt):
        matched = _match(clause)
        if matched is None:
            continue
        predicate, obj = matched
        provenance: dict[str, JsonValue] = {
            "source": "thought_partner",
            "extractor": EXTRACTOR_VERSION,
            "excerpt": clause[:_MAX_EXCERPT_CHARS],
            "extraction_confidence": _RULE_CONFIDENCE,
        }
        if investigation_id is not None and investigation_id.strip():
            provenance["investigation_id"] = investigation_id.strip()
        identity = content_addressed_id(
            "memory-candidate",
            "\x1f".join([owner_user_id, OWNER_SUBJECT, predicate, obj, valid_from.isoformat()]),
        )
        by_key[(OWNER_SUBJECT, predicate)] = MemoryItem(
            memory_id=identity,
            edge_id=f"{identity}-edge",
            owner_user_id=owner_user_id,
            subject=OWNER_SUBJECT,
            predicate=predicate,
            object=obj,
            provenance=provenance,
            valid_from=valid_from,
            created_at=valid_from,
        )
    return list(by_key.values())


def record_interaction_memory(
    con: LockedConnection, candidates: Sequence[MemoryItem]
) -> list[MemoryDecision]:
    """Reconcile each candidate against its timeline and persist the non-NOOPs.

    Returns every decision, including NOOPs, so a caller can see what a turn
    did. Uses the store's own write chokepoint, which preserves and invalidates
    the prior version on SUPERSEDE and UPDATE; nothing here touches an edge
    directly.
    """
    decisions: list[MemoryDecision] = []
    for candidate in candidates:
        decision = route_memory_update(load_memory_timeline(con, candidate), candidate)
        if decision.action != "NOOP":
            store.write_memory_item(
                con,
                owner_user_id=candidate.owner_user_id,
                subject=candidate.subject,
                predicate=candidate.predicate,
                object=candidate.object,
                provenance=candidate.provenance,
                valid_from=candidate.valid_from,
            )
        decisions.append(decision)
    return decisions


def _clauses(prompt: str) -> list[str]:
    clauses: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(prompt):
        for raw in _CLAUSE_SPLIT.split(sentence):
            clause = " ".join(_LEADING_FILLER.sub("", raw.strip()).split())
            if clause:
                clauses.append(clause)
    return clauses


def _match(clause: str) -> tuple[str, str] | None:
    if "?" in clause:
        return None
    for pattern, predicate, negated in _RULES:
        found = pattern.match(clause)
        if found is None:
            continue
        obj = _normalize_object(found.group("object"))
        if obj is None:
            return None
        return predicate, f"not {obj}" if negated else obj
    return None


def _normalize_object(raw: str) -> str | None:
    text = _EXPLANATION_CUT.sub("", raw)
    text = _TRAILING_FILLER.sub("", text.strip(" \t,:-\"'")).strip()
    text = " ".join(text.split())
    tokens = lexical_tokens(text)
    if not tokens or len(text) > _MAX_OBJECT_CHARS or len(tokens) > _MAX_OBJECT_WORDS:
        return None
    if tokens[0] in _DEICTIC_STARTS or _SECOND_PERSON.intersection(tokens):
        return None
    return text


__all__ = [
    "EXTRACTOR_VERSION",
    "INTERACTION_MEMORY_FLAG",
    "OWNER_SUBJECT",
    "extract_memory_candidates",
    "interaction_memory_enabled",
    "record_interaction_memory",
]
