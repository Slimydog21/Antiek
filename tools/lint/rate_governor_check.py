#!/usr/bin/env python3
"""arXiv rate-governor egress lint — HOST-based, not directory-based (SPR-09).

The invariant. arXiv's terms of use cap requests at one per three seconds, and a
breach IP-bans the box for HOURS (project_researchmaxx_arxiv.md). The ban is
HOST-scoped: any fetch to ``arxiv.org`` / ``export.arxiv.org`` (or a subdomain)
shares one IP-rate budget, so EVERY such fetch — from ANYWHERE in the codebase —
must route through the host-global governor (an exclusive ``fcntl.flock`` around
the throttle's >=3s + 429-ban critical section on the canonical
``~/.antiek/arxiv_throttle.json``). At runtime the fetch boundary
``acquisition.arxiv.rate_governor.govern_if_arxiv(url, send)`` makes this
host-based: it parses the URL's host and routes an arXiv host through the
governor, calling a non-arXiv host's send directly.

WHY THE REDESIGN (round-4 — the DIRECTORY-scoped bypass it now closes)
---------------------------------------------------------------------
The round-3 scanner scoped itself to ``_ARXIV_EGRESS_DIRS = ("acquisition/arxiv/",)``
— so any arXiv-host egress OUTSIDE that directory was INVISIBLE. That is the
structural cause of the recurring misses: round-4 found
``acquisition/openaccess/unpaywall.py::download_pdf`` fetching
``https://arxiv.org/pdf/<id>`` (an OpenAlex ``best_oa_pdf_url`` for an
arXiv-mirrored work) under the OA throttle — concurrency-blind to the harvest,
and INVISIBLE to a directory-scoped lint. The fix makes the scanner HOST-based:
it scans the WHOLE acquisition tree and flags any raw external HTTP fetcher that
is not routed through ``govern_if_arxiv`` / ``governed_request`` — because such a
fetcher, if its (often runtime-resolved) URL is an arXiv host, is an ungoverned
arXiv egress wherever it lives.

THE RULE. An external HTTP fetcher — an ``ast.Call`` to an egress verb
(``.get`` / ``.post`` / ``.put`` / ``.delete`` / ``.head`` / ``.patch`` /
``.stream`` / ``.request`` / ``.send``) on an HTTP-CLIENT-SHAPED receiver (the
``httpx`` / ``requests`` module, or a name bound to an ``httpx.Client`` /
``httpx.AsyncClient`` / ``requests.Session``), or a bare ``urlopen`` — in the
acquisition tree MUST route its send through ``govern_if_arxiv`` or
``governed_request`` (so an arXiv-host URL is governed at runtime). A raw
external fetch that is NOT so routed is FLAGGED at ``file:line``. Keying on the
client-shaped RECEIVER (NOT the URL value) makes the check robust to a
runtime-resolved URL AND free of the dict/XML ``.get`` / ``.request`` false
positives (``raw_work.get(...)`` / ``element.get("status")`` are not HTTP
clients, so they are never flagged).

SCOPE = the whole acquisition tree (``acquisition/``). Host-based, not
directory-based: an arXiv-host fetch in ``acquisition/openaccess/`` is now just
as flagged as one in ``acquisition/arxiv/``. (``tools/`` carries no arXiv egress
— the only ``tools/`` HTTP is a localhost demo client to the Antiek API — so it
is out of scope; add it to ``_EGRESS_SCAN_DIRS`` if that ever changes.)

GOVERNED-SEAM RECOGNITION (what is NOT flagged):

  * ``acquisition/arxiv/rate_governor.py`` — the governor itself.
  * ``acquisition/arxiv/throttle.py``      — the reused timing/ban engine.
  * a network call INSIDE a ``send`` / ``_send`` closure (or an inline lambda)
    that is passed to ``governed_request(...)`` OR ``govern_if_arxiv(url, send)``
    in the same scope — this is how every governed fetcher legitimately egresses
    (the raw ``.get`` lives in a nested ``def _send()`` whose NAME is an argument
    to one of those calls). Detected STRUCTURALLY (NOT by URL), so it cannot be
    spoofed by a literal and cannot be missed on a runtime URL.
  * test files                             — tests exercise egress against an
                                             ``httpx.MockTransport`` (no network).

Note that ``public_domain.py`` (Gutenberg / archive.org) is NO LONGER allowlisted
by NAME — it now routes its own send through ``govern_if_arxiv`` like every other
fetcher (a no-op for its non-arXiv hosts, but uniform + bypass-proof), so it is
recognized as governed by the same structural rule, not by a directory exception.

Modeled on ``tools/lint/serve_guard_check.py`` / ``tools/lint/boundary_check.py``:
same ``path:line`` output, same exit-code contract (0 = clean, 1 = violations),
same AST walk.

KNOWN, ACCEPTED LIMITATION (honesty bar 1): the seam recognition is LEXICAL — a
network call is "governed" iff it is inside a closure whose NAME is passed to a
``govern_if_arxiv`` / ``governed_request`` call in the same scope. A pathological
indirection (passing the send through three layers of variables before the call
sees it) would not be recognized and would (conservatively) be FLAGGED — a false
POSITIVE, the safe direction (it forces the obvious closure shape). The dangerous
direction — a raw egress slipping past unflagged — is closed: any raw external
egress not in that recognized shape reds.

Exit 0 = clean; exit 1 = a violation, printed as ``path:line``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent

# HTTP-egress method names (the ``.NAME(...)`` part of an httpx/requests/session
# call). Matching by method name keeps the lint client-library-agnostic — an
# httpx.Client, a requests.Session, or a bare module-level requests.get all use
# these verbs.
_EGRESS_METHODS: frozenset[str] = frozenset(
    {"get", "post", "put", "delete", "head", "patch", "stream", "request", "send"}
)

# The governor seam entry points: a network ``send`` closure handed to EITHER of
# these calls is sanctioned, governed egress. ``govern_if_arxiv(url, send)`` is
# the host-based boundary (routes an arXiv-host URL through the governor, a
# non-arXiv URL directly); ``governed_request(send, ...)`` is the unconditional
# governor seam the arXiv connector uses where the host is statically arXiv.
_GOVERNOR_CALLS: frozenset[str] = frozenset({"governed_request", "govern_if_arxiv"})

# HOST-based scope: scan the WHOLE acquisition tree, not a single directory. An
# arXiv-host fetch in acquisition/openaccess/ is exactly as governed-or-flagged as
# one in acquisition/arxiv/. (tools/ carries no arXiv egress today — add it here
# if that changes.)
#
# SPR-09 round-5 — also scan ``substrate/graph/``. The LLM-callable builtin tool
# ``substrate/graph/rlm_tools.py::fetch_url`` is a raw external fetcher of an
# ARBITRARY model-supplied URL, exported from ``substrate.graph`` OUTSIDE the
# acquisition tree — an LLM could call it with an arxiv URL. It must route through
# ``govern_if_arxiv`` like every other external fetcher (it now does, per hop),
# and the scanner must SEE it so a future raw external fetcher added under
# ``substrate/graph/`` cannot slip past the governed seam. The receiver-shape
# check keeps the many dict / DuckDB-connection ``.get`` / ``.execute`` calls in
# that tree from false-flagging (they are not httpx/requests clients).
_EGRESS_SCAN_DIRS: tuple[str, ...] = ("acquisition/", "substrate/graph/")

# Files (relative to the repo root) where a raw egress is legitimate WITHOUT the
# governor closure: the governor + the reused throttle engine (the seam itself).
# public_domain.py is NO LONGER allowlisted here — it routes through
# ``govern_if_arxiv`` like every other fetcher, so it is recognized as governed by
# the structural rule, not by a directory exception.
_ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "acquisition/arxiv/rate_governor.py",
        "acquisition/arxiv/throttle.py",
    }
)


# Module names that ARE HTTP clients — ``httpx.get(...)`` / ``requests.post(...)``
# is a direct egress. (A bare ``httpx.Client(...)`` constructor is NOT an egress
# verb, so it is not matched; only the verb calls are.)
_HTTP_CLIENT_MODULES: frozenset[str] = frozenset({"httpx", "requests"})

# Constructor attribute names that mint an HTTP client/session — a local bound to
# one of these (``c = httpx.Client(...)``, ``with httpx.Client() as c``) is a
# client receiver for the verb calls that follow.
_HTTP_CLIENT_CTORS: frozenset[str] = frozenset(
    {"Client", "AsyncClient", "Session"}
)

# Annotation attribute names marking a param/var as an HTTP client
# (``client: Optional[httpx.Client]``, ``session: requests.Session``).
_HTTP_CLIENT_ANNOTATIONS: frozenset[str] = _HTTP_CLIENT_CTORS


def _annotation_is_http_client(ann: ast.AST | None) -> bool:
    """Whether a type annotation names an httpx/requests client anywhere inside it
    (``httpx.Client`` / ``Optional[httpx.Client]`` / ``requests.Session``)."""
    if ann is None:
        return False
    for node in ast.walk(ann):
        if isinstance(node, ast.Attribute) and node.attr in _HTTP_CLIENT_ANNOTATIONS:
            # e.g. httpx.Client / requests.Session
            if isinstance(node.value, ast.Name) and node.value.id in _HTTP_CLIENT_MODULES:
                return True
    return False


def _ctor_is_http_client(value: ast.AST | None) -> bool:
    """Whether ``value`` is an ``httpx.Client(...)`` / ``requests.Session(...)``
    (etc.) constructor call — i.e. binding it mints an HTTP client."""
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _HTTP_CLIENT_CTORS
        and isinstance(func.value, ast.Name)
        and func.value.id in _HTTP_CLIENT_MODULES
    )


def _client_names_bound_directly_in(scope: ast.AST) -> set[str]:
    """HTTP-client names bound DIRECTLY in ``scope`` (a module or function body) —
    NOT descending into nested functions, so a name bound in a sibling/inner
    function does not bleed into this scope. Bindings recognized:

      * an assignment ``c = httpx.Client(...)`` / ``s = requests.Session(...)``;
      * a ``with httpx.Client() as c:`` context binding;
      * a function PARAM annotated ``httpx.Client`` / ``Optional[httpx.Client]`` /
        ``requests.Session`` (collected for THIS function's own params).

    Scope-precise binding is what stops the false positive where ``c`` is an
    ``httpx.Client`` in one function but an XML-element loop var in another: each
    scope only sees the clients bound in it or an ENCLOSING scope, never a
    sibling/inner one."""
    names: set[str] = set()

    # This function's own params (annotated as a client).
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = scope.args
        for arg in (
            list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
            + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else [])
        ):
            if arg is not None and _annotation_is_http_client(arg.annotation):
                names.add(arg.arg)

    # Statements in this scope's body, NOT recursing into nested def bodies.
    body = scope.body if hasattr(scope, "body") else []

    def _scan(stmts: list[ast.stmt]) -> None:
        for st in stmts:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue  # a nested scope owns its own bindings
            if isinstance(st, ast.Assign) and _ctor_is_http_client(st.value):
                for tgt in st.targets:
                    if isinstance(tgt, ast.Name):
                        names.add(tgt.id)
            elif isinstance(st, ast.AnnAssign) and (
                _annotation_is_http_client(st.annotation)
                or _ctor_is_http_client(st.value)
            ):
                if isinstance(st.target, ast.Name):
                    names.add(st.target.id)
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                for item in st.items:
                    if _ctor_is_http_client(item.context_expr) and isinstance(
                        item.optional_vars, ast.Name
                    ):
                        names.add(item.optional_vars.id)
            # Descend into compound statements that share THIS scope (if/for/while/
            # try/with bodies are the same function scope), so a client bound in an
            # ``if`` branch or a ``with`` body is still seen.
            for field_name in ("body", "orelse", "finalbody"):
                inner = getattr(st, field_name, None)
                if isinstance(inner, list):
                    _scan([s for s in inner if isinstance(s, ast.stmt)])
            for handler in getattr(st, "handlers", []) or []:
                _scan([s for s in handler.body if isinstance(s, ast.stmt)])

    _scan([s for s in body if isinstance(s, ast.stmt)])
    return names


def _receiver_is_http_client(func: ast.Attribute, client_names: set[str]) -> bool:
    """Whether the verb call's receiver is HTTP-client-shaped: the ``httpx`` /
    ``requests`` module directly, or a Name bound to an httpx/requests client."""
    recv = func.value
    if isinstance(recv, ast.Name):
        return recv.id in _HTTP_CLIENT_MODULES or recv.id in client_names
    return False


def _is_egress_call(node: ast.AST, client_names: set[str]) -> bool:
    """Whether ``node`` is an HTTP NETWORK egress: an egress-verb call on an
    HTTP-client-shaped receiver (the httpx/requests module, or a name bound to an
    httpx/requests client), or a bare ``urlopen`` / ``request.urlopen``.

    Keying on a client-shaped RECEIVER (not the URL) is the robustness pivot: it
    catches a dynamic-URL egress (the round-2 bypass) while NOT flagging a dict /
    XML-element ``.get`` / ``.request`` (those receivers are not clients)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr == "urlopen":
            return True  # urllib.request.urlopen(...) — stdlib egress
        if func.attr in _EGRESS_METHODS:
            return _receiver_is_http_client(func, client_names)
        return False
    if isinstance(func, ast.Name):
        return func.id == "urlopen"
    return False


def _governed_sends(scope: ast.AST) -> tuple[set[str], set[int]]:
    """Discover the governed sends established in ``scope``'s subtree.

    Returns ``(closure_names, inline_lambda_ids)``:
      * ``closure_names`` — names of nested ``def`` send closures passed to a
        ``governed_request(...)`` call in this scope (the ``send`` / ``_send``
        pattern). Any egress inside a function of one of these names is governed,
        REGARDLESS of the client names — the whole closure is the sanctioned send.
      * ``inline_lambda_ids`` — ``id`` of each ``Lambda`` (or other inline expr)
        handed directly to ``governed_request`` (e.g.
        ``governed_request(lambda: c.get(...))``); every egress under such a node
        is governed.

    Using whole-closure governance (not a client-name-dependent egress scan) is
    what makes the seam recognition robust: a governed send's INNER egress —
    ``with httpx.Client() as c: return c.get(...)`` — is allowed without the
    governed-ness decision having to re-derive that ``c`` is a client."""
    closure_names: set[str] = set()
    inline_ids: set[int] = set()
    for node in ast.walk(scope):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        call_name = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else None
        )
        if call_name not in _GOVERNOR_CALLS:
            continue
        # ``governed_request(send, ...)`` → send is positional arg 0.
        # ``govern_if_arxiv(url, send, ...)`` → send is positional arg 1 (the
        # first arg is the URL). Pick the send arg by the call's signature.
        if call_name == "govern_if_arxiv":
            send_arg: ast.AST | None = node.args[1] if len(node.args) >= 2 else None
        else:
            send_arg = node.args[0] if node.args else None
        for kw in node.keywords:
            if kw.arg in ("send", "fn") and kw.value is not None:
                send_arg = kw.value
        if isinstance(send_arg, ast.Name):
            closure_names.add(send_arg.id)
        elif send_arg is not None:
            inline_ids.add(id(send_arg))
    return closure_names, inline_ids


