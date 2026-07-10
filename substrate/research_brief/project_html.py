"""Standalone HTML projection and parsing for editable brief fields."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from html.parser import HTMLParser

from .model import BriefState, BudgetTuple, ResearchBrief


def project_to_html(brief: ResearchBrief) -> str:
    """Project a brief to a standalone, human-editable HTML document."""
    budget = brief.budget
    assert isinstance(budget, BudgetTuple)
    fields: tuple[tuple[str, str], ...] = (
        ("question", brief.question),
        ("scope", brief.scope),
        ("exclusions", "\n".join(brief.exclusions)),
        ("source_preferences", "\n".join(brief.source_preferences)),
        ("budget_tier", budget.tier),
        ("budget_duration_minutes", str(budget.duration_minutes)),
        ("budget_fanout_depth", str(budget.fanout_depth)),
        ("price_ceiling", "" if brief.price_ceiling is None else str(brief.price_ceiling)),
        ("unattended", str(brief.unattended).lower()),
    )
    controls = "".join(
        f'<label>{escape(name.replace("_", " ").title())}'
        f'<textarea data-brief-field="{name}">{escape(value)}</textarea></label>'
        for name, value in fields
    )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>Research brief {escape(brief.brief_id)}</title></head><body>"
        f'<main data-brief-id="{escape(brief.brief_id)}" data-state="{brief.state.value}">'
        f"<h1>Research brief</h1>{controls}</main></body></html>"
    )


class _BriefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.brief_id: str | None = None
        self.state: str | None = None
        self.current: str | None = None
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "main":
            self.brief_id = values.get("data-brief-id")
            self.state = values.get("data-state")
        if tag == "textarea":
            self.current = values.get("data-brief-field")
            if self.current is not None:
                self.fields[self.current] = ""

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.fields[self.current] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "textarea":
            self.current = None


def parse_html(html: str) -> ResearchBrief:
    """Parse fields from a projected document after operator edits."""
    parser = _BriefParser()
    parser.feed(html)
    if parser.brief_id is None or parser.state is None:
        raise ValueError("not a projected research brief")
    fields = parser.fields
    ceiling = fields["price_ceiling"].strip()
    return ResearchBrief(
        brief_id=parser.brief_id,
        question=fields["question"],
        scope=fields["scope"],
        exclusions=tuple(filter(None, fields["exclusions"].splitlines())),
        source_preferences=tuple(filter(None, fields["source_preferences"].splitlines())),
        budget=BudgetTuple(
            fields["budget_tier"],
            int(fields["budget_duration_minutes"]),
            int(fields["budget_fanout_depth"]),
        ),
        price_ceiling=None if not ceiling else Decimal(ceiling),
        unattended=fields["unattended"].strip().lower() == "true",
        state=BriefState(parser.state),
    )

