#!/usr/bin/env python3
"""Dashboards-as-code for the Antiek "North Star" PostHog dashboard (APH SPR-03).

The North Star dashboard was assembled by hand via the API; that is unversioned
and unrecoverable. This tool makes it reproducible:

  --export   read the live dashboard + its insights and write the versioned
             contract `tools/posthog/north_star.json` (normalized: dashboard
             name/description + ordered insights with a stable slug, name, and
             full query; server ids/timestamps/derived fields stripped so the
             contract is portable across projects).
  --apply    create-or-update the live project to MATCH the contract,
             reconciling by stable insight NAME (never server id) so it
             reproduces the dashboard on a brand-new project. Idempotent: a
             second --apply makes no changes.
  --check    export the live state into memory and diff it against the committed
             contract (round-trip); exit non-zero if they differ.

Reconcile key = insight NAME (+ dashboard NAME), NOT the server id 724094 — so
disaster recovery onto a fresh project works. Tile mechanism: writing an
insight's `dashboards` array DOES materialize a tile in `dashboard.tiles` (which
--export reads) — verified on a fresh throwaway dashboard (APH SPR-03,
2026-06-04), so the create path reproduces tiles on a brand-new project.
LIMITATION: because the join key is the name, RENAMING a live insight makes
--apply create a NEW insight under the contract name (a duplicate tile) instead
of reconciling the rename — change the name in the contract AND on the dashboard
together, or re-export. DIRECTION: --export OVERWRITES the committed
north_star.json from live (contract←live); the normal flow is contract→live via
--apply, so run --export deliberately (to capture an intentional change).
Credentials (env, never printed):
  POSTHOG_PERSONAL_API_KEY  phx_…    POSTHOG_PROJECT_ID  default 193061
  POSTHOG_HOST              default https://eu.posthog.com
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

CONTRACT = pathlib.Path(__file__).with_name("north_star.json")
DASHBOARD_NAME = "Antiek — North Star"


def _cfg() -> tuple[str, str, str]:
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not key:
        sys.exit("[sync_dashboards] missing POSTHOG_PERSONAL_API_KEY")
    host = os.environ.get("POSTHOG_HOST", "https://eu.posthog.com").rstrip("/")
    pid = os.environ.get("POSTHOG_PROJECT_ID", "193061")
    return key, host, pid


def _api(method: str, url: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"[sync_dashboards] API {method} {url.split('?')[0]} -> {e.code}: {e.read().decode()[:160]}")


def _paginate(url: str, key: str) -> list:
    out = []
    while url:
        d = _api("GET", url, key)
        out.extend(d.get("results", []))
        url = d.get("next")
    return out


def _normalize_query(q: dict) -> dict:
    """Strip server-volatile bits so the contract is portable + diff-stable."""
    return q  # InsightVizNode/source are already declarative; ids live outside `query`.


def export_contract(key: str, host: str, pid: str) -> dict:
    dashboards = _paginate(f"{host}/api/projects/{pid}/dashboards/?limit=100", key)
    match = [d for d in dashboards if d.get("name") == DASHBOARD_NAME and not d.get("deleted")]
    if not match:
        sys.exit(f"[sync_dashboards] no live dashboard named {DASHBOARD_NAME!r} to export")
    dash = _api("GET", f"{host}/api/projects/{pid}/dashboards/{match[0]['id']}/", key)
    insights = []
    for tile in dash.get("tiles") or []:
        ins = tile.get("insight")
        if not ins:
            continue
        insights.append({
            "slug": _slug(ins.get("name", "")),
            "name": ins.get("name"),
            "query": _normalize_query(ins.get("query") or {}),
        })
    insights.sort(key=lambda i: i["slug"])  # stable order → diff-stable contract
    return {
        "dashboard": {"name": dash.get("name"), "description": dash.get("description", "")},
        "insights": insights,
    }


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def cmd_export(key: str, host: str, pid: str) -> int:
    contract = export_contract(key, host, pid)
    CONTRACT.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(f"[sync_dashboards] exported {len(contract['insights'])} insights -> {CONTRACT.name}")
    return 0


def cmd_check(key: str, host: str, pid: str) -> int:
    if not CONTRACT.exists():
        sys.exit(f"[sync_dashboards] no committed contract at {CONTRACT}")
    live = export_contract(key, host, pid)
    committed = json.loads(CONTRACT.read_text())
    a = json.dumps(live, indent=2, sort_keys=True)
    b = json.dumps(committed, indent=2, sort_keys=True)
    if a == b:
        print("[sync_dashboards] round-trip OK — live state matches the committed contract")
        return 0
    print("[sync_dashboards] DRIFT — live state differs from the committed contract:")
    import difflib
    print("\n".join(difflib.unified_diff(b.splitlines(), a.splitlines(),
                                          "committed", "live", lineterm=""))[:4000])
    return 1


def cmd_apply(key: str, host: str, pid: str) -> int:
    if not CONTRACT.exists():
        sys.exit(f"[sync_dashboards] no contract at {CONTRACT} — run --export first")
    contract = json.loads(CONTRACT.read_text())
    if not isinstance(contract.get("insights"), list) or not contract.get("dashboard", {}).get("name"):
        sys.exit("[sync_dashboards] malformed contract (need dashboard.name + insights[])")
    # Validate every insight BEFORE any API write (M3: reject a malformed
    # contract loudly, never half-apply it).
    for idx, spec in enumerate(contract["insights"]):
        if not spec.get("name") or not isinstance(spec.get("query"), dict) or not spec["query"]:
            sys.exit(f"[sync_dashboards] malformed contract: insight #{idx} needs a non-empty name + query "
                     f"— rejected before any API write")

    changes = 0
    # 1. ensure dashboard (by name).
    dashboards = _paginate(f"{host}/api/projects/{pid}/dashboards/?limit=100", key)
    dmatch = [d for d in dashboards if d.get("name") == contract["dashboard"]["name"] and not d.get("deleted")]
    if dmatch:
        dash_id = dmatch[0]["id"]
        # Reconcile the dashboard description too — otherwise --apply could report
        # "no changes" while --check reports DRIFT on the description (apply and
        # check must agree to be inverses).
        if (dmatch[0].get("description") or "") != contract["dashboard"].get("description", ""):
            _api("PATCH", f"{host}/api/projects/{pid}/dashboards/{dash_id}/", key,
                 {"description": contract["dashboard"].get("description", "")})
            changes += 1
            print("[sync_dashboards] updated dashboard description")
    else:
        dash_id = _api("POST", f"{host}/api/projects/{pid}/dashboards/", key,
                       {"name": contract["dashboard"]["name"], "description": contract["dashboard"].get("description", "")})["id"]
        changes += 1
        print(f"[sync_dashboards] created dashboard {contract['dashboard']['name']!r} (id {dash_id})")

    # 2. ensure each insight (by name) + its query + tile membership.
    existing = {i["name"]: i for i in _paginate(f"{host}/api/projects/{pid}/insights/?limit=200", key) if i.get("name")}
    for spec in contract["insights"]:
        cur = existing.get(spec["name"])
        if cur is None:
            _api("POST", f"{host}/api/projects/{pid}/insights/", key,
                 {"name": spec["name"], "query": spec["query"], "dashboards": [dash_id]})
            changes += 1
            print(f"[sync_dashboards] created insight {spec['name']!r}")
            continue
        # update query if drifted
        if json.dumps(cur.get("query"), sort_keys=True) != json.dumps(spec["query"], sort_keys=True):
            _api("PATCH", f"{host}/api/projects/{pid}/insights/{cur['id']}/", key, {"query": spec["query"]})
            changes += 1
            print(f"[sync_dashboards] updated query for insight {spec['name']!r}")
        # ensure tiled on the dashboard
        cur_dash = cur.get("dashboards") or []
        if dash_id not in cur_dash:
            _api("PATCH", f"{host}/api/projects/{pid}/insights/{cur['id']}/", key,
                 {"dashboards": list(dict.fromkeys(cur_dash + [dash_id]))})
            changes += 1
            print(f"[sync_dashboards] tiled insight {spec['name']!r} onto the dashboard")

    if changes == 0:
        print("[sync_dashboards] no changes — live project already matches the contract (idempotent)")
    else:
        print(f"[sync_dashboards] applied {changes} change(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="North Star dashboard-as-code (APH SPR-03).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", action="store_true", help="write north_star.json from the live dashboard")
    g.add_argument("--apply", action="store_true", help="create-or-update the live project to match the contract (idempotent)")
    g.add_argument("--check", action="store_true", help="diff live state against the committed contract (round-trip)")
    args = ap.parse_args()
    key, host, pid = _cfg()
    if args.export:
        return cmd_export(key, host, pid)
    if args.apply:
        return cmd_apply(key, host, pid)
    return cmd_check(key, host, pid)


if __name__ == "__main__":
    raise SystemExit(main())
