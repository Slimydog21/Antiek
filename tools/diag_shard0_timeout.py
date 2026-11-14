"""TEMPORARY diagnostic, never merged: why does shard 0 time out on /catalog?

Wraps asyncio.wait_for for one test only. On a timeout it writes, to $DIAG_OUT, every
thread's stack, every asyncio task's stack, the default executor's and anyio limiter's
state, whether the test's account-store flock is free, and the GC pauses during the test.
It then waits 5 s more (release still unset) to see whether the request finishes alone.
"""

import asyncio
import fcntl
import faulthandler
import gc
import os
import sys
import threading
import time

TARGET = "test_key_work_is_off_loop_while_same_loop_catalogue_remains_available"
_ORIG = asyncio.wait_for
_GC: list[tuple[int, float]] = []
_START: dict[int, float] = {}


def _gc_cb(phase: str, info: dict[str, int]) -> None:
    if phase == "start":
        _START[0] = time.perf_counter()
    elif 0 in _START:
        _GC.append((info.get("generation", -1), time.perf_counter() - _START.pop(0)))


def _state(fh: object) -> None:
    write = fh.write  # type: ignore[attr-defined]
    loop = asyncio.get_running_loop()
    write(f"loop={type(loop).__module__}.{type(loop).__name__} cpus={os.process_cpu_count()}\n")
    ex = getattr(loop, "_default_executor", None)
    if ex is not None:
        write(f"default executor: max={ex._max_workers} threads={len(ex._threads)} "
              f"queue={ex._work_queue.qsize()} idle={ex._idle_semaphore._value}\n")
    else:
        write("default executor: none yet\n")
    try:
        import anyio.to_thread

        lim = anyio.to_thread.current_default_thread_limiter()
        write(f"anyio limiter: total={lim.total_tokens} borrowed={lim.borrowed_tokens}\n")
    except Exception as exc:
        write(f"anyio limiter: {exc!r}\n")
    store = os.environ.get("ANTIEK_ACCOUNT_STORE")
    if store:
        fd = os.open(store + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            write("account-store flock: free\n")
        except BlockingIOError:
            write("account-store flock: HELD\n")
        finally:
            os.close(fd)
    write(f"threads={threading.active_count()}: "
          f"{sorted(t.name for t in threading.enumerate())}\n")
    write(f"gc pauses: {[(g, round(d, 3)) for g, d in _GC]}\n")


def pytest_runtest_setup(item: object) -> None:
    if getattr(item, "name", "") != TARGET:
        return
    out = os.environ.get("DIAG_OUT", "/dev/stderr")

    # v2: an observer only. The awaited coroutine still runs inside the caller's task
    # under the real asyncio.wait_for (v1 moved it into its own task, and passed).
    async def wait_for(fut: object, timeout: float) -> object:
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        seen: dict[str, float] = {}

        def snap() -> None:  # on the loop, shortly before the deadline
            seen["loop_snapshot"] = time.perf_counter() - t0
            with open(out, "a") as fh:
                fh.write(f"LOOP SNAPSHOT at {seen['loop_snapshot']:.3f}s (timeout {timeout})\n")
                _state(fh)
                fh.flush()
                faulthandler.dump_traceback(file=fh, all_threads=True)
                for t in asyncio.all_tasks(loop):
                    fh.write(f"--- task {t!r}\n")
                    t.print_stack(file=fh)

        def thread_snap() -> None:  # off the loop: shows a loop that is itself blocked
            if "done" in seen:
                return
            with open(out, "a") as fh:
                fh.write(f"THREAD SNAPSHOT at {time.perf_counter() - t0:.3f}s; "
                         f"loop snapshot ran: {'loop_snapshot' in seen}\n")
                fh.flush()
                faulthandler.dump_traceback(file=fh, all_threads=True)

        handle = loop.call_later(timeout * 0.9, snap)
        timer = threading.Timer(timeout * 1.5, thread_snap)
        timer.daemon = True
        timer.start()
        try:
            result = await _ORIG(fut, timeout)  # type: ignore[arg-type]
        except TimeoutError:
            with open(out, "a") as fh:
                fh.write(f"TIMEOUT raised at {time.perf_counter() - t0:.3f}s\n")
            raise
        finally:
            seen["done"] = time.perf_counter() - t0
            handle.cancel()
            timer.cancel()
        with open(out, "a") as fh:
            fh.write(f"wait_for ok in {seen['done']:.3f}s\n")
            _state(fh)
        return result

    asyncio.wait_for = wait_for  # type: ignore[assignment]
    _GC.clear()
    gc.callbacks.append(_gc_cb)
    print(f"diag v2 armed for {TARGET}", file=sys.__stderr__)


def pytest_runtest_teardown(item: object) -> None:
    if getattr(item, "name", "") == TARGET:
        asyncio.wait_for = _ORIG
        if _gc_cb in gc.callbacks:
            gc.callbacks.remove(_gc_cb)
