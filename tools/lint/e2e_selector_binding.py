"""Every selector an e2e spec binds to must exist in the app it tests.

No CI job runs the Playwright spec suite — `apps/reading/package.json` defines
`e2e`, `e2e:ams`, `e2e:feel`, `e2e:login` and `e2e:passkey`, and nothing in
`.github/workflows/` invokes any of them. `visualtest.yml` drives playwright-core
for screenshots and a11y, never the specs. So a spec can bind to a selector whose
component was deleted and every board stays green.

That is not hypothetical. `WernerRig` was removed from `main`;
`e2e/_werner/rod-in-hand.spec.ts` still locates `[data-werner-rod]`, which now
matches nothing in `apps/reading/src`. Nothing went red.

WHAT THIS IS NOT: running the specs. It cannot tell you a selector is *reachable
at runtime* — only a browser can. Wiring Playwright into a required check would
buy that at the price of the flakiest gate on the board, and an untrustworthy
required check is worse than a missing one because people learn to re-run it.
This is the cheap static half: a selector that names nothing in the source is
dead, and that is decidable without a browser.

Selectors a spec INJECTS itself (`el.setAttribute("data-product-id", …)` inside
a `page.evaluate`) are legitimately absent from the source and are exempt.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E2E = ROOT / "apps/reading/e2e"
SRC = ROOT / "apps/reading/src"
BASELINE = ROOT / "tools/lints/baselines/e2e_selector_binding.json"

#: A locator string. The quote is CAPTURED and back-referenced: a single-quoted
#: selector legitimately contains double quotes (``'[data-testid="x"] [data-y]'``),
#: and a naive ``[^"\']+`` truncates it at the first inner quote — which silently
#: turned this lint's findings to zero while a known-dead selector was present.
_LOCATOR = re.compile(r'\.locator\(\s*(["\'])((?:(?!\1).)+)\1')
#: getByTestId("foo")
_TESTID_CALL = re.compile(r'getByTestId\(\s*(["\'])((?:(?!\1).)+)\1')
#: one component of a compound selector
_ATTR = re.compile(r'\[(data-[a-z0-9-]+)(?:\s*=\s*["\']([^"\']*)["\'])?\]')
_CLASS = re.compile(r'(?<![\w.])\.([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\b')
#: names the spec creates for itself inside page.evaluate
_INJECTED = re.compile(r'setAttribute\(\s*["\']([a-z0-9-]+)["\']\s*,\s*["\']([^"\']*)["\']')
#: `data-testid={`prefix-${expr}`}` in source — the literal never appears whole
_TEMPLATE_TESTID = re.compile(r'data-testid=\{\s*`([^`$]*)\$\{')
#: `data-testid="literal"` / getByTestId("literal") in source
_SOURCE_TESTID = re.compile(r'data-testid=["\']([^"\']+)["\']|getByTestId\(\s*["\']([^"\']+)["\']')


#: Files that are EVIDENCE AN ELEMENT RENDERS. Deliberately excludes ``.css``.
#: A stylesheet declares how a class would look if something used it; it does
#: not show that anything does. A dead rule left behind by a deleted component
#: is itself a match, so counting CSS made this lint blind to exactly the case
#: it exists for: ``.werner-rig-flipper-r`` survived only in
#: ``src/werner/waddle.css`` after WernerRig was removed, and a spec binding it
#: went unflagged until the stylesheet was deleted separately.
_RENDER_EVIDENCE_SUFFIXES = {".tsx", ".ts", ".html", ".svg"}


def _source_blob() -> str:
    """Every rendering source file's text, concatenated once."""
    parts: list[str] = []
    for path in sorted(SRC.rglob("*")):
        if path.is_file() and path.suffix in _RENDER_EVIDENCE_SUFFIXES:
            try:
                parts.append(path.read_text())
            except (UnicodeDecodeError, OSError):
                continue
    return "\n".join(parts)


def _spec_files() -> list[Path]:
    return [p for p in sorted(E2E.rglob("*.spec.ts")) if p.is_file()]


def _template_prefixes(blob: str) -> list[str]:
    """Static prefixes of template-literal testids.

    ``data-testid={`thread-hop-${hop.workflow}`}`` never puts
    ``thread-hop-write`` in the source as a literal, but the spec can and does
    bind to it. Treating those as unbound was this lint's own first false
    positive — 8 of its first 13 findings.
    """
    return [prefix for prefix in _TEMPLATE_TESTID.findall(blob) if prefix]


def _component_binds(component: str, blob: str, prefixes: list[str], injected: set[str]) -> bool:
    """Does one simple selector name something the app actually has?"""
    names: list[tuple[str, str]] = []
    for attr, value in _ATTR.findall(component):
        names.append(("testid", value) if attr == "data-testid" and value else ("attr", attr))
    names.extend(("class", k) for k in _CLASS.findall(component))
    if not names:
        return True                       # tag/structural selector — nothing to verify
    for kind, name in names:
        if name in injected or name in blob:
            continue
        if kind == "testid" and any(name.startswith(prefix) for prefix in prefixes):
            continue                      # produced by a template literal
        return False
    return True


def _alternative_binds(alternative: str, blob: str, prefixes: list[str], injected: set[str]) -> bool:
    """A descendant/compound chain binds only if EVERY part of it binds."""
    parts = [p for p in re.split(r"[\s>+~]+", alternative.strip()) if p]
    return all(_component_binds(part, blob, prefixes, injected) for part in parts)


def unbound_selectors() -> list[str]:
    """Locators referenced by a spec that can match nothing in the app source.

    A comma-separated locator is a UNION: ``'[data-testid="x"], [data-x]'``
    binds if EITHER side does, so flagging the dead half is wrong. That was this
    lint's second false positive.
    """
    blob = _source_blob()
    prefixes = _template_prefixes(blob)
    findings: list[str] = []
    for spec in _spec_files():
        text = spec.read_text()
        injected = {v for _, v in _INJECTED.findall(text)} | {a for a, _ in _INJECTED.findall(text)}
        rel = spec.relative_to(ROOT).as_posix()
        locators = [(loc, loc) for _, loc in _LOCATOR.findall(text)]
        locators += [(f'[data-testid="{t}"]', t) for _, t in _TESTID_CALL.findall(text)]
        for selector, shown in sorted(set(locators)):
            alternatives = [a for a in selector.split(",") if a.strip()]
            if any(_alternative_binds(a, blob, prefixes, injected) for a in alternatives):
                continue
            findings.append(f"{rel}: selector {shown!r} matches nothing in apps/reading/src")
    return sorted(set(findings))


def _baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return set(json.loads(BASELINE.read_text()).get("known_unbound", []))


def check() -> list[str]:
    """New drift only. The baseline is shrink-only; see the JSON's own note."""
    if not _spec_files():
        return ["No e2e specs discovered — the lint lost its subject, which is itself a failure."]
    current = set(unbound_selectors())
    known = _baseline()
    failures = [f"NEW unbound selector: {item}" for item in sorted(current - known)]
    failures.extend(
        f"Baseline entry no longer unbound (shrink the baseline): {item}"
        for item in sorted(known - current)
    )
    return failures


if __name__ == "__main__":
    import sys

    if "--list" in sys.argv:
        print(json.dumps(unbound_selectors(), indent=2))
        raise SystemExit(0)
    errors = check()
    print("\n".join(errors) if errors else "Every e2e selector binds to something in the app source")
    raise SystemExit(bool(errors))
