# Original stored-passkey continuity

A successful stored-key WebAuthn authentication can establish the original
operator's canonical account and sole `__operator__` storage alias once. This
is separate from the existing verified-cookie compatibility path in #3732.
Neither path changes documents, passkeys, provider keys or budgets.

The passkey route first consumes and verifies the actual ceremony against the
stored public key, including challenge, signature, RP ID, origin, presence,
user verification and counter. Only its returned stored legacy credential can
reach alias admission. The deployment must explicitly set
`ANTIEK_LEGACY_OPERATOR_EMAIL` to the original operator and retain that same
email in current operator policy. A credential's stored email, when present,
must normalize to that exact email. The interim test mailbox must never be the
original binding.

Atomic locked admission returns an existing matching alias unchanged or
creates one canonical subject with that alias. An existing unaliased account,
another assigned alias, unreadable store or failed persistence refuses login;
it never overwrites, rebinds or falls back to a shared operator cookie. This
works before public signup is enabled. A deployment without an explicit
original binding retains the old closed-mode login policy but cannot create
an alias through this path; account mode requires a persisted account.

Normal account credentials keep their existing subject/email lookup. Public
accounts receive no operator role, private legacy owner, provider credential
or paid budget from successful passkey authentication. Credential records and
public keys remain in their existing store; no migration is performed.

The new controls use real ES256 assertions from an in-memory test key, a
private stored public credential and the unmodified WebAuthn verifier. They
prove source behavior in isolated stores, not the availability of an original
production credential or a completed original-owner browser journey. Root
owns normal merge/deployment, genuine continuity verification and public
signup enablement. No personal mail request, account seeding by configuration
or direct production credential read is needed or permitted by this change.
