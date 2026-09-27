"""O1 admission accounting with disposable objects, no database or capture."""

from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest

from runtime import protected_owner
from runtime.protected_owner import (
    AdmissionError,
    CaptureDisabled,
    DrainTimeout,
    LeaseExpired,
    OwnerAdmission,
    OwnerState,
    SourceChanged,
    SourceIdentity,
    StaleGeneration,
)


def fixture(*, warm_seconds: float = 0, clock=time.monotonic):
    identity = SourceIdentity(uuid4(), 11, 22)
    current = [identity]
    opened: list[object] = []
    closed: list[object] = []

    def open_handle():
        value = object()
        opened.append(value)
        return value

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: current[0],
        open_handle=open_handle,
        close_handle=closed.append,
        warm_seconds=warm_seconds,
        clock=clock,
    )
    return owner, current, opened, closed


def admit(owner, seconds=2):
    return owner.admit(
        generation=owner.identity.generation_uuid, deadline=time.monotonic() + seconds
    )


def test_child_survives_parent_close_and_close_is_idempotent():
    owner, _, opened, closed = fixture()
    parent = admit(owner)
    child = parent.child()
    handle = child.use()
    parent.close()
    parent.close()
    assert owner.borrowers == 1
    assert owner.physical_handles == 1
    assert child.use() is handle
    with pytest.raises(LeaseExpired):
        parent.use()
    child.close()
    child.close()
    assert owner.borrowers == owner.physical_handles == 0
    assert opened == closed == [handle]


def test_warm_handle_counts_and_is_reused_then_expires():
    now = [100.0]
    owner, _, opened, closed = fixture(warm_seconds=10, clock=lambda: now[0])
    first = owner.admit(generation=owner.identity.generation_uuid, deadline=200)
    handle = first.use()
    first.close()
    assert owner.physical_handles == 1
    with pytest.raises(LeaseExpired):
        first.use()
    second = owner.admit(generation=owner.identity.generation_uuid, deadline=200)
    assert second.use() is handle
    second.close()
    now[0] = 111.0
    assert owner.physical_handles == 0
    assert closed == [handle]
    assert len(opened) == 1


def test_waiter_handoff_does_not_wait_for_warm_expiry_and_child_blocks_transfer():
    owner, _, opened, _ = fixture(warm_seconds=20)
    parent = admit(owner)
    child = parent.child()
    parent.close()
    got = threading.Event()
    result = []

    def wait_for_handle():
        next_lease = admit(owner)
        result.append(next_lease.use())
        next_lease.close()
        got.set()

    thread = threading.Thread(target=wait_for_handle)
    thread.start()
    assert not got.wait(0.05)
    child.close()
    assert got.wait(0.5)
    thread.join(1)
    assert result == opened


def test_freeze_blocks_admission_and_drain_waits_for_promised_child():
    owner, _, opened, closed = fixture(warm_seconds=20)
    parent = admit(owner)
    child = parent.child()
    parent.close()
    owner.freeze()
    with pytest.raises(AdmissionError):
        admit(owner)
    with pytest.raises(DrainTimeout):
        owner.drain(deadline=time.monotonic() + 0.02)
    assert owner.state is OwnerState.REFUSED
    assert child.use() is opened[0]
    assert closed == []
    child.close()
    assert closed == opened


def test_successful_drain_closes_warm_handle_without_capture():
    owner, _, opened, closed = fixture(warm_seconds=20)
    lease = admit(owner)
    lease.close()
    owner.freeze()
    owner.drain(deadline=time.monotonic() + 1)
    assert closed == opened
    with pytest.raises(CaptureDisabled):
        owner.capture()


def test_deadline_and_disconnect_reclaim_children_exactly_once():
    owner, _, opened, closed = fixture()
    parent = owner.admit(
        generation=owner.identity.generation_uuid, deadline=time.monotonic() + 0.03
    )
    child = parent.child()
    limit = time.monotonic() + 1
    while owner.physical_handles and time.monotonic() < limit:
        time.sleep(0.005)
    assert closed == opened
    with pytest.raises(LeaseExpired):
        child.use()
    parent.close()
    child.close()
    parent.disconnect()
    assert len(closed) == 1
    second = admit(owner)
    second_child = second.child()
    second.disconnect()
    second.disconnect()
    assert len(closed) == 2
    with pytest.raises(LeaseExpired):
        second_child.use()


