"""Sub-LLM tool-calling pattern for the RLM DAG architecture.

Sprint 9 day 2-3 port of Researchmaxx ``rlm_tools.py``. Deferred
from Sprint 3 because it was waiting on the dispatch router (Sprint
3) AND the graph search layer (Sprint 3) — both now landed, so the
port reads cleanly against the substrate.

**The pattern.** The orchestrator delegates heavy-token-output tool
calls to sub-LLMs so the orchestrator's context window stays clean.
A sub-LLM calls tools (web search, URL fetch, graph retrieval),
processes the verbose output, and returns only a ~500-token
synthesis to the orchestrator.

Used by the connector role bridge when the seed pair has > N hops
of separation and ``substrate.graph.traverse.top_n_paths`` alone
isn't enough — the connector falls back to a sub-LLM that can
iteratively search the graph + web.

Quick start::

    from substrate.graph.rlm_tools import SubLLMWithTools, equipped_llm_batch

    sub = SubLLMWithTools()
    sub.register_builtin("web_search")
    sub.register_builtin("search_graph")
    answer = sub.run(
        "What is PsiQuantum's photonic-fusion approach?",
        investigation_id="inv-1",
    )
    # answer is a ~500-token synthesis; raw tool output never returned

    tasks = [
        {"prompt": "What is QEC threshold?", "tools": ["web_search", "search_graph"]},
        {"prompt": "Who are PsiQuantum's competitors?", "tools": ["web_search"]},
    ]
    answers = equipped_llm_batch(tasks, investigation_id="inv-1")

**Antiek changes from upstream:**

- ``call_openrouter`` → ``substrate.dispatch.dispatch`` (role-tier-aware,
  cost-tracking via DISPATCH_CALL events).
- ``search.py`` direct import → ``substrate.graph.search.search`` +
  ``connect_read`` from ``runtime.db_lock``.
- DDG / SerpAPI / fetch_url external network calls preserved as-is;
  they go through ``requests`` and have no Antiek-specific
  substrate dependency.
- ``HERMES_RESEARCH_GRAPH_DB`` → ``ANTIEK_DUCKDB_PATH``.

**Architecture notes:**

- Max 3 tool-call rounds per sub-LLM (``MAX_TOOL_ROUNDS``). Prevents
  infinite search loops. If the LLM hasn't produced a final answer
  by round 3, the last tool results are force-fed as context and a
  final synthesis is demanded.
- Tool output is truncated to ``MAX_TOOL_OUTPUT_CHARS`` (8000) before
  it reaches the LLM. Raw web pages can be enormous; truncation
  prevents context exhaustion on the sub-LLM side too.
- Sensitive to dispatch config (``substrate/dispatch/config.yaml``)
  for tier routing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from typing import Any

from orchestration.rlm.prime_agent_backend import (
    PrimeAgentOutcome,
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
)

# Ensure substrate root on path.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

try:
    import requests  # type: ignore[import-not-found]
    _REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover — best-effort
    requests = None  # type: ignore[assignment]
    _REQUESTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


MAX_TOOL_ROUNDS = 3
MAX_TOOL_OUTPUT_CHARS = 8_000
DEFAULT_SYNTHESIS_MAX_TOKENS = 600
DEFAULT_TEMPERATURE = 0.0

# Tier the sub-LLM dispatches at. Flash is the right default — sub-LLMs
# do iterative tool calls, so latency cost compounds. The connector
# bridge can override via SubLLMWithTools(role=...).
DEFAULT_SUB_LLM_ROLE = "evidence_retriever"
PRIME_EVIDENCE_LABEL = "[Supplemental Prime Agent evidence; non-canonical]"


# ---------------------------------------------------------------------------
# Tool system prompt
# ---------------------------------------------------------------------------


_TOOL_SYSTEM_PROMPT = """\
You are a research sub-agent with access to tools. Your job is to answer the
user's question by calling tools as needed, then producing a concise synthesis.

