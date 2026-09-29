#!/usr/bin/env python3
"""Discover Grok Bot computers on the tailnet and report what each exposes.

Usage: python3 discover.py [--json]
Exit 0 if at least one online bot answered; 1 if none did.
"""
import json, re, socket, subprocess, sys
import httpx

PORTS = [22, 1340, 6080, 6081, 2375] + list(range(14002, 14014)) + list(range(13602, 13614))

def tailscale_peers():
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=25).stdout
        peers = json.loads(out).get("Peer", {}).values()
    except Exception as e:
        print(f"tailscale status failed: {e}")
        return []
    bots = []
    for p in peers:
        name = p.get("HostName", "")
        if "grok" in name.lower():
            ips = p.get("TailscaleIPs") or []
            bots.append({"host": name, "dns": (p.get("DNSName") or "").rstrip("."),
                         "ip": ips[0] if ips else None, "online": bool(p.get("Online")),
                         "os": p.get("OS")})
    return sorted(bots, key=lambda b: (not b["online"], b["host"]))

def scan(host, timeout=2.0):   # a DERP-relayed tailnet hop measured ~240 ms RTT; 0.4 s produced false negatives
    open_ports = []
    for port in PORTS:
        s = socket.socket(); s.settimeout(timeout)
        try:
            s.connect((host, port)); open_ports.append(port)
        except Exception:
            pass
        finally:
            s.close()
    return open_ports

def health(host):
    try:
        return httpx.get(f"http://{host}:1340/health", timeout=8).json()
    except Exception:
        return None

def main():
    bots = tailscale_peers()
    if not bots:
        print("no grok* peers on the tailnet")
        return 1
    report, any_live = [], False
    for b in bots:
        host = b["ip"] or b["dns"]   # two peers share the name "grokbot"; the IP is unambiguous
        entry = dict(b)
        if b["online"] and host:
            entry["open_ports"] = scan(host)
            entry["agent"] = health(host)
            entry["docker"] = 2375 in entry["open_ports"]
            entry["desktops"] = [p for p in entry["open_ports"] if p in (6080, 6081)]
            entry["exec_daemon"] = [p for p in entry["open_ports"] if 14000 <= p < 14100]
            any_live = any_live or bool(entry["open_ports"])
        report.append(entry)
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        for e in report:
            state = "ONLINE" if e["online"] else "offline"
            print(f"{state:7s} {e['host']:12s} {e.get('ip') or '-':16s} {e.get('os') or ''}")
            if e["online"] and e.get("open_ports"):
                print(f"        docker_api={'YES (unauthenticated!)' if e.get('docker') else 'no'}"
                      f"  desktops={e.get('desktops')}  exec_daemon={len(e.get('exec_daemon') or [])} ports"
                      f"  agent={'busy' if (e.get('agent') or {}).get('isBusy') else 'idle'}"
                      if e.get("agent") else "  agent runtime not answering on :1340")
    return 0 if any_live else 1

if __name__ == "__main__":
    sys.exit(main())
