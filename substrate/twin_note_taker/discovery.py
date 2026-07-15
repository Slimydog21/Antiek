"""Read-only, owner-derived discovery of V20 twin-note candidates."""

from __future__ import annotations

from typing import Any

from runtime.db_lock import connect_read
from substrate.twin_note_taker import compression

MAX_DISCOVERY_ASSETS = 100
MAX_WINDOWS_PER_ASSET = 200
MAX_TOTAL_WINDOWS = 1_000
MAX_SELECTION_MEMBERS = 1_000
MAX_LABEL_BYTES = 256

LIMITS = {
    "assets": MAX_DISCOVERY_ASSETS,
    "windows_per_asset": MAX_WINDOWS_PER_ASSET,
    "total_windows": MAX_TOTAL_WINDOWS,
    "selection_members": MAX_SELECTION_MEMBERS,
}


class TwinNoteDiscoveryIntegrity(RuntimeError):
    """The owner join or database substrate is globally corrupt."""


class TwinNoteDiscoveryUnavailable(RuntimeError):
    """The discovery database cannot currently be read."""


def _label(value: Any) -> str:
    if type(value) is not str or not value.strip():
        return "Untitled document"
    encoded = value.strip().encode("utf-8")[:MAX_LABEL_BYTES]
    while encoded:
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return "Untitled document"


