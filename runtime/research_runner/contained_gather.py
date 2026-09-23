"""The gather loop that runs its step inside an ``ExecutionBackend`` workspace.

This is the join that makes ``runtime/exec_backend`` load-bearing. Until now the
seam terminated in a log line at ``cascade_routes.launch``: a backend was built,
its name was logged, and the ``HostLocalRunner`` ran the same in-process gather
stub as always. Nothing executed anywhere but the API process.

Where the join goes, and why here
---------------------------------
At the **browse loop**, not at the runner.

``interface.py`` defers "a ``RemoteExecProvider`` implemented over an
``ExecutionBackend``". That adapter is the wrong join for this seam and it is
not merely unbuilt, it is unbuildable over this interface:
``RemoteExecProvider.run`` must *stream* events out of a live loop and
``steer`` must reach into a running one, while ``ExecutionBackend`` is
deliberately "``exec`` + files, no streaming, no steering, no event channel".
An adapter would have to fake both. It would also need the in-sandbox leaf
program ``runtime/remote_exec/daytona.py`` names (``python -m
antiek.remote.research_leaf``) — which does not exist in this tree, and whose
absence is why ``DaytonaProvider.run`` is still a ``NotImplementedError``.

So the narrower join: keep the runner, replace what the runner runs. The loop
stays an async generator of ``StepEvent``s — the shape ``HostLocalRunner``,
``PromotionFunnel`` and the cascade surface already consume — and only the
*work inside one step* moves off-process into a workspace.

Single-writer preservation (the constraint that decided the design)
-------------------------------------------------------------------
DuckDB is single-writer and ``PromotionFunnel`` is the sole graph writer. This
loop introduces no second one, and the reason is structural rather than
disciplinary:

  * The workspace receives **bytes** (``put_file`` of a request JSON) and
    returns **bytes** (``ExecResult.stdout`` plus a ``get_file`` of its
    ``out/`` artifact). No graph handle, no db path, no ingest lock and no
    credential crosses the boundary — a ``_LocalWorkspace`` child gets an
    allowlisted ``PATH``/``LANG``/``HOME`` and nothing else, and a
    ``_DockerWorkspace`` child gets only ``profile.env``.
  * Those bytes become ordinary ``StepEvent``s yielded by this loop.
    ``HostLocalRunner._push`` forwards every ``note``/``question`` to
    ``on_emit``, which the cascade launch site binds to ``funnel.submit``.
    Results therefore return through **the existing funnel**, unchanged and
    still serialized.
  * Consequently the writer count is exactly what it was: one, on the host,
    behind ``db_lock``. ``tests/test_cascade_exec_backend_wiring.py`` holds
    that mechanically, in ``TestSingleWriterPreserved``: this module's source
    contains none of the host-writer identifiers, and a run through the real
    ``HostLocalRunner`` shows every promotable result arriving at ``on_emit``
    and nowhere else.

Honest scope of the payload
---------------------------
What runs in the workspace is ``GATHER_PROGRAM`` below: a stdlib-only script
that reads the host's request, appends a record to ``out/gather.jsonl`` and
prints a one-line summary. It performs no retrieval. That is the *same
honesty class* as ``make_contract_gather_stub``, the loop it replaces, which
its own docstring calls "an honest production gather placeholder — not real
research". This lane ships the join, not an agent: the seam, the workspace
lifecycle, the input and artifact channels and the failure taxonomy are real
and exercised end to end; the program they carry is still a placeholder, and
naming it one here is the point.

The program is the *default*, not the *only* payload. ``make_contained_gather_loop``
takes ``program=``, a caller-supplied source string that lands at ``PROGRAM_PATH``
in place of ``GATHER_PROGRAM``; ``cascade_routes._research_loop_factory`` threads
it through so a caller above the loop can reach it. The workspace input contract
is unchanged (bytes in, bytes out): the program is one more ``put_file``, and
whatever it appends to ``out/gather.jsonl`` rides back on the note as
``artifact_records`` (bounded by ``NOTE_ARTIFACT_LIMIT``) through the same
``on_emit`` and nowhere else — a caller's program cannot widen the writer count
any more than the placeholder could.

The one fact it reports that is not a placeholder is ``uid`` — the effective
user the contained step ran as. Under ``DockerBackend`` that is 65534; under
``LocalProcessBackend`` it is the service user, which is precisely the
condition this seam exists to end. The host logs it, so an operator can see
from the event data whether the step was actually contained.

Egress
------
``net_policy`` defaults to ``DENY_ALL``. The gather program needs no network,
and a backend that cannot *enforce* no-egress raises ``NetPolicyUnsupported``
at ``create()`` (invariant I4) rather than pretending. That means
``ANTIEK_EXEC_BACKEND=local`` fails loudly here: ``LocalProcessBackend`` has no
egress filter, so it refuses the policy instead of running agent code on the
bare host while the operator believes it is contained. That refusal is the
feature, and it is a stricter guarantee than a factory-level docker probe
alone: it survives an operator who selects ``local`` deliberately.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

# Plain absolute imports, the style of ``cost_projection`` / ``provider_gateway``
# rather than the try/except direct-script fallback ``host_local`` carries: this
# module is only ever imported as part of the package, so the fallback would be
# dead code and its two ``type: ignore`` comments dead noise.
from runtime.exec_backend.interface import (
    DENY_ALL,
    ExecutionBackend,
    ExecutionBackendError,
    NetPolicy,
    ResourceLimits,
    Workspace,
    WorkspaceProfile,
)
from runtime.research_runner.protocol import StepEvent

logger = logging.getLogger("antiek.research_runner.contained_gather")

#: Workspace-relative paths for the two channels. ``exec`` runs with ``cwd``
#: defaulting to the workspace's ``work/`` dir on every backend, so the program
#: addresses its siblings with ``..`` and the same source works under both
#: ``_LocalWorkspace`` (a host directory) and ``_DockerWorkspace``
#: (``/workspace`` on a tmpfs).
REQUEST_PATH: str = "in/request.json"
ARTIFACT_PATH: str = "out/gather.jsonl"
PROGRAM_PATH: str = "work/gather.py"

#: The default image for the contained step. ``DockerBackend``'s own default is
#: ``alpine:latest``, which ships no interpreter — running ``python3`` there
#: would return exit 127 forever. The loop therefore declares the image its
#: program needs rather than inheriting one that cannot run it.
DEFAULT_GATHER_IMAGE: str = "python:3.12-alpine"

#: Interpreter invoked inside the workspace. Overridable because
#: ``LocalProcessBackend`` runs on the host, where the right interpreter is
#: ``sys.executable``, not whatever ``python3`` resolves to on ``PATH``.
DEFAULT_INTERPRETER: str = "python3"

#: Per-``exec`` ceiling. Mandatory at the seam (invariant I1): there is no safe
#: default for "how long may untrusted code run", so the value is stated here
#: and passed explicitly on every call.
DEFAULT_STEP_TIMEOUT_S: float = 60.0

#: How many exported ``out/gather.jsonl`` records ride on the note as
#: ``artifact_records``. The note's ``data`` becomes node metadata behind the
#: funnel, so the artifact channel is bounded here rather than letting a
#: program size the graph write; ``contained_passes`` still carries the full
#: count.
NOTE_ARTIFACT_LIMIT: int = 32


#: The program that runs inside the workspace. Stdlib only — it must run on a
#: bare image with no wheels, and it must not import anything from this repo
#: (nothing from this repo is in the workspace, by design).
GATHER_PROGRAM: str = '''\
"""Contained gather step. Runs inside an ExecutionBackend workspace.

