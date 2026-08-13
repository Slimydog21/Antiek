"""Link Monster — the front door of the Antiek graph.

Paste any link (X, YouTube, Instagram, TikTok, Substack, or the
generic web); the Monster digests everything extractable — image,
video, transcript, text — labels each artifact with its provenance,
and stews it into the single-writer substrate graph.

Modules:

- ``platforms`` — URL → platform classification
- ``fetchguard`` — SSRF guard (mandatory for a paste-any-URL server)
- ``oembed`` — extraction ladder: oEmbed → OpenGraph → DOM
- ``digest`` — the orchestrator: ``digest_url``
- ``store`` — graph writes: ``store_digest``

Spec: ``docs/specs/link-monster-spec.md`` (art direction:
``docs/specs/link-monster-art-direction.md``).
"""

from .digest import DigestResult, LinkDigest, digest_url
from .fetchguard import UnsafeUrlError
from .platforms import Platform, classify
from .store import StoreResult, get_digest, list_digests, store_digest

__all__ = [
    "DigestResult",
    "LinkDigest",
    "Platform",
    "StoreResult",
    "UnsafeUrlError",
    "classify",
    "digest_url",
    "get_digest",
    "list_digests",
    "store_digest",
]
