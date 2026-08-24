import math

from planning_frame import should_forward_tf, valid_external_nav_odom


def test_forwards_sim_time_non_owned_transform():
    assert should_forward_tf(42, "base_link", "lidar3d_frame") is True


def test_drops_wall_epoch_transform():
    assert should_forward_tf(1_787_543_900, "map", "laser") is False


def test_replaces_original_planar_map_to_body_transform():
    assert should_forward_tf(42, "map", "base_link") is False


def test_accepts_finite_external_nav_planning_state():
    assert valid_external_nav_odom(
        "external_nav", "base_link", (1.0, 2.0, 0.5), (0.0, 0.0, 0.0, 1.0)
    ) is True


def test_rejects_wrong_frame_or_nonfinite_height():
    assert valid_external_nav_odom(
        "map", "base_link", (1.0, 2.0, 0.5), (0.0, 0.0, 0.0, 1.0)
    ) is False
    assert valid_external_nav_odom(
        "external_nav", "base_link", (1.0, 2.0, math.nan), (0.0, 0.0, 0.0, 1.0)
    ) is False
