# Midnight Oil spend-consent wiring contract

This module is a pure money-authority substrate. It is intentionally not wired
while PR #709 owns Midnight Oil route/UI convergence.

The route owner must derive `operator_id` only from `request.state.user_id`,
snapshot the persisted job into `JobConsentConfig`, allocate the canonical paid
operation ID, convert the approved ceiling to integer cents, issue a short-lived receipt, and require an exact successful
claim immediately before changing approval state or entering a paid live step.
Caller-supplied owner IDs are never authority.

Configuration drift, a ceiling change, expiry, unknown key, wrong operator/job,
or a conflicting replay must fail before provider dispatch. Exact replay may
return the prior claim as idempotent only for the same signed `operation_id`; it
may resume that operation but may not authorize a second provider dispatch.

Key material comes from the deployment secret store. Keep the previous verify
key during rotation until every receipt it signed has expired. Never persist or
log receipt tokens or HMAC keys.
