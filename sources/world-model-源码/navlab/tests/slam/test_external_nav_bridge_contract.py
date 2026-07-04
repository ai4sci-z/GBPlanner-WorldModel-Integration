from __future__ import annotations

from pathlib import Path

BRIDGE_SOURCE = Path(
    "navlab/common/slam/ros/bridges/navlab_external_nav_bridge/src/navlab_external_nav_bridge_node.cpp"
)
BRIDGE_PARAMS = Path(
    "navlab/common/slam/ros/bridges/navlab_external_nav_bridge/config/navlab_external_nav_bridge.params.yaml"
)
GO_SLAM_HELPERS = Path("orchestration/sim/internal/tasks/helpers/slam.go")
GO_EXTERNAL_NAV_BRIDGE_TEMPLATE = Path(
    "orchestration/sim/internal/tasks/helpers/templates/yaml/external_nav_bridge_params.yaml.tmpl"
)
RUNTIME_CONFIG = Path("navlab/config.toml")


def test_external_nav_bridge_merges_height_into_fcu_odom() -> None:
    source = BRIDGE_SOURCE.read_text(encoding="utf-8")

    assert "if (!last_odom_ || !last_height_)" in source
    assert "out.pose.pose.position.z = last_height_->z;" in source
    assert "out.twist.twist.linear.z = last_height_->vz;" in source
    assert "out.pose.covariance[14] = last_height_->covariance;" in source
    assert "out.twist.covariance[14] = last_height_->covariance;" in source


def test_external_nav_bridge_reports_height_sources() -> None:
    source = BRIDGE_SOURCE.read_text(encoding="utf-8")

    assert "xy_yaw_source" in source
    assert "z_source" in source
    assert "vz_source" in source


def test_external_nav_requires_height_by_default() -> None:
    assert 'declare_parameter("require_height_for_output", true)' in BRIDGE_SOURCE.read_text(encoding="utf-8")
    assert "require_height_for_output: true" in BRIDGE_PARAMS.read_text(encoding="utf-8")
    assert "require_height_for_output: true" in GO_EXTERNAL_NAV_BRIDGE_TEMPLATE.read_text(encoding="utf-8")
    assert '"require_height_for_external_nav":           true' in GO_SLAM_HELPERS.read_text(encoding="utf-8")
    assert "require_height_for_external_nav = true" in RUNTIME_CONFIG.read_text(encoding="utf-8")
