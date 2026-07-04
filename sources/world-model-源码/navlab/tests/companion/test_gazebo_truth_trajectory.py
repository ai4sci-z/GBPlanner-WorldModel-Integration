from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

from navlab.sim.companion.nodes.gazebo_truth_trajectory import (
    TrajectorySample,
    sample_from_odom,
    summarize_trajectory,
    write_trajectory_json,
)


def _odom(*, stamp_sec: int, stamp_nanosec: int, x: float, y: float, z: float, yaw: float):
    half_yaw = yaw / 2.0
    return SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=stamp_sec, nanosec=stamp_nanosec)),
        pose=SimpleNamespace(
            pose=SimpleNamespace(
                position=SimpleNamespace(x=x, y=y, z=z),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=math.sin(half_yaw), w=math.cos(half_yaw)),
            )
        ),
        twist=SimpleNamespace(
            twist=SimpleNamespace(
                linear=SimpleNamespace(x=0.1, y=0.2, z=0.3),
                angular=SimpleNamespace(z=0.4),
            )
        ),
    )


def test_sample_from_odom_writes_relative_time_and_pose() -> None:
    sample = sample_from_odom(_odom(stamp_sec=12, stamp_nanosec=500, x=1, y=2, z=3, yaw=0.5), first_stamp_sec=10.0)

    assert sample.t_sec == pytest_approx(2.0000005)
    assert sample.x_m == 1.0
    assert sample.y_m == 2.0
    assert sample.z_m == 3.0
    assert sample.yaw_rad == pytest_approx(0.5)
    assert sample.vx_mps == 0.1


def test_summarize_trajectory_reports_spans_and_path_length() -> None:
    samples = [
        TrajectorySample(0.0, 10.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0),
        TrajectorySample(1.0, 11.0, 3.0, 4.0, 0.5, 0.1, 0.0, 0.0, 0.0, 0.0),
    ]

    summary = summarize_trajectory(samples)

    assert summary["sample_count"] == 2
    assert summary["duration_sec"] == 1.0
    assert summary["horizontal_path_length_m"] == 5.0
    assert summary["horizontal_displacement_m"] == 5.0
    assert summary["z_span_m"] == 0.3
    assert summary["min_z_m"] == 0.2
    assert summary["max_z_m"] == 0.5


def test_write_trajectory_json_is_compact_artifact(tmp_path: Path) -> None:
    output = tmp_path / "gazebo_truth_trajectory.json"
    samples = [TrajectorySample(0.0, 10.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0)]

    write_trajectory_json(output_file=output, topic="/gazebo/truth/odom", samples=samples)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema"] == "navlab.gazebo_truth_trajectory.v1"
    assert payload["source_topic"] == "/gazebo/truth/odom"
    assert payload["summary"]["sample_count"] == 1
    assert payload["samples"][0]["z_m"] == 0.2


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value, abs=1e-6)