AVAILABLE TOOLS:
{tool_descriptions}

RESPONSE FORMAT:
You MUST respond with valid JSON only. Choose exactly ONE of these two formats:

1. To call a tool:
   {{"tool_call": {{"name": "<tool_name>", "arguments": {{"arg1": "val1", ...}}}}}}

2. To return your final answer (only after you have enough information):
   {{"final_answer": "<your concise synthesis>"}}

RULES:
- You may call up to {max_rounds} tools per question.
- After each tool call, you will receive the tool's output and may call another
  tool or provide your final answer.
- When you give your final answer, synthesize what you learned concisely.
  Target ~500 tokens or fewer. Be factual, cite sources if you can, and
  note any gaps or uncertainty.
- Do NOT include raw tool output in your final answer — synthesize.
- If a tool returns an error or empty result, note that and try alternatives
  or return a hedged answer.
- NEVER output prose before or after the JSON. ONLY the JSON object."""


def _build_system_prompt(
    tool_specs: list[dict], max_rounds: int,
) -> str:
    """Render the tool list into the system prompt."""
    if not tool_specs:
        return _TOOL_SYSTEM_PROMPT.format(
            tool_descriptions="(none — answer from your own knowledge)",
            max_rounds=max_rounds,
        )
    descs = []
    for ts in tool_specs:
        params_desc = ", ".join(
            f"{p['name']}: {p.get('type', 'string')}"
            + (f" (default: {p['default']})" if "default" in p else "")
            for p in ts.get("parameters", [])
        )
        descs.append(
            f"  {ts['name']}({params_desc}): {ts.get('description', 'No description')}"
        )
    return _TOOL_SYSTEM_PROMPT.format(
        tool_descriptions="\n".join(descs), max_rounds=max_rounds,
    )


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def extract_json(text: str) -> Any:
    """Strict JSON parse with fallback: extract the largest ``{...}``
    or ``[...]`` window. Strips markdown code fences. Raises
    ``ValueError`` only when nothing parses."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            i = text.find(open_ch)
            j = text.rfind(close_ch)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(text[i: j + 1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(
            f"Could not parse JSON from sub-LLM response: {text[:500]}"
        ) from None


# ---------------------------------------------------------------------------
# Built-in tool: web_search
# ---------------------------------------------------------------------------


def web_search(query: str) -> str:
    """Search the web. Prefers SerpAPI when ``SERPAPI_API_KEY`` is set;
    falls back to DuckDuckGo's HTML interface (no key needed).

    Returns up to 5 formatted search-result snippets or an error
    string. Never raises — every failure path returns a diagnostic
    string the sub-LLM can act on."""
    if not _REQUESTS_AVAILABLE:
        return "web_search error: requests library not installed"

    # Route every send through the host-based arXiv governor (SPR-09 round-5).
    # serpapi.com / html.duckduckgo.com are NON-arXiv hosts, so ``govern_if_arxiv``
    # is a NO-OP here (it calls ``send()`` directly) — but routing uniformly keeps
    # this builtin tool on the governed seam (no raw external egress exported from
    # ``substrate.graph`` outside the governor), exactly like the acquisition
    # fetchers. Both hosts are static literals (no redirect-to-arXiv risk), so the
    # initial-host check suffices and no per-hop hook is needed.
    from acquisition.arxiv.rate_governor import (
        canonical_arxiv_throttle,
        govern_if_arxiv,
    )

    serpapi_key = os.environ.get("SERPAPI_API_KEY")
    if serpapi_key:
        try:
            _serp_url = "https://serpapi.com/search"

            def _serp_send() -> requests.Response:
                return requests.get(
                    _serp_url,
                    params={
                        "q": query, "api_key": serpapi_key,
                        "engine": "google", "num": 5,
                    },
                    timeout=15,
                )

            r = govern_if_arxiv(
                _serp_url, _serp_send, throttle=canonical_arxiv_throttle()
            )
            r.raise_for_status()
            data = r.json()
            organic = data.get("organic_results", [])
            if not organic:
                return f"(no results for: {query})"
            snippets = []
            for i, res in enumerate(organic[:5], 1):
                title = res.get("title", "(no title)")
                snippet = res.get("snippet", "")
                link = res.get("link", "")
                snippets.append(
                    f"{i}. {title}\n   {snippet}\n   URL: {link}"
                )
            return "\n\n".join(snippets)
        except Exception:  # pragma: no cover — fall through to DDG
            pass

    try:
        _ddg_url = "https://html.duckduckgo.com/html/"

        def _ddg_send() -> requests.Response:
            return requests.get(
                _ddg_url,
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; Antiek/1.0)"},
                timeout=15,
            )

        r = govern_if_arxiv(_ddg_url, _ddg_send, throttle=canonical_arxiv_throttle())
        r.raise_for_status()
    except Exception as e:
        return f"web_search error: {e}"

    return _parse_ddg_html(r.text, query=query)


def _parse_ddg_html(html: str, *, query: str) -> str:
    """Parse DuckDuckGo HTML search results. Extracted as a pure
    function for testability."""
    from html.parser import HTMLParser

    class DDGParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.results: list[dict] = []
            self._current: dict | None = None
            self._in_snippet = False
            self._in_title = False
            self._buf: str = ""
            self._link: str = ""

        def handle_starttag(self, tag, attrs):
            attrs_d = dict(attrs)
            if tag == "a" and "result__a" in attrs_d.get("class", ""):
                self._current = {"title": "", "snippet": "", "link": ""}
                self._in_title = True
                self._buf = ""
                self._link = attrs_d.get("href", "")
            elif tag == "a" and "result__snippet" in attrs_d.get("class", ""):
                if self._current is not None:
                    self._current["link"] = self._link
                    self._in_snippet = True
                    self._buf = ""

        def handle_endtag(self, tag):
            if tag == "a" and self._in_title and self._current:
                self._current["title"] = self._buf.strip()
                self._in_title = False
                self._buf = ""
            elif tag == "a" and self._in_snippet and self._current:
                self._current["snippet"] = self._buf.strip()
                self._in_snippet = False
                self._buf = ""
                if self._current["title"] or self._current["snippet"]:
                    self.results.append(self._current)
                self._current = None

        def handle_data(self, data):
            if self._in_title or self._in_snippet:
                self._buf += data

    parser = DDGParser()
    parser.feed(html)
    if not parser.results:
        return f"(no results for: {query})"
    snippets = []
    for i, res in enumerate(parser.results[:5], 1):
        title = res.get("title", "(no title)")
        snippet = res.get("snippet", "")
        link = res.get("link", "")
        snippets.append(f"{i}. {title}\n   {snippet}\n   URL: {link}")
    return "\n\n".join(snippets)


# ---------------------------------------------------------------------------
# Built-in tool: fetch_url
# ---------------------------------------------------------------------------


_FETCH_URL_MAX_REDIRECTS = 10


def fetch_url(url: str) -> str:
    """Fetch a URL + extract text. Strips HTML tags, scripts, styles.
    Returns the first ~5000 chars; caller may further truncate.

    ARXIV RATE GOVERNANCE (SPR-09 round-5). This is an LLM-callable builtin tool
    (``_BUILTIN_TOOLS["fetch_url"]``, re-exported from ``substrate.graph``) that
    fetches an ARBITRARY model-supplied URL — including, potentially, an
    ``arxiv.org`` URL. It uses ``requests`` (not httpx), so the httpx per-request
    event hook that makes the acquisition fetchers redirect-safe does NOT apply
    here. To keep this off the existential arXiv egress surface, every hop is
    routed through ``acquisition.arxiv.rate_governor.govern_if_arxiv`` on the
    hop's OWN host: redirects are followed MANUALLY with ``allow_redirects=False``
    so each ``Location`` host is re-checked and an arXiv hop — initial OR a
    redirect target — is held under the host-global flock + >=3s spacing + 429 ban
    sentinel (a non-arXiv hop is fetched directly, unchanged). A non-arXiv→arXiv
    302 can no longer reach arXiv ungoverned. Zero production callers today, but it
    is live-exported, so the governance is by construction, not by trust."""
    if not _REQUESTS_AVAILABLE:
        return "fetch_url error: requests library not installed"

    from urllib.parse import urljoin

    try:
        from acquisition.arxiv.rate_governor import (
            canonical_arxiv_throttle,
            govern_if_arxiv,
        )
    except Exception as e:  # pragma: no cover — defensive: never fetch ungoverned
        return f"fetch_url error: arXiv rate governor unavailable — {e!r}"

    headers = {"User-Agent": "Mozilla/5.0 (compatible; Antiek/1.0)"}
    current = url
    try:
        # Manual redirect loop: each hop is governed on its OWN host so an arXiv
        # redirect TARGET cannot be fetched ungoverned (requests' allow_redirects
        # would follow it without the per-hop host check). ``govern_if_arxiv``
        # routes an arXiv host through the host-global governor, a non-arXiv host
        # directly. The 429 ban sentinel is recorded inside ``govern_if_arxiv``'s
        # governed_request via the throttle's note_response.
        for _ in range(_FETCH_URL_MAX_REDIRECTS + 1):
            def _send(_u: str = current) -> requests.Response:
                return requests.get(
                    _u, headers=headers, timeout=20, allow_redirects=False,
                )

            r = govern_if_arxiv(current, _send, throttle=canonical_arxiv_throttle())
            if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                location = r.headers.get("Location") or r.headers.get("location")
                if not location:
                    break
                current = urljoin(current, location)
                continue
            r.raise_for_status()
            break
        else:
            return (
                f"fetch_url error for {url!r}: too many redirects "
                f"(> {_FETCH_URL_MAX_REDIRECTS})"
            )
    except Exception as e:
        return f"fetch_url error for {url!r}: {e}"

    text = _extract_text_from_html(r.text)
    max_chars = 5_000
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [truncated at {max_chars} chars]"
    if not text.strip():
        return f"(empty content from {url})"
    return f"Source: {url}\n\n{text.strip()}"


def _extract_text_from_html(html: str) -> str:
    """Basic HTML-to-text extraction without external dependencies."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<head[^>]*>.*?</head>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<footer[^>]*>.*?</footer>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    for tag in ("p", "div", "article", "section", "li",
                "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"):
        html = re.sub(f"<{tag}[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Built-in tool: search_graph
# ---------------------------------------------------------------------------


def search_graph(query: str, top_k: int = 5) -> str:
    """Search the Antiek knowledge graph for chunks + edges. Uses
    ``substrate.graph.search.search`` with a read-only connection.
    Returns a formatted string the sub-LLM can read directly."""
    try:
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path, ensure_initialized
        from substrate.graph.search import SentenceTransformerEmbedding
        from substrate.graph.search import search as _graph_search
    except ImportError as e:
        return f"search_graph error: import failed — {e!r}"

    db_path = default_db_path()
    if not os.path.exists(db_path):
        return f"search_graph error: graph database not found at {db_path}"

    try:
        ensure_initialized(db_path)
    except Exception as e:
        return f"search_graph error: ensure_initialized failed — {e!r}"

    try:
        embedder = SentenceTransformerEmbedding()
    except Exception as e:
        return (
            f"search_graph error: embedder unavailable "
            f"(sentence-transformers not installed?) — {e!r}"
        )

    try:
        con = connect_read(db_path)
    except Exception as e:
        return f"search_graph error: connect_read failed — {e!r}"

    try:
        result = _graph_search(
            con, query, model=embedder, top_k=int(top_k),
            with_edges=True,
        )
    except Exception as e:
        return f"search_graph error: {e!r}"
    finally:
        with suppress(Exception):
            con.close()

    return _format_graph_search_result(result, query=query)


def _format_graph_search_result(result: dict, *, query: str) -> str:
    """Render the graph search result as a sub-LLM-friendly string."""
    parts = [f"Graph search results for: {query}\n"]
    chunks = result.get("results", [])
    if not chunks:
        parts.append("(no chunk matches found)")
    else:
        parts.append(f"Top {len(chunks)} chunk matches:\n")
        for i, c in enumerate(chunks, 1):
            parts.append(
                f"{i}. [{c.get('document_title', '?')}] "
                f"(tier={c.get('source_tier', '?')}, "
                f"sim={c.get('similarity', '?')})\n"
                f"   {c.get('chunk_text', '')}"
            )
            edges = c.get("edges", [])
            if edges:
                edge_strs = []
                for e in edges[:5]:
                    s = e.get("source", {}).get("label", "?")
                    t = e.get("target", {}).get("label", "?")
                    rel = e.get("relation", "?")
                    edge_strs.append(f"({s}) —[{rel}]→ ({t})")
                parts.append(f"   Edges: {'; '.join(edge_strs)}")
            parts.append("")
    node_matches = result.get("node_matches", [])
    if node_matches:
        parts.append(f"Node label matches ({len(node_matches)}):")
        for n in node_matches[:5]:
            parts.append(
                f"  - {n.get('label', '?')} [{n.get('node_type', '?')}]"
                + (
                    f": {n.get('description', '')}"
                    if n.get("description") else ""
                )
            )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Built-in tool registry
# ---------------------------------------------------------------------------


_BUILTIN_TOOLS: dict[str, dict] = {
    "web_search": {
        "fn": web_search,
        "description": "Search the web (DuckDuckGo or SerpAPI).",
        "parameters": [
            {"name": "query", "type": "string", "description": "The search query"},
        ],
    },
    "fetch_url": {
        "fn": fetch_url,
        "description": "Fetch and extract text content from a URL.",
        "parameters": [
            {"name": "url", "type": "string", "description": "The URL to fetch"},
        ],
    },
    "search_graph": {
        "fn": search_graph,
        "description": (
            "Search the Antiek knowledge graph for semantically similar "
            "chunks and their associated edges."
        ),
        "parameters": [
            {"name": "query", "type": "string",
             "description": "Natural-language search query"},
            {"name": "top_k", "type": "integer", "default": 5,
             "description": "Number of top results"},
        ],
    },
}


def get_builtin_tool_names() -> list[str]:
    return list(_BUILTIN_TOOLS.keys())


def get_tool_specs(names: list[str]) -> list[dict]:
    """Return tool specs (metadata, not callables) for the given names."""
    specs = []
    for name in names:
        if name in _BUILTIN_TOOLS:
            t = _BUILTIN_TOOLS[name]
            specs.append({
                "name": name,
                "description": t["description"],
                "parameters": t["parameters"],
            })
    return specs


# ---------------------------------------------------------------------------
# SubLLMWithTools
# ---------------------------------------------------------------------------


# Callable shape for the LLM injection. Tests pass a stub; production
# uses the substrate dispatcher closure built in ``_default_llm_call``.
LLMCall = Callable[[str, str], str]
"""``llm_call(system, user) -> str``."""


def _default_llm_call(
    *, investigation_id: str, role: str,
) -> LLMCall:
    """Build a dispatcher closure for the production path. Routes
    through ``substrate.dispatch.dispatch`` so cost tracking +
    fallback chains apply uniformly."""
    from substrate.dispatch import dispatch

    def _call(system: str, user: str) -> str:
        prompt = system + "\n\n" + user
        result = dispatch(
            prompt, role,
            investigation_id=investigation_id,
        )
        return result.text

    return _call


class SubLLMWithTools:
    """A sub-LLM that can call tools, process the output, and return
    a synthesis.

    ``run(prompt)`` returns a concise (~500 token) synthesis. All
    intermediate tool calls and raw tool output stay inside the
    object.

    The LLM is **callable-injected** via ``llm_call``. Construct
    without ``llm_call`` to use the substrate dispatcher (requires
    ``investigation_id``); pass a stub for tests.
    """

    def __init__(
        self,
        *,
        llm_call: LLMCall | None = None,
        investigation_id: str | None = None,
        role: str = DEFAULT_SUB_LLM_ROLE,
        max_rounds: int = MAX_TOOL_ROUNDS,
        temperature: float = DEFAULT_TEMPERATURE,
        synthesis_max_tokens: int = DEFAULT_SYNTHESIS_MAX_TOKENS,
    ):
        if llm_call is None:
            if investigation_id is None:
                raise ValueError(
                    "SubLLMWithTools requires either ``llm_call`` (tests) or "
                    "``investigation_id`` (production — the dispatch router "
                    "needs an id to scope DISPATCH_CALL events)."
                )
            llm_call = _default_llm_call(
                investigation_id=investigation_id, role=role,
            )
        self.llm_call = llm_call
        self.max_rounds = max_rounds
        self.temperature = temperature
        self.synthesis_max_tokens = synthesis_max_tokens
        self._tools: dict[str, dict] = {}

    def register_tool(
        self,
        name: str,
        fn: Callable,
        description: str,
        parameters: list[dict],
    ) -> None:
        """Register a tool the sub-LLM can call."""
        self._tools[name] = {
            "fn": fn, "description": description, "parameters": parameters,
        }

    def register_builtin(self, name: str) -> None:
        """Register a built-in tool by name."""
        if name not in _BUILTIN_TOOLS:
            raise ValueError(f"Unknown built-in tool: {name!r}")
        self._tools[name] = dict(_BUILTIN_TOOLS[name])

    def register_builtins(self, names: list[str]) -> None:
        for name in names:
            self.register_builtin(name)

    def run(self, prompt: str) -> str:
        """Run the tool-calling loop. Returns the synthesized answer.

        On any parse failure or unknown-tool error, the loop continues
        with an error message fed back to the sub-LLM so it can
        recover. On max-rounds exhaustion, a final synthesis is
        forced.
        """
        tool_specs = [
            {
                "name": name,
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for name, t in self._tools.items()
        ]
        system = _build_system_prompt(tool_specs, self.max_rounds)
        user_parts: list[str] = [prompt]

        for _round in range(self.max_rounds):
            raw = self._call_llm(system, "\n\n".join(user_parts))
            try:
                parsed = extract_json(raw)
            except ValueError as e:
                return (
                    f"[Parse error in tool-calling loop: {e}] "
                    f"Raw response: {raw[:500]}"
                )
            if "final_answer" in parsed:
                return str(parsed["final_answer"])
            if "tool_call" in parsed:
                tc = parsed["tool_call"]
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})
                if tool_name not in self._tools:
                    err = (
                        f"Unknown tool: {tool_name!r}. "
                        f"Available: {list(self._tools)}"
                    )
                    user_parts.append(f"Error: {err}")
                    continue
                result = self._execute_tool(tool_name, tool_args)
                if len(result) > MAX_TOOL_OUTPUT_CHARS:
                    result = result[:MAX_TOOL_OUTPUT_CHARS] + (
                        f"\n\n... [truncated, {len(result)} total chars]"
                    )
                user_parts.append(
                    f"Tool result from {tool_name}:\n\n{result}"
                )
                continue
            return f"[Unexpected JSON from sub-LLM] Raw: {raw[:500]}"

        # Max rounds exhausted — force a final synthesis.
        user_parts.append(
            "You have reached the maximum number of tool calls. "
            "Synthesize your best answer NOW using the information "
            "gathered above. Return ONLY: "
            '{"final_answer": "<your synthesis>"}'
        )
        raw = self._call_llm(system, "\n\n".join(user_parts))
        try:
            parsed = extract_json(raw)
            if "final_answer" in parsed:
                return str(parsed["final_answer"])
        except ValueError:
            pass
        return f"[Max rounds exhausted; raw response] {raw[:500]}"

    def _call_llm(self, system: str, user: str) -> str:
        return self.llm_call(system, user)

    def _execute_tool(self, name: str, args: dict) -> str:
        fn = self._tools[name]["fn"]
        try:
            return str(fn(**args))
        except TypeError as e:
            return (
                f"Tool {name!r} argument error: {e}. "
                f"Expected params: {self._tools[name]['parameters']}"
            )
        except Exception as e:
            return f"Tool {name!r} execution error: {e}"


# ---------------------------------------------------------------------------
# Batch dispatch
# ---------------------------------------------------------------------------


def equipped_llm_batch(
    tasks: list[dict],
    *,
    llm_call: LLMCall | None = None,
    investigation_id: str | None = None,
    role: str = DEFAULT_SUB_LLM_ROLE,
    max_parallel: int = 6,
    max_rounds: int = MAX_TOOL_ROUNDS,
    temperature: float = DEFAULT_TEMPERATURE,
    prime_backend: PrimeAgentRLMBackend | None = None,
    prime_outcome_sink: Callable[[PrimeAgentOutcome], None] | None = None,
) -> list[str]:
    """Run multiple tool-equipped sub-LLM calls in parallel.

    Each task: ``{"prompt": str, "tools": ["web_search", ...]}``.
    Returns answers in input order. ``llm_call`` is shared across
    tasks (tests); production resolves a fresh dispatcher per
    investigation."""
    n = len(tasks)
    if n == 0:
        return []

    def _build_sub() -> SubLLMWithTools:
        return SubLLMWithTools(
            llm_call=llm_call,
            investigation_id=investigation_id,
            role=role, max_rounds=max_rounds,
            temperature=temperature,
        )

    effective_prompts = [str(task["prompt"]) for task in tasks]
    if prime_backend is not None:
        # Prime requests are deliberately issued in input order. The canonical
        # sub-LLM work may still fan out, but receipt/evidence ordering remains
        # deterministic and no graph-write tool is exposed to Prime.
        for i, task in enumerate(tasks):
            with suppress(Exception):
                outcome = prime_backend.run(PrimeAgentRequest(
                    prompt=str(task["prompt"]),
                    workflow="rlm-tool-batch",
                    request_id=(
                        f"{investigation_id or 'unscoped'}:tool-batch:{i:04d}"
                    ),
                ))
                if prime_outcome_sink is not None:
                    with suppress(Exception):
                        prime_outcome_sink(outcome)
                if (
                    outcome.receipt.state.value == "success"
                    and outcome.evidence is not None
                    and outcome.evidence.supplemental
                ):
                    effective_prompts[i] += (
                        f"\n\n{PRIME_EVIDENCE_LABEL}\n{outcome.evidence.text}"
                    )

    def _run_one(index: int, task: dict[str, Any]) -> str:
        sub = _build_sub()
        sub.register_builtins(task.get("tools", []))
        return sub.run(effective_prompts[index])

    results: list[str | None] = [None] * n
    if n == 1 or max_parallel <= 1:
        for i, task in enumerate(tasks):
            results[i] = _run_one(i, task)
        return [r for r in results if r is not None]

    with ThreadPoolExecutor(max_workers=min(max_parallel, n)) as ex:
        futures = {ex.submit(_run_one, i, task): i for i, task in enumerate(tasks)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except Exception as exc:
                results[i] = f"ERROR in batch task {i}: {exc}"
    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Category → tools (for connector / orchestrator wiring)
# ---------------------------------------------------------------------------


CATEGORY_TOOL_MAP: dict[str, list[str]] = {
    "fact_retrieval": ["web_search", "search_graph"],
    "parameter_extraction": ["search_graph"],
    "cross_domain_connection": ["search_graph"],
    "synthesis": [],
    "verification": [],
}


def tools_for_category(category: str) -> list[str]:
    """Recommended tool list for a DAG node / role category."""
    return CATEGORY_TOOL_MAP.get(category, [])