def _flag(rel: str, node: ast.AST, out: list[str]) -> None:
    out.append(
        f"{rel}:{node.lineno}: raw external HTTP egress that is NOT routed "
        f"through the host-global arXiv governor — wrap the send in a closure "
        f"passed to acquisition.arxiv.rate_governor.govern_if_arxiv(url, send) "
        f"(or governed_request for a statically-arXiv host). If this URL ever "
        f"resolves to an arxiv.org / export.arxiv.org host, an ungoverned fetch "
        f"here re-opens the un-spaced-parallel-stream hole that historically "
        f"IP-banned the box — REGARDLESS of which module it lives in."
    )


def _scope_violations(
    scope: ast.AST,
    *,
    rel: str,
    inherited_clients: frozenset[str],
    governed_closures: frozenset[str],
    governed_inline_ids: frozenset[int],
    out: list[str],
) -> None:
    """Recursively find ungoverned egress in ``scope`` (a Module / FunctionDef).

    Client names visible here = the ones bound in this scope ∪ the inherited set
    from enclosing scopes (a closure sees the clients of its enclosing function).

    Governance is WHOLE-CLOSURE: a nested ``def`` whose name was passed to a
    ``governed_request(...)`` call (in this scope or an enclosing one), and any
    inline ``lambda`` handed to ``governed_request``, are SANCTIONED sends — every
    egress inside them is governed and skipped. This flows down through recursion
    via ``governed_closures`` / ``governed_inline_ids`` so the egress INSIDE the
    closure's own scope (e.g. ``with httpx.Client() as c: return c.get(...)``) is
    not re-flagged when we recurse into that closure."""
    here = frozenset(inherited_clients | _client_names_bound_directly_in(scope))
    new_closures, new_inline = _governed_sends(scope)
    gov_closures = frozenset(governed_closures | new_closures)
    gov_inline = frozenset(governed_inline_ids | new_inline)

    def _collect(node: ast.AST, scoped_clients: set[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name in gov_closures:
                    continue  # whole governed send closure — its egress is OK
                _scope_violations(
                    child, rel=rel, inherited_clients=here,
                    governed_closures=gov_closures,
                    governed_inline_ids=gov_inline, out=out,
                )
                continue
            if isinstance(child, ast.ClassDef):
                for m in child.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        _scope_violations(
                            m, rel=rel, inherited_clients=here,
                            governed_closures=gov_closures,
                            governed_inline_ids=gov_inline, out=out,
                        )
                continue
            if isinstance(child, ast.Lambda):
                if id(child) in gov_inline:
                    continue  # inline governed send — its egress is OK
                _collect(child, scoped_clients)  # ungoverned lambda shares scope
                continue
            if isinstance(child, ast.Call) and _is_egress_call(child, scoped_clients):
                _flag(rel, child, out)
            _collect(child, scoped_clients)

    _collect(scope, set(here))


def _is_test_file(rel: str) -> bool:
    parts = Path(rel).parts
    if parts and parts[0] == "tests":
        return True
    stem = Path(rel).name
    return stem.startswith("test_") or stem.endswith("_test.py")


def _in_egress_scan_scope(rel: str) -> bool:
    """Whether ``rel`` is in the acquisition tree the host-based governor
    invariant binds (every external fetcher here must route through
    ``govern_if_arxiv`` / ``governed_request``)."""
    return any(rel.startswith(prefix) for prefix in _EGRESS_SCAN_DIRS)


def find_violations(root: Path = _REPO) -> list[str]:
    """Return ``path:line: message`` strings for every raw external HTTP egress
    in the acquisition tree that is NOT routed through the host-based governor."""
    out: list[str] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root).as_posix()
        if not _in_egress_scan_scope(rel):
            continue
        if rel in _ALLOWED_FILES or _is_test_file(rel):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        _scope_violations(
            tree,
            rel=rel,
            inherited_clients=frozenset(),
            governed_closures=frozenset(),
            governed_inline_ids=frozenset(),
            out=out,
        )
    return out


def main() -> int:
    violations = find_violations()
    if violations:
        print("arXiv rate-governor egress violations:")
        for line in violations:
            print(f"  {line}")
        print(
            "\nEvery external HTTP fetcher in the acquisition tree must route its "
            "send through the host-based arXiv governor "
            "(acquisition/arxiv/rate_governor.py: govern_if_arxiv(url, send), or "
            "governed_request for a statically-arXiv host) so that ANY arxiv.org / "
            "export.arxiv.org URL — wherever it is fetched — is held under the "
            "host-global >=3s spacing + 429 ban sentinel. A raw ungoverned external "
            "egress re-opens the un-spaced-parallel-stream hole that historically "
            "IP-banned the box. Governed seam: the governor + throttle.py, a send "
            "closure passed to govern_if_arxiv / governed_request, and test files."
        )
        return 1
    print(
        "OK: no ungoverned raw external HTTP egress in the acquisition tree "
        "outside the host-based rate-governor seam."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
