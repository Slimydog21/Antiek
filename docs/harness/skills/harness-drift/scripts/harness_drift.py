#!/usr/bin/env python3
"""harness-drift - track the harness surface in the production repo against this machine.

The problem it solves: a harness lives in two places. In PRODUCTION (the Antiek repo: its skills/,
CLAUDE.md, and the .infinite/ control plane) and on THIS MACHINE (~/.agents/skills, the doctrine
file, extensions). Lessons learned locally are meant to travel out as a PR; changes made in
production are meant to travel back in. Nothing tracked either direction, so drift was invisible.

    python3 harness_drift.py scan [--repo ~/Antiek] [--ref origin/main] [--json]
    python3 harness_drift.py diff                     # production vs the last baseline
    python3 harness_drift.py compare                  # same-named skills: production vs local
    python3 harness_drift.py apply <repo-path>        # copy one production file into the local harness
    python3 harness_drift.py baseline                 # accept current production state as the baseline

Design notes, deliberately:
  - READ-ONLY against the repository. `apply` never touches the repo; it withdraws FROM it.
  - The baseline is a manifest of path -> sha256 at a ref, so "what changed in production since I
    last looked" is answerable without a diff engine or network.
  - `compare` only reports skills that exist on BOTH sides under the same name. It does not guess
    mappings, because a wrong mapping silently overwrites the wrong file.
  - apply backs up what it replaces and refuses to clobber a directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

HOME = pathlib.Path.home()
BASELINE = HOME / ".prime" / "agent" / "harness-drift-baseline.json"
LOCAL_SKILLS = [HOME / ".agents" / "skills", HOME / ".prime" / "agent" / "skills"]
LOCAL_DOCTRINE = HOME / ".prime" / "agent" / "APPEND_SYSTEM.md"
SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv"}

# The production harness surface: where a repo puts the things that shape agents.
# Measured 2026-09-29: this machine's git root is the HOME DIRECTORY itself (branch master,
# remote Slimydog21/Antiek), and ~/Antiek is a subtree - so the surface is prefixed.
PROD_PATTERNS = ["skills", "CLAUDE.md", "AGENTS.md", ".infinite", "FOOTPRINT.md", ".claude",
                 "Antiek/skills", "Antiek/CLAUDE.md", "Antiek/AGENTS.md", "Antiek/.infinite",
                 "Antiek/FOOTPRINT.md", "Antiek/.claude", "Antiek/.caffenagent", "Antiek/specs"]


def git(repo: pathlib.Path, *args: str, timeout: int = 120) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def prod_files(repo: pathlib.Path, ref: str) -> dict[str, str]:
    """path -> blob sha at `ref`, restricted to the harness surface."""
    code, out = git(repo, "ls-tree", "-r", "-l", ref)
    if code != 0:
        raise SystemExit(f"git ls-tree failed on {ref}: {out[:200]}")
    files = {}
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        meta, path = line.split("\t", 1)
        cols = meta.split()
        if len(cols) < 4 or cols[1] != "blob":
            continue
        if not any(path == p or path.startswith(p + "/") for p in PROD_PATTERNS):
            continue
        if any(seg in SKIP_DIRS for seg in path.split("/")):
            continue
        files[path] = cols[2]          # git blob sha
    return files


def local_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:40]


def load_baseline() -> dict:
    try:
        return json.loads(BASELINE.read_text())
    except Exception:
        return {"ref": None, "files": {}, "taken_at": None}


def scan_compare(repo: pathlib.Path, ref: str, quiet: bool = False) -> dict:
    """Compare local skills against same-named skills in the repo. No guessing: name == name."""
    local_by_name = {}
    for root in LOCAL_SKILLS:
        if root.is_dir():
            for d in root.iterdir():
                if d.is_dir() and (d / "SKILL.md").is_file():
                    local_by_name.setdefault(d.name, d)
    rows = []
    for path, _sha in prod_files(repo, ref).items():
        if not path.startswith("skills/") or not path.endswith("/SKILL.md"):
            continue
        name = path.split("/")[1]
        if name not in local_by_name:
            continue
        code, blob = git(repo, "show", f"{ref}:{path}")
        if code != 0:
            continue
        local_path = local_by_name[name] / "SKILL.md"
        same = blob.strip() == local_path.read_text().strip()
        rows.append({"skill": name, "in_sync": same, "prod_path": path,
                     "local_path": str(local_path)})
    if not quiet:
        drift = [r for r in rows if not r["in_sync"]]
        print(f"{len(rows)} skill(s) exist on both sides; {len(drift)} differ")
        for r in drift:
            print(f"  DIFFERS  {r['skill']:26s} {r['prod_path']}  vs  {r['local_path']}")
    return {"compared": rows}


def diff_against_baseline(files: dict[str, str], quiet: bool = False) -> dict:
    base = load_baseline()
    old = base.get("files") or {}
    added = sorted(set(files) - set(old))
    removed = sorted(set(old) - set(files))
    changed = sorted(p for p in set(files) & set(old) if files[p] != old[p])
    if not quiet:
        if not old:
            print("no baseline yet - run `baseline` to record the current production state")
        else:
            print(f"since baseline taken {base.get('taken_at')} at {base.get('ref')}:")
            print(f"  added in production:   {len(added)}")
            print(f"  changed in production: {len(changed)}")
            print(f"  removed in production: {len(removed)}")
            for label, items in (("ADDED", added), ("CHANGED", changed), ("REMOVED", removed)):
                for p in items[:10]:
                    print(f"    {label:8s} {p}")
    return {"added": added, "changed": changed, "removed": removed,
            "baseline_at": base.get("taken_at"), "baseline_ref": base.get("ref")}


def apply_one(repo: pathlib.Path, ref: str, repo_path: str) -> int:
    code, blob = git(repo, "show", f"{ref}:{repo_path}")
    if code != 0:
        print(f"not found at {ref}: {repo_path}", file=sys.stderr)
        return 1
    name = pathlib.Path(repo_path).name
    if not repo_path.startswith("skills/"):
        print(f"only skills/ may be applied automatically; {repo_path} is not one. "
              f"Read it and port it by hand - doctrine and control-plane files need judgement.",
              file=sys.stderr)
        return 2
    skill = repo_path.split("/")[1]
    dest_dir = LOCAL_SKILLS[0] / skill
    dest = dest_dir / name
    if dest.is_dir():
        print(f"refusing to clobber a directory: {dest}", file=sys.stderr)
        return 2
    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        bak = dest.with_suffix(dest.suffix + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(dest, bak)
        print("backed up ->", bak.name)
    dest.write_text(blob)
    print(f"applied {repo_path} -> {dest}")
    return 0


def write_baseline(repo: pathlib.Path, ref: str, files: dict[str, str]) -> int:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps({"ref": ref, "taken_at": time.strftime("%Y-%m-%d %H:%M"),
                                    "files": files}, indent=1, sort_keys=True))
    print(f"baseline: {len(files)} harness file(s) at {ref} -> {BASELINE}")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd = argv[0]
    repo = pathlib.Path(os.path.expanduser(
        next((a.split("=", 1)[1] for a in argv if a.startswith("--repo=")), "~")))
    # resolve the real git root: ~ can BE the repo (it is on this machine), or contain one
    code, top = git(repo, "rev-parse", "--show-toplevel")
    if code == 0 and top.strip():
        repo = pathlib.Path(top.strip())
    ref = next((a.split("=", 1)[1] for a in argv if a.startswith("--ref=")), None)
    if ref is None:
        code, head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        ref = head.strip() if code == 0 and head.strip() else "origin/master"
    as_json = "--json" in argv

    if not pathlib.Path(repo, ".git").exists():
        print(f"not a git repo root: {repo}", file=sys.stderr); return 1
    if cmd in ("scan", "diff", "compare", "baseline"):
        files = prod_files(repo, ref)
        out = {"repo": str(repo), "ref": ref, "surface_files": len(files)}
        if cmd == "scan":
            out.update(diff_against_baseline(files, quiet=as_json))
            out.update(scan_compare(repo, ref, quiet=as_json))
        elif cmd == "diff":
            out.update(diff_against_baseline(files, quiet=as_json))
        elif cmd == "compare":
            out.update(scan_compare(repo, ref, quiet=as_json))
        else:
            return write_baseline(repo, ref, files)
        if as_json:
            print(json.dumps(out, indent=2))
        return 0
    if cmd == "apply":
        if len(argv) < 2:
            print("usage: apply <repo-path>", file=sys.stderr); return 2
        return apply_one(repo, ref, argv[1])
    print(f"unknown command {cmd!r}", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
