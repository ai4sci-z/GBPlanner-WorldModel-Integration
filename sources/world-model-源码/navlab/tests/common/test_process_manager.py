from __future__ import annotations

import sys
import time

from navlab.common.process_manager import ProcessManager


def test_process_manager_stops_started_subprocess() -> None:
    manager = ProcessManager()
    managed = manager.start_subprocess(
        "sleepy",
        [sys.executable, "-c", "import time; time.sleep(30)"],
    )

    assert managed.poll() is None
    manager.stop_all(timeout_sec=1)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and managed.poll() is None:
        time.sleep(0.05)
    assert managed.poll() is not None


def test_process_manager_stops_started_function_process() -> None:
    manager = ProcessManager()
    managed = manager.start_function("sleepy_function", time.sleep, 30)

    assert managed.poll() is None
    manager.stop_all(timeout_sec=1)

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and managed.poll() is None:
        time.sleep(0.05)
    assert managed.poll() is not None
