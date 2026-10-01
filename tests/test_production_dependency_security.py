"""Security floors shared by the production lock and CI constraint set."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_urllib3_lock_and_constraint_agree_at_or_above_2_8_0() -> None:
    """Close the three urllib3 2.7.0 advisories fixed in 2.8.0.

    The deploy audit reports advisories without failing a release because a
    deploy cannot safely mutate an already-satisfied dependency. This guard
    makes the source release carry the fix before deployment: the exact lock
    and the CI constraint pin must agree, and both must meet the security
    floor. A future coordinated upgrade may move both pins above 2.8.0.
    """

    with (_REPO / "uv.lock").open("rb") as lock_file:
        lock = tomllib.load(lock_file)
    constraints = (_REPO / "tools" / "lints" / "constraints.txt").read_text(encoding="utf-8")
    constraint_match = re.search(r"^urllib3==([0-9.]+)$", constraints, re.MULTILINE)
    assert constraint_match is not None
    packages = [
        package["version"]
        for package in lock["package"]
        if package["name"].lower() == "urllib3"
    ]
    assert packages == [constraint_match.group(1)]
    assert _version_tuple(packages[0]) >= (2, 8, 0)
