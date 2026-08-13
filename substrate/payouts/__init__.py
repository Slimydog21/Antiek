"""Internal per-paper author accrual modules (SPR-06).

A NEW package that COMPOSES the existing per-second ad-economics primitives
(``apportion_cents`` rounding, the ``frame_attention_accrual`` persistence
pattern, the ``UNATTRIBUTED_RIGHTS_BUCKET`` held-bucket semantics, the
``arxiv_tiers`` / ``ad_eligibility`` T1 gate) into an INTERNAL accounting layer
keyed by ``(arxiv_id, author_position)``.

Scope wall: this package ACCRUES OWED amounts only. It writes NO escrow, moves
NO money, contacts NO author, and disburses NOTHING — it is the substrate SPR-07
(claim) and SPR-08 (payout) build on. See ``ledger.py`` for the full scope
contract.

This package intentionally has no public barrel API. Production consumers
import the specific ``ledger``, ``split``, or ``contact_guard`` module they
use, which keeps the reachable accounting seams explicit.
"""
