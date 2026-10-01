"""Vendor Google's distributed OFL WOFF2 files byte-for-byte.

--refresh obtains current CSS and replaces the lock. Default reproduces the
locked assets. --check validates hashes, font axes and Latin coverage offline.
Tooling requires fonttools[woff]; the application has no font dependency.
"""
import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1] / "public/fonts/reading"
CSS = Path(__file__).resolve().parents[1] / "src/design/readingFonts.css"
REVISION = "9710da1eacb3be272583c3224dcb70f9da6eadbb"
FAMILIES = {
    "source-serif": ("sourceserif4", "Source+Serif+4", "ital,opsz,wght@0,8..60,200..900;1,8..60,200..900"),
    "source-sans": ("sourcesans3", "Source+Sans+3", "ital,wght@0,200..900;1,200..900"),
    "literata": ("literata", "Literata", "ital,opsz,wght@0,7..72,200..900;1,7..72,200..900"),
    "atkinson": ("atkinsonhyperlegiblenext", "Atkinson+Hyperlegible+Next", "ital,wght@0,200..800;1,200..800"),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def font_metadata(font):
    return {
        "family": font["name"].getDebugName(1),
        "version": font["name"].getDebugName(5),
        "copyright": font["name"].getDebugName(0),
        "glyph_count": len(font.getBestCmap()),
        "x_height_ratio": font["OS/2"].sxHeight / font["head"].unitsPerEm,
    }


def fetch(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def check():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    if digest(CSS.read_bytes()) != manifest["css_sha256"]:
        raise ValueError("Font CSS differs from the lock")
    total = 0
    latin = 0
    for entry in manifest["files"]:
        data = (ROOT / entry["file"]).read_bytes()
        if digest(data) != entry["sha256"]:
            raise ValueError(f"Hash mismatch: {entry['file']}")
        if entry["file"].endswith(".woff2"):
            font = TTFont(io.BytesIO(data))
            axes = {a.axisTag: [a.minValue, a.defaultValue, a.maxValue] for a in font["fvar"].axes}
            if axes != entry["axes"]:
                raise ValueError(f"Axis mismatch: {entry['file']}")
            if font_metadata(font) != entry["metadata"]:
                raise ValueError(f"Metadata mismatch: {entry['file']}")
            if not (axes["wght"][0] <= 400 and axes["wght"][2] >= 700):
                raise ValueError(f"Regular/bold unavailable: {entry['file']}")
            if entry["family_id"] in ["source-serif", "literata"] and "opsz" not in axes:
                raise ValueError(f"Optical size unavailable: {entry['file']}")
            if entry["subset"] == "latin":
                cmap = font.getBestCmap()
                for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789éöñÅ“”‘’–—…±×÷":
                    if ord(char) not in cmap:
                        raise ValueError(f"Missing {char!r}: {entry['file']}")
                latin += len(data)
            total += len(data)
    if total > 2_500_000 or latin > 800_000:
        raise ValueError(f"Portfolio exceeds byte budget: {total}, Latin {latin}")
    print(f"FONT_ASSETS_OK files={len(manifest['files'])} woff2_bytes={total} latin_bytes={latin}")


def refresh():
    ROOT.mkdir(parents=True, exist_ok=True)
    files = []
    rendered = []
    for key, (directory, family, axes) in FAMILIES.items():
        css_url = f"https://fonts.googleapis.com/css2?family={family}:{axes}&display=swap"
        raw = fetch(css_url)
        original = ROOT / f"{key}-upstream.txt"
        original.write_bytes(raw)
        files.append({"file": original.name, "source": css_url, "sha256": digest(raw), "bytes": len(raw)})
        for subset, block in re.findall(r"/\* ([\w-]+) \*/\s*(@font-face\s*\{[^}]+\})", raw.decode()):
            style = "italic" if "font-style: italic" in block else "regular"
            url = re.search(r"url\((https://fonts.gstatic.com/[^)]+)\)", block).group(1)
            name = f"{key}-{style}-{subset}.woff2"
            payload = fetch(url)
            (ROOT / name).write_bytes(payload)
            font = TTFont(io.BytesIO(payload))
            files.append({"file": name, "source": url, "sha256": digest(payload), "bytes": len(payload),
                          "family_id": key, "subset": subset, "style": style,
                          "axes": {a.axisTag: [a.minValue, a.defaultValue, a.maxValue] for a in font["fvar"].axes},
                          "metadata": font_metadata(font)})
            rendered.append(f"/* {key}, {style}, {subset} */\n" + block.replace(url, f"/fonts/reading/{name}"))
        url = f"https://raw.githubusercontent.com/google/fonts/{REVISION}/ofl/{directory}/OFL.txt"
        license_data = fetch(url)
        name = f"{key}-OFL.txt"
        (ROOT / name).write_bytes(license_data)
        files.append({"file": name, "source": url, "sha256": digest(license_data), "bytes": len(license_data)})
    CSS.write_text("/* Generated by scripts/vendor_reading_fonts.py. See public/fonts/reading/manifest.json. */\n" + "\n\n".join(rendered) + "\n")
    (ROOT / "manifest.json").write_text(json.dumps({"license_revision": REVISION, "distribution": "Google Fonts WOFF2 subsets, unmodified; same-origin CSS with original unicode ranges and axes", "css_sha256": digest(CSS.read_bytes()), "files": files}, indent=2) + "\n")
    # Remove only superseded, lane-owned assets from the earlier full-font build.
    current = {entry["file"] for entry in files}
    for path in ROOT.glob("*.woff2"):
        if path.name not in current:
            path.unlink()
    check()


def reproduce():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for entry in manifest["files"]:
        if entry["file"].endswith("-upstream.txt"):
            continue  # API CSS is mutable. The response captured in the lock is authoritative.
        payload = fetch(entry["source"])
        if digest(payload) != entry["sha256"]:
            raise ValueError(f"Upstream hash mismatch: {entry['file']}")
        (ROOT / entry["file"]).write_bytes(payload)
    check()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    elif args.refresh:
        refresh()
    else:
        reproduce()
