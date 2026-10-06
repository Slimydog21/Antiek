# Retain the original operator at signup rollout

The existing-session followup accepts an already valid legacy `ANTIEK_SESSION` cookie for the explicitly configured original operator. It creates the stable account and sole private-owner alias under the existing account-store lock. It sends no new email, migrates no passkey or graph owner, and leaves ordinary-account credential/budget authority separate from the legacy private owner.

The middleware verifies HMAC, the session audience and time bounds before calling this path. The subject must be `__operator__`; the signed email must equal `ANTIEK_LEGACY_OPERATOR_EMAIL` and be in the current operator policy. Root must bind the actual original email, never the temporary dedicated inbox. Configuration or an allowlist entry alone does not establish the alias.

The current issuer's normal cookies have signed `exp - iat = 2592000` (30 days); `/auth/dev-login` emits seven days. Only that normal lifetime can enter this continuity path. Dev-login cookies, missing expiry, other lifetimes, expired/future/bad-signature/wrong-audience tokens and other subjects/emails refuse. This discriminator applies to the known issuer format; it does not guess provenance for unspecified historical formats or equate a session with fresh mailbox possession. Bearer credentials retain their existing service authority but cannot create the alias. Callback tokens cannot be substituted for session-cookie proof. Existing genuine email-proof signup remains unchanged.

Inside the exclusive atomic store, a matching already-established alias is returned unchanged. A new original account is created only if that email has no prior account and nobody has the legacy alias. An existing unaliased account or an alias held by another stored identity is a no-write conflict, requiring owner disposition. The implementation does not overwrite, upgrade or rebind it.

Root's normal rollout ordering:

1. Normally merge/deploy the parent signup candidate with signup disabled, retaining stable auth secret, real sender and actual passkey store.
2. Normally review/test/merge this separate followup, then configure the explicit original binding and durable account store. Exclude the temporary test inbox from the original binding and remove only its interim operator policy entry at the coordinated boundary.
3. Enable account mode under Root's configuration custody and verify continuity with the genuine already-held original cookie. A cookie must actually be available and pass current verification; no account row or signed proof may be fabricated to fill a resource gap.
4. Verify the persisted canonical subject/operator role, retained original private data, lookup-only legacy passkey continuity and distinct ordinary dedicated accounts. Verify visitor-IP attribution and real sender delivery before treating public signup as operational.

Private middleware controls use local test secrets, the real cookie codec and isolated stores. They cover actual old email-claim issuance, canonical subject/role, retained notebook body, ordinary-account denial, concurrent alias creation, dev-route cookies and all no-write refusal arms. They are not a production session, mailbox-deliverability or two-account journey receipt. Never print session values, claim codes or provider credentials in rollout transport.
