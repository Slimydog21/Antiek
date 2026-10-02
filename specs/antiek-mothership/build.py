#!/usr/bin/env python3
"""Inline ~/.claude/skills/htmlspec/templates/style.css into every *.src.html -> *.html (htmlspec invariant 1: self-contained)."""
import glob
import os

with open(os.path.expanduser("~/.claude/skills/htmlspec/templates/style.css")) as fh:
    css = fh.read()
for src in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "*.src.html"))):
    with open(src) as fh:
        html = fh.read()
    assert "/*STYLE*/" in html, src
    out = src.replace(".src.html", ".html")
    with open(out, "w") as fh:
        fh.write(html.replace("/*STYLE*/", css))
    print(os.path.basename(out), os.path.getsize(out))
