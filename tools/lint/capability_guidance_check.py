from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

CATALOG = Path("apps/reading/src/workspace/capabilityGuidanceLinks.ts")
SETTINGS = Path("apps/reading/src/modes/Settings/index.tsx")
APP = Path("apps/reading/src/App.tsx")
READING_SOURCE = Path("apps/reading/src")

ENTRY_RE = re.compile(r'^\s*([A-Za-z][A-Za-z0-9]*):\s*"([^"]+)",\s*$', re.MULTILINE)
ID_RE = re.compile(r'\bid\s*=\s*"([^"]+)"')
RUNTIME_DOCS_RE = re.compile(r"[\"']/docs/")


def validate(repo: Path) -> tuple[str, ...]:
    catalog_text = (repo / CATALOG).read_text(encoding="utf-8")
    settings_text = (repo / SETTINGS).read_text(encoding="utf-8")
    app_text = (repo / APP).read_text(encoding="utf-8")
    entries = ENTRY_RE.findall(catalog_text)
    anchors = set(ID_RE.findall(settings_text))
    errors: list[str] = []

    if not entries:
        errors.append(f"{CATALOG}: no guidance entries found")
    if not re.search(r'<Route\s+path="/settings"(?:\s|>)', app_text):
        errors.append(f"{APP}: /settings route is not served")

    for name, href in entries:
        split = urlsplit(href)
        if split.path != "/settings" or not split.fragment:
            errors.append(f"{CATALOG}: {name} must target /settings#<anchor>: {href}")
        elif split.fragment not in anchors:
            errors.append(f"{CATALOG}: {name} targets missing Settings anchor: {split.fragment}")

    for path in sorted((repo / READING_SOURCE).rglob("*")):
        if not path.is_file() or path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        if RUNTIME_DOCS_RE.search(text):
            errors.append(
                f"{path.relative_to(repo)}: repository-only /docs target is not a served app route"
            )

    return tuple(errors)


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    repo = Path(arguments[0]).resolve() if arguments else Path.cwd().resolve()
    errors = validate(repo)
    if errors:
        print(f"capability-guidance-check: {len(errors)} violation(s)", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("capability-guidance-check: typed Settings destinations are reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
