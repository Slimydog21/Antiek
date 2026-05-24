"""Fixture for unannotated_bypass lint tests."""

from __future__ import annotations


def unannotated_duckdb_violation() -> None:
    con = duckdb.connect("path.db")  # type: ignore[name-defined]
    con.close()


def unannotated_requests_violation() -> None:
    response = requests.get("https://example.com")  # type: ignore[name-defined]
    print(response.status_code)


def annotated_with_context_is_allowed() -> None:
    with escape_hatch(reason="benchmark-needs-raw-duckdb"):  # type: ignore[name-defined]
        con = duckdb.connect("path.db")  # type: ignore[name-defined]
        con.close()


@escape_hatch(reason="weekly-compaction-script")  # type: ignore[name-defined]
def annotated_with_decorator_is_allowed() -> None:
    con = duckdb.connect("path.db")  # type: ignore[name-defined]
    con.execute("VACUUM")


def nested_with_escape_is_allowed() -> None:
    with escape_hatch(reason="benchmark"):  # type: ignore[name-defined]
        if True:
            response = requests.get("https://example.com")  # type: ignore[name-defined]
            assert response.status_code == 200


def escape_then_unannotated_violation() -> None:
    with escape_hatch(reason="ok-fine"):  # type: ignore[name-defined]
        con = duckdb.connect("p1.db")  # type: ignore[name-defined]
        con.close()
    second_con = duckdb.connect("p2.db")  # type: ignore[name-defined]
    second_con.close()
