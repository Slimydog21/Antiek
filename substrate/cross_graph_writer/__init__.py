"""Cross-graph writer queue (§13.2 discovered-rule propagation).

Per master-spec §13.2:
*"Cross-graph writes flow through the shared substrate, never
directly. A skill patch derived in a user's private-facing notes
propagates to all users via the shared-substrate writer queue —
not as the patched private content, but as the **discovered rule**.
The user's specific chunks stay walled; the discovered fact
propagates as a shared skill patch with differential-privacy
guarantees per §13.3."*

This module is the writer queue with a DP shuffler in front. The
architectural invariant: a `DiscoveredRule` is the only thing that
crosses the personal-graph → shared-substrate boundary. The
original private chunks the rule was derived FROM do not.

Discipline:
- `propose_rule(...)` constructs a `DiscoveredRule` from a
  private-graph derivation. The rule's `evidence` field holds
  HASHES of supporting chunks, never the chunk content.
- `enqueue_for_propagation(...)` runs the DP shuffler over the rule's
  *strength* signal so the across-user aggregation is differentially
  private.
- `drain_queue(...)` writes the aggregated rule to the shared
  substrate via a caller-injected writer.

The substrate refuses to propagate a rule whose evidence section
contains any non-hash value — a static invariant that the structural
test enforces.
"""

from .queue import (
    CrossGraphWriterQueue,
    DiscoveredRule,
    RulePropagationEvent,
    RulePropagationEventKind,
    SharedSubstrateWriter,
    drain_queue,
    enqueue_for_propagation,
    propose_rule,
)

__all__ = [
    "CrossGraphWriterQueue",
    "DiscoveredRule",
    "RulePropagationEvent",
    "RulePropagationEventKind",
    "SharedSubstrateWriter",
    "drain_queue",
    "enqueue_for_propagation",
    "propose_rule",
]
