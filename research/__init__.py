"""Antiek research-provider abstraction.

This top-level package owns the **provider contract** for deep-research
engines (Exa Deep, Parallel, future providers). It is the single place
where the normalized ``ResearchResult`` shape and the ``ResearchProvider``
interface live. Adapters behind this interface (SPR-03 Exa, SPR-04
Parallel) translate their provider-specific payloads into the normalized
shape; nothing above the adapter boundary branches on a raw provider
payload.

Scope (SPR-01): types + interface + conformance harness + stub. Real
adapters, resilience wrapping, and the router are later sprints.
"""

from __future__ import annotations
