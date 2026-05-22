# Trust Center

**Last updated:** 2026-05-22 _(scaffold — see "What this is, what it isn't" below)_

Antiek is built on engineering-grade privacy. This page is the
public, operator-maintained accounting of *what is collected, why,
under what privacy budget, how long it is retained, and how to delete
it*. It is the consumer-facing companion to the master product
spec §13.3 + §13.7.

## What this is, what it isn't

This is the **scaffold** of the production Trust Center. The
operator and counsel (when engaged) edit the bracketed sections
to land the binding compliance language. The structure here matches
the §13.7 requirement set — privacy architecture description, ε
registry per surface, data retention policy, deletion SLA, incident
response process, privacy dashboard tutorial.

**This page is NOT compliance advice.** It is the operator's
public commitment to architectural separation, audited via the
substrate code at the references called out per section.

---

## 1. Privacy architecture (§13.2 + §13.3)

Antiek runs on a **two-graph architecture** with physical storage
separation:

- **Personal graph** — one per user. Contains every note, voice
  memo, highlighted region, and curated insight the user has
  produced. Partitioned at the application layer into
  **public-facing** and **private-facing** sections. The user
  controls which.
- **Collective graph** — one global aggregation, built from every
  user's **public-facing** notes plus operator-curated source
  corpus plus pre-onboarded IP-holder content (per §9.10).
  Quality-gated on entry (§13.9): verification + voice-style
  scoring + source-tier validation.
- **Shared substrate** — platform-owned. Skill versions, source-tier
  rules, rubric registry, attribution algorithms, model routing
  config. Single-writer at platform level.

The **private-facing partition of every personal graph is
physically separated** at the storage layer (per-user DuckDB files
with per-partition encryption keys), not merely tagged. A query
against a user's private-facing notes **cannot, by schema design,
write into the collective graph.**

Substrate audit trail of this commitment lives at:

- `substrate/multi_user/partition.py` — per-user file routing
- `substrate/cross_graph/` — controlled cross-graph write path
- `substrate/graph/search.py` — retrieval-time policy gating

---

## 2. The ε registry per surface (§13.3)

Antiek collects only three categories of telemetry, and only one
of them collects telemetry on individual users at all. The
**differential-privacy shuffler** routes the one user-level signal
so the aggregate is useful while no individual sample is identifying.

| Surface | Sensitivity | ε per day | Opt-in required | What is collected |
|---|---|---|---|---|
| `skill_invocation_frequency` | low | 2.0 | no | Counts of which skills are invoked, per skill. Aggregated daily. |
| `source_tier_preference` | medium | 1.0 | **yes** | Counts of which source tiers (Tier 1 / 2 / 3 / etc.) a user favors. Opt-in because tier preferences correlate with research domain. |
| `query_content_telemetry` | forbidden | 0 (no collection) | n/a | Query text itself. **Not collected.** §13.3 + §16.2 explicit REJECT. |

ε is the differential-privacy parameter — lower means stronger
privacy. The expert consensus band:

- ε < 1 — strong privacy
- ε ∈ [1, 10] — various degrees of better than nothing
- ε > 10 — not a meaningful privacy guarantee

Antiek's substrate **rejects** registration of any surface with
ε > 10 (`MAX_EPSILON = 10` in
`substrate/dp_shuffler/epsilon_registry.py`).

The substrate emits a `dp.routed` typed event every time a value
passes through randomized response, with the surface + recorded
ε. The aggregator publishes the running daily ε per surface so
this table is verifiable, not promised:

```bash
# View today's running ε per surface (operator runs this):
./.venv/bin/python -c "
from substrate.dp_shuffler.production import daily_epsilon_used
from substrate.event_log import trajectory_global
events = trajectory_global()  # all dp.routed events
for s in ['skill_invocation_frequency', 'source_tier_preference']:
    print(s, daily_epsilon_used(surface_name=s, events=events))
"
```

---

## 3. Data retention policy

| Data category | Default retention | Operator override |
|---|---|---|
| **Personal graph (private-facing)** | Indefinite while account active | User can purge at any time via Privacy Dashboard |
| **Personal graph (public-facing)** | Indefinite while account active OR until user retracts | Retraction available; existing collective-graph citations remain but content un-resolvable |
| **Investigation event logs** | 90 days for trajectory replay; aggregated metrics retained longer | Operator-configurable per-user |
| **DP-routed telemetry (dp.routed events)** | 30 days for aggregation, then deleted | n/a — already noise |
| **Magic-link tokens** | 15 min (token TTL) | Hard cap |
| **Session cookies** | 30 days | Hard cap; rotate `ANTIEK_AUTH_SECRET` to invalidate all |
| **Stripe Connect records** | Per Stripe retention (7+ years for tax) | Cannot be deleted by operator; Stripe is the regulatory party |

---

## 4. Deletion SLA — 30 days

Per §13.3 the Privacy Dashboard exposes a **"delete everything"**
button. When the user clicks it:

- Personal graph (both partitions): scheduled for deletion within 30
  days. The actual delete runs nightly; the SLA is the maximum
  delay.
