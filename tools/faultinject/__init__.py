"""Opt-in deterministic fault injectors for Antiek seam tests."""

from .inject import REGISTRY, FaultArmed, RegisteredInjector, arm
from .locked_db import LockedDBInjector, locked_db
from .provider_fault import ProviderFaultInjector, provider_fault
from .readonly_fs import ReadonlyFSInjector, readonly_fs

__all__ = [
    "FaultArmed",
    "REGISTRY",
    "RegisteredInjector",
    "arm",
    "ReadonlyFSInjector",
    "readonly_fs",
    "LockedDBInjector",
    "locked_db",
    "ProviderFaultInjector",
    "provider_fault",
]