def test_stale_generation_and_source_replacement_refuse():
    owner, current, opened, closed = fixture()
    with pytest.raises(StaleGeneration):
        owner.admit(generation=uuid4(), deadline=time.monotonic() + 1)
    lease = admit(owner)
    child = lease.child()
    current[0] = SourceIdentity(owner.identity.generation_uuid, 11, 23)
    with pytest.raises(SourceChanged):
        child.use()
    with pytest.raises(SourceChanged):
        owner.freeze()
    assert owner.state is OwnerState.REFUSED
    lease.close()
    child.close()
    assert closed == opened


def test_source_changes_during_drain_refuses_even_after_release():
    owner, current, opened, closed = fixture()
    lease = admit(owner)
    owner.freeze()
    current[0] = SourceIdentity(uuid4(), 11, 22)
    lease.close()
    with pytest.raises(SourceChanged):
        owner.drain(deadline=time.monotonic() + 1)
    assert closed == opened


def test_close_callback_can_reenter_owner_without_deadlock():
    identity = SourceIdentity(uuid4(), 1, 2)
    observed = []
    owner = OwnerAdmission(
        identity,
        current_identity=lambda: identity,
        open_handle=object,
        close_handle=lambda _: observed.append(owner.physical_handles),
    )
    lease = admit(owner)
    lease.close()
    assert observed == [1]
    assert owner.physical_handles == 0


def test_close_callback_block_does_not_hold_state_mutex():
    identity = SourceIdentity(uuid4(), 1, 2)
    entered = threading.Event()
    release = threading.Event()

    def close_handle(_):
        entered.set()
        assert release.wait(1)

    owner = OwnerAdmission(
        identity, current_identity=lambda: identity, open_handle=object, close_handle=close_handle
    )
    lease = admit(owner)
    thread = threading.Thread(target=lease.close)
    thread.start()
    assert entered.wait(1)
    assert owner.physical_handles == 1
    release.set()
    thread.join(1)
    assert not thread.is_alive()
    assert owner.physical_handles == 0


def test_concurrent_parent_child_close_and_disconnect_release_once():
    owner, _, opened, closed = fixture()
    parent = admit(owner)
    child = parent.child()
    start = threading.Barrier(4)
    threads = [
        threading.Thread(target=lambda action=action: (start.wait(), action()))
        for action in (parent.close, child.close, parent.disconnect)
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(1)
        assert not thread.is_alive()
    assert owner.borrowers == owner.physical_handles == 0
    assert closed == opened


def test_close_failure_refuses_and_keeps_physical_handle_counted():
    identity = SourceIdentity(uuid4(), 1, 2)
    handle = object()

    def close_handle(_):
        raise OSError("close failed")

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: identity,
        open_handle=lambda: handle,
        close_handle=close_handle,
    )
    lease = admit(owner)
    with pytest.raises(OSError):
        lease.close()
    assert owner.state is OwnerState.REFUSED
    assert owner.physical_handles == 1


def test_warm_handle_expires_without_another_owner_call():
    owner, _, opened, closed = fixture(warm_seconds=0.03)
    lease = admit(owner)
    lease.close()
    limit = time.monotonic() + 1
    while len(closed) == 0 and time.monotonic() < limit:
        time.sleep(0.005)
    assert closed == opened


def test_external_handoff_waits_for_child_and_closes_warm_slot():
    owner, _, opened, closed = fixture(warm_seconds=20)
    parent = admit(owner)
    child = parent.child()
    parent.close()
    completed = threading.Event()

    def handoff():
        owner.handoff_to_external_waiter(deadline=time.monotonic() + 1)
        completed.set()

    thread = threading.Thread(target=handoff)
    thread.start()
    assert not completed.wait(0.05)
    with pytest.raises(AdmissionError):
        admit(owner)
    child.close()
    assert completed.wait(0.5)
    thread.join(1)
    assert closed == opened


