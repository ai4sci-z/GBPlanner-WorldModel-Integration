from __future__ import annotations

import math
from types import SimpleNamespace

from navlab.sim.companion.nodes.gazebo_truth_odom import (
    Pose2D,
    child_frame_matches,
    normalize_angle,
    pose_from_transform,
    relative_pose,
    select_transform,
    transform_identity,
    truth_odom_fields,
)


def _transform(*, x: float, y: float, z: float, yaw: float, child_frame_id: str = "", frame_id: str = ""):
    half_yaw = yaw * 0.5
    return SimpleNamespace(
        header=SimpleNamespace(frame_id=frame_id),
        child_frame_id=child_frame_id,
        transform=SimpleNamespace(
            translation=SimpleNamespace(x=x, y=y, z=z),
            rotation=SimpleNamespace(x=0.0, y=0.0, z=math.sin(half_yaw), w=math.cos(half_yaw)),
        ),
    )


def test_relative_pose_uses_first_gazebo_pose_as_origin() -> None:
    origin = Pose2D(x=10.0, y=20.0, z=0.2, yaw=0.5)
    pose = Pose2D(x=11.0, y=20.0, z=1.2, yaw=0.7)

    relative = relative_pose(pose=pose, origin=origin)

    assert relative.x == pytest_approx(math.cos(-0.5))
    assert relative.y == pytest_approx(math.sin(-0.5))
    assert relative.z == pytest_approx(1.0)
    assert relative.yaw == pytest_approx(0.2)


def test_truth_odom_fields_estimates_velocity_in_relative_frame() -> None:
    origin = Pose2D(x=0.0, y=0.0, z=0.2, yaw=0.0)
    previous = Pose2D(x=0.0, y=0.0, z=0.2, yaw=0.0)
    pose = Pose2D(x=2.0, y=1.0, z=1.2, yaw=0.4)

    fields = truth_odom_fields(
        pose=pose,
        origin=origin,
        previous_pose=previous,
        previous_monotonic=10.0,
        now_monotonic=12.0,
    )

    assert fields.x == pytest_approx(2.0)
    assert fields.y == pytest_approx(1.0)
    assert fields.z == pytest_approx(1.0)
    assert fields.vx == pytest_approx(1.0)
    assert fields.vy == pytest_approx(0.5)
    assert fields.vz == pytest_approx(0.5)
    assert fields.yaw_rate == pytest_approx(0.2)


def test_select_transform_prefers_child_frame_and_falls_back_to_index() -> None:
    transforms = [
        _transform(x=0.0, y=0.0, z=0.0, yaw=0.0),
        _transform(x=1.0, y=0.0, z=0.0, yaw=0.0, child_frame_id="quad"),
    ]

    assert select_transform(transforms, child_frame_id="quad", transform_index=0) is transforms[1]
    assert select_transform(transforms, child_frame_id="", transform_index=0) is transforms[0]


def test_select_transform_matches_gazebo_scoped_child_frame() -> None:
    transforms = [
        _transform(x=0.0, y=0.0, z=0.0, yaw=0.0, child_frame_id="ground_plane"),
        _transform(x=1.0, y=0.0, z=0.0, yaw=0.0, child_frame_id="navlab_iq_quad::base_link"),
        _transform(
            x=2.0,
            y=0.0,
            z=0.0,
            yaw=0.0,
            child_frame_id="navlab_iq_quad::iris_with_ardupilot::iris_with_standoffs::base_link",
        ),
    ]

    assert child_frame_matches("navlab_iq_quad::base_link", "navlab_iq_quad") is True
    assert select_transform(transforms, child_frame_id="navlab_iq_quad", transform_index=0) is transforms[1]
    assert child_frame_matches(
        "navlab_iq_quad::iris_with_ardupilot::iris_with_standoffs::base_link",
        "navlab_iq_quad::iris_with_ardupilot::iris_with_standoffs",
    )
    assert (
        select_transform(
            transforms,
            child_frame_id="navlab_iq_quad::iris_with_ardupilot::iris_with_standoffs",
            transform_index=0,
        )
        is transforms[2]
    )


def test_select_transform_does_not_fallback_when_child_frame_is_explicit() -> None:
    transforms = [_transform(x=0.0, y=0.0, z=0.0, yaw=0.0, child_frame_id="ground_plane")]

    assert select_transform(transforms, child_frame_id="missing_model", transform_index=0) is None


def test_select_transform_can_match_pose_info_header_frame() -> None:
    transforms = [
        _transform(x=0.0, y=0.0, z=0.0, yaw=0.0, frame_id="ground_plane"),
        _transform(
            x=1.0,
            y=0.0,
            z=0.0,
            yaw=0.0,
            frame_id="navlab_iq_quad::iris_with_ardupilot::iris_with_standoffs",
        ),
    ]

    selected = select_transform(
        transforms,
        child_frame_id="navlab_iq_quad::iris_with_ardupilot::iris_with_standoffs",
        transform_index=0,
    )
    assert selected is transforms[1]
    assert transform_identity(selected) == "navlab_iq_quad::iris_with_ardupilot::iris_with_standoffs"


def test_pose_from_transform_reads_yaw_quaternion() -> None:
    pose = pose_from_transform(_transform(x=1.0, y=2.0, z=3.0, yaw=-0.25))

    assert pose.x == pytest_approx(1.0)
    assert pose.y == pytest_approx(2.0)
    assert pose.z == pytest_approx(3.0)
    assert normalize_angle(pose.yaw + 0.25) == pytest_approx(0.0)


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value, abs=1e-6)
