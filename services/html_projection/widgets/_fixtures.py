"""Canonical widget fixtures (HPRJ SPR-03, orchestrator-owned).

Two fixture sets, both deterministic (no wall-clock, no randomness — every
value is a literal or a pure comprehension over ``range``):

``FIXTURES`` — the golden shapes. For each of the seven widgets, three
size-shapes the sprint's rigor names as the places SVG layout actually
breaks:

  * ``empty``       — the boundary: no data / missing required field. Exercises
                      the deterministic placeholder path (div-by-zero on an
                      empty range, an absent required key).
  * ``typical``     — a normal, legible instance.
  * ``degenerate``  — the large end: a 500-point sparkline, a 40-node
                      dep-graph, long labels. Exercises bounded-output /
                      truncation (the ``+N more`` marker), never an unreadable
                      smear.

These 21 (7 × 3) are what the golden-file tests freeze and the gallery renders.
All values are BENIGN — golden bytes must be stable and reviewable.

``HOSTILE_FIXTURES`` — adversarial inputs (markup injection, ``javascript:``
URLs, ``on*=`` lookalikes) NOT goldened, asserted only to (a) pass the
zero-script gate and (b) not echo their payload unescaped. This is the
separate security lens: the §7 daemon ingests artifacts autonomously, so a
widget that trusts its input is an RCE vector.
"""

from __future__ import annotations

# ── Golden size-shapes: {kind: {shape: data}} ──

FIXTURES: dict[str, dict[str, dict]] = {
    "stat_chip": {
        # empty: both required fields absent -> visible placeholder, no crash.
        "empty": {},
        "typical": {
            "label": "Latency p95",
            "value": "194.85 µs",
            "delta": "-12%",
            "delta_label": "vs locked baseline",
            "tone": "success",
        },
        # degenerate: long label + long value + an unknown tone (-> neutral).
        "degenerate": {
            "label": "Cumulative tokens processed across every investigation "
            "in the operator graph since first light",
            "value": "1,402,981,556",
            "delta": "+18.4%",
            "tone": "not-a-real-tone",
        },
    },
    "bar_chart": {
        "empty": {"bars": [], "title": "No endpoints sampled"},
        "typical": {
            "title": "Latency by endpoint",
            "unit": "ms",
            "bars": [
                {"label": "/health", "value": 12},
                {"label": "/search", "value": 48},
                {"label": "/synthesize", "value": 210},
                {"label": "/ingest", "value": 96},
            ],
        },
        # degenerate: 30 bars + a non-numeric value (-> 0), bounded output.
        "degenerate": {
            "title": "Per-shard write counts",
            "unit": "ops",
            "bars": [{"label": f"shard-{i:02d}", "value": (i * 37) % 211}
                     for i in range(30)]
            + [{"label": "shard-bad", "value": "not-a-number"}],
        },
    },
    "sparkline": {
        "empty": {"points": []},
        "typical": {"points": [3, 5, 4, 8, 6, 9, 7, 11, 10, 13]},
        # degenerate: 500 points + a non-numeric (dropped). Must bound width.
        "degenerate": {
            "points": [(i * 37) % 97 for i in range(500)] + ["nan"],
            "width": 240,
            "height": 40,
        },
    },
    "donut": {
        "empty": {"categories": [], "title": "No sources"},
        "typical": {
            "title": "Sources by class",
            "categories": [
                {"label": "arXiv", "value": 40},
                {"label": "web", "value": 35},
                {"label": "books", "value": 25},
            ],
        },
        # degenerate: 20 categories + a negative (clamped to 0).
        "degenerate": {
            "title": "Token spend by role",
            "categories": [{"label": f"role-{i:02d}", "value": (i * 13) % 50}
                           for i in range(20)]
            + [{"label": "role-neg", "value": -42}],
        },
    },
    "timeline": {
        "empty": {"events": [], "title": "No events"},
        "typical": {
            "title": "Investigation lifecycle",
            "events": [
                {"label": "Prompt decomposed", "at": "T+0",
                 "detail": "7 sub-questions", "tone": "info"},
                {"label": "Gather complete", "at": "T+2m",
                 "detail": "Exa + 3 fetches", "tone": "primary"},
                {"label": "Synthesis graded", "at": "T+4m",
                 "detail": "rubric pass", "tone": "success"},
            ],
        },
        # degenerate: 40 events, unknown tone (-> default), bounded output.
        "degenerate": {
            "title": "Daemon scan log",
            "events": [{"label": f"scan {i:02d}", "at": f"T+{i}m",
                        "detail": f"gap delta {i}", "tone": "weird"}
                       for i in range(40)],
        },
    },
    "dep_graph": {
        "empty": {"nodes": [], "title": "No nodes"},
        "typical": {
            "title": "Sprint dependency",
            "nodes": [
                {"id": "spr01", "label": "SPR-01 format", "tone": "accent"},
                {"id": "spr02", "label": "SPR-02 renderer"},
                {"id": "spr03", "label": "SPR-03 widgets"},
                {"id": "spr04", "label": "SPR-04 shell"},
            ],
            "edges": [
                {"from": "spr01", "to": "spr02"},
                {"from": "spr02", "to": "spr03"},
                {"from": "spr03", "to": "spr04"},
            ],
        },
        # degenerate: 40 nodes + edges incl. a dangling ref (dropped).
        "degenerate": {
            "title": "Module graph",
            "nodes": [{"id": f"n{i:02d}", "label": f"module-{i:02d}"}
                      for i in range(40)],
            "edges": [{"from": f"n{i:02d}", "to": f"n{i + 1:02d}"}
                      for i in range(39)]
            + [{"from": "n00", "to": "does-not-exist"}],
            "direction": "down",
        },
    },
    "cite_block": {
        # empty: title (required) absent -> placeholder.
        "empty": {},
        "typical": {
            "title": "Hachette v. Internet Archive, 2d Cir. (2024)",
            "url": "https://www.courtlistener.com/opinion/hachette",
            "quote": "Controlled digital lending is not a fair use.",
            "accessed": "2026-06-29",
            "tone": "info",
        },
        # degenerate: very long quote + long title, no url.
        "degenerate": {
            "title": "Bartz v. Anthropic — settlement docket and the "
            "implications for pre-payout exposure under prospective use",
            "quote": "The pre-payout exposure posture converts a takedown "
            "into a prospective-use offer; the opt-in-only payout gate is the "
            "load-bearing distinction the section 9.0 architecture rests on, "
            "and it must never be relabeled to a servable class by accident.",
            "accessed": "2026-06-29",
        },
    },
}


