"""Reader-outline behavior pinned to the selected browser parser corpus."""

from __future__ import annotations

from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.books.html_sanitizer import SANITIZER_VERSION, sanitize_book_html
from substrate.graph import ensure_initialized
from substrate.reader_html.outline import (
    choose_initial_upload_title,
    outline_html_document,
)
from substrate.reader_html.store import (
    MAX_READER_HTML_CHARS,
    bounded_sanitized_reader_html,
    store_reader_html,
)


def _browser_cases() -> list[tuple[str, str, tuple[tuple[str, int], ...], int]]:
    cap = MAX_READER_HTML_CHARS
    return [
        (
            "two_headings",
            "<p>Lead text</p><h1>First <em>heading</em></h1><p>one</p><h2>Second</h2><p>two</p>",
            (("First heading", 0), ("Second", 1)),
            2,
        ),
        (
            "nested_malformed",
            "<article><h1>Outer <b>bold<h2>Inner</h2> tail</b></h1><h3>After</article>",
            (("Outer boldInner tail", 0), ("Inner", 1), ("After", 2)),
            3,
        ),
        (
            "table_headings",
            "<table><tr><td><h2>Cell one</h2><p>A</p></td>"
            "<td><h3>Cell two</h3><p>B</p></td></tr></table>",
            (("Cell one", 0), ("Cell two", 1)),
            2,
        ),
        (
            "duplicate_ids",
            '<h1 id="same">A</h1><h2 id="same">B</h2><h3 id="unique">C</h3>',
            (("A", 0), ("B", 1), ("C", 2)),
            3,
        ),
        (
            "empty_heading",
            "<h1> \n </h1><p>Visible</p><h2>&amp; &nbsp; Title</h2>",
            (("& \u00a0 Title", 0),),
            1,
        ),
        (
            "entities_whitespace",
            "<p>  Lead &amp; more </p><h1> A&nbsp;  B <span>C</span> </h1><p>tail</p>",
            (("A\u00a0  B C", 0),),
            1,
        ),
        (
            "preamble",
            "plain start<h2>Second-level start</h2><p>body</p>",
            (("Second-level start", 0),),
            1,
        ),
        ("no_headings", "<p>No headings <strong>here</strong>.</p>", (), 1),
        (
            "near_cap",
            "<p>"
            + ("x" * (cap - 3 - len("</p><h1>Boundary heading</h1>")))
            + "</p><h1>Boundary heading</h1>",
            (("Boundary heading", 0),),
            1,
        ),
        (
            "past_cap",
            "<p>" + ("x" * (cap - 3)) + "</p><h1>Beyond cap</h1>",
            (),
            1,
        ),
        (
            "ecma_nel",
            "<h1>\u0085</h1><h2>Real title</h2>",
            (("\u0085", 0), ("Real title", 1)),
            2,
        ),
        (
            "ecma_feff",
            "<h1>\ufeff</h1><h2>Real title</h2>",
            (("Real title", 0),),
            1,
        ),
        (
            "comment_in_heading",
            "<h1>One<!-- omitted -->Two</h1><h2>Next</h2>",
            (("OneTwo", 0), ("Next", 1)),
            2,
        ),
        (
            "foster_parented_table_heading",
            "<table><h2>Fostered</h2><tr><td>Cell</td></tr></table><h3>After</h3>",
            (("Fostered", 0), ("After", 1)),
            2,
        ),
        ("empty_body", "", (), 0),
        (
            "nested_formatting",
            "<h1>A <b>B</b> <em>C</em></h1><p>body</p><h2>D <span>E</span></h2>",
            (("A B C", 0), ("D E", 1)),
            2,
        ),
    ]


@pytest.mark.parametrize(
    ("name", "original_html", "expected_headings", "expected_windows"),
    _browser_cases(),
    ids=[case[0] for case in _browser_cases()],
)
def test_outline_matches_chrome_heading_oracle(
    name: str,
    original_html: str,
    expected_headings: tuple[tuple[str, int], ...],
    expected_windows: int,
) -> None:
    final_html = bounded_sanitized_reader_html(original_html)
    outline = outline_html_document(final_html)

    assert tuple((item.title, item.level) for item in outline.toc) == expected_headings, name
    assert tuple(item.page_index for item in outline.toc) == tuple(range(len(expected_headings)))
    assert outline.page_count == expected_windows
    assert outline.first_heading == (expected_headings[0][0] if expected_headings else None)