- Public-facing notes the user previously promoted: hard-removed
  from the collective graph index; existing citations in syntheses
  return a 410 Gone with the original chunk text NOT restored.
- DP-routed aggregate buckets that included this user's noisy
  contributions: noise persists (it's debiased aggregate, not
  identifying), so we cannot "remove" the user from the aggregate.
  We document this honestly — the aggregate is a derivative
  artifact, not the user's data.
- Stripe Connect records: cannot be deleted by the operator. The
  user must request closure of the Connect account directly with
  Stripe under their own regulatory rights.

If the 30-day SLA is missed for any reason, the operator commits
to publish the breach on this page within 7 days.

---

## 5. Incident-response process

Defined process for any privacy incident (suspected leak,
unauthorized access, mis-routed DP signal):

1. **Triage within 24 hours.** Operator + (if engaged) counsel
   review the scope. The incident is logged at
   `docs/incidents/<date>-<slug>.md` regardless of severity.
2. **Disclose within 72 hours** to any user whose private graph
   was affected. Disclosure goes via the magic-link auth email
   channel.
3. **Public disclosure within 30 days** for any incident affecting
   >1 user OR involving collective-graph contamination. Listed on
   this page under "Past incidents."
4. **Postmortem within 90 days**, published to `docs/incidents/`
   with the substrate-level remediation committed before the
   postmortem closes.

### Past incidents

_None as of 2026-05-22._

---

## 6. Privacy Dashboard tutorial

The Privacy Dashboard lives at `https://antiek.ai/privacy` (visible
to authenticated users; not public).

### What it shows

- **Per-category telemetry switches** — toggle on/off for each
  surface (`skill_invocation_frequency`, `source_tier_preference`).
- **Today's running ε per surface** — the same number this Trust
  Center publishes daily, recomputed live from the user's own
  `dp.routed` event stream.
- **Public-facing notes** — list of notes the user has promoted to
  the collective graph, with retraction button per note.
- **Deletion request** — "Delete everything" button. Confirms with
  a 5-second hold. Schedules the 30-day SLA delete; returns a
  delete-request id the user can quote to operator support.
- **Export** — download the user's full personal graph as a
  newline-delimited JSON dump, suitable for re-import or
  archival.

### What it does NOT show

- Other users' graphs (impossible by storage separation).
- Aggregate telemetry from other users.
- The platform's internal substrate state (skill versions,
  attribution algorithms, etc.) — those live in the shared
  substrate, public via this Trust Center.

---

## 7. Compliance frameworks

Antiek's Phase 1 (consumer subscription) compliance posture per
§13.7:

| Framework | Status |
|---|---|
| GDPR Article 13/14 (EU users) | Architecturally compliant; operator + counsel review pending for the binding wording on this page. |
| CCPA notice + opt-out (California users) | Architecturally compliant; same review pending. |
| Engineering-grade privacy architecture (§13.3) | **Live.** Substrate-level enforcement audited in code. |
| SOC 2 Type II | **Deferred.** Not required for Phase 1 consumer subscriptions. Will be revisited if/when enterprise procurement opens. The substrate-controls work (encryption-at-rest, access logging, change management, vulnerability scanning, backup testing) ships regardless per §13.10. |

---

## 8. Contact + reporting

- **Privacy questions:** `ftn208@nyu.edu` (the operator email is
  the same address that gates the magic-link auth allowlist).
- **Suspected privacy incident:** same address. Mark the subject
  `[PRIVACY INCIDENT]` for triage routing.
- **DSR / GDPR / CCPA requests:** same address; operator commits
  to acknowledge within 7 days and resolve within 30 (per the SLA
  above).

---

## What's still in [BRACKETS]

The following sections need operator + counsel input before this
page can be considered binding compliance copy:

- **[OPERATOR + LAWYER: GDPR Article 13/14 wording]** — currently
  "architecturally compliant" placeholder; needs the precise
  privacy-notice language including lawful basis, data-subject
  rights enumeration, controller identity, processor list (Stripe,
  Resend, Cloudflare, Hetzner), international transfer mechanism.
- **[OPERATOR + LAWYER: CCPA notice wording]** — same shape for
  California residents; needs "Do not sell my personal information"
  surface even though Antiek does not sell.
- **[OPERATOR: legal entity name + jurisdiction]** — the operator
  is in Saudi Arabia; the platform's incorporating entity (US LLC
  / Saudi entity / dual) must be named explicitly.
- **[OPERATOR: data processor list]** — concrete vendors: Stripe
  (USA), Resend (USA), Cloudflare (USA), Hetzner (Germany),
  OpenAI / Anthropic / Hermes (USA / xAI). EU-USA Data Privacy
  Framework references where relevant.
- **[COUNSEL: incident-disclosure thresholds]** — the 24/72/30/90
  numbers above are operator-chosen defaults; counsel should
  confirm whether they meet GDPR Article 33 (72-hour notification)
  + CCPA + state-level requirements.

Once those are filled in, this page becomes the production Trust
Center publication.
