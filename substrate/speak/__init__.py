"""Speak — the fourth Antiek workflow (Research · Read · Write · Speak).

Interview-as-acquisition / biography-as-a-service (the DeepBlu origin
idea, master-spec §11): invite stakeholders, interview them with a
compounding interviewer, corroborate across interviewees, author with
Write, publish with Read, and route the 70% ad-revenue slice to
contributors by what they actually contributed.

Speak is primarily an *acquisition* method feeding the shared
insight/question graph the other three workflows use. It reuses the
existing machinery (``roles/interviewer/``, ``orchestration/interview/``,
``acquisition/voice/``, ``roles/grounder/``, ``substrate/ad_inventory/
attribution.py``, ``substrate/ip_holders/``, ``substrate/books/``) and
owns only the net-new parts: the consent/rights gate, the multi-
interviewee project + invitation container, the compounding interviewer
context, cross-interviewee corroboration, the informant→payee economics,
the economics matrix, biography authoring orchestration, and publishing.

Binding invariants (see specs/speak/index.html):
  • Consent before substance, verification before publish.
  • Corroboration ≠ truth (multiply-attested is never "proven").
  • Public ⇒ algorithmic 70% split always (even private invitations).
  • Accrue now, disburse later (gated on G2/G3); slop doesn't earn.
  • Public ecosystem gated on G7; v1 is private projects + invite-link
    contributors (sources, not accounts).
  • Single-writer / db_lock for every mutation.

Submodules are imported directly (``from substrate.speak import
consent``); this package init keeps the schema + event surface handy.
"""

from __future__ import annotations

from .schema import (
    ANTIEK_SPEAK_SCHEMA_SQL,
    SPEAK_SCHEMA_TABLES,
    ensure_speak_schema,
)
from .events import (
    SPEAK_ACTION_TYPES,
    record_speak_event,
)
from .consent import ConsentScope, ScopedConsentRequired
from .publish_gate import PublishBlocked, PublishDecision

__all__ = [
    "ANTIEK_SPEAK_SCHEMA_SQL",
    "SPEAK_SCHEMA_TABLES",
    "ensure_speak_schema",
    "SPEAK_ACTION_TYPES",
    "record_speak_event",
    # SPR-01 consent & rights gate
    "ConsentScope",
    "ScopedConsentRequired",
    "PublishBlocked",
    "PublishDecision",
]
