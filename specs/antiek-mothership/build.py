#!/usr/bin/env python3
"""Inline ~/.claude/skills/htmlspec/templates/style.css into every *.src.html -> *.html (htmlspec invariant 1: self-contained)."""
import glob, os
css = open(os.path.expanduser("~/.claude/skills/htmlspec/templates/style.css")).read()
for src in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "*.src.html"))):
    html = open(src).read()
    assert "/*STYLE*/" in html, src
    out = src.replace(".src.html", ".html")
    open(out, "w").write(html.replace("/*STYLE*/", css))
    print(os.path.basename(out), os.path.getsize(out))
