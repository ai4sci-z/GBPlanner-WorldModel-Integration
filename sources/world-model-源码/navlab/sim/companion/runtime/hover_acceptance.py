from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from navlab.common.logging import logger
from navlab.common.process_manager import ProcessManager
from navlab.sim.companion.runtime.acceptance import (
    build_rosbag_topic_plan,
    collect_samples,
    load_gazebo_truth_trajectory_summary,
    pose_mirror_set_pose_disabled,
    record_gazebo_truth_trajectory,
    record_profile_topics,
    sample_payload,
    slam_truth_comparison,
    wait_for_metadata,
    write_effective_rosbag_profile,
    write_foxglove_notes,
    x2_scan_ideal_fresh,
)
from navlab.sim.companion.runtime.config import RuntimeConfig
from navlab.sim.companion.runtime.rosbag_profile import validate_rosbag_profile

HOVER_DIAGNOSTIC_MINIMUM_ROSBAG_TOPICS = (
    "/scan",
    "/scan_ideal",
    "/scan_features",
    "/scan_nearest_point",
    "/sim/markers",
    "/sim/uav_pose",
    "/sim/log",
    "/sim/x2/status",
    "/rangefinder/down/range",
    "/rangefinder/down/status",
    "/gazebo/truth/odom",
    "/gazebo/truth/status",
    "/gazebo/tf",
    "/gazebo/tf_static",
    "/navlab/fcu/local_position_pose",
    "/tf",
    "/tf_static",
    "/navlab/mavlink/status",
    "/navlab/pose_mirror/status",
    "/navlab/mission/status",
    "/navlab/landing/status",
)


def _run_hover_mission(
    *,
    artifact_dir: Path,
    duration_sec: float,
    config: RuntimeConfig,
    extra_args: list[str] | None = None,
) -> int:
    from navlab.sim.companion.nodes.hover_mission import run as run_hover_mission

    logger.info("Running hover mission for {}s via {}", duration_sec, config.mission.endpoint)
    argv = config.mission.argv(duration_sec=duration_sec, summary_file=str(artifact_dir / "mission_summary.json"))
    if extra_args:
        argv.extend(extra_args)
    try:
        rc = run_hover_mission(argv)
    except SystemExit as exc:
        rc = int(exc.code or 0)
    (artifact_dir / "mission_rc.txt").write_text(str(rc), encoding="utf-8")
    logger.info("Hover mission completed rc={}", rc)
    return rc


