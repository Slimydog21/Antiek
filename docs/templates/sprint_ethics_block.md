# Sprint ethics block — template

Every Antiek sprint document that touches a §9.0-relevant surface must
include an ethics block in its header. Trigger surfaces per
`tools/lint/ethics_trigger_terms.txt`: publisher, consent, legal_gate,
advertiser, attribution, Bartz, Hachette, MDL, opt-in, opt-out,
autoresearch_output, ip_holder, payout.

If the sprint genuinely doesn't touch any of those, declare with a
one-line "ethics N/A" comment so reviewers can scan-confirm.

## Template

Copy this block into the sprint header:

```
## Ethics articulation

- **Technical risk:** _What can go wrong technically — corruption,
  attribution drift, gating bypass, etc. Be specific to this sprint._
- **Societal / user risk:** _Who absorbs the cost if this fails? What
  harm could surface for users, publishers, advertisers?_
- **Reputational risk:** _Cite the named legal exposure where it
  applies (Bartz/Hachette/AG MDL, publisher contracts). If none,
  describe the worst-case headline._
- **Operator decision:** _The single trade-off question this sprint
  hands to the operator. Frame as a yes/no or a-vs-b question — not
  a "consider various factors" hedge._
```

## What counts as "real" vs platitude

A real ethics block:

> **Technical risk:** Ingest-time gating bypass: if §9.0 checks fire
> AFTER chunk persistence, the chunk lands in DuckDB with the
> ip_holder_id but without consent, contaminating downstream retrieval.
>
> **Societal / user risk:** Publishers see their content in payout
> reports for sessions that never had their consent. Direct exposure
> to the Bartz/Hachette/AG MDL theory of harm.

A platitude block (do not ship):

> **Technical risk:** Could affect users in some way.
>
> **Societal / user risk:** Some risks possible.

The lint at `tools/lint/sprint_ethics_check.py` checks PRESENCE, not
quality. Quality is operator + peer review.

## Skip-if-N/A rule

For sprints that genuinely don't touch §9.0 surfaces:

```
## Ethics articulation

Ethics N/A — _one-sentence justification, e.g._ this sprint only
modifies a frontend tooltip; no substrate / publisher / advertiser
surface is touched.
```

The lint accepts this form as a valid block. Reviewers can confirm
in seconds.
