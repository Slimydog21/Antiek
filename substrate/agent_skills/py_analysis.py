"""Skill 2 of 3 — ``py_analysis``: bounded, dependency-light data analysis.

A research agent mined a dataset and needs to know what it says before
deciding what to do next. This skill computes column-wise summary
statistics and grouped aggregations over a row-of-dicts (or raw series)
dataset, returning frozen, structured results. The whole module is
STDLIB-ONLY by deliberate contract — ``statistics`` for moments,
``collections.Counter`` for frequencies — so the skill runs on any host
where the substrate runs, with no pandas/numpy dependency added. (Antiek
core already depends on DuckDB; pandas is NOT a core dependency
(``pyproject.toml``: only the ``embedding`` extra pulls numpy), and the
skill's mandate is summary stats + aggregations, not dataframe algebra —
stdlib covers exactly that.)

DETERMINISM AND HONESTY RULES (why the kind lattice exists):

* ``kind`` is one of ``"numeric"`` (every non-missing value coerces to a
  finite float — ints, floats, numeric strings), ``"categorical"`` (none
  coerce — strings, bools, objects), ``"mixed"`` (some coerce, some
  don't — reported as-is, never quietly forced), ``"empty"`` (nothing to
  summarize). Stats fields are None except for ``numeric``; a mixed
  column is a signal to the agent, not a coercion.
* ``None`` and non-finite values (``nan``, ``inf`` — including the
  strings ``"nan"``/``"inf"``) count as MISSING: reported in
  ``SeriesSummary.missing`` and excluded from every statistic. Silently
  averaging a column containing ``nan`` would be the kind of wrongness
  this skill exists to prevent.
* ``bool`` is categorical, never numeric (it is a ``Real`` subclass by
  inheritance accident, and a 0/1 mean of True/False is a lie).
* ``top_values`` orders ties by label, groups by (-count, group), so the
  output is a pure function of the dataset, not of row order.
* Population (not sample) standard deviation — ``pstdev``: the data is
  the whole observation set, not a sample of a larger population.
* For fewer than 4 numeric values, quartiles are not meaningful; they
  fall back to the observed min/max (documented in the field docstring)
  rather than being invented.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from substrate.agent_skills.manifest import SkillManifest, SkillParameter

__all__ = [
    "AnalysisReport",
    "GroupSummary",
    "SeriesSummary",
    "group_summarize",
    "summarize_rows",
    "summarize_series",
]

Kind = Literal["numeric", "categorical", "mixed", "empty"]

# How many top values are reported per series (bounded surface).
_TOP_N = 5


@dataclass(frozen=True)
class SeriesSummary:
    """Summary statistics for one column/series.

    Attributes
    ----------
    name:
        Column name (or the caller-supplied name for a raw series).
    kind:
        ``"numeric"``, ``"categorical"``, ``"mixed"``, or ``"empty"`` —
        see module docstring for the coercion rules.
    count:
        Number of non-missing values (missing = None + non-finite).
    missing:
        Number of values counted as missing (None, nan, inf).
    distinct:
        Number of distinct values among the non-missing.
    mean, stddev, minimum, p25, median, p75, maximum, total:
        Population-mean/stddev, min, linear-interpolated quartiles,
        max, sum — all None unless ``kind == "numeric"``. For fewer than
        4 numeric values p25/p75 fall back to the observed extremes
        (a sample that small has no meaningful quartile; the fallback is
        documented, not silent).
    top_values:
        Up to 5 most frequent (label, count) pairs; ties ordered by
        label, so this is deterministic independent of row order.
    """

    name: str
    kind: Kind
    count: int
    missing: int
    distinct: int
    mean: float | None
    stddev: float | None
    minimum: float | None
    p25: float | None
    median: float | None
    p75: float | None
    maximum: float | None
    total: float | None
    top_values: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AnalysisReport:
    """Column-wise summary of a dataset (rows of dicts)."""

    row_count: int
    columns: tuple[str, ...]
    summaries: tuple[SeriesSummary, ...]

    def summary(self, column: str) -> SeriesSummary | None:
        """The summary for ``column``, or None if the column is absent."""
        for s in self.summaries:
            if s.name == column:
                return s
        return None


@dataclass(frozen=True)
class GroupSummary:
    """One group from :func:`group_summarize`.

    ``count`` is the number of rows in the group. ``total``/``mean``/
    ``minimum``/``maximum`` are computed over the numeric-coerced,
    finite values of the value column; they are all None if the value
    column has no numeric values in this group (never silently coerced).
    """

    group: str
    count: int
    total: float | None
    mean: float | None
    minimum: float | None
    maximum: float | None


def _is_missing(value: object) -> bool:
    """True for None and for values that float() to a non-finite number.

    ``"nan"``/``"inf"``/``"Infinity"`` strings are missing (they coerce
    but are not numbers in any statistical sense). Booleans are NOT
    missing — they are categorical values (handled by ``_to_float``).
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, int):
        return False
    if isinstance(value, str):
        try:
            return not math.isfinite(float(value))
        except ValueError:
            return False
    return False


