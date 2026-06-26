"""M5: determinism proof tests (HPRJ SPR-02).

Render the golden corpus TWICE in one process and ONCE in a FRESH process
(subprocess, not thread); byte-compare all three. Pin every enumerable
nondeterminism source with a dedicated test that would fail if pinning
regressed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from services.html_projection import Provenance, RenderContext, render
from services.html_projection.tests.fixtures.golden import golden_corpus

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _ctx() -> RenderContext:
    """A deterministic context. No wall-clock; rendered_at is a fixed
    string (DATA, not now())."""
    return RenderContext(
        provenance=Provenance(
            document_id="doc-det-1",
            notebook_id="nbk-det-1",
            title="Determinism",
            content_class="notebook",
            schema_version="1.0.0",
            creator_user_id="user-det",
            rendered_at="2026-05-21T12:00:00Z",
            signature_valid=True,
        )
    )


# ── In-process determinism: render twice, byte-identical ──


@pytest.mark.parametrize("idx", range(len(golden_corpus())))
def test_in_process_double_render_byte_identical(idx):
    """Render the same doc-model twice in one process → byte-identical."""
    doc = golden_corpus()[idx]
    ctx = _ctx()
    a = render(doc, ctx)
    b = render(doc, ctx)
    assert a == b, f"in-process double render differs for golden doc {idx}"


# ── Cross-process determinism: fresh subprocess leg ──

_SUBPROCESS_SCRIPT = """
import json, os, sys
sys.path.insert(0, {repo_root!r})
from services.html_projection import Provenance, RenderContext, render
doc = json.loads(sys.stdin.read())
ctx = RenderContext(
    provenance=Provenance(
        document_id="doc-det-1",
        notebook_id="nbk-det-1",
        title="Determinism",
        content_class="notebook",
        schema_version="1.0.0",
        creator_user_id="user-det",
        rendered_at="2026-05-21T12:00:00Z",
        signature_valid=True,
    )
)
sys.stdout.write(render(doc, ctx))
"""


def _render_in_subprocess(doc: dict) -> str:
    """Render ``doc`` in a FRESH Python subprocess (not a thread). The
    subprocess has its own interpreter, its own hash seed, its own
    import order — so this leg catches nondeterminism a thread would
    miss (PYTHONHASHSEED, import-order side effects)."""
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT.format(repo_root=_REPO_ROOT)],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": "random"},
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"subprocess render failed: {result.stderr}"
    )
    return result.stdout


@pytest.mark.parametrize("idx", range(len(golden_corpus())))
def test_cross_process_byte_identical(idx):
    """Render in-process AND in a fresh subprocess → byte-identical. The
    subprocess uses PYTHONHASHSEED=random so dict/set hash-order variance
    would surface here if the renderer depended on it."""
    doc = golden_corpus()[idx]
    ctx = _ctx()
    in_proc = render(doc, ctx)
    fresh_proc = _render_in_subprocess(doc)
    assert in_proc == fresh_proc, (
        f"cross-process render differs for golden doc {idx}:\n"
        f"--- in-process (first 200) ---\n{in_proc[:200]}\n"
        f"--- fresh-process (first 200) ---\n{fresh_proc[:200]}"
    )


def test_subprocess_leg_is_real_subprocess_not_thread():
    """The fresh-process leg is a real subprocess (separate PID), not a
    thread. A thread shares the parent's hash seed + import state and
    would not catch cross-process nondeterminism."""
    # We confirm by having the subprocess report its own PID, which must
    # differ from the test process's PID.
    script = (
        f"import sys; sys.path.insert(0, {_REPO_ROOT!r}); "
        "import os; sys.stdout.write(str(os.getpid()))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0
    sub_pid = int(result.stdout)
    assert sub_pid != os.getpid(), (
        "subprocess leg ran in the same PID — it is not a real subprocess"
    )


# ── Pinned nondeterminism sources ──
# Each test below pins ONE source of nondeterminism. If the renderer ever
# regressed to depend on it, the test goes red. These are the sources the
# master-spec determinism invariant calls out.


def test_pin_dict_iteration_order_does_not_matter():
    """Dict iteration order must not affect output. The doc-model's
    ``content`` is a list (ordered); the renderer must not reorder blocks
    by a dict-keyed dispatch. To actually EXERCISE order-independence
    (not a no-op), build TWO distinct doc-model objects with the SAME
    logical content but DIFFERENT dict key insertion order in the block
    attrs, and assert byte-identical output. Rendering the same object
    twice in the same process proves nothing — it can't detect a
    set-based or hash-based dispatch that would reorder under different
    insertion order."""
    ctx = _ctx()
    # Two blocks, same logical content, but the attrs dict is constructed
    # with different key insertion order (block_id first vs last). If the
    # renderer ever dispatched on a dict-keyed/set structure, the output
    # could differ. The renderer must depend only on ``type`` + ordered
    # ``content``, not on attrs dict order.
    doc_a = {
        "title": "Dict order",
        "content": [
            {"type": "antiek_prose", "attrs": {"block_id": "a", "class": "prose"}, "content": [{"type": "text", "text": "a"}]},
            {"type": "antiek_prose", "attrs": {"block_id": "b", "class": "prose"}, "content": [{"type": "text", "text": "b"}]},
        ],
    }
    doc_b = {
        "title": "Dict order",
        "content": [
            {"type": "antiek_prose", "attrs": {"class": "prose", "block_id": "a"}, "content": [{"type": "text", "text": "a"}]},
            {"type": "antiek_prose", "attrs": {"class": "prose", "block_id": "b"}, "content": [{"type": "text", "text": "b"}]},
        ],
    }
    a = render(doc_a, ctx)
    b = render(doc_b, ctx)
    assert a == b, (
        "output differs when the same logical doc-model has different "
        "dict key insertion order — the renderer is order-dependent "
        "(set/hash-based dispatch leak)"
    )


def test_pin_hash_seed_does_not_matter():
    """PYTHONHASHSEED must not affect output. Run the same render under
    two different hash seeds (both as subprocesses) and compare. If the
    renderer iterated a set or relied on hash-based ordering, the output
    would differ across seeds."""
    doc = golden_corpus()[0]
    a = _render_in_subprocess_with_seed(doc, "0")
    b = _render_in_subprocess_with_seed(doc, "42")
    assert a == b, "output differs across PYTHONHASHSEED values — hash-order leak"


def _render_in_subprocess_with_seed(doc: dict, seed: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT.format(repo_root=_REPO_ROOT)],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": seed},
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, f"subprocess failed under seed {seed}: {result.stderr}"
    return result.stdout


def test_pin_import_order_does_not_matter():
    """Import order must not affect output. Import the renderer with a
    pre-imported vs not-pre-imported partial set; the dispatch table is
    built deterministically from the contract table (not from
    sys.modules order)."""
    import services.html_projection.renderer as r1

    # Force a re-import in a subprocess that imports partials in a
    # different order first. Uses the SAME provenance as _ctx() so the
    # only variable is import order.
    script = f"""
