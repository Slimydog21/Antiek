# Provider consumer OAuth boundary

**Decision date:** 2026-08-12  
**Status:** Ratified for v1

Antiek v1 supports provider API keys for server-side inference. It does not import, copy, scrape, or directly use ChatGPT, Claude, or Grok consumer-subscription credentials.

## Why

- OpenAI documents API-key authentication for its API. Official Codex clients can manage ChatGPT login through Codex app-server, but that native-client contract is not a public grant for Antiek to reuse Codex credentials against OpenAI APIs.
- Anthropic explicitly states that third parties may not offer Claude.ai login or route requests through Free, Pro, Max, Team, or Enterprise subscription credentials. Third-party applications must use the Anthropic API or supported cloud providers.
- xAI documents API-key authentication for `api.x.ai`. Grok Build supports device login for its official client, but Antiek has no registered xAI OAuth client or evidence that Grok Build bearer tokens may be used by Antiek for API inference.
- T3Code does not implement these OAuth exchanges. It delegates authentication and provider traffic to official Codex and Claude processes. Copying token files or client registrations would discard the safety property that makes that design defensible.

## Required behavior

1. Server-hosted Antiek actions use owner-scoped, encrypted provider API keys and frozen payer/route authority.
2. Product copy says “Connect with API key” and explains that provider API billing is separate from consumer subscriptions.
3. Antiek never reads Codex `auth.json`, Claude credential files/Keychain items, browser cookies, or first-party CLI OAuth tokens.
4. A future local harness may invoke official Codex app-server or Claude Agent SDK/CLI while the official process retains credential custody. That work requires per-owner process and filesystem isolation; one shared operator login is not acceptable for friends.
5. True Antiek web OAuth remains disabled until the provider issues Antiek a registered client and documented third-party scopes, refresh/revoke semantics, inference entitlement, and written permission.

## Rejected alternatives

- Reusing first-party CLI client IDs: identity impersonation and an unverified inference contract.
- Asking users to paste token files: breaks secure storage, rotation, revocation, and owner isolation.
- Treating subscriptions as API credit: contradicts provider billing boundaries and produces ambiguous payer authority.
- Shipping a disabled OAuth button: promises a capability Antiek cannot responsibly activate.

## Revisit evidence

This decision may change only when a provider supplies all of: public or partner client registration, exact scopes, third-party inference permission, redirect/device contract, refresh rotation, revoke behavior, billing identity, and an opt-in live test tenant.

## Sources

- OpenAI API authentication: <https://platform.openai.com/docs/api-reference/authentication>
- OpenAI Codex app-server authentication: <https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md#auth-endpoints>
- Anthropic authentication and credential-use policy: <https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use>
- Anthropic API/subscription separation: <https://support.anthropic.com/en/articles/9876003-i-subscribe-to-a-paid-claude-ai-plan-why-do-i-have-to-pay-separately-for-api-usage-on-console>
- xAI API authentication: <https://docs.x.ai/developers/rest-api-reference/management/auth>
- xAI Grok Build authentication: <https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/02-authentication.md>
- T3Code: <https://github.com/pingdotgg/t3code> (audited at `52e5a75a872289040df85621d7a82ea9cba05182`)
- Executable sprint tree: [`../htmlspec/provider-auth-v1/index.html`](../htmlspec/provider-auth-v1/index.html)
