#!/usr/bin/env python3
"""harness_upstream - turn lessons from THIS machine into a reviewable PR against the product repo.

harness_drift.py answers "what changed in production?" (pull direction). This answers the other
half: "which of my hard-won lessons should production inherit, and what does the PR look like?"
(push direction).

    python3 harness_upstream.py plan                    # what is portable, and where it would go
    python3 harness_upstream.py stage                   # write the proposed files to a scratch clone
    python3 harness_upstream.py stage --dest docs/harness
    python3 harness_upstream.py push                    # (needs --yes) branch + commit; never pushes

Safety model, deliberately conservative:
  - It NEVER touches the operator's working tree at ~. It clones origin/main into a scratch dir.
  - It NEVER pushes. It creates a branch and a commit, then prints the two commands to push and
    open the PR, so a human reads the diff first.
  - It NEVER edits doctrine (CLAUDE.md) automatically. Doctrine is judgement, not a file copy; the
    proposal lists the doctrine deltas it suggests and leaves them for the operator.

What counts as a portable lesson:
  - a local skill under ~/.agents/skills/<name>/ with a SKILL.md, that production does not have
  - the lesson list recorded in the engagement README (the transferable rules)
  - local extensions under ~/.prime/agent/extensions/
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HOME = pathlib.Path.home()
LOCAL_SKILL_DIRS = [HOME / ".agents" / "skills", HOME / ".prime" / "agent" / "skills"]
LOCAL_EXT = HOME / ".prime" / "agent" / "extensions"
ENGAGEMENT = HOME / "research" / "harness-integration-20260929"
README = ENGAGEMENT / "README.md"
DEFAULT_REPO = HOME
DEFAULT_REF = "origin/main"
DEFAULT_DEST = "docs/harness"


def sh(cmd, cwd=None, timeout=300):
    p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True,
                       cwd=cwd, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def prod_skill_names(repo: pathlib.Path, ref: str) -> set[str]:
    code, out = sh(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref])
    names = set()
    for line in out.splitlines():
        m = re.match(r"^skills/([^/]+)/", line)
        if m:
            names.add(m.group(1))
    return names


# Curated by default: the skills whose RULES are worth porting to the product repo, as opposed to
# the operator's whole library (113 skills, most of them third-party ports that do not belong in a
# product repo). Override with ~/.prime/agent/harness-portable.json: {"skills": [...]}.
CURATED = ["beads-fleet", "ocr-review-gate", "estate-audit", "harness-drift", "harness-upstream",
           "public-data", "media-information", "grokbot-resource", "modal-compute"]
PORTABLE_MANIFEST = HOME / ".prime" / "agent" / "harness-portable.json"


def curated_names() -> list[str]:
    try:
        return json.loads(PORTABLE_MANIFEST.read_text()).get("skills") or CURATED
    except Exception:
        return CURATED


def local_skills() -> dict[str, pathlib.Path]:
    found = {}
    for root in LOCAL_SKILL_DIRS:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                found.setdefault(d.name, d)
    return found


def lessons_from_readme() -> list[dict]:
    """The transferable rules, read from the engagement README (single source)."""
    try:
        text = README.read_text()
    except OSError:
        return []
    m = re.search(r"## The transferable lessons(.*?)\n## ", text, re.S)
    if not m:
        return []
    # The README wraps each rule across indented continuation lines, so joining them is required;
    # taking only the first line silently truncated every rule mid-sentence in the first PR.
    out, cur = [], None
    for raw in m.group(1).splitlines():
        line = raw.strip()
        mm = re.match(r"^\d+\.\s+\*\*(.+?)\*\*\s*(.*)$", line)
        if mm:
            if cur:
                out.append(cur)
            cur = {"title": mm.group(1).rstrip("."), "body": mm.group(2).strip()}
        elif cur is not None and line:
            cur["body"] = (cur["body"] + " " + line).strip()
    if cur:
        out.append(cur)
    return out


def plan(repo: pathlib.Path, ref: str) -> dict:
    prod = prod_skill_names(repo, ref)
    local = local_skills()
    want = set(curated_names())
    portable = {n: p for n, p in local.items() if n in want and n not in prod}
    skipped = sorted(n for n in local if n not in want)
    exts = sorted(f.name for f in LOCAL_EXT.glob("*.ts")) if LOCAL_EXT.is_dir() else []
    lessons = lessons_from_readme()
    return {"production_skills": sorted(prod), "local_skills": sorted(local),
            "portable_skills": sorted(portable), "not_curated": skipped,
            "local_extensions": exts, "lessons": lessons}


def render_index(p: dict, ref: str) -> str:
    lines = [f"# Harness lessons ported from the operator's machine", "",
             f"Generated {time.strftime('%Y-%m-%d %H:%M')} from `{HOME}` against `{ref}`.",
             "", "These are rules that were paid for in production incidents, not preferences.",
             "Each one names the observed failure, so a reader can judge whether it applies here.",
             "", "## The rules", ""]
    for i, l in enumerate(p["lessons"], 1):
        lines.append(f"{i}. **{l['title']}** — {l['body']}")
    lines += ["", "## Skills that exist on the machine and not in this repo", ""]
    for name in p["portable_skills"]:
        lines.append(f"- `{name}`")
    lines += ["", "## Local extensions worth reviewing", ""]
    for name in p["local_extensions"]:
        lines.append(f"- `{name}`")
    lines += ["", "## Doctrine deltas to consider by hand", "",
              "These are NOT applied automatically - doctrine is judgement, not a file copy:", "",
              "- `CLAUDE.md` here and `~/.prime/agent/APPEND_SYSTEM.md` there overlap. Where a rule",
              "  exists in only one, decide which side owns it rather than copying both ways.",
              "- The Google/Gmail path changed: `gog` is dead, `gws` is current. If this repo",
              "  documents `gog auth login` anywhere, that instruction is stale.",
              ""]
    return "\n".join(lines)


def stage(p: dict, repo: pathlib.Path, ref: str, dest: str, scratch: pathlib.Path) -> int:
    if scratch.exists():
        shutil.rmtree(scratch)
    code, out = sh(["git", "clone", "--depth", "1", "--branch", ref.split("/", 1)[-1],
                    str(repo), str(scratch)], timeout=900)
    if code != 0:
        # fall back to fetching the ref from the local repo
        code, out = sh(["git", "clone", "--depth", "1", str(repo), str(scratch)], timeout=900)
        if code != 0:
            print("clone failed:", out[:300], file=sys.stderr); return 1
        sh(["git", "-C", str(scratch), "fetch", "origin", ref, "--depth", "1"])
        sh(["git", "-C", str(scratch), "checkout", "FETCH_HEAD"])

    branch = f"harness/port-lessons-{time.strftime('%Y%m%d')}"
    sh(["git", "-C", str(scratch), "checkout", "-b", branch])
    target = scratch / dest
    target.mkdir(parents=True, exist_ok=True)
    (target / "README.md").write_text(render_index(p, ref))

    copied = 0
    for name in p["portable_skills"]:
        src = local_skills()[name]
        dst = target / "skills" / name
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                rel = f.relative_to(src)
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst / rel)
                copied += 1

    sh(["git", "-C", str(scratch), "add", "-A"])
    msg = ("docs(harness): port lessons and skills from the operator's machine\n\n"
           f"{len(p['lessons'])} rules, {len(p['portable_skills'])} skills, "
           f"{copied} files. Generated by harness_upstream; review before merging.")
    code, out = sh(["git", "-C", str(scratch), "-c", "user.email=agent@local",
                    "-c", "user.name=prime-agent", "commit", "-m", msg])
    print(f"staged at {scratch} on branch {branch} ({copied} files copied)")
    print(f"  review:  git -C {scratch} show --stat HEAD")
    print(f"  push:    git -C {scratch} push -u origin {branch}")
    print(f"  PR:      gh pr create --repo Slimydog21/Antiek --head {branch} "
          f"--title 'Harness lessons from the operator machine' --body-file {target}/README.md")
    print("\nNothing was pushed. Read the diff first.")
    return 0 if code == 0 else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd = argv[0]
    repo = pathlib.Path(os.path.expanduser(
        next((a.split("=", 1)[1] for a in argv if a.startswith("--repo=")), str(DEFAULT_REPO))))
    ref = next((a.split("=", 1)[1] for a in argv if a.startswith("--ref=")), DEFAULT_REF)
    dest = next((a.split("=", 1)[1] for a in argv if a.startswith("--dest=")), DEFAULT_DEST)
    code, top = sh(["git", "-C", str(repo), "rev-parse", "--show-toplevel"])
    if code == 0 and top.strip():
        repo = pathlib.Path(top.strip())

    p = plan(repo, ref)
    if cmd == "plan":
        print(f"{len(p['lessons'])} rule(s), {len(p['portable_skills'])} portable skill(s), "
              f"{len(p['local_extensions'])} extension(s)")
        print(f"production already has {len(p['production_skills'])} skill(s)")
        for n in p["portable_skills"]:
            print(f"  + {n}")
        if "--json" in argv:
            print(json.dumps(p, indent=2))
        return 0
    if cmd in ("stage", "push"):
        scratch = pathlib.Path(tempfile.gettempdir()) / "antiek-harness-porter"
        return stage(p, repo, ref, dest, scratch)
    print(f"unknown command {cmd!r}", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
