"""Fail-closed normalization for cached scholarly and newsletter records."""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping
from html.parser import HTMLParser
from typing import cast

from substrate.corpus_contract import CorpusContractError
from substrate.corpus_contract.protocol import validate_utc

from .adapter import AcquisitionCorpusAdapter, _Entry


def _text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if type(value) is not str or not value.strip():
        raise CorpusContractError(f"{key} must be a nonempty exact str")
    return value


def _id(record: Mapping[str, object], key: str) -> str:
    value = _text(record, key)
    if value != value.strip():
        raise CorpusContractError(f"{key} must not have surrounding whitespace")
    return value


def _optional_text(record: Mapping[str, object], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise CorpusContractError(f"{key} must be null or a nonempty exact str")
    return value


def _time(record: Mapping[str, object]) -> datetime.datetime:
    value = record.get("fetched_at")
    if type(value) not in {int, float} or isinstance(value, bool):
        raise CorpusContractError("fetched_at must be a finite Unix timestamp")
    try:
        parsed = datetime.datetime.fromtimestamp(float(cast(int | float, value)), tz=datetime.UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise CorpusContractError("fetched_at must be a finite Unix timestamp") from error
    return validate_utc(parsed, "fetched_at")


def _records(records: Iterable[Mapping[str, object]]) -> tuple[Mapping[str, object], ...]:
    if type(records) is not tuple:
        raise CorpusContractError("records must be an exact tuple snapshot")
    if any(type(record) is not dict for record in records):
        raise CorpusContractError("each cached record must be an exact dict")
    return records


def _require(record: Mapping[str, object], keys: frozenset[str]) -> None:
    missing = keys - record.keys()
    if missing:
        raise CorpusContractError(f"cached record missing required fields: {sorted(missing)}")


def _abstract(record: Mapping[str, object]) -> str | None:
    direct = _optional_text(record, "abstract")
    if direct is not None:
        return direct
    raw = record.get("abstract_inverted_index")
    if raw is None:
        return None
    if type(raw) is not dict or not raw:
        raise CorpusContractError("abstract_inverted_index must be a nonempty exact dict")
    positioned: dict[int, str] = {}
    for word, locations in raw.items():
        if type(word) is not str or not word or type(locations) is not list or not locations:
            raise CorpusContractError("invalid abstract inverted index entry")
        for location in locations:
            if type(location) is not int or isinstance(location, bool) or location < 0:
                raise CorpusContractError("invalid abstract word position")
            if location in positioned:
                raise CorpusContractError("duplicate abstract word position")
            positioned[location] = word
    if set(positioned) != set(range(len(positioned))):
        raise CorpusContractError("abstract positions must be contiguous")
    return " ".join(positioned[index] for index in range(len(positioned)))


class _InertText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._suppressed: list[str] = []
        self.invalid_suppression = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in {"script", "style", "template", "noscript"}:
            self._suppressed.append(tag.casefold())

    def handle_endtag(self, tag: str) -> None:
        folded = tag.casefold()
        if folded in {"script", "style", "template", "noscript"}:
            if not self._suppressed or self._suppressed[-1] != folded:
                self.invalid_suppression = True
            else:
                self._suppressed.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag, attrs

    def handle_data(self, data: str) -> None:
        if not self._suppressed and data.strip():
            self.parts.append(data)


def _html_text(value: str) -> str:
    parser = _InertText()
    try:
        parser.feed(value)
        parser.close()
    except Exception as error:
        raise CorpusContractError("body_html is malformed") from error
    if parser._suppressed or parser.invalid_suppression:
        raise CorpusContractError("body_html has malformed suppressed content")
    text = " ".join(parser.parts)
    if not text.strip():
        raise CorpusContractError("accessible body_html produced no research text")
    return text


def from_arxiv_oai(records: tuple[Mapping[str, object], ...]) -> AcquisitionCorpusAdapter:
    entries: list[_Entry] = []
    for record in _records(records):
        _require(record, frozenset({"id", "title", "datestamp", "fetched_at", "source"}))
        if record.get("source") != "arxiv_oai_pmh":
            raise CorpusContractError("OAI record source mismatch")
        id, title, datestamp = (
            _id(record, "id"),
            _text(record, "title"),
            _text(record, "datestamp"),
        )
        search_text = f"{title}\nArXiv identifier: {id}\nOAI datestamp: {datestamp}"
        entries.append(
            _Entry(
                id,
                "arxiv_oai_pmh",
                search_text,
                title,
                _time(record),
                "source_terms_governed_metadata",
            )
        )
    return AcquisitionCorpusAdapter(tuple(entries))


def from_openalex(records: tuple[Mapping[str, object], ...]) -> AcquisitionCorpusAdapter:
    entries: list[_Entry] = []
    for record in _records(records):
        _require(record, frozenset({"id", "title", "fetched_at"}))
        id, title = _id(record, "id"), _text(record, "title")
        abstract = _abstract(record)
        content = "\n\n".join(part for part in (title, abstract) if part)
        search_text = f"{id}\n{content}"
        entries.append(
            _Entry(
                id,
                "openalex",
                search_text,
                content,
                _time(record),
                "source_terms_governed_metadata",
            )
        )
    return AcquisitionCorpusAdapter(tuple(entries))


def from_substack(records: tuple[Mapping[str, object], ...]) -> AcquisitionCorpusAdapter:
    entries: list[_Entry] = []
    for record in _records(records):
        _require(
            record,
            frozenset({"url", "title", "body_html", "accessible", "fetched_at"}),
        )
        id, title = _id(record, "url"), _text(record, "title")
        accessible = record.get("accessible")
        if type(accessible) is not bool:
            raise CorpusContractError("accessible must be an exact bool")
        body = record.get("body_html")
        if accessible:
            if type(body) is not str or not body.strip():
                raise CorpusContractError("accessible Substack record requires body_html")
            content = _html_text(body)
            search_text = f"{title}\n\n{content}"
            license_class = "publisher_rights_unknown_accessible"
        else:
            if body is not None:
                raise CorpusContractError("inaccessible Substack record must not retain body_html")
            content = None
            search_text = title
            license_class = "publisher_metadata_only"
        entries.append(_Entry(id, "substack", search_text, content, _time(record), license_class))
    return AcquisitionCorpusAdapter(tuple(entries))
