"""Negative static type proof: wrong-signature adapter that mypy MUST reject.

This module is checked by ``test_negative_type_proof`` which runs mypy on
this file and asserts that mypy reports type errors.  If mypy ever stops
rejecting this assignment, the Protocol has lost its teeth.
"""

from __future__ import annotations

from collections.abc import Sequence

from substrate.corpus_contract.protocol import CorpusAdapter, CorpusHit, FetchResult


class WrongSignatureAdapter:
    """An adapter whose method signatures do NOT match the CorpusAdapter Protocol.

    - ``search`` takes ``int`` instead of ``str``
    - ``fetch`` returns ``str`` instead of ``FetchResult``
    """

    def search(self, query: int) -> Sequence[CorpusHit]:
        return ()

    def fetch(self, id: str) -> str:
        return ""


# This assignment MUST be rejected by mypy.
# The Protocol requires search(str) -> Sequence[CorpusHit] and
# fetch(str) -> FetchResult.
_adapter: CorpusAdapter = WrongSignatureAdapter()