Reads the host's request from ../in/request.json, appends one record to
../out/gather.jsonl and prints a one-line summary on stdout. Stdlib only; it
holds no graph handle and no credentials, because none were put in the
workspace. It performs no retrieval - this is the placeholder payload the
host-side loop documents, not a research agent.
"""

import json
import os
import sys

REQUEST = os.path.join("..", "in", "request.json")
ARTIFACT = os.path.join("..", "out", "gather.jsonl")


def main() -> int:
    step = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    with open(REQUEST, encoding="utf-8") as fh:
        request = json.load(fh)
    sub_question = request["sub_question"]
    record = {
        "step": step,
        "investigation_id": request["investigation_id"],
        "sub_question": sub_question,
        "gather_mode": "exec_backend",
        "uid": os.getuid(),
        "cwd": os.getcwd(),
    }
    os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
    with open(ARTIFACT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\\n")
    print("[contained] pass %d on %r as uid %d" % (step, sub_question, os.getuid()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _fail(result: Any, argv: list[str]) -> ExecutionBackendError:
    """Turn a non-zero / timed-out ``ExecResult`` into a loud failure.

    A contained step that did not run is not a step that produced nothing — it
    is a step whose result is unknown. Raising marks the leaf FAILED with the
    real exit code and stderr tail rather than emitting a note the operator
    would read as gathered evidence.
    """
    tail = (result.stderr or result.stdout or "").strip()[-500:]
    what = "timed out" if result.timed_out else f"exited {result.exit_code}"
    return ExecutionBackendError(f"contained gather step {argv} {what}: {tail}")


def make_contained_gather_loop(
    backend: ExecutionBackend,
    *,
    steps: int = 2,
    cost_per_step: float = 0.01,
    interpreter: str = DEFAULT_INTERPRETER,
    image: str | None = DEFAULT_GATHER_IMAGE,
    net_policy: NetPolicy = DENY_ALL,
    limits: ResourceLimits | None = None,
    timeout_s: float = DEFAULT_STEP_TIMEOUT_S,
    program: str = GATHER_PROGRAM,
) -> Callable[[Any], AsyncIterator[StepEvent]]:
    """Build a ``BrowseLoop`` whose gather step executes in *backend*.

    One workspace per investigation, provisioned when the leaf's loop starts
    and destroyed in a ``finally``. Each of *steps* passes is one ``exec``, so
    the runner's cooperative checkpoint still lands between passes and
    pause / stop / redirect keep working exactly as they do for the in-process
    stub. The workspace's ``out/`` artifact is exported once at the end and
    becomes the note the promotion funnel promotes.

    Signature mirrors ``make_contract_gather_stub`` (*steps*, *cost_per_step*)
    so the swap at ``cascade_routes._research_loop_factory`` is one line and the
    budget arithmetic is unchanged.

    *program* is the source that runs in the workspace, written to
    ``PROGRAM_PATH`` before the first pass; it defaults to the placeholder
    ``GATHER_PROGRAM``. It is invoked as ``<interpreter> gather.py <pass>``
    with ``work/`` as cwd, reads ``../in/request.json`` and appends records to
    ``../out/gather.jsonl`` — the same contract the placeholder documents.
    """
    profile = WorkspaceProfile(name="antiek-contained-gather", image=image)
    resource_limits = limits if limits is not None else ResourceLimits()

    async def _loop(ctx: Any) -> AsyncIterator[StepEvent]:
        yield ctx.plan_event(
            f"[contained] plan: {ctx.sub_question}",
            gather_mode="exec_backend",
            backend=backend.name,
        )
        # create() is the honest gate: a backend that cannot enforce the
        # declared net policy raises here (I4) and the leaf fails with that
        # reason, rather than gathering uncontained.
        workspace: Workspace = await backend.create(
            profile, limits=resource_limits, net_policy=net_policy
        )
        try:
            await workspace.put_file(PROGRAM_PATH, program.encode("utf-8"))
            await workspace.put_file(
                REQUEST_PATH,
                json.dumps(
                    {
                        "investigation_id": ctx.investigation_id,
                        "sub_question": ctx.sub_question,
                    },
                    sort_keys=True,
                ).encode("utf-8"),
            )
            for i in range(steps):
                sub_q = await ctx.checkpoint()
                # A redirect between passes changes the question the contained
                # program sees: rewrite the input channel, do not restart the
                # workspace.
                await workspace.put_file(
                    REQUEST_PATH,
                    json.dumps(
                        {
                            "investigation_id": ctx.investigation_id,
                            "sub_question": sub_q,
                        },
                        sort_keys=True,
                    ).encode("utf-8"),
                )
                argv = [interpreter, "gather.py", str(i)]
                result = await workspace.exec(argv, timeout_s=timeout_s)
                if result.timed_out or result.exit_code != 0:
                    raise _fail(result, argv)
                yield ctx.step(
                    result.stdout.strip() or f"[contained] pass {i} on '{sub_q}'",
                    cost_usd=cost_per_step,
                    tokens=0,
                    gather_mode="exec_backend",
                    backend=backend.name,
                    workspace_id=workspace.workspace_id,
                    exit_code=result.exit_code,
                    truncated=result.truncated,
                )

            # Artifact export (invariant I3): the workspace wrote to its own
            # out/ dir; the host copies it out and is the only thing that goes
            # near the graph with it.
            raw = await workspace.get_file(ARTIFACT_PATH)
            records = [
                json.loads(line)
                for line in raw.decode("utf-8", errors="replace").splitlines()
                if line.strip()
            ]
            uids = sorted({r.get("uid") for r in records if "uid" in r})
            logger.info(
                "contained gather complete: investigation=%s backend=%s "
                "workspace=%s passes=%d ran_as_uid=%s",
                ctx.investigation_id,
                backend.name,
                workspace.workspace_id,
                len(records),
                uids,
            )
            yield ctx.note(
                f"[contained] provisional note from {ctx.investigation_id}: "
                f"{ctx.sub_question}",
                gather_mode="exec_backend",
                backend=backend.name,
                workspace_id=workspace.workspace_id,
                contained_passes=len(records),
                ran_as_uid=uids[0] if len(uids) == 1 else uids,
                artifact_records=records[:NOTE_ARTIFACT_LIMIT],
            )
        finally:
            # Idempotent by contract (I6). This runs inline on the normal and
            # raising paths. On the abandonment paths — HostLocalRunner raises
            # BudgetExceeded out of its ``async for`` body without aclosing the
            # generator — it runs when asyncio finalizes the async generator
            # instead, which is prompt but not deterministic. Nothing tests
            # that path; HANDOFF.md carries it as the lane's open risk.
            with contextlib.suppress(Exception):
                await workspace.destroy()

    return _loop


__all__ = [
    "make_contained_gather_loop",
    "GATHER_PROGRAM",
    "REQUEST_PATH",
    "ARTIFACT_PATH",
    "PROGRAM_PATH",
    "DEFAULT_GATHER_IMAGE",
    "DEFAULT_INTERPRETER",
    "DEFAULT_STEP_TIMEOUT_S",
    "NOTE_ARTIFACT_LIMIT",
]
