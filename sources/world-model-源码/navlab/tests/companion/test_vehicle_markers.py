from __future__ import annotations

from math import isclose, pi

from navlab.sim.companion.nodes.vehicle_markers import (
    rotate_planar,
    vehicle_marker_parts,
    yaw_from_quaternion,
)


def test_vehicle_markers_are_portable_primitives() -> None:
    parts = vehicle_marker_parts()

    assert {part.shape for part in parts} <= {"arrow", "cube", "cylinder", "sphere"}
    assert all("mesh" not in part.namespace for part in parts)
    assert {part.namespace for part in parts} >= {
        "navlab_vehicle_body",
        "navlab_vehicle_nose",
        "navlab_vehicle_x2_lidar",
        "navlab_vehicle_rotor_0_disc",
        "navlab_vehicle_rotor_3_motor",
    }


def test_vehicle_marker_layout_has_forward_nose_and_four_rotors() -> None:
    parts = {part.namespace: part for part in vehicle_marker_parts()}
    nose = parts["navlab_vehicle_nose"]
    rotor_discs = [part for part in parts.values() if part.namespace.endswith("_disc")]

    assert nose.dx > 0.0
    assert nose.shape == "arrow"
    assert len(rotor_discs) == 4
    assert {round(part.dx, 2) for part in rotor_discs} == {-0.24, 0.24}
    assert {round(part.dy, 2) for part in rotor_discs} == {-0.24, 0.24}


def test_vehicle_marker_pose_helpers_use_standard_yaw_math() -> None:
    x, y = rotate_planar(1.0, 0.0, pi / 2.0)

    assert isclose(x, 0.0, abs_tol=1e-9)
    assert isclose(y, 1.0, abs_tol=1e-9)
    assert isclose(yaw_from_quaternion(0.0, 0.0, 0.0, 1.0), 0.0, abs_tol=1e-9)
