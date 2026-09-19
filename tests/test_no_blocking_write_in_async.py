"""Bite tests for the blocking-write-on-the-event-loop lint.

Every case runs against fixture source written into ``tmp_path``, never against
the real tree, so the suite cannot rot when a route is migrated or a baseline
entry is burned down.

The two directions the gate exists for — a NEW violation reds, and a
grandfathered one stays green — are exercised end to end through
``tools.lints.cli_with_baseline`` at the bottom of the file.
"""

from __future__ import annotations

import textwrap

from tools.lints.baseline import load_baseline, write_baseline
from tools.lints.cli_with_baseline import main as baseline_main
from tools.lints.no_blocking_write_in_async import scan_file, scan_paths


def _write(tmp_path, code: str, name: str = "m.py"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


# --------------------------------------------------------------------------
# The violation: a write-lock acquisition whose nearest scope is an async def.
# --------------------------------------------------------------------------


def test_flags_connect_write_directly_in_async_def(tmp_path):
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write

        async def handler(db):
            with connect_write(db, purpose="x") as con:
                con.execute("INSERT INTO t VALUES (1)")
    """)
    v = scan_file(p)
    assert len(v) == 1
    assert v[0].call == "connect_write"
    assert v[0].func == "handler"


def test_flags_async_route_nested_in_a_sync_factory(tmp_path):
    # interfaces/research/api/app.py is one create_app() factory holding every
    # route, so the enclosing chain is sync -> async. Only the NEAREST scope
    # decides, otherwise the whole file would read as non-blocking.
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write

        def create_app():
            app = object()

            async def handler(db):
                with connect_write(db) as con:
                    con.execute("INSERT INTO t VALUES (1)")

            return app
    """)
    v = scan_file(p)
    assert len(v) == 1
    assert v[0].func == "handler"


def test_flags_every_write_lock_entry_point(tmp_path):
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write, connect_write_retrying

        async def a(db):
            connect_write(db)

        async def b(db):
            connect_write_retrying(db)

        async def c(coord):
            coord.acquire_write_context("purpose")
    """)
    assert sorted(x.call for x in scan_file(p)) == [
        "acquire_write_context",
        "connect_write",
        "connect_write_retrying",
    ]


def test_flags_a_bare_call_not_only_a_with_block(tmp_path):
    # wrestling.py acquires the connection bare and closes it later; that
    # blocks exactly as much as the context-manager form.
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write

        async def handler(db):
            con = connect_write(db, purpose="wrestling")
            con.execute("INSERT INTO t VALUES (1)")
            con.close()
    """)
    assert len(scan_file(p)) == 1


# --------------------------------------------------------------------------
# The sanctioned fix, and the other shapes that must stay green.
# --------------------------------------------------------------------------


def test_clean_when_the_locked_section_is_a_sync_def_hopped_to_a_thread(tmp_path):
    # The shape adopted in ad_routes.py / agent_work_routes.py — the pattern the
    # lint is steering new code toward. It must never red.
    p = _write(tmp_path, """
        import asyncio
        from runtime.db_lock import WriteLockTimeout, connect_write

        async def handler(db):
            def _sync():
                with connect_write(db, timeout_s=2.0) as con:
                    return con.execute("INSERT INTO t VALUES (1)")

            try:
                return await asyncio.to_thread(_sync)
            except WriteLockTimeout:
                return None
    """)
    assert scan_file(p) == []


def test_clean_for_run_in_threadpool_and_run_in_executor(tmp_path):
    # upload_routes.py uses starlette's run_in_threadpool; ad_routes.py uses a
    # dedicated executor. Neither hop is named in the rule: what makes both
    # green is the nested sync def interposing a scope, which is why an aliased
    # or re-exported hop needs no special handling.
    p = _write(tmp_path, """
        import asyncio
        from starlette.concurrency import run_in_threadpool
        from runtime.db_lock import connect_write

        async def a(db):
            def _sync():
                with connect_write(db) as con:
                    return con
            return await run_in_threadpool(_sync)

        async def b(db, executor):
            def _sync():
                with connect_write(db) as con:
                    return con
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, _sync)
    """)
    assert scan_file(p) == []