def _to_float(value: object) -> float | None:
    """Coerce to a finite float, or None when not numeric/missing.

    Accepts int/float and numeric strings; rejects bool (categorical by
    contract, see module docstring) and non-finite floats.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, str):
        try:
            f = float(value)
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


def _label(value: object) -> str:
    """Deterministic label for top-values/frequency counting."""
    return str(value)


def _summarize(name: str, values: Sequence[object]) -> SeriesSummary:
    """Compute a SeriesSummary over ``values`` (the pure core; no I/O)."""
    nums: list[float] = []
    labels: list[str] = []
    missing = 0
    for v in values:
        if _is_missing(v):
            missing += 1
            continue
        f = _to_float(v)
        if f is not None:
            nums.append(f)
            labels.append(_label(v))
        else:
            labels.append(_label(v))
    if not nums and not labels:
        return SeriesSummary(
            name=name,
            kind="empty",
            count=0,
            missing=missing,
            distinct=0,
            mean=None,
            stddev=None,
            minimum=None,
            p25=None,
            median=None,
            p75=None,
            maximum=None,
            total=None,
            top_values=(),
        )
    # Every non-missing value lands in labels; numeric values also land in
    # nums. So: labels == nums means all-numeric, 0 < nums < labels means
    # mixed, and nums empty (labels non-empty) means categorical.
    if nums and len(nums) == len(labels):
        kind: Kind = "numeric"
    elif nums:
        kind = "mixed"
    else:
        kind = "categorical"

    distinct = len(set(labels))
    top: list[tuple[str, int]] = []
    if labels:
        counts = Counter(labels)
        top = sorted(counts.most_common(_TOP_N), key=lambda p: (-p[1], p[0]))

    if kind != "numeric":
        return SeriesSummary(
            name=name,
            kind=kind,
            count=len(labels),
            missing=missing,
            distinct=distinct,
            mean=None,
            stddev=None,
            minimum=None,
            p25=None,
            median=None,
            p75=None,
            maximum=None,
            total=None,
            top_values=tuple(top),
        )

    n = len(nums)
    mean = statistics.fmean(nums)
    if n >= 4:
        q25, _q50, q75 = statistics.quantiles(nums, n=4)
    else:
        q25, q75 = min(nums), max(nums)
    return SeriesSummary(
        name=name,
        kind=kind,
        count=n,
        missing=missing,
        distinct=distinct,
        mean=mean,
        stddev=statistics.pstdev(nums),
        minimum=min(nums),
        p25=q25,
        median=statistics.median(nums),
        p75=q75,
        maximum=max(nums),
        total=math.fsum(nums),
        top_values=tuple(top),
    )


def summarize_series(values: Sequence[object], *, name: str = "values") -> SeriesSummary:
    """Summarize one raw series (e.g. a column extracted from mined data).

    Parameters
    ----------
    values:
        The series values. Mixed types are handled per the kind lattice
        in the module docstring.
    name:
        A label for the series, echoed in the result.
    """
    return _summarize(name, values)


def summarize_rows(rows: Sequence[Mapping[str, object]]) -> AnalysisReport:
    """Summarize a dataset of rows (dicts sharing keys).

    Column order follows first appearance across the rows; a column is
    summarized over its values in every row where it appears. All None
    values in a column are missing; rows missing the key entirely simply
    contribute nothing to that column's summary (their absence is not a
    value, and is not counted as missing).

    Returns
    -------
    AnalysisReport
        row_count (number of input rows), columns, and one SeriesSummary
        per column; ``report.summary(name)`` for indexed access.
    """
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    summaries = tuple(
        _summarize(col, [row.get(col) for row in rows]) for col in columns
    )
    return AnalysisReport(
        row_count=len(rows),
        columns=tuple(columns),
        summaries=summaries,
    )


def group_summarize(
    rows: Sequence[Mapping[str, object]],
    *,
    key: str,
    value: str,
) -> tuple[GroupSummary, ...]:
    """Aggregate ``rows`` by ``key``, summarizing the ``value`` column.

    Grouping is by the string label of the key value (``str``), so
    ``1`` and ``"1"`` land in the same group and None keys group under
    ``"None"`` — deterministic, and groups are returned ordered by
    (-count, group) so the output does not depend on row order.

    Parameters
    ----------
    rows:
        The dataset.
    key:
        Column to group by. Rows missing the key group under ``"None"``.
    value:
        Column to aggregate. ``count`` is always the group's row count;
        total/mean/min/max are computed over numeric-coerced finite
        values and are None when the group has none (documented, never
        silently coerced).

    Returns
    -------
    tuple[GroupSummary, ...]
        One summary per group, canonical order (largest first, ties by
        group label).
    """
    buckets: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        g = _label(row.get(key))
        counts[g] = counts.get(g, 0) + 1
        f = _to_float(row.get(value))
        if f is not None:
            buckets.setdefault(g, []).append(f)
    out: list[GroupSummary] = []
    for g in sorted(counts, key=lambda g: (-counts[g], g)):
        vals = buckets.get(g, [])
        if vals:
            out.append(
                GroupSummary(
                    group=g,
                    count=counts[g],
                    total=math.fsum(vals),
                    mean=statistics.fmean(vals),
                    minimum=min(vals),
                    maximum=max(vals),
                )
            )
        else:
            out.append(
                GroupSummary(group=g, count=counts[g], total=None, mean=None, minimum=None, maximum=None)
            )
    return tuple(out)


MANIFEST = SkillManifest(
    name="py_analysis",
    summary="Summary stats + grouped aggregations over a dataset, stdlib-only.",
    description=(
        "Column-wise describe (numeric/categorical/mixed/empty with means, quartiles, "
        "frequencies) and group-by aggregation, pure stdlib — no pandas, no numpy. "
        "Deterministic: output is a pure function of the data, never of row order."
    ),
    entrypoint=summarize_rows,
    functions=("summarize_rows", "summarize_series", "group_summarize"),
    parameters=(
        SkillParameter(
            "rows",
            "Sequence[Mapping[str, object]]",
            "The dataset: rows as dicts sharing column keys.",
        ),
        SkillParameter(
            "key",
            "str",
            "group_summarize: column to group by.",
            required=False,
            default="None",
        ),
        SkillParameter(
            "value",
            "str",
            "group_summarize: column to aggregate (sum/mean/min/max).",
            required=False,
            default="None",
        ),
    ),
    returns=(
        "summarize_rows -> AnalysisReport (row_count, columns, per-column "
        "SeriesSummary). summarize_series -> SeriesSummary. group_summarize -> "
        "tuple[GroupSummary, ...] ordered by (-count, group)."
    ),
    safety=(
        "Stdlib-only: statistics + collections; runs wherever the substrate runs, no "
        "heavy dep added.",
        "Missing and non-finite values are counted and excluded, never silently "
        "averaged; mixed-kind columns are reported as mixed, never coerced.",
        "Deterministic output: no row-order dependence (ties in top_values and "
        "groups are label-ordered).",
    ),
    examples=(
        "report = summarize_rows(rows)",
        "report.summary('amount').median",
        "groups = group_summarize(rows, key='dept', value='amount')",
        "summarize_series([1, 2, 3, None, 100]).mean",
    ),
)
