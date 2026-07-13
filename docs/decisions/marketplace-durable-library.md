# Marketplace durable library composition

**Status:** implemented offline; no payment rail or production deployment
**Date:** 2026-07-13

## Decision

Add a standard-library SQLite implementation of the existing `HostStore`
protocol and make the API store an explicit app-scoped dependency. Marketplace
and generic hosted-document routes must resolve the same store from the current
request. `create_app` may receive a validated store object; if omitted, the
existing in-memory default remains for networkless local and test operation.

SQLite is selected over the existing file-per-record store because it provides
transactional writes, unique membership constraints, and safe concurrent
connections without a new package. The application factory does not infer a
database path from environment variables. A production launcher must construct
and pass the store explicitly, so a bad durable configuration cannot silently
fall back to process memory.

## Scope boundary

This decision persists extracted HTML-native documents, account memberships,
projection receipts, and opaque manual purchase references. It does not add
payment processing, card storage, retailer download automation, DRM handling,
or a right to redistribute purchased content.

## Reconsider if

Move to a service database only when multi-host deployment requires shared
storage. Preserve the same `HostStore` boundary and restart/owner-isolation
acceptance suite.