def test_freeze_during_slow_open_waits_for_close_and_never_admits():
    identity = SourceIdentity(uuid4(), 1, 2)
    entered = threading.Event()
    release = threading.Event()
    closed = []
    outcome = []

    def open_handle():
        entered.set()
        assert release.wait(1)
        return object()

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: identity,
        open_handle=open_handle,
        close_handle=closed.append,
    )

    def opener():
        try:
            admit(owner)
        except AdmissionError as exc:
            outcome.append(exc)

    thread = threading.Thread(target=opener)
    thread.start()
    assert entered.wait(1)
    owner.freeze()
    with pytest.raises(DrainTimeout):
        owner.drain(deadline=time.monotonic() + 0.02)
    release.set()
    thread.join(1)
    assert not thread.is_alive()
    assert len(outcome) == len(closed) == 1
    assert owner.physical_handles == 0


def test_source_swap_during_open_refuses_admission_and_closes_handle():
    identity = SourceIdentity(uuid4(), 1, 2)
    current = [identity]
    entered = threading.Event()
    release = threading.Event()
    closed = []
    outcome = []

    def open_handle():
        entered.set()
        assert release.wait(1)
        return object()

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: current[0],
        open_handle=open_handle,
        close_handle=closed.append,
    )

    def opener():
        try:
            admit(owner)
        except SourceChanged as exc:
            outcome.append(exc)

    thread = threading.Thread(target=opener)
    thread.start()
    assert entered.wait(1)
    current[0] = SourceIdentity(uuid4(), 1, 2)
    release.set()
    thread.join(1)
    assert not thread.is_alive()
    assert len(outcome) == len(closed) == 1
    assert owner.state is OwnerState.REFUSED


def test_open_finishing_after_deadline_closes_handle_before_refusal():
    now = [10.0]
    identity = SourceIdentity(uuid4(), 1, 2)
    opened = []
    closed = []

    def open_handle():
        handle = object()
        opened.append(handle)
        now[0] = 12.0
        return handle

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: identity,
        open_handle=open_handle,
        close_handle=closed.append,
        clock=lambda: now[0],
    )
    with pytest.raises(LeaseExpired):
        owner.admit(generation=identity.generation_uuid, deadline=11.0)
    assert owner.borrowers == owner.physical_handles == 0
    assert closed == opened

    lease = owner.admit(generation=identity.generation_uuid, deadline=20.0)
    lease.close()
    assert closed == opened


def test_probe_after_open_crossing_deadline_closes_only_unassigned_handle():
    now = [10.0]
    identity = SourceIdentity(uuid4(), 1, 2)
    probes = [0]
    opened = []
    closed = []

    def current_identity():
        probes[0] += 1
        if probes[0] == 3:
            now[0] = 12.0
        return identity

    def open_handle():
        handle = object()
        opened.append(handle)
        return handle

    owner = OwnerAdmission(
        identity,
        current_identity=current_identity,
        open_handle=open_handle,
        close_handle=closed.append,
        warm_seconds=20,
        clock=lambda: now[0],
    )
    with pytest.raises(LeaseExpired):
        owner.admit(generation=identity.generation_uuid, deadline=11.0)
    assert closed == opened
    assert owner.physical_handles == 0

    lease = owner.admit(generation=identity.generation_uuid, deadline=30.0)
    lease.close()
    assert owner.physical_handles == 1
    with pytest.raises(LeaseExpired):
        owner.admit(generation=identity.generation_uuid, deadline=11.0)
    assert len(opened) == 2
    assert len(closed) == 1
    assert owner.physical_handles == 1
    owner.freeze()
    assert closed == opened


@pytest.mark.parametrize("failure_mode", ["deadline", "source_swap"])
def test_failed_close_of_unassigned_handle_is_not_retried(failure_mode):
    now = [10.0]
    identity = SourceIdentity(uuid4(), 1, 2)
    current = [identity]
    handle = object()
    close_calls = []

    def open_handle():
        if failure_mode == "deadline":
            now[0] = 12.0
        else:
            current[0] = SourceIdentity(uuid4(), 1, 2)
        return handle

    def close_handle(value):
        close_calls.append(value)
        raise OSError("unknown physical close outcome")

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: current[0],
        open_handle=open_handle,
        close_handle=close_handle,
        clock=lambda: now[0],
    )
    with pytest.raises(OSError, match="unknown physical close outcome"):
        owner.admit(generation=identity.generation_uuid, deadline=11.0)
    assert close_calls == [handle]
    assert owner.state is OwnerState.REFUSED
    assert owner.physical_handles == 1


