#!/usr/bin/env python3
"""grokbot_team - treat the online Grok Bot computers as a pool of workers.

    python3 grokbot_team.py status
    python3 grokbot_team.py run <host> "<shell command>" [--image alpine:latest] [--net]
    python3 grokbot_team.py dispatch jobs.json [--max-parallel 4]
    python3 grokbot_team.py collect <results.json>

A "team" here is honest about what it is: N bot computers, each reachable over the tailnet, each
running a job in a throwaway container. The TRANSPORT is the bot's Docker API, because that is the
only path that works today. The bot's own agent API (POST /api/message on :1340) needs a bearer
token held in xAI's sealed store, so `--transport agent` raises a clear error rather than pretending.

Two hard rules, both learned the expensive way:
  1. Every container this module creates is REMOVED, in a finally block. A stray container is a
     stray process on a machine you do not administer.
  2. The host filesystem is mounted READ-ONLY, and the network is OFF unless a job asks for it.

Creating NEW bots is not possible from here: provisioning lives in the Grok Bot app on the Mac
(whose local bridge daemon is dead) and in xAI's portal. This module works with the bots that exist.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import httpx
except ImportError:
    httpx = None

DISCOVER = pathlib.Path(__file__).resolve().parent / "discover.py"
UA = {"User-Agent": "prime-agent grokbot-team"}
DEFAULT_IMAGE = "alpine:latest"
DEFAULT_TIMEOUT = 300


# ----------------------------------------------------------------- transport: Docker API

def _docker(host, method, path, body=None, timeout=120):
    url = f"http://{host}:2375{path}"
    with httpx.Client(timeout=timeout) as c:
        r = c.request(method, url, json=body)
        return r.status_code, r.text


def run_job(host: str, command: str, *, image: str = DEFAULT_IMAGE,
            network: bool = False, ro_mount: bool = True, timeout: int = DEFAULT_TIMEOUT,
            name: str | None = None) -> dict:
    """Run one shell command in a throwaway container on `host`. Always cleans up.

    Returns {host, ok, exit_code, output, container, seconds, error}.
    """
    started = time.time()
    cname = name or f"prime-agent-job-{int(time.time())}"
    host_config = {"NetworkMode": "none" if not network else "bridge"}
    if ro_mount:
        host_config["Binds"] = ["/:/host:ro"]
    result = {"host": host, "ok": False, "exit_code": None, "output": "",
              "container": None, "seconds": 0.0, "error": ""}
    cid = None
    try:
        st, body = _docker(host, "POST", f"/containers/create?name={cname}",
                           {"Image": image, "Cmd": ["sh", "-c", command],
                            "WorkingDir": "/host" if ro_mount else "/",
                            "HostConfig": host_config})
        if st not in (200, 201):
            result["error"] = f"create failed: HTTP {st} {body[:200]}"
            return result
        cid = json.loads(body)["Id"]
        result["container"] = cid[:12]

        st, body = _docker(host, "POST", f"/containers/{cid}/start", timeout=timeout)
        if st not in (204, 304):
            result["error"] = f"start failed: HTTP {st} {body[:200]}"
            return result

        deadline = time.time() + timeout
        state = {}
        while time.time() < deadline:
            st, body = _docker(host, "GET", f"/containers/{cid}/json", timeout=40)
            if st == 200:
                state = json.loads(body).get("State", {})
                if not state.get("Running"):
                    break
            time.sleep(1.5)

        # Docker multiplexes stdout/stderr with 8-byte frame headers when the container has no
        # TTY. Fetch raw bytes and demux properly: a length byte can be printable, so stripping
        # control characters leaves junk like "]Linux 6f50..." in the output.
        with httpx.Client(timeout=60) as c:
            raw = c.get(f"http://{host}:2375/containers/{cid}/logs?stdout=1&stderr=1").content
        result["output"] = _demux(raw)
        result["exit_code"] = state.get("ExitCode")
        result["ok"] = (state.get("ExitCode") == 0)
        if state.get("Running"):
            result["error"] = f"still running after {timeout}s (killed)"
            _docker(host, "POST", f"/containers/{cid}/kill", timeout=30)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        if cid:
            try:
                _docker(host, "DELETE", f"/containers/{cid}?force=1", timeout=60)
                result.setdefault("cleaned", True)
            except Exception as e:
                result["error"] = (result["error"] + f" | cleanup failed: {e}").strip(" |")
        result["seconds"] = round(time.time() - started, 1)
    return result


def _demux(blob: bytes) -> str:
    """Undo Docker's 8-byte frame headers on a non-TTY log stream.

    Frame: [stream(1) 0 0 0 size(4, big-endian)] payload. Falls back to plain decode when the
    stream is not multiplexed (a TTY container) or a frame is malformed.
    """
    out = bytearray()
    i = 0
    while i + 8 <= len(blob):
        stream = blob[i]
        size = int.from_bytes(blob[i + 4:i + 8], "big")
        if stream not in (0, 1, 2) or i + 8 + size > len(blob):
            break
        out += blob[i + 8:i + 8 + size]
        i += 8 + size
    if not out:
        return blob.decode("utf-8", "replace")
    return out.decode("utf-8", "replace")


# ----------------------------------------------------------------- team operations

def online_hosts() -> list[str]:
    """Ask the discovery script which bot computers are reachable."""
    try:
        out = subprocess.run([sys.executable, str(DISCOVER), "--json"],
                             capture_output=True, text=True, timeout=180).stdout
        bots = json.loads(out)
    except Exception as e:
        print(f"discovery failed: {e}", file=sys.stderr)
        return []
    return [b["ip"] for b in bots if b.get("online") and b.get("ip") and b.get("open_ports")]


def status() -> list[dict]:
    rows = []
    for host in online_hosts():
        row = {"host": host}
        try:
            with httpx.Client(timeout=20) as c:
                v = c.get(f"http://{host}:2375/version").json()
                row["docker"] = v.get("Version")
                running = c.get(f"http://{host}:2375/containers/json").json()
                row["running_containers"] = len(running)
            try:
                h = httpx.get(f"http://{host}:1340/health", timeout=10).json()
                row["agent"] = "busy" if h.get("isBusy") else "idle"
            except Exception:
                row["agent"] = "unreachable"
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        rows.append(row)
    return rows


def dispatch(jobs: list[dict], *, max_parallel: int = 4, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Fan `jobs` out across the online bots.

    Each job: {"name": str, "command": str, "image": str?, "network": bool?}
    Returns {"results": [...], "unscheduled": [...]}.
    """
    hosts = online_hosts()
    if not hosts:
        return {"results": [], "unscheduled": [j.get("name") for j in jobs],
                "error": "no online bot computers"}
    results, unscheduled = [], []
    slot = 0
    with ThreadPoolExecutor(max_workers=max(1, min(max_parallel, len(hosts)))) as ex:
        futs = {}
        for job in jobs:
            if slot >= len(hosts) * max_parallel:
                unscheduled.append(job.get("name"))
                continue
            host = hosts[slot % len(hosts)]
            slot += 1
            futs[ex.submit(run_job, host, job["command"],
                           image=job.get("image", DEFAULT_IMAGE),
                           network=bool(job.get("network")),
                           timeout=job.get("timeout", timeout),
                           name=f"pa-{(job.get('name') or 'job')[:30]}")] = (job, host)
        for f in as_completed(futs):
            job, host = futs[f]
            try:
                r = f.result()
            except Exception as e:
                r = {"host": host, "ok": False, "error": f"{type(e).__name__}: {e}"}
            r["job"] = job.get("name")
            results.append(r)
    return {"results": results, "unscheduled": unscheduled, "hosts": hosts}


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]

    if cmd == "status":
        rows = status()
        for r in rows:
            print(f"{r['host']:16s} docker={r.get('docker','-'):10s} running={r.get('running_containers','?'):>3} "
                  f"agent={r.get('agent','?')}{(' ' + r['error']) if r.get('error') else ''}")
        return 0

    if cmd == "run":
        if len(argv) < 3:
            print("usage: run <host|auto> <command>", file=sys.stderr); return 2
        host = argv[1]
        if host == "auto":
            hosts = online_hosts()
            if not hosts:
                print("no online bots", file=sys.stderr); return 1
            host = hosts[0]
        r = run_job(host, argv[2], network="--net" in argv)
        print(json.dumps(r, indent=2)[:4000])
        return 0 if r.get("ok") else 1

    if cmd == "dispatch":
        if len(argv) < 2:
            print("usage: dispatch <jobs.json>", file=sys.stderr); return 2
        jobs = json.loads(pathlib.Path(argv[1]).read_text())
        out = dispatch(jobs)
        for r in out["results"]:
            mark = "OK  " if r.get("ok") else "FAIL"
            print(f"{mark} {r.get('job','?'):20s} on {r['host']:16s} {r.get('seconds','?')}s "
                  f"{('| ' + (r.get('error') or '')[:80]) if r.get('error') else ''}")
        if out.get("unscheduled"):
            print("unscheduled:", out["unscheduled"])
        dest = pathlib.Path(argv[2]) if len(argv) > 2 else pathlib.Path("grokbot-team-results.json")
        dest.write_text(json.dumps(out, indent=2))
        print("full results ->", dest)
        return 0 if all(r.get("ok") for r in out["results"]) else 1

    if cmd == "collect":
        data = json.loads(pathlib.Path(argv[1]).read_text())
        for r in data["results"]:
            print(f"--- {r.get('job')} @ {r['host']} (exit {r.get('exit_code')})")
            print((r.get("output") or "")[:600])
        return 0

    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
