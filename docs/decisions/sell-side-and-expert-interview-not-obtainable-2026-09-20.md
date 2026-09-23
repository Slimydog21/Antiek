# Sell-side research and expert-interview data are NOT OBTAINABLE as BYOT vendors

**Date:** 2026-09-20 (recorded 2026-09-22)  
**Lane:** BYOT, bring your own TOOLS (`runtime/connectors/*`, `/settings/tools`); not the bring-your-own-TOKENS lane under `substrate/byot_usage/`.  
**Status:** closed question. This is a finding, not a gap, and not an operator gate. Do not reopen either category as a "gap" in a future recon.

The operator's data-vendor ask named three categories: sell-side research, expert interviews, and survey data. Two of the three cannot be connected by any user of Antiek at any price an individual can pay, and none of the vendors in those two categories permit passing their content on to a builder's own users. The third, survey data, is genuinely obtainable and is handled by SPR-04 tasks 8 and 9 (Typeform first, Qualtrics if Typeform proves the shape).

## Sell-side research: NOT OBTAINABLE

| Vendor | Access terms | Why a BYOT connector cannot exist |
|---|---|---|
| Bloomberg Terminal / B-PIPE | 24,000 to 27,000 USD per seat per year; the API requires an existing terminal subscription bound to the seat | No self-serve key. A user cannot paste a credential Antiek could spend on their behalf. |
| FactSet | Developer portal gives docs and limited test access; full data needs an active contract with no published list price | No individual tier. The portal credential does not reach production data. |
| S&P Capital IQ | One-year minimum starting around 25,000 USD per team | Enterprise-only, team-licensed; no per-user API credential. |

The redistribution constraint is decisive on its own. None of the three licenses permit the subscriber to redistribute research to a third party's users, so even a user who holds a seat could not lawfully have Antiek serve that research to anyone else. There is no rights state in `substrate/chunk_provenance` under which a sell-side document could be SERVABLE.

**Antiek-native substitute.** The user uploads the research they already hold lawful access to. It is ingested at `personal_reading` (`PERSONAL_READING_CONTENT_CLASS`) with the user as the fetch agent and never the platform, which is the §9.0 posture. That path already exists and needs no vendor code.

## Expert-interview data: NOT OBTAINABLE

The accessible tier consolidated away. AlphaSense acquired Tegus for 930 million USD in 2024; the surviving API and MCP surfaces (Tegus-AlphaSense, Third Bridge, Guidepoint) are subscription-only to institutions. GLG and AlphaSights have no individual API at all. There is no vendor an individual can register with, so there is nothing for a paste-key or OAuth connector to hold.

**Antiek-native substitute.** Two paths, both already on main:

1. Transcripts the user already holds lawful access to are uploaded and ingested at `personal_reading` with the user as the fetch agent, exactly as for sell-side research above.
2. Interviews the user conducts themselves route at the existing `acquisition/interview` lane (DeepBlu lineage: capture, transcription, diarization, `primary_interview` source tier, consent and citation-rights attribution). The expert-interview story points at that lane, never at a vendor.

## Survey data: obtainable

Qualtrics and Typeform both ship OAuth APIs an individual can register for. This is the one category in the ask where the honest answer is yes. It is operator-gated only in the ordinary sense that someone must register the OAuth application; see SPR-04 tasks 8 and 9 and their operator gates.

## What this closes

- `docs/specs/byot-tools-vendors-2026-08-12.md` §2 Tier 2 and §5 already reached this verdict in softer words. This record makes it binding: sell-side research and expert-interview vendors are NOT OBTAINABLE and are not to be re-listed as candidates.
- The same spec's §1 was stale (it named only X and YouTube, and §2 proposed RSS and Substack as if unbuilt). Corrected in the same change as this record: the shipped catalog is `youtube`, `polygon`, `fmp`, `edgar`, `x` per `runtime/connectors/registry.py`, and `acquisition/rss` plus `acquisition/substack` exist as server-side lanes that are not user-connectable, which is a different claim from unbuilt.
