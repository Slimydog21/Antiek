# SPR-02 eventlog-query handoff

## Round 2 sharpen

- FIX 1: `where-did-it-stall` keeps JSON `null` values unchanged, but the human table now renders completed-run stall-only fields as `-` instead of `unknown`. Test: `test_where_did_it_stall_table_marks_completed_stall_fields_not_applicable`; stalled table output is covered in `test_where_did_it_stall_detects_truncated_open_phase`.
- FIX 2: `_latency` now accepts non-negative finite whole-number floats such as `1500.0` and coerces them to `int`; bools, negatives, NaN/inf, and fractional floats remain rejected. Test: `test_which_phase_slowest_accepts_whole_number_float_latency`.
- FIX 3: `substrate.event_log.trajectory()` skips malformed/truncated JSON lines that fail `json.loads`, but it does not skip valid JSON rows that are not dicts; those raise later when the reader sorts/accesses `.get()`. `_safe_trajectory` catches that exception, returns `[]`, and emits the existing stderr warning. Test: `test_malformed_trajectory_warns_and_exits_cleanly`.
- FIX 4: Added comments for the nearest-rank p95 index and the `-1` aggregate sort sentinel; no logic change.

Verification:

- `/Users/slimydog/Desktop/Antiek/.venv/bin/python -m pytest tests/tools/test_eventlog_query.py -q` -> `8 passed in 2.52s`.
- Rechecked `which-phase-slowest`, `which-provider-fails`, and `where-did-it-stall` against `tests/fixtures/trajectories`; completed `healthy` table output now shows `-` for `stalled_phase`, `phase_name`, and `diagnostic`.
