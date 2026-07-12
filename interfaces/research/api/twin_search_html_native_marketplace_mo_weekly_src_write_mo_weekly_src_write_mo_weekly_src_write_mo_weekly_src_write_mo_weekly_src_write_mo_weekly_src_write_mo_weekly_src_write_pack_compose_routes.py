"""Registerable HTTP surface for twin search over HTML-native marketplace MO weekly src write pack."""

from __future__ import annotations

import sys

# Nested residual Pydantic body graphs exceed default recursion depth.
if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    HtmlViewBody,
    MarketPackBody,
)
from substrate.twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    TwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/twin-search-html-native-marketplace-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
    tags=["twin-search-html-native-marketplace-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str]
    questions: list[str]
    source_label: str | None = Field(default=None, max_length=256)


class HtmlPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    market_pack: MarketPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2000)
    twin_records: list[TwinRecordBody]
    html_pack: HtmlPackBody
    operator_ack: bool = Field(strict=True)
    search_limit: int | None = Field(default=None, ge=1, le=1000)
    require_both: bool = Field(default=True, strict=True)



def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + hit_count only.

    Full recursive to_dict() exceeds pydantic JSON depth on deep residual stacks.
    """
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "hit_count": result.hit_count,
        "search": {
            "query": result.search.query,
            "hits": [
                {
                    "twin_id": h.twin_id if hasattr(h, "twin_id") else h.get("twin_id"),
                    "score": h.score if hasattr(h, "score") else h.get("score"),
                }
                for h in (result.search.hits if hasattr(result.search, "hits") else [])
            ],
        },
        "html_pack": {
            "pack_ready": result.html_pack.pack_ready,
            "pdf_primary": False,
            "production_router_verdict": "REJECT",
        },
        "pack_ready": result.pack_ready,
        "remote_index_queried": False,
        "twin_written": False,
        "purchase_executed": False,
        "hosted": False,
        "pdf_view_authorized": False,
        "pdf_primary": False,
        "live_execution_authorized": False,
        "charge_executed": False,
        "secrets_stored": False,
        "inventory_mutated": False,
        "live_router_authorized": False,
        "live_dispatch_authorized": False,
        "remote_fetched": False,
        "backlog_mutated": False,
        "store_mutated": False,
        "suite_rewritten": False,
        "prompts_injected": False,
        "merge_executed": False,
        "draft_written": False,
        "analysis_written": False,
        "live_dispatched": False,
        "pack_dispatched": False,
        "record_persisted": False,
        "production_router_verdict": "REJECT",
        "authority": result.authority,
    }


@twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            search_query=req.search_query,
            twin_records=[r.model_dump() for r in req.twin_records],
            html_pack=req.html_pack.model_dump(),
            operator_ack=req.operator_ack,
            search_limit=req.search_limit,
            require_both=req.require_both,
        )
    except TwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_twin_search_html_native_marketplace_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]
