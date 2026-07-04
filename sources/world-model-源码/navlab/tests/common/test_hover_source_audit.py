from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path("scripts/diagnostics/hover_source_audit.py")
    spec = importlib.util.spec_from_file_location("hover_source_audit", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hover_source_audit_marks_first_divergence_as_summary_scoped(tmp_path: Path) -> None:
    module = _load_module()
    summary = {
        "run_id": "testrun",
        "metrics": {
            "gate": {
                "hover_xy_alignment": {
                    "window_source": "hover_status_phase_hover_hold",
                    "window_start_sec": 10.0,
                    "window_end_sec": 12.0,
                    "window_duration_sec": 2.0,
                    "sources": {
                        "gazebo_model_odometry": {
                            "source_topic": "/gazebo/model/odometry",
                            "frame_id": "odom",
                            "child_frame_id": "base_link",
                            "sample_count": 2,
                            "raw_sample_count": 2,
                            "final_x_m": 1.0,
                            "final_y_m": 0.0,
                            "max_horizontal_drift_m": 1.0,
                        },
                        "slam_odom_corrected": {
                            "source_topic": "/slam/odom_corrected",
                            "frame_id": "map",
                            "child_frame_id": "base_link",
                            "sample_count": 2,
                            "raw_sample_count": 2,
                            "final_x_m": -1.0,
                            "final_y_m": 0.0,
                            "max_horizontal_drift_m": 1.0,
                        },
                        "external_nav_odom_candidate": {
                            "source_topic": "/external_nav/odom_candidate",
                            "frame_id": "map",
                            "child_frame_id": "base_link",
                            "sample_count": 2,
                            "raw_sample_count": 2,
                            "final_x_m": -1.0,
                            "final_y_m": 0.0,
                            "max_horizontal_drift_m": 1.0,
                        },
                    },
                    "pairwise": {
                        "gazebo_model_odometry__slam_odom_corrected": {
                            "sample_count_ok": True,
                            "direction_check_ok": True,
                            "direction_cosine": -1.0,
                            "scale_ratio": 1.0,
                            "left_magnitude_m": 1.0,
                            "right_magnitude_m": 1.0,
                        },
                        "slam_odom_corrected__external_nav_odom_candidate": {
                            "sample_count_ok": True,
                            "direction_check_ok": True,
                            "direction_cosine": 1.0,
                            "scale_ratio": 1.0,
                            "left_magnitude_m": 1.0,
                            "right_magnitude_m": 1.0,
                        },
                    },
                }
            }
        },
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    metadata = tmp_path / "rosbag" / "hover_rosbag"
    metadata.mkdir(parents=True)
    (metadata / "metadata.yaml").write_text(
        """
rosbag2_bagfile_information:
  topics_with_message_count:
    - topic_metadata:
        name: /slam/odom
        type: nav_msgs/msg/Odometry
      message_count: 12
    - topic_metadata:
        name: /gazebo/model/odometry
        type: nav_msgs/msg/Odometry
      message_count: 4
""".lstrip(),
        encoding="utf-8",
    )

    audit = module.build_audit(tmp_path)

    assert audit["diagnostic_only"] is True
    divergence = audit["first_summarized_divergence"]
    assert divergence["status"] == "found"
    assert divergence["scope"] == "summarized_sources_only"
    assert divergence["left"] == "gazebo_model_odometry"
    assert divergence["right"] == "slam_odom_corrected"
    assert divergence["reason"] == "direction_mismatch"
    assert "not a final root cause" in divergence["note"]
    assert audit["topic_availability"]["slam_odom"]["status"] == "available_in_bag_not_summarized"
    assert audit["topic_availability"]["gazebo_model_states"]["status"] == "missing_from_bag_metadata"