# ── Adversarial inputs (security lens — NOT goldened) ──
# Each is (kind, data). The payloads try markup injection, a javascript:
# URL, and an event-handler lookalike. The widget MUST escape them and the
# output MUST pass the zero-script gate; the raw payload must NOT appear.

_XSS = '<script>alert(1)</script>'
_IMG = '"><img src=x onerror=alert(1)>'
_JS_URL = "javascript:alert(document.cookie)"

HOSTILE_FIXTURES: list[tuple[str, dict]] = [
    ("stat_chip", {"label": _XSS, "value": _IMG, "delta": _XSS}),
    ("bar_chart", {"bars": [{"label": _XSS, "value": 5},
                            {"label": _IMG, "value": 9}], "unit": _XSS}),
    ("sparkline", {"points": [1, 2, 3], "stroke": _JS_URL}),
    ("donut", {"categories": [{"label": _XSS, "value": 3},
                              {"label": _IMG, "value": 7}], "title": _XSS}),
    ("timeline", {"events": [{"label": _XSS, "at": _IMG, "detail": _XSS}]}),
    ("dep_graph", {"nodes": [{"id": _XSS, "label": _IMG}],
                   "edges": [{"from": _XSS, "to": _XSS}]}),
    ("cite_block", {"title": _XSS, "url": _JS_URL, "quote": _IMG}),
]

# Active-tag openings that must NEVER appear raw in output: correct escaping
# turns them into ``&lt;script`` / ``&lt;img``. (We do NOT needle-check
# ``onerror=`` or ``javascript:`` as bare substrings — those survive as inert
# ESCAPED TEXT and would false-positive; the zero-script gate is the
# authoritative check that they are not live in an attribute/scheme context.)
HOSTILE_RAW_NEEDLES: tuple[str, ...] = (
    "<script",
    "<img",
)
