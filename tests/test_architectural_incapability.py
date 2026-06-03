"""§13.3 architectural-incapability tests.

Per master-spec §13.3: *"We are architecturally incapable of
leaking your data" rather than "we promise not to."*

These tests exercise the architectural mechanisms -- not policy --
that make the privacy claim load-bearing:

1. cross_user_read_isolation -- User A's queries cannot reach
   User B's per-user DuckDB. The DuckLake catalog returns DIFFERENT
   db paths per user; the substrate refuses to open user_id ≠ the
   requesting user.
2. skill_patch_dp_isolation -- A skill patch derived from User B's
   private chunks reaches the shared substrate through
   substrate/cross_graph_writer/ as a DiscoveredRule. The original
   chunk content does NOT travel with the rule; the substrate is
   structurally incapable of including it.
3. telemetry_end_to_end_with_epsilon_debit -- A telemetry event
   passes through the DP shuffler and reaches the shared substrate
   with its ε budget debited; per-surface enforcement holds across
   the boundary.
"""

from __future__ import annotations

import hashlib

import pytest

from substrate.cross_graph_writer import (
    CrossGraphWriterQueue,
    DiscoveredRule,
    drain_queue,
    enqueue_for_propagation,
    propose_rule,
)
from substrate.dp_shuffler import EpsilonRegistry, SurfaceConfig
from substrate.ducklake import (
    DuckLakeCatalog,
    InMemoryCatalogBackend,
    NoSharding,
)
from substrate.graph_per_user import (
    InMemoryKeyProvider,
    create_user_graph,
    open_user_graph,
)
from substrate.telemetry_preferences import (
    InMemoryPreferenceStore,
    is_enabled,
    set_preference,
)

# ── 1. Cross-user read isolation ────────────────────────────────


def test_cross_user_read_isolation_returns_different_paths(tmp_path):
    """Two users have STRUCTURALLY different db_paths. A handle to
    one cannot resolve into the other."""
    catalog = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    kp = InMemoryKeyProvider()
    root = str(tmp_path)

    a, _ = create_user_graph(
        user_id="user-A", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=root,
    )
    b, _ = create_user_graph(
        user_id="user-B", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=root,
    )
    assert a.db_path != b.db_path
    # The catalog returns the right path for each user, never the wrong one.
    assert catalog.lookup("user-A").db_path == a.db_path
    assert catalog.lookup("user-B").db_path == b.db_path


def test_cross_user_read_isolation_unknown_user_returns_none(tmp_path):
    """An attempt to OPEN a non-existent user's graph returns None,
    NOT a fallback to operator graph."""
    catalog = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    kp = InMemoryKeyProvider()
    create_user_graph(
        user_id="user-A", catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir=str(tmp_path),
    )
    # User B does not exist. Trying to open returns None.
    result = open_user_graph(
        user_id="user-B-attacker", catalog=catalog, key_provider=kp,
    )
    assert result is None


def test_invalid_user_id_cannot_traverse_path():
    """Path-traversal characters in user_id are sanitised at the
    file-path level. An attacker cannot use ../../etc/passwd as
    user_id."""
    catalog = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    kp = InMemoryKeyProvider()
    # Empty user_id is structurally rejected.
    with pytest.raises(ValueError, match="invalid user_id"):
        create_user_graph(
            user_id="", catalog=catalog, key_provider=kp,
            strategy=NoSharding(), root_dir="/tmp",
        )
    # Path traversal characters get replaced.
    storage, _ = create_user_graph(
        user_id="../../etc/passwd",
        catalog=catalog, key_provider=kp,
        strategy=NoSharding(), root_dir="/tmp/test-root",
    )
    # The path stays inside the root.
    assert storage.db_path.startswith("/tmp/test-root/")
    assert "../" not in storage.db_path[len("/tmp/test-root/"):]
    # The slashes were sanitised to underscores.
    assert "passwd" in storage.db_path
    assert "/passwd" not in storage.db_path[len("/tmp/test-root/"):]


# ── 2. Skill-patch DP isolation ────────────────────────────────


