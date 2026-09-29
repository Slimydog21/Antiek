#!/usr/bin/env python3
"""estate-audit - report-only health check of the prime-agent estate.

Writes a dated report to ~/.prime/agent/estate-report.md and prints a summary.
It NEVER fixes anything. The DeepSeek-OCR-2 incident (2026-09-29) is why: a "fix" that
turned a loud failure into a quiet success cost more than the failure would have.

Usage: python3 estate_audit.py [--json]
Exit 0 always (it reports; it does not gate). Exit 1 only if the report could not be written.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

HOME = pathlib.Path.home()
REPORT = HOME / ".prime" / "agent" / "estate-report.md"
SKILL_DIRS = [HOME / ".agents" / "skills", HOME / ".prime" / "agent" / "skills"]
FINDINGS: list[tuple[str, str, str, str]] = []   # (area, severity, what, evidence)


def add(area, severity, what, evidence):
    FINDINGS.append((area, severity, what, str(evidence)[:400]))


def sh(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return f"{type(e).__name__}: {e}"


# --- 1. skill hygiene: the two frontmatter defect classes, statically ---------------
def check_skills():
    import yaml
    bad = []
    for d in SKILL_DIRS:
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            f = entry / "SKILL.md"
            if not f.is_file():
                continue
            try:
                text = f.read_text(errors="replace")
                if not text.startswith("---"):
                    continue
                fm = yaml.safe_load(text.split("---")[1])
                if not isinstance(fm, dict):
                    continue
                desc = str(fm.get("description") or "")
                if len(desc) > 1024:
                    bad.append(f"{entry.name}: description {len(desc)} chars (>1024)")
                # NOTE: a colon-space in the description is only a defect when it breaks PARSING
                # (a nested mapping in a folded scalar). A raw ": " heuristic produced 24 false
                # positives on 2026-09-29 against skills that load fine, so it is deliberately not
                # checked here. A parse failure below is the real signal.
                if fm.get("name") != entry.name:
                    bad.append(f"{entry.name}: name field is {fm.get('name')!r}")
            except Exception as e:
                bad.append(f"{entry.name}: frontmatter unparseable ({type(e).__name__})")
    if bad:
        add("skills", "warn", f"{len(bad)} skill frontmatter defect(s)", "; ".join(bad[:6]))
    else:
        add("skills", "ok", "all skill frontmatter parses and matches its directory", f"{sum(1 for d in SKILL_DIRS if d.is_dir())} skill dirs")


# --- 2. shadowed binaries ----------------------------------------------------------
def check_shadowing():
    for binary in ["claude", "node", "npm", "curl", "python3", "modal", "gws"]:
        out = sh(f"which -a {binary} 2>/dev/null").strip().splitlines()
        real = []
        for p in out:
            p = p.strip()
            if not p:
                continue
            broken = not os.path.exists(p)          # a dangling symlink resolves here
            real.append(f"{p}{' [BROKEN]' if broken else ''}")
        if len(real) > 1 or any("[BROKEN]" in r for r in real):
            add("binaries", "warn" if any("[BROKEN]" in r for r in real) else "info",
                f"{binary}: {len(real)} installs on PATH", " ; ".join(real))


# --- 3. credentials ----------------------------------------------------------------
def check_credentials():
    st = sh("gws auth status 2>/dev/null")
    try:
        j = json.loads(st)
        if j.get("auth_method") == "none":
            add("credentials", "warn", "gws has no credentials", "run gws auth login")
        else:
            add("credentials", "ok", f"gws authenticated ({j.get('auth_method')})",
                f"refresh_token={j.get('has_refresh_token')}")
    except Exception:
        add("credentials", "warn", "gws auth status unreadable", st[:120])
    for name, cmd in [("x cli", "x me"), ("modal", "modal profile current")]:
        out = sh(cmd, timeout=45)
        ok = "error" not in out.lower() and "cannot" not in out.lower() and out.strip() != ""
        add("credentials", "ok" if ok else "warn", f"{name} {'works' if ok else 'is not usable'}",
            out.strip().splitlines()[0] if out.strip() else "no output")


# --- 4. modal money -----------------------------------------------------------------
def check_modal():
    out = sh("modal billing summary --json 2>/dev/null", timeout=90)
    try:
        j = json.loads(out)
        cash = float(j.get("billed_cost", 0))
        breakdown = j.get("metered_cost_breakdown") or {}
        sev = "warn" if cash > 5 else "ok"
        add("modal", sev, f"${cash:.2f} cash due this cycle",
            json.dumps(breakdown)[:200])
    except Exception:
        add("modal", "info", "modal billing not readable", out[:120])
    vols = sh("modal volume list 2>/dev/null")
    n = len([l for l in vols.splitlines() if l.strip().startswith("│")]) - 1 if "│" in vols else 0
    add("modal", "ok" if n == 0 else "warn", f"{max(n,0)} modal volume(s)", vols.strip()[-160:] or "none")


# --- 5. failover + stale state ------------------------------------------------------
def check_state_files():
    paths = {
        "websearch-failover": HOME / ".prime/agent/skills/websearch-failover/state.json",
        "grokbot daemon": HOME / ".grokbot/local-exec-daemon.json",
    }
    for name, p in paths.items():
        if not p.exists():
            add("state", "info", f"{name}: no state file", p)
            continue
        age_days = (time.time() - p.stat().st_mtime) / 86400
        detail = f"{age_days:.1f} days old"
        if "failover" in name:
            try:
                s = json.loads(p.read_text())
                ex = s.get("exhausted") or {}
                if ex:
                    detail += f"; EXHAUSTED FLAGS PRESENT: {list(ex)} (a stale flag silently skips a provider)"
                    add("state", "warn", f"{name}: providers marked exhausted", detail)
                    continue
                detail += f"; exa_spend ${s.get('exa_spend', 0):.2f}"
            except Exception:
                pass
        add("state", "ok", f"{name}: {detail}", p)


# --- 6. disk and tailnet exposure ---------------------------------------------------
def check_environment():
    out = sh("df -h /System/Volumes/Data 2>/dev/null | tail -1")
    m = re.search(r"(\d+)%", out)
    if m and int(m.group(1)) > 90:
        add("disk", "warn", f"data volume at {m.group(1)}%", out.strip())
    else:
        add("disk", "ok", f"data volume at {m.group(1) + '%' if m else '?'}", out.strip())
    ts = sh("tailscale status 2>/dev/null | grep -i grok")
    if ts.strip():
        bots = [l.split()[0] for l in ts.strip().splitlines()]
        add("tailnet", "info", f"{len(bots)} grok peer(s)", " ; ".join(bots[:4]))
        for ip in bots:
            probe = sh(f"nc -z -G 3 {ip} 2375 && echo OPEN || echo closed", timeout=20)
            if "OPEN" in probe:
                # Source-blind: this Mac may itself be the allowed source (a firewall rule
                # scoped to it), so this measures reachability FROM HERE, not exposure to all.
                add("tailnet", "info", f"{ip}:2375 accepts docker API connections from this Mac",
                    "if no firewall scopes it to this host, that is root-equivalent for anything on "
                    "the tailnet - verify with a second vantage point, e.g. from omarchy")


def check_harness_drift():
    """Report production harness drift, read-only. Silent when there is nothing to say."""
    script = HOME / ".agents" / "skills" / "harness-drift" / "scripts" / "harness_drift.py"
    if not script.is_file():
        return
    out = sh(f"python3 {script} diff --json", timeout=180)
    try:
        d = json.loads(out)
    except Exception:
        add("drift", "info", "harness-drift could not be read", out[:160])
        return
    n = len(d.get("added", [])) + len(d.get("changed", [])) + len(d.get("removed", []))
    if n == 0:
        add("drift", "ok", "production harness unchanged since the last baseline",
            f"baseline {d.get('baseline_at')} at {d.get('baseline_ref')}")
    else:
        detail = (f"+{len(d.get('added', []))} ~{len(d.get('changed', []))} -{len(d.get('removed', []))}; "
                  + ", ".join((d.get("added") or [])[:3] + (d.get("changed") or [])[:3]))
        add("drift", "warn", f"{n} change(s) in the production harness", detail)


def main():
    check_skills()
    check_shadowing()
    check_credentials()
    check_modal()
    check_state_files()
    check_environment()
    check_harness_drift()

    if "--json" in sys.argv:
        print(json.dumps(FINDINGS, indent=2))
        return 0

    order = {"warn": 0, "info": 1, "ok": 2}
    FINDINGS.sort(key=lambda f: (order.get(f[1], 3), f[0]))
    worst = sum(1 for f in FINDINGS if f[1] == "warn")
    lines = [f"# Estate report - {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"{worst} warning(s), {sum(1 for f in FINDINGS if f[1] == 'ok')} check(s) clean.",
             "Report-only: this audit never changes anything.", ""]
    for area, sev, what, ev in FINDINGS:
        lines.append(f"## [{sev.upper()}] {area}: {what}")
        if ev:
            lines.append(f"    {ev}")
        lines.append("")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))
    for area, sev, what, ev in FINDINGS[:12]:
        print(f"{sev.upper():5s} {area:11s} {what}")
    print(f"\n{worst} warning(s) -> {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
