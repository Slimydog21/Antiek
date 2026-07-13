"""Twin-staleness — is the twin still reflecting the CURRENT source, or stale?

Operator vision (ask #4): *"every information asset created on my platform has a
twin document with all the insights and questions proposed by that information
document written by an LLM as LLMs are perfect note takers."* The twin is the
recursive note-taker — an LLM-generated distilled companion to every asset. Its
VALUE depends on it reflecting the CURRENT source. A twin generated against an
old version of the source, left un-refreshed after the source was rewritten,
becomes a STALE note-taker: its insights and questions describe content the
operator no longer sees. Staleness is the silent integrity rot of the twin layer.

**Genuinely distinct (temporal vs content correspondence):**

* ``twin_fidelity`` (#1954): does the twin HALLUCINATE? (content in the twin NOT
  in the source — fabrication, measured at a point in time)
* ``twin_coverage`` (#1964): did the twin CAPTURE the source? (source content
  missing from the twin — omission, measured at a point in time)
* ``twin_question_support`` (#1959): are the twin's questions grounded?
* THIS (``twin_staleness``): is the twin OUT OF DATE with its source? (TEMPORAL
  drift — the source changed AFTER the twin was generated)

Fidelity/coverage measure CONTENT correspondence at a single instant (is the twin
an accurate reflection of the source?). Staleness measures TEMPORAL
correspondence across time (is the twin still reflecting the CURRENT version, or
the version it was made against?). A twin can be 100% faithful and fully covering
(at generation time) yet completely stale after the source was heavily rewritten
— fidelity and coverage would still pass against the OLD snapshot they were
measured against, but the twin no longer describes what the operator reads now.
That temporal gap — *how far behind the current source is the twin?* — is this
axis.

**The measurement (hard to vary):**

Given the source's monotonic version counter and the version the twin was
generated against:

* ``source_version`` = the source's current version (>= 1, monotonic)
* ``twin_generated_at_version`` = the source version the twin was generated
  against (>= 1, must be <= ``source_version``)
* ``version_offset = source_version - twin_generated_at_version`` (>= 0; 0 = the
  twin is current, positive = behind by that many versions)
* ``staleness_ratio = version_offset / source_version`` in ``[0, 1)`` (0 =
  current; normalised so it is comparable across sources at different ages — a
  2-version offset on a 4-version source is further behind than on a 100-version
  source)

**Verdict:**

* ``unknown`` — version data missing (``source_version`` or
  ``twin_generated_at_version`` is None / < 1 — defer, never fabricate staleness)
* ``current`` — ``version_offset == 0`` (the twin was generated against the
  current source version)
* ``stale`` — ``version_offset >= 1`` (the source has advanced since the twin was
  generated — the twin is behind)
* ``stale_critical`` — ``version_offset >= regenerate_threshold`` (default 5 — so
  far behind that regeneration is the honest recommendation; boundary inclusive)

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates a verdict when version data is missing — a twin
  with no recorded generation version cannot be assessed for staleness (defer
  rather than assert current/stale).
* ``twin_generated_at_version > source_version`` is a RECORDING ERROR (a twin
  cannot be generated against a future version) — it raises, never silently
  clamped.
* ``version_offset == 0`` (current) is a REAL measured verdict, not the default
  — a twin generated against the current version is honestly current; it is not
  "unknown just in case." The twin layer earns ``current`` by being freshly
  generated.
* ``staleness_ratio`` is ``None`` when ``source_version`` is unavailable (the
  denominator — defer, never ``0.0``).
* the staleness EXISTENCE (version moved) is honest regardless of whether the
  version change altered content materially: a version increment with identical
  content still makes the twin ``stale`` by offset (we do not fabricate ``current``
  by guessing the change was trivial — the version moved, the twin is behind).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** Defines its own ``TwinVersionInput`` shape
(the route layer adapts 1:1 from the twin-generation records, which are NOT on
frozen main). Pure-Python: stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_REGENERATE_THRESHOLD: int = 5


@dataclass(frozen=True)
class TwinVersionInput:
    """The source's current version + the version the twin was generated against.

    Pure input. Both are monotonic version counters (>= 1) from the source's
    edit history; ``twin_generated_at_version`` must be <= ``source_version``.
    """

    source_version: int | None
    twin_generated_at_version: int | None


@dataclass(frozen=True)
class TwinStalenessReport:
    """The twin-staleness verdict. Advisory, pure."""

    source_version: int | None
    twin_generated_at_version: int | None
    version_offset: int | None  # source - twin-generated; None when data missing
    staleness_ratio: float | None  # offset/source; None when source unavailable
    regenerate_threshold: int
    verdict: str  # unknown | current | stale | stale_critical
    notes: tuple[str, ...]
    authority: str = "advisory"


class TwinStalenessError(ValueError):
    """A twin-staleness input violates a load-bearing invariant."""


def measure_twin_staleness(
    versions: TwinVersionInput,
    *,
    regenerate_threshold: int = _DEFAULT_REGENERATE_THRESHOLD,
) -> TwinStalenessReport:
    """Measure whether the twin is stale relative to its current source version.

    ``versions`` carries the source's current version + the version the twin was
    generated against.
    ``regenerate_threshold`` is the version-offset at which staleness is critical
    (default 5 — regeneration recommended).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if regenerate_threshold < 1:
        raise TwinStalenessError(
            f"regenerate_threshold must be >= 1, got {regenerate_threshold!r}"
        )

    source_version = versions.source_version
    twin_generated_at = versions.twin_generated_at_version

    # Validate present versions are positive (a version counter is >= 1).
    if source_version is not None and source_version < 1:
        raise TwinStalenessError(
            f"source_version must be >= 1, got {source_version!r}"
        )
    if twin_generated_at is not None and twin_generated_at < 1:
        raise TwinStalenessError(
            f"twin_generated_at_version must be >= 1, got {twin_generated_at!r}"
        )

    # A twin generated against a FUTURE version is a recording error.
    if (
        source_version is not None
        and twin_generated_at is not None
        and twin_generated_at > source_version
    ):
        raise TwinStalenessError(
            f"twin_generated_at_version {twin_generated_at} cannot exceed "
            f"source_version {source_version} (a twin cannot be generated "
            "against a future version)"
        )

    # Missing version data -> unknown (defer, never fabricate staleness).
    if source_version is None or twin_generated_at is None:
        return _report(
            source_version,
            twin_generated_at,
            None,
            None,
            regenerate_threshold,
            "unknown",
            [
                "twin-staleness measures TEMPORAL drift — is the twin still "
                "reflecting the CURRENT source version, or the version it was made "
                "against? Distinct from twin_fidelity #1954 (hallucination) and "
                "twin_coverage #1964 (omission), which measure content "
                "correspondence at a single instant — a twin can be 100% faithful "
                "yet completely stale after the source was rewritten",
                "verdict unknown — version data is missing (source_version or "
                "twin_generated_at_version is None); version_offset and "
                "staleness_ratio are None (defer, never fabricated)",
            ],
        )

    version_offset = source_version - twin_generated_at

    # staleness_ratio: offset normalized by source age (None only if source==0,
    # but source>=1 is validated above, so always computable here).
    staleness_ratio = version_offset / source_version

    if version_offset == 0:
        verdict = "current"
    elif version_offset >= regenerate_threshold:
        verdict = "stale_critical"
    else:
        verdict = "stale"

    notes: list[str] = [
        "twin-staleness measures TEMPORAL drift — is the twin still reflecting "
        "the CURRENT source version, or stale? version_offset = source_version - "
        "twin_generated_at_version (0 = current, positive = behind); "
        "staleness_ratio = offset/source_version normalised in [0,1) for "
        "comparability across sources at different ages",
        "verdict: current (offset 0 — twin generated against the current version; "
        "a REAL measured verdict, not a default), stale (offset >= 1 — source "
        "advanced), stale_critical (offset >= regenerate_threshold — regenerate)",
        "distinct from twin_fidelity #1954 (content in twin NOT in source) and "
        "twin_coverage #1964 (source content missing from twin) — those measure "
        "content correspondence at a point in time; THIS measures temporal "
        "correspondence across time (the source changed AFTER the twin was made)",
        "the staleness EXISTENCE is honest regardless of content impact: a version "
        "increment with identical content still makes the twin stale by offset (we "
        "do not fabricate current by guessing the change was trivial); "
        "twin_generated_at > source_version is a recording error (raises)",
    ]
    notes.append(
        f"verdict {verdict}: source_version {source_version}, twin generated at "
        f"version {twin_generated_at}, version_offset {version_offset}, "
        f"staleness_ratio {staleness_ratio:.0%}, regenerate_threshold "
        f"{regenerate_threshold}"
    )

    return _report(
        source_version,
        twin_generated_at,
        version_offset,
        staleness_ratio,
        regenerate_threshold,
        verdict,
        notes,
    )


def _report(
    source_version: int | None,
    twin_generated_at_version: int | None,
    version_offset: int | None,
    staleness_ratio: float | None,
    regenerate_threshold: int,
    verdict: str,
    notes: list[str],
) -> TwinStalenessReport:
    return TwinStalenessReport(
        source_version=source_version,
        twin_generated_at_version=twin_generated_at_version,
        version_offset=version_offset,
        staleness_ratio=staleness_ratio,
        regenerate_threshold=regenerate_threshold,
        verdict=verdict,
        notes=tuple(notes),
    )
