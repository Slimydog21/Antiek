from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "docs/htmlspec/live-integration-gates"
SPRINTS = tuple(sorted(SPEC.glob("sprint-*.html")))


class _HtmlContract(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.sections: list[str | None] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if value := values.get("id"):
            self.ids.add(value)
        if tag == "a" and (href := values.get("href")):
            self.hrefs.append(href)
        if tag == "section":
            self.sections.append(values.get("id"))


def _parse(path: Path) -> tuple[str, _HtmlContract]:
    text = path.read_text(encoding="utf-8")
    parser = _HtmlContract()
    parser.feed(text)
    return text, parser


def test_master_has_lineage_and_exact_sprint_roster() -> None:
    text, parsed = _parse(SPEC / "index.html")
    assert "spec-lineage" in parsed.ids
    assert len(SPRINTS) == 7
    assert {path.name for path in SPRINTS} == {
        f"sprint-{number:02d}-{slug}.html"
        for number, slug in enumerate(
            (
                "arxiv-hydration",
                "substack-acquisition",
                "twin-seed",
                "midnight-oil-live-step",
                "digital-book-payment",
                "collective-council",
                "notdiamond-advisory",
            ),
            start=1,
        )
    }
    assert all(path.name in text for path in SPRINTS)
    assert parsed.sections[-1] == "harness-hint-run"


def test_sprints_are_self_contained_cold_executable_contracts() -> None:
    values = (
        "1 · Intellectual honesty",
        "2 · Fairness",
        "3 · Rigor",
        "4 · Diligence",
        "5 · Defensibility",
    )
    for sprint in SPRINTS:
        text, parsed = _parse(sprint)
        assert "<style>" in text
        assert '<link rel="stylesheet"' not in text
        assert "<script" not in text
        assert 3 <= text.count('<div class="milestone">') <= 10
        assert all(text.count(value) == 1 for value in values)
        assert parsed.sections[-1] == "harness-hint"
        assert 'data-harness-rounds-floor="2"' in text
        assert 'data-harness-rounds-cap="6"' in text
        assert "NOT RUN" in text


def test_every_relative_html_link_resolves() -> None:
    for source in (SPEC / "index.html", *SPRINTS):
        _, parsed = _parse(source)
        for href in parsed.hrefs:
            split = urlsplit(href)
            if split.scheme or split.netloc:
                continue
            target = (source.parent / split.path).resolve()
            assert target.is_file(), f"{source.relative_to(REPO)} -> {href}"
            if split.fragment and target.suffix == ".html":
                _, target_parsed = _parse(target)
                assert split.fragment in target_parsed.ids
