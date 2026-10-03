"""The public replay phase never publishes the worker's private recovery report."""

import pytest

from interfaces.research.api.public_replay_health import _public_note_taker_replay


@pytest.mark.parametrize(
    "status",
    [
        "starting",
        "waiting_for_database",
        "waiting_for_writer",
        "catching_up",
        "current",
        "backoff",
        "idle",
    ],
)
def test_public_phase_withholds_current_and_future_private_fields(status: str) -> None:
    private_fields = {
        "investigations": 12,
        "failures": 3,
        "consecutive_barren_passes": 4,
        "suppressed_failures": 2,
        "backoff_s": 30,
        "last_success_at": "synthetic-success-time",
        "last_failure_at": "synthetic-failure-time",
        "last_failure_class": "SyntheticPrivateError",
        "last_failure_investigation": "synthetic-private-investigation",
        "future_private_field": {"owner": "synthetic-private-owner"},
    }
    report = {"status": status, **private_fields}
    original = report.copy()

    public = _public_note_taker_replay(report)

    assert public == {"status": status}
    assert public is not report
    assert report == original
    assert report["future_private_field"] is original["future_private_field"]


@pytest.mark.parametrize(
    "report",
    [
        None,
        False,
        0,
        "current",
        [],
        [("status", "current")],
        {},
        {"status": None},
        {"status": False},
        {"status": 1},
        {"status": []},
        {"status": {}},
        {"status": "unknown"},
        {"status": "CURRENT"},
        {"status": "current "},
    ],
)
def test_unadmitted_report_does_not_invent_a_public_phase(report: object) -> None:
    assert _public_note_taker_replay(report) == {}


def test_dict_subclass_is_not_a_public_report() -> None:
    class PrivateReport(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            raise AssertionError("unadmitted mapping must not be consulted")

    assert _public_note_taker_replay(PrivateReport(status="current")) == {}


def test_string_subclass_is_not_an_admitted_phase() -> None:
    class PrivatePhase(str):
        def __eq__(self, other: object) -> bool:
            raise AssertionError("unadmitted string must not be compared")

    assert _public_note_taker_replay({"status": PrivatePhase("current")}) == {}
