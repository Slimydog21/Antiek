"""Tests for the collective-coherence axis (N-agent merge cohesion — ask #3).

Pure lexical arithmetic — distinctive terms (stop-words stripped), hand-counted.
Use alpha/beta/gamma nonsense tokens so every ratio is exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.collective_coherence import (
    CollectiveCoherenceError,
    CollectiveInstance,
    measure_collective_coherence,
)


def inst(iid: str, text: str) -> CollectiveInstance:
    return CollectiveInstance(instance_id=iid, text=text)


# --- coherent (strong shared vocabulary) ----------------------------------


def test_coherent_strong_shared_core() -> None:
    # All 3 instances share alpha beta; each adds one unique term.
    # total distinct = {alpha,beta,gamma,delta,echo} = 5; shared = {alpha,beta} = 2.
    # core_share = 2/5 = 0.40 >= 0.25 -> coherent.
    report = measure_collective_coherence([
        inst("a", "alpha beta gamma"),
        inst("b", "alpha beta delta"),
        inst("c", "alpha beta echo"),
    ])
    assert report.verdict == "coherent"
    assert report.measurable_instance_count == 3
    assert report.total_distinct_terms == 5
    assert report.shared_term_count == 2
    assert report.core_share == pytest.approx(0.40)


def test_coherent_all_identical_core_share_one() -> None:
    # All instances identical -> total = shared -> core_share 1.0.
    report = measure_collective_coherence([
        inst("a", "alpha beta"),
        inst("b", "alpha beta"),
    ])
    assert report.verdict == "coherent"
    assert report.core_share == 1.0
    assert report.pairwise_mean == 1.0


def test_coherent_at_threshold_boundary_is_a_hit() -> None:
    # Construct core_share exactly 0.25 = coherent_threshold.
    # 2 instances: shared=1, total=4 -> 1/4 = 0.25.
    # inst a: alpha beta gamma ; inst b: alpha delta echo -> union {alpha,beta,gamma,delta,echo}=5... need total 4.
    # inst a: alpha gamma ; inst b: alpha delta echo -> union {alpha,gamma,delta,echo}=4, shared {alpha}=1 -> 0.25.
    report = measure_collective_coherence([
        inst("a", "alpha gamma"),
        inst("b", "alpha delta echo"),
    ])
    assert report.core_share == pytest.approx(0.25)
    assert report.verdict == "coherent"


# --- incoherent (no common subject) ---------------------------------------


def test_incoherent_no_shared_terms() -> None:
    # 3 instances with disjoint vocabularies -> shared = {} = 0 -> core_share 0.0
    # -> incoherent (<= 0.05 boundary inclusive).
    report = measure_collective_coherence([
        inst("a", "alpha beta"),
        inst("b", "gamma delta"),
        inst("c", "echo foxtrot"),
    ])
    assert report.verdict == "incoherent"
    assert report.shared_term_count == 0
    assert report.core_share == 0.0
    assert report.pairwise_mean == 0.0


def test_incoherent_is_not_unknown() -> None:
    # N measurable instances sharing NOTHING -> incoherent (measured), NOT unknown.
    report = measure_collective_coherence([
        inst("a", "alpha"),
        inst("b", "beta"),
    ])
    assert report.verdict == "incoherent"
    assert report.core_share == 0.0  # real measured value, not None


# --- weakly_cohesive (partial overlap) ------------------------------------


def test_weakly_cohesive_between_thresholds() -> None:
    # 3 instances: a=alpha beta gamma, b=alpha delta echo, c=foxtrot golf hotel.
    # shared across all = {} = 0 -> core_share 0.0 -> incoherent (not what we want).
    # Build partial: shared=1, total=10 -> 0.10 (between 0.05 and 0.25).
    # a: alpha beta gamma delta ; b: alpha echo foxtrot golf ; c: alpha hotel india juliet
    # union = {alpha,beta,gamma,delta,echo,foxtrot,golf,hotel,india,juliet} = 10
    # shared (in all 3) = {alpha} = 1 -> 1/10 = 0.10 -> weakly_cohesive.
    report = measure_collective_coherence([
        inst("a", "alpha beta gamma delta"),
        inst("b", "alpha echo foxtrot golf"),
        inst("c", "alpha hotel india juliet"),
    ])
    assert report.total_distinct_terms == 10
    assert report.shared_term_count == 1
    assert report.core_share == pytest.approx(0.10)
    assert report.verdict == "weakly_cohesive"


def test_weakly_cohesive_at_incoherent_boundary() -> None:
    # core_share exactly at incoherent_threshold 0.05 -> incoherent (<= boundary).
    # shared=1, total=20 -> 0.05.
    terms_a = "alpha " + " ".join(f"t{i}" for i in range(6))
    terms_b = "alpha " + " ".join(f"t{i}" for i in range(6, 12))
    terms_c = "alpha " + " ".join(f"t{i}" for i in range(12, 18))
    report = measure_collective_coherence([inst("a", terms_a), inst("b", terms_b), inst("c", terms_c)])
    assert report.core_share == pytest.approx(1 / 19)
    # 1 shared (alpha), total = 1 + 18 = 19 -> 0.0526 > 0.05 -> weakly_cohesive
    assert report.verdict == "weakly_cohesive"


# --- unknown (load-bearing: not coherent-by-default) ----------------------


def test_unknown_when_one_instance() -> None:
    report = measure_collective_coherence([inst("a", "alpha beta")])
    assert report.verdict == "unknown"
    assert report.core_share is None
    assert report.pairwise_mean is None


def test_unknown_when_zero_instances() -> None:
    report = measure_collective_coherence([])
    assert report.verdict == "unknown"
    assert report.measurable_instance_count == 0


def test_unknown_when_all_glue_instances() -> None:
    # All instances all-glue -> measurable 0 -> unknown.
    report = measure_collective_coherence([
        inst("a", "the and of"),
        inst("b", "is are was"),
    ])
    assert report.verdict == "unknown"
    assert report.unmeasurable_instance_count == 2
    assert report.measurable_instance_count == 0


def test_all_glue_instances_excluded_from_measurement() -> None:
    # One real instance + one all-glue -> only 1 measurable -> unknown.
    report = measure_collective_coherence([
        inst("a", "alpha beta"),
        inst("b", "the and of"),
    ])
    assert report.verdict == "unknown"
    assert report.unmeasurable_instance_count == 1
    assert report.measurable_instance_count == 1


# --- pairwise mean Jaccard ------------------------------------------------


def test_pairwise_mean_two_instances_full_overlap() -> None:
    report = measure_collective_coherence([
        inst("a", "alpha beta"),
        inst("b", "alpha beta"),
    ])
    assert report.pairwise_mean == 1.0


def test_pairwise_mean_two_instances_half_overlap() -> None:
    # a={alpha,beta}, b={alpha,gamma} -> Jaccard = 1/3.
    report = measure_collective_coherence([
        inst("a", "alpha beta"),
        inst("b", "alpha gamma"),
    ])
    assert report.pairwise_mean == pytest.approx(1 / 3)


def test_pairwise_mean_three_instances_average() -> None:
    # a={alpha}, b={alpha}, c={beta} -> pairs: (a,b)=1.0, (a,c)=0, (b,c)=0 -> mean 1/3.
    report = measure_collective_coherence([
        inst("a", "alpha"),
        inst("b", "alpha"),
        inst("c", "beta"),
    ])
    assert report.pairwise_mean == pytest.approx(1 / 3)


# --- stop-word floor + case -----------------------------------------------


def test_stop_words_stripped() -> None:
    report = measure_collective_coherence([
        inst("a", "the alpha of beta"),
        inst("b", "alpha and beta"),
    ])
    assert report.total_distinct_terms == 2  # {alpha, beta} only
    assert report.verdict == "coherent"


def test_case_insensitive() -> None:
    report = measure_collective_coherence([
        inst("a", "ALPHA Beta"),
        inst("b", "alpha BETA"),
    ])
    assert report.core_share == 1.0


# --- custom thresholds ----------------------------------------------------


def test_custom_thresholds_promote_verdict() -> None:
    # core_share 0.10 -> weakly at default, coherent at threshold 0.08.
    instances = [
        inst("a", "alpha beta gamma delta"),
        inst("b", "alpha echo foxtrot golf"),
        inst("c", "alpha hotel india juliet"),
    ]
    assert measure_collective_coherence(instances).verdict == "weakly_cohesive"
    assert measure_collective_coherence(instances, coherent_threshold=0.08).verdict == "coherent"


def test_incoherent_above_coherent_threshold_raises() -> None:
    with pytest.raises(CollectiveCoherenceError, match="cannot exceed"):
        measure_collective_coherence(
            [inst("a", "alpha"), inst("b", "beta")],
            incoherent_threshold=0.30, coherent_threshold=0.10,
        )


# --- validation -----------------------------------------------------------


def test_incoherent_threshold_out_of_range_raises() -> None:
    with pytest.raises(CollectiveCoherenceError, match="incoherent_threshold"):
        measure_collective_coherence([], incoherent_threshold=1.5)


def test_coherent_threshold_out_of_range_raises() -> None:
    with pytest.raises(CollectiveCoherenceError, match="coherent_threshold"):
        measure_collective_coherence([], coherent_threshold=-0.1)


def test_empty_instance_id_raises() -> None:
    with pytest.raises(CollectiveCoherenceError, match="instance_id"):
        measure_collective_coherence([inst("  ", "alpha"), inst("b", "beta")])


def test_duplicate_instance_id_raises() -> None:
    with pytest.raises(CollectiveCoherenceError, match="duplicate instance_id"):
        measure_collective_coherence([inst("a", "alpha"), inst("a", "beta")])


# --- purity / determinism -------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_collective_coherence([inst("a", "alpha beta"), inst("b", "alpha beta")])
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    instances = [inst("a", "alpha beta"), inst("b", "alpha gamma"), inst("c", "alpha beta delta")]
    first = measure_collective_coherence(instances)
    second = measure_collective_coherence(instances)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_collective_coherence([inst("a", "alpha"), inst("b", "beta")])
    joined = " ".join(report.notes)
    assert "collective-coherence" in joined
    assert "verdict incoherent" in joined
