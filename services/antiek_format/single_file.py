"""Single-file ``name.antiek.html`` variant (SPR-04 M5).

For share paths where a ZIP is awkward: one HTML file that opens anywhere,
carrying BOTH the SPR-02 doc-model island (already embedded by the renderer)
AND a detached Ed25519 signature in a second inert
``<template data-antiek="signature">`` island.

Signature scheme (``ed25519-over-rendered-html-excised-sig-v1``)
---------------------------------------------------------------
We sign the WHOLE rendered projection with the signature island EXCISED — the
signed bytes are exactly the ``projection.html`` the renderer produced, before
the signature template is injected. On verify we strip the signature island
and check the signature over the remaining bytes.

Why sign the rendered file and not only the doc-model island: the sprint
requires that BOTH a tampered island AND tampered rendered markup fail
verification. Signing only the island would miss markup tampering. Signing
the whole (sig-excised) file catches both and is trivially verifiable — strip
one known inert template, verify the rest. The doc-model island is inside the
signed bytes, so the canonical payload is transitively covered.

The trade-off, recorded in the amendment doc: the single-file signature is
over the DERIVED projection, not the canonical ``content.tiptap.json`` — that
is what the ``.antiek`` container's own signature is for. A single file is a
share artifact, not the canonical store. The injection is deterministic (one
known marker, fixed position), so build is reproducible.

Zero-script: the signature island is an inert ``<template>`` exactly like the
doc-model island; the single file passes the same zero-script gate.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys

try:
    from .signature import Keypair, sign_bytes, verify_bytes
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from services.antiek_format.signature import (  # type: ignore[no-redef]
        Keypair,
        sign_bytes,
        verify_bytes,
    )

SINGLE_FILE_SIG_SCHEME: str = "ed25519-over-rendered-html-excised-sig-v1"

_SIG_OPEN: str = '<template data-antiek="signature">'
_SIG_CLOSE: str = "</template>"
_SIG_ISLAND_RE = re.compile(
    re.escape(_SIG_OPEN) + r".*?" + re.escape(_SIG_CLOSE), re.DOTALL
)


def build_single_file(projection_html: str, *, keypair: Keypair) -> str:
    """Wrap a rendered projection into a signed single-file ``.antiek.html``.

    ``projection_html`` is the SPR-02 renderer output (it already carries the
    doc-model island). Deterministic for the same projection + keypair: the
    signed bytes, the canonical-JSON signature island, and the fixed injection
    point are all stable.
    """
    if _SIG_ISLAND_RE.search(projection_html):
        raise ValueError(
            "build_single_file: input already carries a signature island; "
            "refusing to double-wrap"
        )
    signed_bytes = projection_html.encode("utf-8")
    sig = sign_bytes(keypair, signed_bytes)
    payload = {
        "scheme": SINGLE_FILE_SIG_SCHEME,
        "pubkey": keypair.public_key_b64,
        "sig": base64.b64encode(sig).decode("ascii"),
    }
    island = (
        _SIG_OPEN
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        + _SIG_CLOSE
    )
    # Inject just before </body> (one deterministic occurrence). Stripping the
    # island in verify is the exact inverse, recovering signed_bytes verbatim.
    if "</body>" in projection_html:
        return projection_html.replace("</body>", island + "</body>", 1)
    if "</html>" in projection_html:
        return projection_html.replace("</html>", island + "</html>", 1)
    return projection_html + island


def verify_single_file_html(html: str) -> bool:
    """Verify a single-file ``.antiek.html`` given its markup. Returns False on
    ANY failure: missing/garbled signature island, tampered island OR tampered
    rendered markup, malformed key, or a wrong-scheme island."""
    match = _SIG_ISLAND_RE.search(html)
    if match is None:
        return False
    inner = match.group(0)[len(_SIG_OPEN) : -len(_SIG_CLOSE)]
    try:
        payload = json.loads(inner)
        if payload.get("scheme") != SINGLE_FILE_SIG_SCHEME:
            return False
        pubkey = payload["pubkey"]
        sig = base64.b64decode(payload["sig"], validate=True)
    except Exception:
        return False
    # Strip the signature island -> exactly the bytes that were signed.
    recovered = _SIG_ISLAND_RE.sub("", html, count=1)
    return verify_bytes(
        creator_pubkey_b64=pubkey,
        signing_input=recovered.encode("utf-8"),
        signature=sig,
    )


def verify_single_file(path: str) -> bool:
    """Verify a single-file ``.antiek.html`` on disk. Returns False on any
    failure (including a missing/unreadable file)."""
    try:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
    except OSError:
        return False
    return verify_single_file_html(html)


__all__ = [
    "SINGLE_FILE_SIG_SCHEME",
    "build_single_file",
    "verify_single_file",
    "verify_single_file_html",
]
