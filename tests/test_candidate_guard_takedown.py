import pytest

from substrate.books.serve_guard import guard_candidate_full_text
from substrate.constants import PERSONAL_READING_CONTENT_CLASS


@pytest.mark.parametrize(
    ("content_class", "owner", "taken_down", "expected"),
    [
        pytest.param(
            PERSONAL_READING_CONTENT_CLASS, True, True, None, id="personal-owner-taken-down"
        ),
        pytest.param(
            PERSONAL_READING_CONTENT_CLASS, True, False, "body", id="personal-owner-readable"
        ),
        pytest.param(
            PERSONAL_READING_CONTENT_CLASS, False, True, None, id="personal-nonowner-taken-down"
        ),
        pytest.param(
            PERSONAL_READING_CONTENT_CLASS, False, False, None, id="personal-nonowner-private"
        ),
        pytest.param("public_domain", False, True, None, id="public-taken-down"),
        pytest.param("public_domain", False, False, "body", id="public-readable"),
        pytest.param("public_domain", True, True, None, id="public-owner-taken-down"),
    ],
)
def test_candidate_body_preserves_owner_privacy_and_takedown(
    content_class: str, owner: bool, taken_down: bool, expected: str | None
) -> None:
    assert (
        guard_candidate_full_text("body", content_class, {}, owner=owner, taken_down=taken_down)
        == expected
    )