def test_freeze_during_warm_reap_blocks_a_new_open():
    now = [10.0]
    identity = SourceIdentity(uuid4(), 1, 2)
    opened = []
    closed = []

    def open_handle():
        handle = object()
        opened.append(handle)
        return handle

    def close_handle(handle):
        closed.append(handle)
        owner.freeze()

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: identity,
        open_handle=open_handle,
        close_handle=close_handle,
        warm_seconds=1,
        clock=lambda: now[0],
    )
    first = owner.admit(generation=identity.generation_uuid, deadline=20.0)
    first.close()
    now[0] = 12.0
    with pytest.raises(AdmissionError):
        owner.admit(generation=identity.generation_uuid, deadline=20.0)
    assert owner.state is OwnerState.FREEZING
    assert len(opened) == 1
    assert closed == opened


def test_short_drain_refusal_cannot_become_long_drain_success():
    owner, _, opened, closed = fixture()
    parent = admit(owner)
    child = parent.child()
    parent.close()
    owner.freeze()
    started = threading.Event()
    outcome = []

    def long_drain():
        started.set()
        try:
            owner.drain(deadline=time.monotonic() + 1)
        except AdmissionError as exc:
            outcome.append(exc)
        else:
            outcome.append("success")

    thread = threading.Thread(target=long_drain)
    thread.start()
    assert started.wait(1)
    with pytest.raises(DrainTimeout):
        owner.drain(deadline=time.monotonic() + 0.02)
    assert owner.state is OwnerState.REFUSED
    child.close()
    thread.join(1)
    assert not thread.is_alive()
    assert len(outcome) == 1
    assert isinstance(outcome[0], AdmissionError)
    assert closed == opened


def test_deadline_callback_at_publication_cannot_strand_handle(monkeypatch):
    owner, _, opened, closed = fixture()

    def fire_before_start_returns(timer):
        timer.function()

    monkeypatch.setattr(protected_owner.threading.Timer, "start", fire_before_start_returns)
    lease = admit(owner)
    with pytest.raises(LeaseExpired):
        lease.use()
    assert owner.borrowers == owner.physical_handles == 0
    assert closed == opened


def test_lease_timer_start_failure_revokes_and_closes(monkeypatch):
    owner, _, opened, closed = fixture(warm_seconds=20)

    def fail_start(_):
        raise RuntimeError("cannot start timer")

    monkeypatch.setattr(protected_owner.threading.Timer, "start", fail_start)
    with pytest.raises(RuntimeError, match="cannot start timer"):
        admit(owner)
    assert owner.state is OwnerState.REFUSED
    assert owner.borrowers == owner.physical_handles == 0
    assert closed == opened


def test_warm_timer_start_failure_closes_instead_of_parking(monkeypatch):
    owner, _, opened, closed = fixture(warm_seconds=20)
    original_start = protected_owner.threading.Timer.start
    starts = [0]

    def fail_second_start(timer):
        starts[0] += 1
        if starts[0] == 2:
            raise RuntimeError("cannot start warm timer")
        return original_start(timer)

    monkeypatch.setattr(protected_owner.threading.Timer, "start", fail_second_start)
    lease = admit(owner)
    with pytest.raises(RuntimeError, match="cannot start warm timer"):
        lease.close()
    assert owner.state is OwnerState.REFUSED
    assert owner.borrowers == owner.physical_handles == 0
    assert closed == opened


def test_base_exception_from_close_keeps_handle_counted_and_refuses():
    identity = SourceIdentity(uuid4(), 1, 2)

    def close_handle(_):
        raise KeyboardInterrupt()

    owner = OwnerAdmission(
        identity,
        current_identity=lambda: identity,
        open_handle=object,
        close_handle=close_handle,
    )
    lease = admit(owner)
    with pytest.raises(KeyboardInterrupt):
        lease.close()
    assert owner.state is OwnerState.REFUSED
    assert owner.physical_handles == 1
