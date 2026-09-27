"""Disposable admission and physical-handle accounting for a future owner.

This module neither opens a database nor implements capture. The caller supplies
an opaque handle factory and a source identity probe; no path or SQL is accepted.
``use()`` returns a fake/raw handle only inside a future trusted owner. A handle
must never cross an application RPC boundary.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar
from uuid import UUID

Handle = TypeVar("Handle")


@dataclass(frozen=True)
class SourceIdentity:
    generation_uuid: UUID
    device: int
    inode: int


class OwnerState(Enum):
    SERVING = "serving"
    FREEZING = "freezing"
    REFUSED = "refused"


class AdmissionError(RuntimeError):
    pass


class LeaseExpired(AdmissionError):
    pass


class StaleGeneration(AdmissionError):
    pass


class SourceChanged(AdmissionError):
    pass


class DrainTimeout(AdmissionError):
    pass


class CaptureDisabled(AdmissionError):
    pass


class OwnerAdmission(Generic[Handle]):  # noqa: UP046 - Python 3.11 syntax
    """One generation, one physical handle, and explicit borrower lifetimes.

    A transport must call ``disconnect`` when its peer disappears. Absolute
    deadlines and warm expiry have timers, so abandoned borrowers and parked
    handles release without a subsequent owner call.
    """

    def __init__(
        self,
        identity: SourceIdentity,
        *,
        current_identity: Callable[[], SourceIdentity],
        open_handle: Callable[[], Handle],
        close_handle: Callable[[Handle], None],
        warm_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(warm_seconds) or warm_seconds < 0:
            raise ValueError("warm_seconds must be finite and nonnegative")
        self.identity = identity
        self._current_identity = current_identity
        self._open_handle = open_handle
        self._close_handle = close_handle
        self._warm_seconds = warm_seconds
        self._clock = clock
        self._condition = threading.Condition(threading.RLock())
        self._handle: Handle | None = None
        self._opening = False
        self._closing = False
        self._close_failed = False
        self._active: Lease[Handle] | None = None
        self._warm_until: float | None = None
        self._warm_timer: threading.Timer | None = None
        self._state = OwnerState.SERVING
        self._identity_lost = False

    @property
    def state(self) -> OwnerState:
        with self._condition:
            return self._state

    @property
    def physical_handles(self) -> int:
        with self._condition:
            self._reap_warm()
            return int(self._handle is not None or self._closing)

    @property
    def borrowers(self) -> int:
        with self._condition:
            return self._active._borrowers if self._active is not None else 0

    def _check_identity(self) -> None:
        if self._identity_lost:
            raise SourceChanged("source identity was previously lost")
        try:
            matches = self._current_identity() == self.identity
        except Exception as exc:
            self._identity_lost = True
            self._state = OwnerState.REFUSED
            self._condition.notify_all()
            self._reap_warm()
            raise SourceChanged("source identity cannot be verified") from exc
        if not matches:
            self._identity_lost = True
            self._state = OwnerState.REFUSED
            self._condition.notify_all()
            self._reap_warm()
            raise SourceChanged("source generation or inode changed")

    def _close_physical(self) -> None:
        handle, self._handle = self._handle, None
        self._warm_until = None
        if self._warm_timer is not None:
            self._warm_timer.cancel()
            self._warm_timer = None
        if handle is not None:
            self._closing = True
            self._condition.release()
            try:
                self._close_handle(handle)
            except BaseException:
                self._condition.acquire()
                self._handle = handle
                self._close_failed = True
                self._state = OwnerState.REFUSED
                raise
            else:
                self._condition.acquire()
            finally:
                self._closing = False
                self._condition.notify_all()

    def _reap_warm(self) -> None:
        if (
            self._active is None
            and self._handle is not None
            and not self._close_failed
            and (
                self._state is not OwnerState.SERVING
                or (self._warm_until is not None and self._clock() >= self._warm_until)
            )
        ):
            self._close_physical()

    def _expire_warm(self) -> None:
        with self._condition:
            self._reap_warm()

    def admit(self, *, generation: UUID, deadline: float) -> Lease[Handle]:
        if not math.isfinite(deadline):
            raise ValueError("deadline must be finite and absolute monotonic time")
        with self._condition:
            if generation != self.identity.generation_uuid:
                raise StaleGeneration("requested generation differs from owner")
            opened_here = False
            try:
                while True:
                    self._check_identity()
                    if self._state is not OwnerState.SERVING:
                        raise AdmissionError("admission is frozen or refused")
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise LeaseExpired("admission deadline expired")
                    self._reap_warm()
                    # A physical close releases the mutex; freeze or identity
                    # drift can occur before this thread resumes.
                    self._check_identity()
                    if self._state is not OwnerState.SERVING:
                        raise AdmissionError("admission is frozen or refused")
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise LeaseExpired("admission deadline expired")
                    if self._active is None and not self._closing and not self._opening:
                        if self._handle is None:
                            self._opening = True
                            self._condition.release()
                            try:
                                handle = self._open_handle()
                            except BaseException:
                                self._condition.acquire()
                                self._opening = False
                                self._condition.notify_all()
                                raise
                            else:
                                self._condition.acquire()
                                self._handle = handle
                                opened_here = True
                                self._opening = False
                                self._condition.notify_all()
                                if (
                                    self._state is not OwnerState.SERVING
                                    or self._clock() >= deadline
                                ):
                                    self._close_physical()
                                continue
                        if self._warm_timer is not None:
                            self._warm_timer.cancel()
                            self._warm_timer = None
                        self._warm_until = None
                        lease = Lease(self, generation, deadline)
                        self._active = lease
                        opened_here = False
                        try:
                            lease._timer.start()
                        except BaseException:
                            self._state = OwnerState.REFUSED
                            lease._disconnect_locked()
                            raise
                        return lease
                    self._condition.wait(remaining)
            except BaseException:
                if (
                    opened_here
                    and self._active is None
                    and self._handle is handle
                    and not self._close_failed
                ):
                    self._close_physical()
                raise

    def _released(self, lease: Lease[Handle]) -> None:
        if self._active is not lease or lease._borrowers:
            return
        self._active = None
        lease._timer.cancel()
        if self._state is OwnerState.SERVING and self._warm_seconds > 0:
            self._warm_until = self._clock() + self._warm_seconds
            self._warm_timer = threading.Timer(self._warm_seconds, self._expire_warm)
            self._warm_timer.daemon = True
            try:
                self._warm_timer.start()
            except BaseException:
                self._state = OwnerState.REFUSED
                self._close_physical()
                raise
        else:
            self._close_physical()
        self._condition.notify_all()

    def freeze(self) -> None:
        with self._condition:
            self._check_identity()
            if self._state is OwnerState.REFUSED:
                raise AdmissionError("owner refused")
            self._state = OwnerState.FREEZING
            self._reap_warm()
            self._condition.notify_all()

    def drain(self, *, deadline: float) -> None:
        """Wait for physical release; timeout refuses without closing children."""
        if not math.isfinite(deadline):
            raise ValueError("deadline must be finite and absolute monotonic time")
        with self._condition:
            if self._state is not OwnerState.FREEZING:
                raise AdmissionError("freeze is required before drain")
            while True:
                self._check_identity()
                if self._state is not OwnerState.FREEZING:
                    raise AdmissionError("drain was refused")
                self._reap_warm()
                # Closing a warm handle releases the mutex. Another drain may
                # have timed out and made refusal permanent in that interval.
                self._check_identity()
                if self._state is not OwnerState.FREEZING:
                    raise AdmissionError("drain was refused")
                if self._handle is None and not self._closing and not self._opening:
                    return
                remaining = deadline - self._clock()
                if remaining <= 0:
                    self._state = OwnerState.REFUSED
                    self._condition.notify_all()
                    raise DrainTimeout("physical borrowers did not drain")
                self._condition.wait(remaining)

    def handoff_to_external_waiter(self, *, deadline: float) -> None:
        """Stop admission and release the handle for a privileged waiter.

        This is a one-way drain barrier. It grants no source or capture access.
        """
        self.freeze()
        self.drain(deadline=deadline)

    def capture(self) -> None:
        raise CaptureDisabled("capture has no implementation or success receipt")


class Lease(Generic[Handle]):  # noqa: UP046 - Python 3.11 syntax
    def __init__(self, owner: OwnerAdmission[Handle], generation: UUID, deadline: float) -> None:
        self._owner = owner
        self.generation = generation
        self.deadline = deadline
        self._borrowers = 1
        self._closed = False
        self._children: set[ChildLease[Handle]] = set()
        self._timer = threading.Timer(max(0.0, deadline - owner._clock()), self.disconnect)
        self._timer.daemon = True

    def _check(self) -> Handle:
        owner = self._owner
        owner._check_identity()
        if self.generation != owner.identity.generation_uuid:
            raise StaleGeneration("lease generation differs from owner")
        if self._closed or owner._active is not self:
            raise LeaseExpired("lease is closed")
        if owner._clock() >= self.deadline:
            self._disconnect_locked()
            raise LeaseExpired("lease deadline expired")
        assert owner._handle is not None
        return owner._handle

    def use(self) -> Handle:
        with self._owner._condition:
            return self._check()

    def child(self) -> ChildLease[Handle]:
        with self._owner._condition:
            self._check()
            child = ChildLease(self)
            self._children.add(child)
            self._borrowers += 1
            return child

    def close(self) -> None:
        with self._owner._condition:
            if not self._closed:
                self._closed = True
                self._borrowers -= 1
                self._owner._released(self)

    def _disconnect_locked(self) -> None:
        self._closed = True
        for child in self._children:
            child._closed = True
        self._children.clear()
        self._borrowers = 0
        self._owner._released(self)

    def disconnect(self) -> None:
        with self._owner._condition:
            self._disconnect_locked()

    def __enter__(self) -> Lease[Handle]:
        self.use()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class ChildLease(Generic[Handle]):  # noqa: UP046 - Python 3.11 syntax
    def __init__(self, parent: Lease[Handle]) -> None:
        self._parent = parent
        self._closed = False

    def use(self) -> Handle:
        parent = self._parent
        with parent._owner._condition:
            if self._closed:
                raise LeaseExpired("child is closed")
            parent._owner._check_identity()
            if parent.generation != parent._owner.identity.generation_uuid:
                raise StaleGeneration("child generation differs from owner")
            if parent._owner._clock() >= parent.deadline:
                parent._disconnect_locked()
                raise LeaseExpired("child deadline expired")
            if parent._owner._active is not parent:
                raise LeaseExpired("child is stale")
            assert parent._owner._handle is not None
            return parent._owner._handle

    def close(self) -> None:
        parent = self._parent
        with parent._owner._condition:
            if not self._closed:
                self._closed = True
                parent._children.discard(self)
                parent._borrowers -= 1
                parent._owner._released(parent)

    def __enter__(self) -> ChildLease[Handle]:
        self.use()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