import sys; sys.path.insert(0, {_REPO_ROOT!r})
# Import partials in reverse order before the renderer.
import services.html_projection.partials.latex
import services.html_projection.partials.image
import services.html_projection.partials.prose
import services.html_projection.renderer
import json
doc = json.loads(sys.stdin.read())
from services.html_projection import Provenance, RenderContext, render
ctx = RenderContext(provenance=Provenance(
    document_id="doc-det-1",
    notebook_id="nbk-det-1",
    title="Determinism",
    content_class="notebook",
    schema_version="1.0.0",
    creator_user_id="user-det",
    rendered_at="2026-05-21T12:00:00Z",
    signature_valid=True,
))
sys.stdout.write(render(doc, ctx))
"""
    doc = golden_corpus()[0]
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    in_proc = render(doc, _ctx())
    assert in_proc == result.stdout, "import order affected output"


def test_pin_tempfile_paths_do_not_appear():
    """No tempfile paths or process-local paths leak into output. The
    renderer never touches the filesystem, so no temp path can appear."""
    import re

    ctx = _ctx()
    for doc in golden_corpus():
        html = render(doc, ctx)
        # No /var/folders, /tmp, or .pyc-style paths.
        assert not re.search(r"/(?:var/folders|tmp|private/tmp)/", html)
        assert ".venv" not in html
        assert __file__ not in html


def test_pin_no_uuid_or_random_in_output():
    """No uuid/random bytes appear in output. The renderer must not call
    uuid.uuid4() or random.random(). We check the output doesn't contain
    a fresh uuid-shaped token by rendering twice and confirming no
    uuid-pattern string appears that differs."""
    import re

    ctx = _ctx()
    doc = golden_corpus()[0]
    a = render(doc, ctx)
    # A uuid-shaped hex string (8-4-4-4-12) that isn't in the input.
    uuids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", a)
    # The golden doc has no uuids in its content; any uuid in output is a leak.
    input_uuids = re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        json.dumps(doc),
    )
    assert set(uuids) == set(input_uuids), (
        f"renderer emitted a uuid not in the input: {set(uuids) - set(input_uuids)}"
    )


def test_island_canonicalisation_is_stable():
    """The island JSON is canonicalised (sorted keys) so two renders of
    the same doc-model produce byte-identical island bytes, regardless of
    the input dict's key insertion order."""
    from services.html_projection.island import embed_island

    doc_a = {"b": 1, "a": 2, "content": []}
    doc_b = {"a": 2, "b": 1, "content": []}  # same content, different insertion order
    assert embed_island(doc_a) == embed_island(doc_b)


def test_repeated_renders_stable_over_many_iterations():
    """Render the same doc 50 times; all outputs identical. Catches
    mutable-global drift (e.g. a partial that appends to a module-level
    list across calls)."""
    ctx = _ctx()
    doc = golden_corpus()[0]
    first = render(doc, ctx)
    for _ in range(50):
        assert render(doc, ctx) == first
