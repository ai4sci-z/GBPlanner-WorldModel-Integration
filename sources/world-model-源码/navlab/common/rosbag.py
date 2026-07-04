from __future__ import annotations

import functools
import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ParamSpec, TypeVar

DEFAULT_TOPIC_FILE = Path("/workspace/profiles/rosbag-topics.txt")
DEFAULT_OUTPUT_ROOT = Path("/workspace/artifacts/ros")
_PROFILE_PREFIXES = {"required", "optional"}


def parse_rosbag_topic_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = stripped.split()
    if parts[0] in _PROFILE_PREFIXES and len(parts) != 2:
        raise ValueError(f"invalid rosbag topic profile line: {line!r}")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2 and parts[0] in _PROFILE_PREFIXES:
        return parts[1]
    raise ValueError(f"invalid rosbag topic profile line: {line!r}")


def load_rosbag_topics(topic_file: str | Path) -> list[str]:
    path = Path(topic_file)
    if not path.is_file():
        raise FileNotFoundError(f"rosbag topic file missing: {path}")

    topics = [
        topic
        for line in path.read_text(encoding="utf-8").splitlines()
        if (topic := parse_rosbag_topic_line(line)) is not None
    ]
    if not topics:
        raise ValueError(f"no rosbag topics configured in {path}")
    return topics


@dataclass(frozen=True, slots=True)
class RosbagOptions:
    enabled: bool = False
    label: str = "run"
    topic_file: Path = DEFAULT_TOPIC_FILE
    output_root: Path = DEFAULT_OUTPUT_ROOT
    session_id: str = "manual"
    startup_delay_sec: float = 2.0


class RosbagRecorder:
    def __init__(self, options: RosbagOptions) -> None:
        self._options = options
        self._process: subprocess.Popen[str] | None = None
        self.output_dir: Path | None = None

    def __enter__(self) -> RosbagRecorder:
        if not self._options.enabled:
            return self

        topics = load_rosbag_topics(self._options.topic_file)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = self._options.output_root / self._options.session_id / self._options.label / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_uri = self.output_dir / "rosbag"

        command = ["ros2", "bag", "record", "-o", str(output_uri), "--topics", *topics]
        self._process = subprocess.Popen(command, start_new_session=True)
        time.sleep(self._options.startup_delay_sec)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._process is None:
            return
        try:
            os.killpg(self._process.pid, signal.SIGINT)
            self._process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(self._process.pid, signal.SIGKILL)
            self._process.wait(timeout=5)


P = ParamSpec("P")
R = TypeVar("R")


def with_rosbag_recording(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(
        *args: P.args,
        rosbag_options: RosbagOptions | None = None,
        **kwargs: P.kwargs,
    ) -> R:
        options = rosbag_options or RosbagOptions()
        with RosbagRecorder(options):
            return func(*args, **kwargs)

    return wrapper