def _relay_gazebo_truth_to_external_nav(*, manager: ProcessManager, artifact_dir: Path) -> None:
    logger.info("Starting diagnostic Gazebo truth odom relay for FCU ExternalNav")
    manager.start_subprocess(
        "gazebo_truth_external_nav_relay",
        [
            "python3",
            "-m",
            "navlab.sim.companion.nodes.odom_relay",
            "--input-topic",
            "/gazebo/truth/odom",
            "--output-topic",
            "/external_nav/odom",
        ],
        log_path=artifact_dir / "gazebo_truth_external_nav_relay.log",
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _truth_hover_containment(artifact_dir: Path, *, max_radius_m: float = 1.0) -> dict[str, Any]:
    trajectory = _load_json(artifact_dir / "gazebo_truth_trajectory.json")
    samples = trajectory.get("samples", [])
    max_radius = 0.0
    max_sample: dict[str, Any] | None = None
    if isinstance(samples, list):
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            try:
                radius = (float(sample.get("x_m", 0.0)) ** 2 + float(sample.get("y_m", 0.0)) ** 2) ** 0.5
            except (TypeError, ValueError):
                continue
            if radius > max_radius:
                max_radius = radius
                max_sample = sample
    return {
        "ok": max_radius <= max_radius_m,
        "max_radius_m": max_radius,
        "max_allowed_radius_m": max_radius_m,
        "max_sample": max_sample,
    }


def write_hover_summary(
    *,
    artifact_dir: Path,
    duration_sec: float,
    mission_rc: int,
    rosbag_profile: dict[str, Any],
    config: RuntimeConfig,
    scan_source: str,
    require_slam_external_nav: bool = True,
    require_imu_status: bool = True,
    control_mode: str = "fcu_guided_arm_takeoff_hover",
    containment_max_radius_m: float = 1.0,
    max_slam_truth_horizontal_error_m: float | None = None,
) -> int:
    samples = (artifact_dir / "samples.txt").read_text(encoding="utf-8")
    mission_summary = _load_json(artifact_dir / "mission_summary.json")
    mavlink_status = sample_payload(samples, "MAVLINK_STATUS_SAMPLE")
    pose_mirror_status = sample_payload(samples, "POSE_MIRROR_STATUS_SAMPLE")
    imu_status = sample_payload(samples, "IMU_STATUS_SAMPLE")
    slam_status = sample_payload(samples, "SLAM_STATUS_SAMPLE")
    gazebo_truth_status = sample_payload(samples, "GAZEBO_TRUTH_STATUS_SAMPLE")
    external_status = sample_payload(samples, "EXTERNAL_STATUS_SAMPLE")
    mavlink_external_nav_status = sample_payload(samples, "MAVLINK_EXTERNAL_NAV_STATUS_SAMPLE")
    x2_status = sample_payload(samples, "X2_STATUS_SAMPLE")
    rangefinder_down_status = sample_payload(samples, "RANGEFINDER_DOWN_STATUS_SAMPLE")
    landing_status = sample_payload(samples, "LANDING_STATUS_SAMPLE")
    gazebo_truth_trajectory = load_gazebo_truth_trajectory_summary(artifact_dir)
    truth_hover_containment = _truth_hover_containment(artifact_dir, max_radius_m=containment_max_radius_m)
    slam_truth_comparison_result = slam_truth_comparison(samples)
    slam_truth_error = slam_truth_comparison_result.get("horizontal_error_m")
    slam_truth_error_ok = (
        True
        if max_slam_truth_horizontal_error_m is None
        else (
            slam_truth_comparison_result.get("available") is True
            and isinstance(slam_truth_error, int | float)
            and float(slam_truth_error) <= max_slam_truth_horizontal_error_m
        )
    )
    message_counts = rosbag_profile.get("message_counts", {})
    mavlink_counts = mavlink_status.get("message_counts", {})
    external_odom_status = external_status.get("odom", {})
    if not isinstance(external_odom_status, dict):
        external_odom_status = {}
    external_nav_input_topic = str(external_odom_status.get("input_topic") or "")
    rangefinder_fcu_observed = (
        int(mavlink_counts.get("RANGEFINDER", 0) or 0) > 0
        or int(mavlink_counts.get("DISTANCE_SENSOR", 0) or 0) > 0
        or int(mission_summary.get("rangefinder_count", 0) or 0) > 0
    )
    legacy_mavlink_rangefinder_sender = rangefinder_down_status.get("mavlink_message") == "DISTANCE_SENSOR"
    rangefinder_serial_ok = (
        rangefinder_fcu_observed
        and rangefinder_down_status.get("source") == "gazebo_down_range_projection"
        and rangefinder_down_status.get("fcu_transport") == "serial7_uart"
        and rangefinder_down_status.get("rangefinder_simulation_fidelity") == "benewake_serial_emulated"
        and not legacy_mavlink_rangefinder_sender
    )
    rangefinder_simulation_fidelity = (
        "benewake_serial_emulated" if rangefinder_serial_ok else "blocked_missing_benewake_serial"
    )
    local_position_count = int(mission_summary.get("local_position_count", 0) or 0)
    hover_drift = mission_summary.get("hover_drift", {})
    hover_altitude_sources = mission_summary.get("hover_altitude_sources", {})
    hover_altitude_crosscheck = mission_summary.get("hover_altitude_crosscheck", {})
    hover_altitude_crosscheck_ok = (
        isinstance(hover_altitude_crosscheck, dict) and hover_altitude_crosscheck.get("ok") is True
    )
    hover_duration_tolerance_sec = float(hover_drift.get("duration_tolerance_sec", 0.25) or 0.25)
    phases_seen = mission_summary.get("phases_seen", [])
    pose_mirror_observation_only = (
        pose_mirror_set_pose_disabled(config)
        and int(pose_mirror_status.get("set_pose_count", 0) or 0) == 0
        and pose_mirror_status.get("reason") != "set_pose_sent"
    )
    hover_ok = (
        mission_summary.get("ok") is True
        and mission_summary.get("crash_detected") is not True
        and "hover_hold" in phases_seen
        and hover_drift.get("ok") is True
        and hover_altitude_crosscheck_ok
        and float(hover_drift.get("duration_sec", 0.0) or 0.0)
        >= float(mission_summary.get("hover_hold_sec", 0.0) or 0.0) - hover_duration_tolerance_sec
    )
    slam_external_nav_ok = (
        slam_status.get("ready") is True
        and external_status.get("state") == "healthy"
        and external_status.get("ready") is True
        and external_nav_input_topic == "/slam/odom"
        and mavlink_external_nav_status.get("state") == "sending"
    )
    feedback_ok = slam_external_nav_ok if require_slam_external_nav else True
    imu_ok = imu_status.get("state") == "streaming_fcu_imu" and imu_status.get("ready") is True
    summary = {
        "ok": (
            rosbag_profile.get("ok") is True
            and mission_rc == 0
            and mission_summary.get("guided_seen") is True
            and mission_summary.get("armed_seen") is True
            and mission_summary.get("airborne_seen") is True
            and local_position_count > 0
            and rangefinder_serial_ok
            and hover_ok
            and truth_hover_containment.get("ok") is True
            and slam_truth_error_ok
            and pose_mirror_observation_only
            and (imu_ok if require_imu_status else True)
            and feedback_ok
        ),
        "duration_sec": duration_sec,
        "mission_rc": mission_rc,
        "reason": mission_summary.get("reason"),
        "scan_source": scan_source,
        "gps_free": True,
        "control_mode": control_mode,
        "require_slam_external_nav": require_slam_external_nav,
        "require_imu_status": require_imu_status,
        "external_nav_input_topic": external_nav_input_topic,
        "external_nav_uses_slam_odom": external_nav_input_topic == "/slam/odom",
        "external_nav_uses_gazebo_truth": external_nav_input_topic == "/gazebo/truth/odom",
        "sitl_heartbeat": mavlink_status.get("heartbeat_seen") is True,
        "guided_ok": mission_summary.get("guided_seen") is True,
        "arm_ok": mission_summary.get("armed_seen") is True,
        "takeoff_ok": mission_summary.get("airborne_seen") is True,
        "takeoff_ack_ok": mission_summary.get("takeoff_ack_ok") is True,
        "local_position_ok": local_position_count > 0,
        "local_position_count": local_position_count,
        "rangefinder_fcu_observed": rangefinder_fcu_observed,
        "rangefinder_serial_ok": rangefinder_serial_ok,
        "rangefinder_simulation_fidelity": rangefinder_simulation_fidelity,
        "legacy_mavlink_rangefinder_sender": legacy_mavlink_rangefinder_sender,
        "rangefinder_count": mission_summary.get("rangefinder_count", 0),
        "crash_detected": mission_summary.get("crash_detected") is True,
        "hover_ok": hover_ok,
        "hover_drift": hover_drift,
        "hover_drift_quality": hover_drift.get("quality") if isinstance(hover_drift, dict) else None,
        "hover_altitude_sources": hover_altitude_sources,
        "hover_altitude_crosscheck": hover_altitude_crosscheck,
        "truth_hover_containment": truth_hover_containment,
        "slam_truth_error_ok": slam_truth_error_ok,
        "max_slam_truth_horizontal_error_m": max_slam_truth_horizontal_error_m,
        "pose_mirror_observation_only": pose_mirror_observation_only,
        "slam_truth_comparison": slam_truth_comparison_result,
        "gazebo_truth_trajectory": gazebo_truth_trajectory,
        "rosbag_profile_ok": rosbag_profile.get("ok") is True,
        "rosbag_profile": rosbag_profile,
        "mission_summary": mission_summary,
        "landing_status": landing_status,
        "mavlink_status": mavlink_status,
        "pose_mirror_status": pose_mirror_status,
        "imu_status": imu_status,
        "slam_status": slam_status,
        "gazebo_truth_status": gazebo_truth_status,
        "external_nav_status": external_status,
        "mavlink_external_nav_status": mavlink_external_nav_status,
        "x2_status": x2_status,
        "x2_status_fresh": x2_scan_ideal_fresh(x2_status),
        "rangefinder_down_status": rangefinder_down_status,
        "message_counts": {
            "odom": message_counts.get("/odom", 0),
            "external_nav_odom": message_counts.get("/external_nav/odom", 0),
            "external_nav_status": message_counts.get("/external_nav/status", 0),
            "mavlink_external_nav_status": message_counts.get("/mavlink_external_nav/status", 0),
            "local_position_pose": message_counts.get("/navlab/fcu/local_position_pose", 0),
            "rangefinder_status": message_counts.get("/rangefinder/down/status", 0),
        },
        "foxglove_notes": str(artifact_dir / "foxglove_notes.md"),
    }
    (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if summary["ok"] else 3


def execute_hover_acceptance(
    *,
    artifact_dir: Path,
    duration_sec: float,
    rosbag_profile_path: Path,
    companion_image: str,
    scan_source: str,
    config: RuntimeConfig,
) -> int:
    logger.info("Starting NavLab hover acceptance artifact_dir={} duration_sec={}", artifact_dir, duration_sec)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    time.sleep(14)

    topics = build_rosbag_topic_plan(rosbag_profile_path)
    effective_profile = write_effective_rosbag_profile(
        artifact_dir=artifact_dir,
        source_profile=rosbag_profile_path,
        topics=topics,
    )
    (artifact_dir / "rosbag_record_mode.txt").write_text("profile-topics-only\n", encoding="utf-8")

    manager = ProcessManager()
    record_profile_topics(manager=manager, artifact_dir=artifact_dir, topics=topics)
    record_gazebo_truth_trajectory(manager=manager, artifact_dir=artifact_dir)
    try:
        time.sleep(2)
        mission_rc = _run_hover_mission(artifact_dir=artifact_dir, duration_sec=duration_sec, config=config)
        collect_samples(artifact_dir=artifact_dir)
    finally:
        manager.stop_all(timeout_sec=15)
        wait_for_metadata(artifact_dir / "rosbag" / "metadata.yaml")

    rosbag_summary = validate_rosbag_profile(
        profile=effective_profile,
        metadata=artifact_dir / "rosbag" / "metadata.yaml",
        summary_file=artifact_dir / "rosbag_profile_summary.json",
    )
    (artifact_dir / "rosbag_profile_rc.txt").write_text("0" if rosbag_summary["ok"] else "3", encoding="utf-8")
    write_foxglove_notes(artifact_dir=artifact_dir)
    rc = write_hover_summary(
        artifact_dir=artifact_dir,
        duration_sec=duration_sec,
        mission_rc=mission_rc,
        rosbag_profile=rosbag_summary,
        config=config,
        scan_source=scan_source,
    )
    logger.info("NavLab hover acceptance completed rc={}", rc)
    return rc


def execute_hover_slam_diagnostic_acceptance(
    *,
    artifact_dir: Path,
    duration_sec: float,
    rosbag_profile_path: Path,
    companion_image: str,
    scan_source: str,
    config: RuntimeConfig,
) -> int:
    logger.info(
        "Starting NavLab SLAM ExternalNav hover diagnostic artifact_dir={} duration_sec={}",
        artifact_dir,
        duration_sec,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    time.sleep(14)

    topics = build_rosbag_topic_plan(rosbag_profile_path)
    effective_profile = write_effective_rosbag_profile(
        artifact_dir=artifact_dir,
        source_profile=rosbag_profile_path,
        topics=topics,
    )
    (artifact_dir / "rosbag_record_mode.txt").write_text("slam-diagnostic-profile-topics-only\n", encoding="utf-8")

    manager = ProcessManager()
    record_profile_topics(manager=manager, artifact_dir=artifact_dir, topics=topics)
    record_gazebo_truth_trajectory(manager=manager, artifact_dir=artifact_dir)
    try:
        time.sleep(2)
        mission_rc = _run_hover_mission(artifact_dir=artifact_dir, duration_sec=duration_sec, config=config)
        collect_samples(artifact_dir=artifact_dir)
    finally:
        manager.stop_all(timeout_sec=15)
        wait_for_metadata(artifact_dir / "rosbag" / "metadata.yaml")

    rosbag_summary = validate_rosbag_profile(
        profile=effective_profile,
        metadata=artifact_dir / "rosbag" / "metadata.yaml",
        summary_file=artifact_dir / "rosbag_profile_summary.json",
    )
    (artifact_dir / "rosbag_profile_rc.txt").write_text("0" if rosbag_summary["ok"] else "3", encoding="utf-8")
    write_foxglove_notes(artifact_dir=artifact_dir)
    rc = write_hover_summary(
        artifact_dir=artifact_dir,
        duration_sec=duration_sec,
        mission_rc=mission_rc,
        rosbag_profile=rosbag_summary,
        config=config,
        scan_source=scan_source,
        require_slam_external_nav=True,
        require_imu_status=True,
        control_mode="fcu_guided_rangefinder_altitude_slam_external_nav_position_hold",
        containment_max_radius_m=1.0,
        max_slam_truth_horizontal_error_m=0.35,
    )
    logger.info("NavLab SLAM ExternalNav hover diagnostic completed rc={}", rc)
    return rc


def execute_hover_diagnostic_acceptance(
    *,
    artifact_dir: Path,
    duration_sec: float,
    rosbag_profile_path: Path,
    companion_image: str,
    scan_source: str,
    config: RuntimeConfig,
) -> int:
    logger.info(
        "Starting NavLab rangefinder hover diagnostic artifact_dir={} duration_sec={}",
        artifact_dir,
        duration_sec,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    time.sleep(14)

    topics = build_rosbag_topic_plan(
        rosbag_profile_path,
        minimum_topics=HOVER_DIAGNOSTIC_MINIMUM_ROSBAG_TOPICS,
    )
    effective_profile = write_effective_rosbag_profile(
        artifact_dir=artifact_dir,
        source_profile=rosbag_profile_path,
        topics=topics,
        minimum_topics=HOVER_DIAGNOSTIC_MINIMUM_ROSBAG_TOPICS,
    )
    (artifact_dir / "rosbag_record_mode.txt").write_text("diagnostic-profile-topics-only\n", encoding="utf-8")

    manager = ProcessManager()
    record_profile_topics(manager=manager, artifact_dir=artifact_dir, topics=topics)
    record_gazebo_truth_trajectory(manager=manager, artifact_dir=artifact_dir)
    _relay_gazebo_truth_to_external_nav(manager=manager, artifact_dir=artifact_dir)
    try:
        time.sleep(2)
        mission_rc = _run_hover_mission(
            artifact_dir=artifact_dir,
            duration_sec=duration_sec,
            config=config,
            extra_args=[
                "--no-require-external-nav",
                "--no-require-imu-status",
                "--no-send-position-setpoints",
                "--max-horizontal-drift-m",
                "100",
            ],
        )
        collect_samples(artifact_dir=artifact_dir)
    finally:
        manager.stop_all(timeout_sec=15)
        wait_for_metadata(artifact_dir / "rosbag" / "metadata.yaml")

    rosbag_summary = validate_rosbag_profile(
        profile=effective_profile,
        metadata=artifact_dir / "rosbag" / "metadata.yaml",
        summary_file=artifact_dir / "rosbag_profile_summary.json",
    )
    (artifact_dir / "rosbag_profile_rc.txt").write_text("0" if rosbag_summary["ok"] else "3", encoding="utf-8")
    write_foxglove_notes(artifact_dir=artifact_dir)
    rc = write_hover_summary(
        artifact_dir=artifact_dir,
        duration_sec=duration_sec,
        mission_rc=mission_rc,
        rosbag_profile=rosbag_summary,
        config=config,
        scan_source=scan_source,
        require_slam_external_nav=False,
        require_imu_status=False,
        control_mode="fcu_guided_rangefinder_altitude_no_slam_horizontal_control",
        containment_max_radius_m=3.0,
    )
    logger.info("NavLab rangefinder hover diagnostic completed rc={}", rc)
    return rc
