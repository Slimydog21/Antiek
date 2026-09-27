"""The companion document (THREAD-CONTRACT §1.12, signed rev 8.10): the
derived findings of a project's or a document's member threads, served as
GatedText entries over the owner-safe ``evidence_index``.

LB-9a lands the store (``store``), the pure entry gate and content hash
(``gate``) and the rights switch (``rights``). No route reads them yet, and
``rights.bound()`` answers None until LB-9d, so every companion-document
route answers ``unavailable_until_rights`` when it lands.
"""