class TwinNoteDiscoveryService:
    """One-connection advisory read model; deliberately has no write seams."""

    def __init__(self, *, db_path: str) -> None:
        self.db_path = db_path

    def candidates(self, account_id: str) -> dict[str, Any]:
        if type(account_id) is not str or not account_id:
            raise TwinNoteDiscoveryIntegrity("invalid account authority")
        try:
            con = connect_read(self.db_path)
        except Exception as exc:
            raise TwinNoteDiscoveryUnavailable("discovery database unavailable") from exc

        try:
            with con:
                con.execute("BEGIN TRANSACTION")
                result = self._snapshot_candidates(con, account_id)
                con.execute("COMMIT")
                return result
        except TwinNoteDiscoveryIntegrity:
            raise
        except Exception as exc:
            # Once a connection opened, malformed schema/invariants are an
            # integrity conflict. Driver details remain behind the boundary.
            raise TwinNoteDiscoveryIntegrity("discovery substrate conflict") from exc

    def _snapshot_candidates(self, con: Any, account_id: str) -> dict[str, Any]:
        # Rank only narrow owner-derived identities. Evidence blobs are fetched
        # later, once, and only for the final emitted prefix.
        asset_rows = con.execute(
            """
            SELECT DISTINCT d.document_id, d.title
            FROM documents d
            JOIN notebooks n
              ON n.document_id = d.document_id
             AND n.owner_user_id = d.owner_user_id
            JOIN note_taker_windows w
              ON w.investigation_id = n.investigation_id
            WHERE d.owner_user_id = ? AND n.owner_user_id = ?
              AND n.document_id IS NOT NULL
              AND n.investigation_id IS NOT NULL
            ORDER BY d.document_id
            LIMIT ?
            """,
            [account_id, account_id, MAX_DISCOVERY_ASSETS + 1],
        ).fetchall()
        asset_overflow = len(asset_rows) > MAX_DISCOVERY_ASSETS
        asset_rows = asset_rows[:MAX_DISCOVERY_ASSETS]

        staged: list[dict[str, Any]] = []
        flat: list[tuple[str, str, int, str, int]] = []
        omitted_first_asset: str | None = None
        total_overflow = False
        any_per_asset_overflow = False
        for asset_id, asset_label in asset_rows:
            if type(asset_id) is not str or not asset_id:
                raise TwinNoteDiscoveryIntegrity("invalid owner join identity")
            remaining = MAX_TOTAL_WINDOWS - len(flat)
            identity_limit = min(MAX_WINDOWS_PER_ASSET + 1, remaining + 1)
            identity_rows = con.execute(
                """
                SELECT DISTINCT w.window_id, w.consumer_version,
                                w.investigation_id, w.ordinal
                FROM documents d
                JOIN notebooks n
                  ON n.document_id = d.document_id
                 AND n.owner_user_id = d.owner_user_id
                JOIN note_taker_windows w
                  ON w.investigation_id = n.investigation_id
                WHERE d.document_id = ?
                  AND d.owner_user_id = ? AND n.owner_user_id = ?
                  AND n.document_id IS NOT NULL
                  AND n.investigation_id IS NOT NULL
                ORDER BY w.investigation_id, w.consumer_version,
                         w.ordinal, w.window_id
                LIMIT ?
                """,
                [asset_id, account_id, account_id, identity_limit],
            ).fetchall()
            per_asset_overflow = (identity_limit == MAX_WINDOWS_PER_ASSET + 1
                                  and len(identity_rows) > MAX_WINDOWS_PER_ASSET)
            any_per_asset_overflow = any_per_asset_overflow or per_asset_overflow
            total_sentinel = len(identity_rows) > remaining
            identities = identity_rows[:min(MAX_WINDOWS_PER_ASSET, remaining)]
            emitted_for_asset: list[tuple[str, int, str, int]] = []
            for window_id, consumer_version, investigation_id, ordinal in identities:
                if (type(window_id) is not str or not window_id
                        or type(investigation_id) is not str or not investigation_id
                        or type(consumer_version) is not int or type(ordinal) is not int):
                    raise TwinNoteDiscoveryIntegrity("invalid owner join identity")
                identity = (window_id, consumer_version, investigation_id, ordinal)
                emitted_for_asset.append(identity)
                flat.append((asset_id, *identity))
            if total_sentinel:
                total_overflow = True
                omitted_first_asset = asset_id
            if emitted_for_asset:
                staged.append({
                    "asset_id": asset_id,
                    "asset_label": _label(asset_label),
                    "identities": emitted_for_asset,
                    "truncated": per_asset_overflow or omitted_first_asset == asset_id,
                })
            if total_overflow:
                break

        evidence_by_id: dict[str, tuple[Any, ...]] = {}
        emitted_ids = tuple(dict.fromkeys(row[1] for row in flat))
        if emitted_ids:
            placeholders = ",".join("?" for _ in emitted_ids)
            evidence_rows = con.execute(
                "SELECT window_id,consumer_version,investigation_id,ordinal,"
                "source_event_ids_json,source_digest,request_json,request_sha256,"
                "state,raw_result,raw_result_sha256 FROM note_taker_windows "
                f"WHERE window_id IN ({placeholders})",
                list(emitted_ids),
            ).fetchall()
            evidence_by_id = {row[0]: tuple(row) for row in evidence_rows}
            if set(evidence_by_id) != set(emitted_ids):
                raise TwinNoteDiscoveryIntegrity("bounded evidence disappeared")

        assets: list[dict[str, Any]] = []
        for asset in staged:
            windows: list[dict[str, Any]] = []
            for identity in asset.pop("identities"):
                window_id, consumer_version, investigation_id, ordinal = identity
                validation_row = evidence_by_id[window_id]
                if validation_row[:4] != identity:
                    raise TwinNoteDiscoveryIntegrity("bounded evidence identity drift")
                validation = compression.validate_window_evidence(validation_row)
                reason = validation.exclusion_reason
                note_count = len(validation.notes) if reason is None else 0
                source_count = len(validation.sources) if reason is None else 0
                windows.append({
                    "window_id": window_id,
                    "investigation_id": investigation_id,
                    "consumer_version": consumer_version,
                    "window_ordinal": ordinal,
                    "note_count": note_count,
                    "source_count": source_count,
                    "eligibility": "eligible" if reason is None else "excluded",
                    "exclusion_reason": reason,
                })
            asset["windows"] = windows
            assets.append(asset)

        return {
            "assets": assets,
            "truncated": asset_overflow or total_overflow or any_per_asset_overflow,
            "limits": dict(LIMITS),
        }


__all__ = [
    "LIMITS",
    "TwinNoteDiscoveryIntegrity",
    "TwinNoteDiscoveryService",
    "TwinNoteDiscoveryUnavailable",
]