def test_clean_for_a_lambda_handed_straight_to_a_thread_hop(tmp_path):
    p = _write(tmp_path, """
        import asyncio
        from runtime.db_lock import connect_write

        async def handler(db):
            return await asyncio.to_thread(lambda: connect_write(db))
    """)
    assert scan_file(p) == []


def test_flags_an_eager_call_in_a_thread_hops_arguments(tmp_path):
    # Python evaluates a call's arguments on the calling thread, so this takes
    # the flock on the event loop and only then hands the open connection to a
    # worker. Being lexically inside to_thread(...) is not an exemption.
    p = _write(tmp_path, """
        import asyncio
        from runtime.db_lock import connect_write

        async def handler(db, apply):
            return await asyncio.to_thread(apply, connect_write(db))
    """)
    v = scan_file(p)
    assert len(v) == 1
    assert v[0].func == "handler"


def test_flags_a_function_local_aliased_import(tmp_path):
    # The acquisition/youtube/adapter.py idiom, moved into an async body: the
    # alias binds the same blocking function and the module's own AST can say so.
    p = _write(tmp_path, """
        async def handler(db):
            from runtime.db_lock import connect_write as _cw
            with _cw(db, purpose="x") as con:
                con.execute("INSERT INTO t VALUES (1)")
    """)
    v = scan_file(p)
    assert len(v) == 1
    # Reported under the canonical entry name, not the alias.
    assert v[0].call == "connect_write"


def test_flags_a_module_level_alias_and_a_plain_rebinding(tmp_path):
    # runtime/remote_exec/funnel.py binds _GRAPH_WRITER = connect_write today.
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write as cw

        _GRAPH_WRITER = cw

        async def a(db):
            with cw(db) as con:
                con.execute("INSERT INTO t VALUES (1)")

        async def b(db):
            with _GRAPH_WRITER(db) as con:
                con.execute("INSERT INTO t VALUES (2)")
    """)
    assert sorted(v.func for v in scan_file(p)) == ["a", "b"]


def test_an_unrelated_alias_is_not_flagged(tmp_path):
    # The alias map must not turn every local name into a write-lock entry.
    p = _write(tmp_path, """
        from runtime.db_lock import connect_read as cr

        _READER = cr

        async def handler(db):
            with cr(db) as con:
                con.execute("SELECT 1")
            with _READER(db) as con:
                con.execute("SELECT 1")
    """)
    assert scan_file(p) == []


def test_known_false_negative_lambda_that_is_never_dispatched(tmp_path):
    """A lambda holding the acquisition and then called inline still blocks.

    Same gap as the nested sync def above and pinned for the same reason: the
    lambda is the shape handed to a thread hop, so the scope rule has to let it
    through. See the module docstring, limitation 1.
    """
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write

        async def handler(db):
            f = lambda: connect_write(db)   # noqa: E731
            return f()
    """)
    assert scan_file(p) == []


def test_clean_for_a_plain_sync_function(tmp_path):
    # The ~210 acquisition/ and tools/ call sites: no event loop, no problem.
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write

        def ingest(db):
            with connect_write(db) as con:
                con.execute("INSERT INTO t VALUES (1)")
    """)
    assert scan_file(p) == []


def test_known_false_negative_sync_closure_that_never_reaches_a_hop(tmp_path):
    """A nested sync def that is CALLED rather than dispatched still blocks.

    The lint deliberately does not flag it: deciding whether a closure reaches a
    thread hop needs a call graph, and flagging every nested sync def would red
    the sanctioned fix shape above. This test pins the gap so a future
    call-graph-aware version has to change it on purpose rather than by
    accident. See the module docstring, limitation 1.
    """
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write

        async def handler(db):
            def _sync():
                with connect_write(db) as con:
                    return con
            return _sync()   # NOT dispatched — this really does block
    """)
    assert scan_file(p) == []