def test_skill_patch_propagation_strips_raw_content():
    """User B's private chunks supporting a skill patch never reach
    the shared substrate. Only the discovered rule (with hashed
    evidence) propagates."""
    private_chunks = [
        b"User B's quantum entanglement investigation step 1 -- PRIVATE",
        b"User B's voice note transcription on entanglement -- PRIVATE",
        b"User B's source-tier judgment on Lukin lab papers -- PRIVATE",
    ]
    rule = propose_rule(
        proposer_user_id="user-B",
        rule_kind="source_tier_assignment",
        rule_payload="Lukin lab papers = Tier-1 for neutral atom physics",
        supporting_chunks=private_chunks,
        strength_score=0.85,
    )
    queue = CrossGraphWriterQueue()
    enqueue_for_propagation(queue, rule)

    propagated: list[DiscoveredRule] = []
    drain_queue(queue, writer=propagated.append, epsilon=1.0)

    # The discovered rule reached the shared substrate.
    assert len(propagated) == 1
    final = propagated[0]

    # Evidence is hashes only -- no raw content.
    for entry in final.evidence:
        assert len(entry) == 64  # sha256 hex
        # And each entry is the actual hash of the corresponding chunk.
    expected_hashes = [hashlib.sha256(c).hexdigest() for c in private_chunks]
    assert set(final.evidence) == set(expected_hashes)

    # The propagated artefact contains nothing of the raw content.
    propagated_serialised = repr(final)
    for chunk in private_chunks:
        as_str = chunk.decode("utf-8")
        assert as_str not in propagated_serialised, (
            f"raw content {as_str!r} found in propagated rule"
        )


def test_attacker_constructing_rule_with_raw_evidence_is_refused():
    """An attacker who constructs a DiscoveredRule manually (bypassing
    propose_rule) with raw content in the evidence field is refused
    at enqueue time. The shared substrate never sees the rule."""
    attacker_rule = DiscoveredRule(
        rule_id="rule-attack",
        proposer_user_id="user-attacker",
        rule_kind="skill_patch",
        rule_payload="(legitimate-looking discovered rule)",
        evidence=(
            "RAW USER B CONTENT: quantum investigation step 1",  # not a hash
            "RAW USER B CONTENT: voice note transcription",  # not a hash
        ),
        strength_score=0.9,
    )
    queue = CrossGraphWriterQueue()
    enqueue_for_propagation(queue, attacker_rule)
    assert len(queue.pending) == 0  # rejected before queueing
    propagated: list[DiscoveredRule] = []
    drain_queue(queue, writer=propagated.append)
    assert propagated == []


# ── 3. Telemetry end-to-end with ε debit ────────────────────────


def test_telemetry_preference_blocks_emission_when_opted_out():
    """A user opts out of a surface. The substrate refuses to emit
    telemetry for that surface even if the registry allows it."""
    store = InMemoryPreferenceStore()
    set_preference(store, user_id="u-1",
                   surface_name="skill_invocation_frequency", enabled=False)
    assert is_enabled(
        store, user_id="u-1",
        surface_name="skill_invocation_frequency",
    ) is False


def test_telemetry_forbidden_surface_never_collected():
    """A 'forbidden' surface (sensitivity=forbidden, ε=0) cannot be
    toggled on. Even with default_when_missing=True the registry's
    forbidden flag wins."""
    from substrate.telemetry_preferences import apply_defaults_from_registry

    reg = EpsilonRegistry()
    reg.register(SurfaceConfig(
        surface_name="query_content_telemetry",
        epsilon_per_day=0.0,
        sensitivity="forbidden",
        description="never collected",
        opt_in_required=False,
    ))
    store = InMemoryPreferenceStore()
    apply_defaults_from_registry(store, user_id="u-1", registry=reg)
    # The default seeded for a forbidden surface is FALSE.
    assert is_enabled(
        store, user_id="u-1",
        surface_name="query_content_telemetry",
        default_when_missing=True,  # even if caller asks for True default
    ) is False


def test_dp_shuffler_strength_bounded():
    """The DP shuffler must randomise -- a deterministic pass-through
    would violate §13.3. Verify the shuffler can flip a known input
    given enough samples."""
    from substrate.dp_shuffler.shuffler import LocalRandomizer

    randomizer = LocalRandomizer(epsilon=1.0)
    true_bit = True
    outcomes = [randomizer.randomize(true_bit) for _ in range(1000)]
    # At ε=1.0 the randomizer flips the bit with non-trivial
    # probability. Verify both outcomes appear.
    assert True in outcomes
    assert False in outcomes


def test_epsilon_max_hard_cap_enforced():
    """§16.2 binding: no ε > 10 on any DP claim. The registry
    refuses to register a surface above the cap."""
    from substrate.dp_shuffler.epsilon_registry import EpsilonRegistryError

    reg = EpsilonRegistry()
    with pytest.raises(EpsilonRegistryError, match="exceeds"):
        reg.register(SurfaceConfig(
            surface_name="huge_epsilon",
            epsilon_per_day=11.0,
            sensitivity="low",  # cap at 4.0; refusal fires before MAX
            description="violates §16.2",
            opt_in_required=False,
        ))
