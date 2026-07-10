"""Deep-research eval harness (W0): frozen queries, pinned judge, fail-closed regression."""

from .bench_bridge import BENCH_TASK, IncompleteRunError, deep_research_bench_record
from .dataset import (
    EXPECTED_QUERY_COUNT,
    DatasetValidationError,
    Query,
    QueryDataset,
    default_dataset_path,
    load_dataset,
)
from .journal import DEFAULT_JOURNAL_PATH, EvalJournalCorruptionError, EvalRunJournal
from .regression import (
    DEFAULT_MAX_COVERAGE_DROP,
    DEFAULT_MAX_JUDGE_SCORE_DROP,
    NotComparableError,
    RegressionThresholds,
    RegressionVerdict,
    Verdict,
    compare_runs,
)
from .rubric import (
    AXES,
    JUDGE_MODEL_ID,
    RUBRIC_VERSION,
    JudgeScores,
    ResearchReport,
    SourceRef,
    build_judge_prompt,
    parse_judge_response,
)
from .runner import (
    STATUS_MEASURED,
    STATUS_NOT_MEASURED,
    EvalRun,
    JudgeFn,
    ProviderFn,
    QueryScore,
    QueryStatus,
    run_eval,
)

__all__ = [
    "AXES",
    "BENCH_TASK",
    "DEFAULT_JOURNAL_PATH",
    "DEFAULT_MAX_COVERAGE_DROP",
    "DEFAULT_MAX_JUDGE_SCORE_DROP",
    "EXPECTED_QUERY_COUNT",
    "JUDGE_MODEL_ID",
    "RUBRIC_VERSION",
    "STATUS_MEASURED",
    "STATUS_NOT_MEASURED",
    "DatasetValidationError",
    "EvalJournalCorruptionError",
    "EvalRun",
    "EvalRunJournal",
    "IncompleteRunError",
    "JudgeFn",
    "JudgeScores",
    "NotComparableError",
    "ProviderFn",
    "Query",
    "QueryDataset",
    "QueryScore",
    "QueryStatus",
    "RegressionThresholds",
    "RegressionVerdict",
    "ResearchReport",
    "SourceRef",
    "Verdict",
    "build_judge_prompt",
    "compare_runs",
    "deep_research_bench_record",
    "default_dataset_path",
    "load_dataset",
    "parse_judge_response",
    "run_eval",
]
