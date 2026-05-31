"""Per-account BYOK pipeline configuration (Personal-Reading Lane SPR-08, M2).

The operator registers one or more X accounts, each binding an
``account_handle`` + a stored credential (``cred_id`` from M1) + a
``pipeline_kind``:

  * ``general_feed``   — a deep-research-style ambient pull over the account's
                         accessible timeline / recent-search (the "frolic in
                         information" feed);
  * ``thread_specific``— ingest the threads under a named ``seed`` (a tweet /
                         conversation id, or a search query).

Multiple pipelines may coexist for one account (e.g. one general feed + several
thread-specific). This is the input SPR-09's monitoring mode reads to know what
feeds exist.

DATA-ONLY (§16 box-bounded). This module persists config; it runs NOTHING. There
is no daemon, no scheduler, no polling loop here — the cadence is SPR-09's
operator-invoked refresh. The config record carries ONLY ids / handles / the
kind / the optional seed; it NEVER stores a raw tweet body and NEVER stores the
plaintext key (the key lives encrypted in ``store.py``; this record references it
by the non-secret ``cred_id`` only).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

PIPELINE_KINDS: frozenset[str] = frozenset({"general_feed", "thread_specific"})

_DEFAULT_CONFIG_NAME = "pipelines.json"
_ENV_CONFIG = "ANTIEK_BYOK_PIPELINES"


def _byok_dir() -> Path:
    return Path(__file__).resolve().parent


def _default_config_path() -> str:
    env = os.environ.get(_ENV_CONFIG)
    if env:
        return os.path.expanduser(env)
    return str(_byok_dir() / _DEFAULT_CONFIG_NAME)


@dataclass(frozen=True)
class BYOKPipeline:
    """One registered ingestion pipeline. All fields are NON-SECRET metadata.

    ``cred_id`` references a credential in the encrypted store (never the key
    itself). ``seed`` is required-ish for ``thread_specific`` (a conversation /
    tweet id or a query) and unused for ``general_feed``. ``investigation_id``
    is the substrate investigation the ingested docs attach to.
    """

    pipeline_id: str
    account_handle: str
    cred_id: str
    pipeline_kind: str
    seed: Optional[str] = None
    investigation_id: Optional[str] = None


def _read_config(config_path: str) -> dict:
    p = Path(config_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _write_config(config_path: str, data: dict) -> None:
    p = Path(config_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def register_pipeline(
    account_handle: str,
    cred_id: str,
    pipeline_kind: str,
    *,
    seed: Optional[str] = None,
    investigation_id: Optional[str] = None,
    config_path: Optional[str] = None,
) -> BYOKPipeline:
    """Register a pipeline and persist it. Returns the stored :class:`BYOKPipeline`.

    ``pipeline_kind`` MUST be in :data:`PIPELINE_KINDS`; an unknown kind raises
    ``ValueError``. The record stores only ids / handle / kind / seed — never the
    key, never a tweet body.
    """
    if pipeline_kind not in PIPELINE_KINDS:
        raise ValueError(
            f"unknown pipeline_kind {pipeline_kind!r}; "
            f"must be one of {sorted(PIPELINE_KINDS)}"
        )
    handle = account_handle.lstrip("@")
    pipeline_id = f"pl-x-{uuid.uuid4().hex[:16]}"
    pipeline = BYOKPipeline(
        pipeline_id=pipeline_id,
        account_handle=handle,
        cred_id=cred_id,
        pipeline_kind=pipeline_kind,
        seed=seed,
        investigation_id=investigation_id,
    )
    config = config_path or _default_config_path()
    data = _read_config(config)
    data[pipeline_id] = asdict(pipeline)
    _write_config(config, data)
    return pipeline


def list_pipelines(
    *,
    account_handle: Optional[str] = None,
    config_path: Optional[str] = None,
) -> list[BYOKPipeline]:
    """List registered pipelines (optionally filtered by ``account_handle``).

    Each carries its ``cred_id`` (a reference into the encrypted store) but never
    the plaintext key. This is the surface SPR-09's monitoring mode reads.
    """
    config = config_path or _default_config_path()
    data = _read_config(config)
    out: list[BYOKPipeline] = []
    for rec in data.values():
        pl = BYOKPipeline(
            pipeline_id=rec["pipeline_id"],
            account_handle=rec["account_handle"],
            cred_id=rec["cred_id"],
            pipeline_kind=rec["pipeline_kind"],
            seed=rec.get("seed"),
            investigation_id=rec.get("investigation_id"),
        )
        if account_handle is not None and pl.account_handle != account_handle.lstrip("@"):
            continue
        out.append(pl)
    out.sort(key=lambda p: p.pipeline_id)
    return out


def get_pipeline(
    pipeline_id: str,
    *,
    config_path: Optional[str] = None,
) -> BYOKPipeline:
    """Fetch a single pipeline by id. Raises ``KeyError`` if unknown."""
    config = config_path or _default_config_path()
    data = _read_config(config)
    rec = data.get(pipeline_id)
    if rec is None:
        raise KeyError(f"unknown pipeline_id: {pipeline_id}")
    return BYOKPipeline(
        pipeline_id=rec["pipeline_id"],
        account_handle=rec["account_handle"],
        cred_id=rec["cred_id"],
        pipeline_kind=rec["pipeline_kind"],
        seed=rec.get("seed"),
        investigation_id=rec.get("investigation_id"),
    )


__all__ = [
    "PIPELINE_KINDS",
    "BYOKPipeline",
    "register_pipeline",
    "list_pipelines",
    "get_pipeline",
]
