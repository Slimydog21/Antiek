# Prod-parity assertion

> SPR-07 · antiek-foundation-v2 Wave 1 (operational hygiene)

A ~10-line parity assertion that compares the commit SHA the **live**
service reports against the tip of `main`, and confirms the provider
registry came up non-empty. Earlier this month a stale-SPA drift shipped
to `api.antiek.ai` and went undetected for an extended period because
**nothing in the system asserted that the deployed commit equals main's
tip**. This is the cheap catch the pipeline lacked.

## What it asserts

`tools/prod_parity/check.py` fetches `GET <url>/health` and asserts
**both**:

1. `build_sha == expected_sha` — the SHA the running process was built
   from equals the expected ref (default `git rev-parse origin/main`).
   `build_sha` is exposed on `/health` (added in SPR-07; see
   `interfaces/research/api/app.py` `HealthResponse` + `_resolve_build_sha`).
2. `len(registered_providers) > 0` — the live provider registry is
   non-empty (catches the credential-gated silent-empty mode, where the
   secrets file is unpopulated so the API runs but can serve no AI).

```sh
python tools/prod_parity/check.py \
    --url https://api.antiek.ai \
    --expected-sha <the-just-deployed-sha>
```

Exit `0` only when **both** assertions hold; exit `1` on a parity
failure (naming which condition failed); exit `2` if it could not reach
`/health` or compute the expected SHA. `--expected-sha` defaults to
`git rev-parse origin/main` when omitted.

Where does `build_sha` come from? At process startup the API resolves it
(first hit wins): the `ANTIEK_BUILD_SHA` env the deploy stamps → a
`git rev-parse HEAD` of the local checkout (local dev) → the literal
`"unknown"`. The deploy is responsible for exporting `ANTIEK_BUILD_SHA`
so prod reports the true running SHA.

## Where it runs — two surfaces, honestly

| Surface | Where | Blocking? | Why |
| --- | --- | --- | --- |
| **Post-deploy** | `infrastructure/ansible/playbooks/deploy.yml` | **Yes — blocking** | At deploy time the deployed SHA is *known* (`git_pull.after`) and the URL is *live*. A non-zero exit fails the play, so a stale deploy reds immediately. |
| **Scheduled probe** | `.github/workflows/prod_parity.yml` | **No — informational** | It needs the live prod URL, which is only meaningful *after* a deploy — a PR has no deployed SHA to compare. The external endpoint can also be down for non-code reasons. So it is `continue-on-error: true` and never blocks a PR. |

### Why this cannot be a required PR-blocking CI gate

A PR-time job structurally **cannot see deploy drift**: at PR time there
is no deployed SHA to compare against (the code hasn't been deployed),
and the live URL it would need can be down for reasons unrelated to the
PR's code. Dressing such a probe up as a hard gate would be dishonest —
it would gate PRs on the health of an external endpoint they don't
change. The honest split is: **block where the SHA is known and the URL
is live (post-deploy); inform elsewhere (scheduled probe).** This follows
the standing informational-gate discipline in
`docs/decisions/ci-informational-gates.md`.

## Non-vacuity

A check that only ever exits `0` is worse than nothing — it manufactures
false confidence. `tests/test_prod_parity.py` proves the assertion can
fail: a simulated SHA mismatch reds, an empty provider registry reds, and
the in-parity case (matching SHA + providers present) greens — all
observed in the same test run.

## Steelmanned alternative — "the operator already eyeballs /health"

Manual checks are zero-maintenance and catch obvious outages — a fair
counter-position. Its specific failure is exactly the one this catches:
the stale-SPA drift survived because eyeballing `status: ok` does **not**
compare a SHA. The assertion wins only because it mechanizes the one
comparison a human reliably skips, not because manual checking is
worthless.

## Rejected alternative — "trust the deploy pipeline"

Empirically false here: the stale-SPA drift already shipped and went
undetected, so "the pipeline is fine, we don't need a parity check" is
contradicted by the record. Trust is not a control. A ~10-line assertion
comparing deployed-SHA to `main` is the cheap catch the pipeline lacked.

## Out of scope (this sprint)

Auto-deploy / ArgoCD / GitOps / k8s; fixing the *current* stale SPA (an
operator deploy action, not a code change); rollback / alerting
integrations / dashboards; and a SPA-side SHA field (the Cloudflare-Pages
SPA is a separate deploy target — a fair follow-up, not this sprint).
