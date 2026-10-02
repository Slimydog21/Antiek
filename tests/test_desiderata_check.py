

# ── network + poll-deadline exemptions (2026-09-22) ───────────────────────────


def _findings(tmp_path, body: str) -> list[str]:
    """Run the lint over one synthetic test file and return its messages."""
    from tools.lint.test_desiderata_check import find_violations

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_probe.py").write_text(body, encoding="utf-8")
    return [v.message for v in find_violations([tests_dir], ("determinism",), root=tmp_path)]


def test_httpx_client_with_a_mock_transport_is_not_a_network_call(tmp_path) -> None:
    """72 of the lint's 99 findings on main were this shape — all false.

    The transport is usually built by a module-level helper, so
    `_network_mocked_in_scope` (which walks only the test body) cannot see it.
    """
    body = (
        "import httpx\n\n\n"
        "def _transport():\n"
        "    return httpx.MockTransport(lambda r: httpx.Response(200))\n\n\n"
        "def test_uses_a_mock():\n"
        "    with httpx.Client(transport=_transport()) as c:\n"
        "        assert c is not None\n"
    )
    assert not [m for m in _findings(tmp_path, body) if "network call" in m]


def test_an_explicitly_real_transport_still_flags(tmp_path) -> None:
    """The exemption must stay narrow: opting INTO real networking is still a finding."""
    body = (
        "import httpx\n\n\n"
        "def test_uses_the_real_thing():\n"
        "    with httpx.Client(transport=httpx.HTTPTransport()) as c:\n"
        "        assert c is not None\n"
    )
    assert [m for m in _findings(tmp_path, body) if "network call" in m]


def test_a_poll_deadline_guard_is_not_a_time_of_day_assertion(tmp_path) -> None:
    """`assert monotonic() < deadline` is a timeout guard, not a clock read.

    The rule's own docstring already exempts the `while time.time() < deadline`
    form; the assert form is the same idiom with a hard failure instead of a
    silent exit.
    """
    body = (
        "import time\n\n\n"
        "def test_polls():\n"
        "    deadline = time.monotonic() + 3\n"
        "    while True:\n"
        "        assert time.monotonic() < deadline\n"
        "        break\n"
    )
    assert not [m for m in _findings(tmp_path, body) if "wall-clock" in m]


def test_a_boundary_clock_read_still_flags(tmp_path) -> None:
    """The shape the rule exists for must survive both exemptions.

    Here the clock is the RIGHT operand and the left is a value under test —
    flaky exactly at a second boundary.
    """
    body = (
        "import time\n\n\n"
        "def test_boundary():\n"
        "    issued_at = 5\n"
        "    assert issued_at <= int(time.time())\n"
    )
    assert [m for m in _findings(tmp_path, body) if "wall-clock" in m]