def test_outline_levels_are_relative_to_shallowest_visible_heading() -> None:
    outline = outline_html_document(
        bounded_sanitized_reader_html("<h4>Deep</h4><h2>Shallow</h2><h5>Deeper</h5>")
    )

    assert [(item.title, item.level) for item in outline.toc] == [
        ("Deep", 2),
        ("Shallow", 0),
        ("Deeper", 3),
    ]


def test_initial_title_uses_first_nonblank_candidate_and_keeps_inner_text() -> None:
    assert (
        choose_initial_upload_title(
            explicit_title="  Human\tchoice  ",
            first_heading="Heading",
            filename_stem="file",
            document_id="doc-1",
        )
        == "Human\tchoice"
    )
    assert (
        choose_initial_upload_title(
            explicit_title=" \ufeff ",
            first_heading="\u0085",
            filename_stem="  file  ",
            document_id="doc-1",
        )
        == "\u0085"
    )
    assert (
        choose_initial_upload_title(
            explicit_title=" \ufeff ",
            first_heading=" \ufeff ",
            filename_stem=" file stem ",
            document_id="doc-1",
        )
        == "file stem"
    )
    assert (
        choose_initial_upload_title(
            explicit_title=" ",
            first_heading=None,
            filename_stem=None,
            document_id="stable-doc-id",
        )
        == "stable-doc-id"
    )
    assert (
        choose_initial_upload_title(
            explicit_title=None,
            first_heading="Heading",
            filename_stem="file",
            document_id="doc-1",
        )
        == "Heading"
    )


@pytest.mark.parametrize(
    ("final_html", "expected_page_count"),
    [(" \t\n\ufeff", 0), ("<p></p>", 1)],
    ids=["javascript-blank", "nonblank-tag-only"],
)
def test_no_heading_page_count_matches_javascript_trim(
    final_html: str, expected_page_count: int
) -> None:
    outline = outline_html_document(final_html)

    assert outline.toc == ()
    assert outline.page_count == expected_page_count
    assert outline.first_heading is None


@pytest.mark.parametrize(
    "original_html",
    [
        "<article><h1>Stored title</h1><p>Body</p></article>",
        "<p>Prefix</p>" + ("x" * MAX_READER_HTML_CHARS) + "<h1>Outside cap</h1>",
    ],
    ids=["normal", "cap-boundary"],
)
def test_preview_matches_real_sidecar_write_and_revision(
    tmp_path: Path, original_html: str
) -> None:
    database_path = str(tmp_path / "graph.duckdb")
    ensure_initialized(database_path)
    document_id = f"doc-outline-{len(original_html)}"
    with connect_write(database_path, purpose="test/upload-reader-outline") as writer:
        writer.execute(
            """INSERT INTO documents (
                document_id, document_type, content_class, source_tier,
                raw_text, metadata, source_uri, title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                document_id,
                "web_article",
                "personal_reading",
                4,
                "source",
                "{}",
                "https://example.com/source",
                "First title",
            ],
        )
        expected_body = bounded_sanitized_reader_html(original_html)
        assert expected_body == sanitize_book_html(original_html[:MAX_READER_HTML_CHARS])
        expected_bytes = len(expected_body.encode("utf-8"))

        for expected_revision in (1, 2):
            byte_count = store_reader_html(
                writer,
                document_id=document_id,
                main_html=original_html,
                source_kind="upload",
                source_url=None,
            )
            stored = writer.execute(
                """SELECT html_body, sanitizer_version, revision, source_kind, source_url
                   FROM document_reader_html WHERE document_id = ?""",
                [document_id],
            ).fetchone()

            assert stored == (
                expected_body,
                SANITIZER_VERSION,
                expected_revision,
                "upload",
                None,
            )
            assert byte_count == expected_bytes
