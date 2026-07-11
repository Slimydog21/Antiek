"""Deterministic read-only federation over independently governed corpora."""

from __future__ import annotations

import math
from dataclasses import dataclass

from substrate.corpus_contract import (
    CorpusAdapter,
    CorpusContractError,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    FetchResult,
)

_RRF_K = 60


@dataclass(frozen=True)
class MountedCorpus:
    name: str
    adapter: CorpusAdapter

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or ":" in self.name:
            raise CorpusContractError("mount name must be a nonempty colon-free exact str")
        if not isinstance(self.adapter, CorpusAdapter):
            raise CorpusContractError("mount adapter must satisfy CorpusAdapter")


class FederatedCorpus:
    """Search every mount and qualify opaque ids as ``mount:id``.

    Reciprocal-rank fusion avoids pretending provider-local scores share a
    calibrated scale. A failing mount aborts the whole search rather than
    silently presenting an incomplete evidence universe.
    """

    def __init__(self, mounts: tuple[MountedCorpus, ...]) -> None:
        if type(mounts) is not tuple or not mounts:
            raise CorpusContractError("federation requires a nonempty exact mount tuple")
        if any(type(mount) is not MountedCorpus for mount in mounts):
            raise CorpusContractError("federation mounts must be exact MountedCorpus values")
        names = tuple(mount.name for mount in mounts)
        if len(names) != len(set(names)):
            raise CorpusContractError("federation mount names must be unique")
        self._mounts = tuple(sorted(mounts, key=lambda mount: mount.name))
        self._by_name = {mount.name: mount for mount in self._mounts}

    def search(self, query: str) -> tuple[CorpusHit, ...]:
        if type(query) is not str:
            raise CorpusContractError("query must be an exact str")
        fused: list[CorpusHit] = []
        for mount in self._mounts:
            local = mount.adapter.search(query)
            if type(local) is not tuple or any(type(hit) is not CorpusHit for hit in local):
                raise CorpusContractError("mounted search returned invalid hits")
            local_ids = tuple(hit.id for hit in local)
            if len(local_ids) != len(set(local_ids)):
                raise CorpusContractError("mounted search returned duplicate ids")
            for rank, hit in enumerate(local, start=1):
                score = 1.0 / float(_RRF_K + rank)
                if not math.isfinite(score):
                    raise CorpusContractError("federated score is not finite")
                fused.append(
                    CorpusHit(
                        id=f"{mount.name}:{hit.id}",
                        score=score,
                        snippet=hit.snippet,
                    )
                )
        return tuple(sorted(fused, key=lambda hit: (-hit.score, hit.id)))

    def fetch(self, id: str) -> FetchResult:
        if type(id) is not str or not id.strip() or ":" not in id:
            raise CorpusContractError("federated id must be a qualified nonempty exact str")
        name, local_id = id.split(":", 1)
        if not name or not local_id:
            raise CorpusContractError("federated id must contain mount and local id")
        mount = self._by_name.get(name)
        if mount is None:
            return CorpusMiss(id=id, reason="unknown corpus mount")
        result = mount.adapter.fetch(local_id)
        if type(result) is CorpusMiss:
            return CorpusMiss(id=id, reason=result.reason)
        if type(result) is not CorpusDocument:
            raise CorpusContractError("mounted fetch returned an unsupported result")
        return result
