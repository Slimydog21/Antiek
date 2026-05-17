# middleware/backtest/

Cohort evaluation against outcomes.

## What it does

For investigations that produced syntheses under specific parameter +
skill versions, joins the syntheses against realized outcomes (where
known) and produces:

- Per-skill-version quality metric (constraint-pass rate, archive
  rate, outcome correlation).
- Per-parameter-version quality metric.
- Per-routing-configuration quality metric.

This is the **skill compounding metric** in the hardware-decision
criteria (architecture_notes §6).

## Caveat

Outcome data is sparse and arrives slowly. Backtest signal strengthens
over months, not weeks. The build's job is to capture the data
faithfully so the eventual decision is data-driven.
