"""Read-only host headroom samples. Unknown samples never permit execution."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import ReasonCode

_SAMPLE_ERRORS = (OSError, ValueError, KeyError, subprocess.SubprocessError)


@dataclass(frozen=True)
class CapacitySnapshot:
    free_memory_percent: float
    free_disk_bytes: int
    memory_pressure: int | None = None


def linux_memory_percent(text: str) -> float:
    fields = {}
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] in {"MemTotal:", "MemAvailable:"}:
            if len(parts) != 3 or parts[2] != "kB" or parts[0] in fields:
                raise ValueError("invalid memory sample")
            fields[parts[0]] = int(parts[1])
    total, available = fields["MemTotal:"], fields["MemAvailable:"]
    if total <= 0 or not 0 <= available <= total:
        raise ValueError("invalid memory headroom")
    return 100 * available / total


def host_capacity(disk_path: Path) -> CapacitySnapshot | None:
    try:
        pressure = None
        if sys.platform == "linux":
            free = linux_memory_percent(Path("/proc/meminfo").read_text())
        elif sys.platform == "darwin":
            sample = subprocess.run(
                [
                    "/usr/sbin/sysctl",
                    "-n",
                    "kern.memorystatus_level",
                    "kern.memorystatus_vm_pressure_level",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
                env={"PATH": os.defpath},
            )
            values = sample.stdout.split()
            if len(values) != 2:
                return None
            free, pressure = float(values[0]), int(values[1])
            if pressure not in {1, 2, 4}:
                return None
        else:
            return None
        if not 0 <= free <= 100:
            return None
        return CapacitySnapshot(free, shutil.disk_usage(disk_path).free, pressure)
    except _SAMPLE_ERRORS:
        return None


def capacity_refusal(
    sample: CapacitySnapshot | None,
    min_free_memory_percent: float,
    min_free_disk_bytes: int,
    max_memory_pressure: int,
) -> ReasonCode | None:
    if sample is None or not 0 <= sample.free_memory_percent <= 100 or sample.free_disk_bytes < 0:
        return ReasonCode.CAPACITY_UNKNOWN
    if sample.memory_pressure is not None and sample.memory_pressure not in {1, 2, 4}:
        return ReasonCode.CAPACITY_UNKNOWN
    if sample.free_memory_percent < min_free_memory_percent or (
        sample.memory_pressure is not None and sample.memory_pressure > max_memory_pressure
    ):
        return ReasonCode.MEMORY_LOW
    if sample.free_disk_bytes < min_free_disk_bytes:
        return ReasonCode.DISK_LOW
    return None