def test_known_false_negative_contextmanager_helper(tmp_path):
    """A @contextmanager wrapper called from async code is invisible here.

    Limitation 3 in the module docstring. Pinned for the same reason as above.
    """
    p = _write(tmp_path, """
        import contextlib
        from runtime.db_lock import connect_write

        @contextlib.contextmanager
        def writer(db):
            with connect_write(db) as con:
                yield con

        async def handler(db):
            with writer(db) as con:      # really blocks; not lexically visible
                con.execute("INSERT INTO t VALUES (1)")
    """)
    assert scan_file(p) == []


def test_scan_paths_recurses_into_subpackages(tmp_path):
    # The gate is pointed at top-level directories, so a violation buried in
    # interfaces/research/api has to be found from `interfaces` alone.
    nested = tmp_path / "interfaces" / "research" / "api"
    nested.mkdir(parents=True)
    _write(nested, """
        from runtime.db_lock import connect_write

        async def handler(db):
            with connect_write(db) as con:
                con.execute("INSERT INTO t VALUES (1)")
    """, name="route.py")
    assert len(scan_paths([tmp_path])) == 1


def test_test_files_are_skipped(tmp_path):
    p = _write(tmp_path, """
        from runtime.db_lock import connect_write

        async def test_thing(db):
            with connect_write(db) as con:
                con.execute("INSERT INTO t VALUES (1)")
    """, name="test_something.py")
    assert scan_file(p) == []
    assert scan_paths([tmp_path]) == []


# --------------------------------------------------------------------------
# Baseline behaviour: grandfathered stays green, new reds.
# --------------------------------------------------------------------------


def _fixture_tree(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write(src, """
        from runtime.db_lock import connect_write

        async def legacy(db):
            with connect_write(db) as con:
                con.execute("INSERT INTO t VALUES (1)")
    """, name="legacy.py")
    return src


def _capture(src, baseline_file) -> int:
    return baseline_main([
        "capture", "blocking_write_in_async",
        "--paths", str(src),
        "--baseline-file", str(baseline_file),
    ])


def _enforce(src, baseline_file) -> int:
    return baseline_main([
        "enforce", "blocking_write_in_async",
        "--paths", str(src),
        "--baseline-file", str(baseline_file),
    ])


def test_baselined_violation_is_green(tmp_path):
    src = _fixture_tree(tmp_path)
    baseline_file = tmp_path / "baseline.json"
    assert _capture(src, baseline_file) == 0
    assert len(load_baseline(baseline_file).violations) == 1
    assert _enforce(src, baseline_file) == 0


def test_a_new_violation_reds_against_the_baseline(tmp_path):
    src = _fixture_tree(tmp_path)
    baseline_file = tmp_path / "baseline.json"
    assert _capture(src, baseline_file) == 0

    _write(src, """
        from runtime.db_lock import connect_write

        async def freshly_added(db):
            with connect_write(db) as con:
                con.execute("INSERT INTO t VALUES (2)")
    """, name="new_route.py")

    assert _enforce(src, baseline_file) == 1


def test_removing_a_baseline_entry_reds(tmp_path):
    src = _fixture_tree(tmp_path)
    baseline_file = tmp_path / "baseline.json"
    assert _capture(src, baseline_file) == 0

    schema = load_baseline(baseline_file)
    write_baseline(baseline_file, lint=schema.lint, violations=[])

    assert _enforce(src, baseline_file) == 1


def test_fixing_the_violation_is_green_and_reports_stale(tmp_path, capsys):
    src = _fixture_tree(tmp_path)
    baseline_file = tmp_path / "baseline.json"
    assert _capture(src, baseline_file) == 0

    _write(src, """
        import asyncio
        from runtime.db_lock import connect_write

        async def legacy(db):
            def _sync():
                with connect_write(db, timeout_s=2.0) as con:
                    return con.execute("INSERT INTO t VALUES (1)")
            return await asyncio.to_thread(_sync)
    """, name="legacy.py")

    # No NEW violation, so plain enforce is green...
    assert _enforce(src, baseline_file) == 0

    # ...and --check-stale surfaces the burned-down entry so the baseline shrinks.
    rc = baseline_main([
        "enforce", "blocking_write_in_async",
        "--paths", str(src),
        "--baseline-file", str(baseline_file),
        "--check-stale",
    ])
    assert rc == 1
    assert "stale baseline entr" in capsys.readouterr().err
