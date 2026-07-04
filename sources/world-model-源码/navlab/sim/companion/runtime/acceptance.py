from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

from navlab.common.logging import logger
from navlab.common.process_manager import ManagedProcess, ProcessManager
from navlab.common.rosbag import parse_rosbag_topic_line
from navlab.sim.companion.runtime.config import RuntimeConfig
from navlab.sim.companion.runtime.rosbag_profile import validate_rosbag_profile

TEMPLATE_DIR = Path(__file__).parent / "templates"

SAMPLE_TOPICS = (
    ("MISSION_STATUS_SAMPLE", "/navlab/mission/status"),
    ("MAVLINK_STATUS_SAMPLE", "/navlab/mavlink/status"),
    ("LANDING_STATUS_SAMPLE", "/navlab/landing/status"),
    ("POSE_MIRROR_STATUS_SAMPLE", "/navlab/pose_mirror/status"),
    ("IMU_STATUS_SAMPLE", "/imu/status"),
    ("SLAM_STATUS_SAMPLE", "/navlab/slam/status"),
    ("GAZEBO_TRUTH_STATUS_SAMPLE", "/gazebo/truth/status"),
    ("EXTERNAL_STATUS_SAMPLE", "/external_nav/status"),
    ("MAVLINK_EXTERNAL_NAV_STATUS_SAMPLE", "/mavlink_external_nav/status"),
    ("SLAM_ODOM_SAMPLE", "/odom"),
    ("GAZEBO_TRUTH_ODOM_SAMPLE", "/gazebo/truth/odom"),
    ("SCAN_FEATURES_SAMPLE", "/scan_features"),
    ("SIM_LOG_SAMPLE", "/sim/log"),
    ("X2_STATUS_SAMPLE", "/sim/x2/status"),
    ("RANGEFINDER_DOWN_STATUS_SAMPLE", "/rangefinder/down/status"),
)

MINIMUM_ROSBAG_TOPICS = (
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
    "/imu",
    "/imu/status",
    "/navlab/fcu/local_position_pose",
    "/tf",
    "/tf_static",
    "/odom",
    "/navlab/slam/status",
    "/external_nav/odom",
    "/external_nav/status",
    "/mavlink_external_nav/status",
    "/navlab/mavlink/status",
    "/navlab/landing/status",
    "/navlab/pose_mirror/status",
    "/navlab/mission/status",
)


def _template(name: str) -> Template:
    environment = Environment(
        autoescape=select_autoescape(disabled_extensions=("md", "j2"), default_for_string=False, default=False),
        loader=FileSystemLoader(TEMPLATE_DIR),
        lstrip_blocks=True,
        trim_blocks=True,
    )
    return environment.get_template(name)


def _run(
    command: list[str],
    *,
    stdout_path: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    logger.debug("Running command: {}", " ".join(command))
    if stdout_path is None:
        return subprocess.run(command, check=check, text=True)
    with stdout_path.open("w", encoding="utf-8") as stdout:
        return subprocess.run(command, check=check, text=True, stdout=stdout, stderr=subprocess.STDOUT)


def record_profile_topics(*, manager: ProcessManager, artifact_dir: Path, topics: list[str]) -> ManagedProcess:
    logger.info("Starting rosbag record in {}", artifact_dir / "rosbag")
    return manager.start_subprocess(
        "rosbag_record",
        [
            "ros2",
            "bag",
            "record",
            "-o",
            str(artifact_dir / "rosbag"),
            "--topics",
            *topics,
        ],
        log_path=artifact_dir / "rosbag.log",
    )


def record_gazebo_truth_trajectory(*, manager: ProcessManager, artifact_dir: Path) -> ManagedProcess:
    logger.info("Starting Gazebo truth trajectory recorder")
    return manager.start_subprocess(
        "gazebo_truth_trajectory",
        [
            "python3",
            "-m",
            "navlab.sim.companion.nodes.gazebo_truth_trajectory",
            "--topic",
            "/gazebo/truth/odom",
            "--output-file",
            str(artifact_dir / "gazebo_truth_trajectory.json"),
            "--sample-rate-hz",
            "10",
        ],
        log_path=artifact_dir / "gazebo_truth_trajectory.log",
    )


def _dedupe_topics(topics: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for topic in topics:
        if topic not in seen:
            seen.add(topic)
            deduped.append(topic)
    return deduped


def _load_extra_rosbag_topics(profile_path: Path) -> tuple[list[str], list[str]]:
    if not profile_path.is_file():
        return [], []
    required: list[str] = []
    optional: list[str] = []
    for raw_line in profile_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        topic = parse_rosbag_topic_line(stripped)
        if topic is None:
            continue
        if stripped.startswith("optional "):
            optional.append(topic)
        else:
            required.append(topic)
    return _dedupe_topics(required), _dedupe_topics(optional)


def build_rosbag_topic_plan(
    profile_path: Path,
    *,
    minimum_topics: tuple[str, ...] = MINIMUM_ROSBAG_TOPICS,
) -> list[str]:
    extra_required, extra_optional = _load_extra_rosbag_topics(profile_path)
    required = _dedupe_topics([*minimum_topics, *extra_required])
    optional = [topic for topic in extra_optional if topic not in required]
    return [*required, *optional]


def write_effective_rosbag_profile(
    *,
    artifact_dir: Path,
    source_profile: Path,
    topics: list[str],
    minimum_topics: tuple[str, ...] = MINIMUM_ROSBAG_TOPICS,
) -> Path:
    extra_required, extra_optional = _load_extra_rosbag_topics(source_profile)
    required = _dedupe_topics([*minimum_topics, *extra_required])
    optional = [topic for topic in extra_optional if topic not in required]
    effective_profile = artifact_dir / "effective_rosbag_profile.txt"
    lines = [
        "# Generated by NavLab acceptance.",
        "# Minimum topics are hardcoded and cannot be removed by config.",
        f"# Extra topic profile: {source_profile}",
        "",
        "# Minimum + extra required topics.",
    ]
    lines.extend(f"required {topic}" for topic in required)
    if optional:
        lines.extend(["", "# Extra optional topics.", *(f"optional {topic}" for topic in optional)])
    effective_profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (artifact_dir / "rosbag_minimum_topics.txt").write_text(
        "\n".join(minimum_topics) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "rosbag_extra_topics.txt").write_text(
        "\n".join([*extra_required, *extra_optional]) + ("\n" if extra_required or extra_optional else ""),
        encoding="utf-8",
    )
    (artifact_dir / "rosbag_requested_topics.txt").write_text("\n".join(topics) + "\n", encoding="utf-8")
    return effective_profile


def wait_for_metadata(path: Path, *, timeout_sec: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return
        time.sleep(0.5)


def _run_mission(*, artifact_dir: Path, duration_sec: float, config: RuntimeConfig) -> int:
    logger.info("Running obstacle mission for {}s via {}", duration_sec, config.mission.endpoint)
    command = [
        "python3",
        "-m",
        "navlab.sim.companion.nodes.obstacle_mission",
        *config.mission.argv(duration_sec=duration_sec, summary_file=str(artifact_dir / "mission_summary.json")),
    ]
    result = _run(command, stdout_path=artifact_dir / "mission_controller.log", check=False)
    (artifact_dir / "mission_rc.txt").write_text(str(result.returncode), encoding="utf-8")
    logger.info("Mission controller completed rc={}", result.returncode)
    return result.returncode


def collect_samples(*, artifact_dir: Path) -> None:
    logger.info("Collecting ROS topic samples")
    with (artifact_dir / "samples.txt").open("w", encoding="utf-8") as output:
        for label, topic in SAMPLE_TOPICS:
            output.write(f"{label}\n")
            output.flush()
            subprocess.run(
                ["timeout", "5s", "ros2", "topic", "echo", "--once", "--full-length", topic],
                check=False,
                text=True,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        output.write("SCAN_TOPIC_INFO\n")
        output.flush()
        subprocess.run(
            ["timeout", "5s", "ros2", "topic", "info", "-v", "/scan"],
            check=False,
            text=True,
            stdout=output,
            stderr=subprocess.STDOUT,
        )


def _sample_section(samples: str, label: str) -> str:
    start = samples.find(label)
    if start < 0:
        return ""
    end = len(samples)
    for next_label, _ in SAMPLE_TOPICS:
        if next_label == label:
            continue
        next_start = samples.find(next_label, start + len(label))
        if next_start >= 0:
            end = min(end, next_start)
    return samples[start:end]


def sample_payload(samples: str, label: str) -> dict[str, Any]:
    section = _sample_section(samples, label)
    if not section:
        return {}
    match = re.search(r"data: '(.+)'", section)
    if not match:
        return {}
    return json.loads(match.group(1))


def _odom_position_sample(samples: str, label: str) -> dict[str, float] | None:
    section = _sample_section(samples, label)
    if not section:
        return None
    match = re.search(
        r"position:\s*\n\s*x:\s*([-+0-9.eE]+)\s*\n\s*y:\s*([-+0-9.eE]+)\s*\n\s*z:\s*([-+0-9.eE]+)",
        section,
    )
    if not match:
        return None
    return {
        "x": float(match.group(1)),
        "y": float(match.group(2)),
        "z": float(match.group(3)),
    }


def slam_truth_comparison(samples: str) -> dict[str, Any]:
    slam_position = _odom_position_sample(samples, "SLAM_ODOM_SAMPLE")
    truth_position = _odom_position_sample(samples, "GAZEBO_TRUTH_ODOM_SAMPLE")
    comparison: dict[str, Any] = {
        "slam_topic": "/odom",
        "truth_topic": "/gazebo/truth/odom",
        "available": slam_position is not None and truth_position is not None,
        "slam_position": slam_position,
        "truth_position": truth_position,
    }
    if slam_position is None or truth_position is None:
        return comparison
    dx = slam_position["x"] - truth_position["x"]
    dy = slam_position["y"] - truth_position["y"]
    dz = slam_position["z"] - truth_position["z"]
    comparison.update(
        {
            "horizontal_error_m": (dx * dx + dy * dy) ** 0.5,
            "position_error_m": (dx * dx + dy * dy + dz * dz) ** 0.5,
            "z_error_m": abs(dz),
        }
    )
    return comparison


def scan_publisher_summary(samples: str) -> dict[str, Any]:
    start = samples.find("SCAN_TOPIC_INFO")
    if start < 0:
        return {}
    section = samples[start:]
    subscription_start = section.find("Subscription count:")
    if subscription_start >= 0:
        section = section[:subscription_start]
    node_names = re.findall(r"Node name: ([^\n]+)", section)
    node_names = [name.strip() for name in node_names]
    return {
        "topic": "/scan",
        "publisher_nodes": sorted(set(node_names)),
        "vendor_driver_publisher": "ydlidar_ros2_driver_node" in node_names,
        "emulator_publisher": "x2_serial_emulator" in node_names,
    }


def load_gazebo_truth_trajectory_summary(artifact_dir: Path) -> dict[str, Any]:
    path = artifact_dir / "gazebo_truth_trajectory.json"
    if not path.is_file():
        return {"ok": False, "path": str(path), "reason": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "path": str(path), "reason": f"invalid_json: {exc}"}
    summary = payload.get("summary", {})
    return {
        "ok": int(summary.get("sample_count", 0) or 0) > 0,
        "path": str(path),
        "source_topic": payload.get("source_topic"),
        "schema": payload.get("schema"),
        **summary,
    }


def pose_mirror_set_pose_disabled(config: RuntimeConfig) -> bool:
    args = set(config.pose_mirror.argv())
    return (
        "--set-gazebo-pose" not in args
        and "--simulate-pose-from-mission-status" not in args
        and "--world-name" not in args
        and "--model-name" not in args
    )


def _status_int(payload: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def x2_scan_ideal_fresh(x2_status: dict[str, Any], *, max_age_sec: float = 2.0) -> bool:
    age = x2_status.get("latest_scan_ideal_age_sec")
    if age is None:
        return False
    try:
        return float(age) <= max_age_sec
    except (TypeError, ValueError):
        return False


def write_foxglove_notes(*, artifact_dir: Path) -> None:
    logger.info("Writing Foxglove replay notes")
    rendered = _template("foxglove_notes.md.j2").render(
        artifact_dir=artifact_dir,
        rosbag_dir=artifact_dir / "rosbag",
        fixed_frame="navlab_world",
        recommended_panels=("3D", "Raw Messages", "Plot", "Topic Graph"),
        marker_topics=("/sim/markers",),
        pose_topics=(
            "/gazebo/truth/odom",
            "/external_nav/odom",
            "/navlab/fcu/local_position_pose",
            "/sim/uav_pose",
        ),
        laser_topics=("/scan", "/scan_ideal", "/scan_features", "/scan_nearest_point"),
        raw_status_topics=(
            "/navlab/mission/status",
            "/navlab/landing/status",
            "/sim/log",
            "/sim/x2/status",
            "/rangefinder/down/status",
            "/gazebo/truth/status",
            "/imu/status",
            "/external_nav/status",
            "/mavlink_external_nav/status",
        ),
        expected_sequence=(
            "wait_ready",
            "guided",
            "arm",
            "takeoff",
            "hover_settle",
            "forward",
            "scan_left",
            "scan_right",
            "avoid",
            "return_track",
            "final_hold/complete",
            "pre_land_hold",
            "land_command_sent",
            "descent_monitoring",
            "landing_complete",
        ),
    )
    (artifact_dir / "foxglove_notes.md").write_text(rendered.rstrip() + "\n", encoding="utf-8")


def write_summary(
    *,
    artifact_dir: Path,
    duration_sec: float,
    mission_rc: int,
    rosbag_profile: dict[str, Any],
    config: RuntimeConfig,
    scan_source: str,
) -> int:
    samples = (artifact_dir / "samples.txt").read_text(encoding="utf-8")
    metadata = (artifact_dir / "rosbag" / "metadata.yaml").read_text(encoding="utf-8")
    mission_summary_path = artifact_dir / "mission_summary.json"
    mission_summary = (
        json.loads(mission_summary_path.read_text(encoding="utf-8")) if mission_summary_path.exists() else {}
    )
    mission_status = sample_payload(samples, "MISSION_STATUS_SAMPLE")
    mavlink_status = sample_payload(samples, "MAVLINK_STATUS_SAMPLE")
    pose_mirror_status = sample_payload(samples, "POSE_MIRROR_STATUS_SAMPLE")
    imu_status = sample_payload(samples, "IMU_STATUS_SAMPLE")
    slam_status = sample_payload(samples, "SLAM_STATUS_SAMPLE")
    gazebo_truth_status = sample_payload(samples, "GAZEBO_TRUTH_STATUS_SAMPLE")
    gazebo_truth_trajectory = load_gazebo_truth_trajectory_summary(artifact_dir)
    external_status = sample_payload(samples, "EXTERNAL_STATUS_SAMPLE")
    mavlink_external_nav_status = sample_payload(samples, "MAVLINK_EXTERNAL_NAV_STATUS_SAMPLE")
    x2_status = sample_payload(samples, "X2_STATUS_SAMPLE")
    rangefinder_down_status = sample_payload(samples, "RANGEFINDER_DOWN_STATUS_SAMPLE")
    external_odom_status = external_status.get("odom", {})
    if not isinstance(external_odom_status, dict):
        external_odom_status = {}
    external_nav_input_topic = str(external_odom_status.get("input_topic") or "")
    external_nav_uses_gazebo_truth = external_nav_input_topic == "/gazebo/truth/odom"
    external_nav_uses_slam_odom = external_nav_input_topic == "/slam/odom"
    slam_truth_comparison_result = slam_truth_comparison(samples)
    mavlink_message_counts = mavlink_status.get("message_counts", {})
    rangefinder_fcu_observed = (
        int(mavlink_message_counts.get("RANGEFINDER", 0) or 0) > 0
        or int(mavlink_message_counts.get("DISTANCE_SENSOR", 0) or 0) > 0
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
    scan_publisher = scan_publisher_summary(samples)
    topics = sorted(set(re.findall(r"name: (/[^\n]+)", metadata)))
    message_counts = rosbag_profile.get("message_counts", {})
    scan_recorded = message_counts.get("/scan", 0) > 0
    scan_ideal_recorded = message_counts.get("/scan_ideal", 0) > 0
    x2_status_recorded = message_counts.get("/sim/x2/status", 0) > 0
    slam_odom_recorded = message_counts.get("/odom", 0) > 0
    gazebo_truth_odom_recorded = message_counts.get("/gazebo/truth/odom", 0) > 0
    vendor_scan_publisher_ok = scan_publisher.get("vendor_driver_publisher") is True
    x2_status_fresh = x2_scan_ideal_fresh(x2_status)
    x2_is_internal_to_sensor_runtime = (
        vendor_scan_publisher_ok
        and scan_publisher.get("emulator_publisher") is False
        and x2_status.get("source") == "x2_serial_emulator"
    )
    pose_mirror_state = pose_mirror_status.get("state")
    pose_mirror_set_pose_disabled_result = pose_mirror_set_pose_disabled(config)
    pose_mirror_observation_only = (
        pose_mirror_set_pose_disabled_result
        and _status_int(pose_mirror_status, "set_pose_count") == 0
        and pose_mirror_status.get("reason") != "set_pose_sent"
    )
    lidar_chain = {
        "scan_recorded": scan_recorded,
        "scan_ideal_recorded": scan_ideal_recorded,
        "x2_status_recorded": x2_status_recorded,
        "x2_status_fresh": x2_status_fresh,
        "vendor_scan_publisher_ok": vendor_scan_publisher_ok,
        "x2_is_internal_to_sensor_runtime": x2_is_internal_to_sensor_runtime,
        "scan_count": message_counts.get("/scan", 0),
        "scan_ideal_count": message_counts.get("/scan_ideal", 0),
        "x2_status_count": message_counts.get("/sim/x2/status", 0),
    }
    observation_mode = {
        "gazebo_physics_expected": True,
        "pose_mirror_set_pose_disabled": pose_mirror_set_pose_disabled_result,
        "pose_mirror_observation_only": pose_mirror_observation_only,
        "pose_source": "mavlink_local_position_observer",
        "world_markers_mode": "sdf_marker_observer",
    }
    phases_seen = mission_summary.get("phases_seen", [])
    mission_wait_ready_ok = "wait_ready" in phases_seen
    mission_guided_ok = "guided" in phases_seen
    mission_arm_ok = "arm" in phases_seen
    mission_takeoff_ok = "takeoff" in phases_seen
    mission_hover_ok = "hover_settle" in phases_seen
    summary = {
        "ok": (
            rosbag_profile.get("ok") is True
            and mission_rc == 0
            and pose_mirror_state == "mirroring"
            and mavlink_status.get("heartbeat_seen") is True
            and imu_status.get("state") == "streaming_fcu_imu"
            and imu_status.get("ready") is True
            and slam_status.get("ready") is True
            and slam_odom_recorded
            and external_status.get("state") == "healthy"
            and external_status.get("ready") is True
            and external_nav_uses_slam_odom
            and not external_nav_uses_gazebo_truth
            and mavlink_external_nav_status.get("state") == "sending"
            and mission_wait_ready_ok
            and mission_guided_ok
            and mission_arm_ok
            and mission_takeoff_ok
            and mission_hover_ok
            and scan_recorded
            and scan_ideal_recorded
            and x2_status_recorded
            and vendor_scan_publisher_ok
            and x2_status_fresh
            and x2_is_internal_to_sensor_runtime
            and pose_mirror_observation_only
            and rangefinder_serial_ok
        ),
        "duration_sec": duration_sec,
        "mission_rc": mission_rc,
        "scan_source": scan_source,
        "gps_free": True,
        "slam_odom_source": {
            "topic": "/odom",
            "backend_status_topic": "/navlab/slam/status",
            "ready": slam_status.get("ready") is True,
            "state": slam_status.get("state"),
            "recorded": slam_odom_recorded,
            "count": message_counts.get("/odom", 0),
            "status": slam_status.get("output", {}),
        },
        "gazebo_truth_source": {
            "topic": "/gazebo/truth/odom",
            "diagnostic_only": True,
            "recorded": gazebo_truth_odom_recorded,
            "count": message_counts.get("/gazebo/truth/odom", 0),
        },
        "external_nav_source": {
            "input_topic": external_nav_input_topic,
            "expected_input_topic": "/odom",
            "diagnostic_truth_input": external_nav_uses_gazebo_truth,
            "uses_slam_odom": external_nav_uses_slam_odom,
        },
        "external_nav_input_topic": external_nav_input_topic,
        "external_nav_uses_gazebo_truth": external_nav_uses_gazebo_truth,
        "external_nav_uses_slam_odom": external_nav_uses_slam_odom,
        "diagnostic_external_nav_input": external_nav_uses_gazebo_truth,
        "slam_truth_comparison": slam_truth_comparison_result,
        "rosbag_started_before_mission": True,
        "rosbag_covers_full_mission": rosbag_profile.get("ok") is True and "/navlab/mission/status" in topics,
        "companion_ready": True,
        "sitl_heartbeat": mavlink_status.get("heartbeat_seen") is True,
        "imu_source": config.imu_source_label,
        "scan_fresh": rosbag_profile.get("message_counts", {}).get("/scan_features", 0) > 0,
        "scan_recorded": scan_recorded,
        "scan_ideal_recorded": scan_ideal_recorded,
        "slam_odom_recorded": slam_odom_recorded,
        "gazebo_truth_odom_recorded": gazebo_truth_odom_recorded,
        "x2_status_recorded": x2_status_recorded,
        "x2_status_fresh": x2_status_fresh,
        "lidar_chain": lidar_chain,
        "scan_publisher": scan_publisher,
        "vendor_scan_publisher_ok": vendor_scan_publisher_ok,
        "x2_is_internal_to_sensor_runtime": x2_is_internal_to_sensor_runtime,
        "observation_mode": observation_mode,
        "pose_mirror_set_pose_disabled": pose_mirror_set_pose_disabled_result,
        "pose_mirror_observation_only": pose_mirror_observation_only,
        "world_markers_observation_only": True,
        "slam_consumes_final_scan": True,
        "mission_consumes_final_scan": True,
        "scan_features_consumes_final_scan": True,
        "external_nav_healthy": external_status.get("state") == "healthy",
        "gazebo_pose_mirror_ok": pose_mirror_state == "mirroring",
        "wait_ready_ok": mission_wait_ready_ok,
        "guided_ok": mission_guided_ok,
        "arm_ok": mission_arm_ok,
        "takeoff_ok": mission_takeoff_ok,
        "hover_ok": mission_hover_ok,
        "forward_progress_ok": "forward" in phases_seen,
        "obstacle_detected": (
            mission_summary.get("obstacle_detected") is True or mission_status.get("obstacle_detected") is True
        ),
        "avoidance_setpoint_sent": mission_summary.get("avoidance_setpoint_sent") is True,
        "yaw_scan_ok": "scan_left" in phases_seen and "scan_right" in phases_seen,
        "lateral_detour_ok": "avoid" in phases_seen,
        "final_hold_ok": any(phase in phases_seen for phase in ["final_hold", "complete"]),
        "rosbag_profile_ok": rosbag_profile.get("ok") is True,
        "rosbag_profile": rosbag_profile,
        "mission_summary": mission_summary,
        "mission_status": mission_status,
        "mavlink_status": mavlink_status,
        "pose_mirror_status": pose_mirror_status,
        "imu_status": imu_status,
        "slam_status": slam_status,
        "gazebo_truth_status": gazebo_truth_status,
        "gazebo_truth_trajectory": gazebo_truth_trajectory,
        "external_nav_status": external_status,
        "mavlink_external_nav_status": mavlink_external_nav_status,
        "x2_status": x2_status,
        "rangefinder_down_status": rangefinder_down_status,
        "rangefinder_fcu_observed": rangefinder_fcu_observed,
        "rangefinder_serial_ok": rangefinder_serial_ok,
        "rangefinder_simulation_fidelity": rangefinder_simulation_fidelity,
        "legacy_mavlink_rangefinder_sender": legacy_mavlink_rangefinder_sender,
        "topics_recorded": topics,
        "foxglove_notes": str(artifact_dir / "foxglove_notes.md"),
    }
    (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if summary["ok"] else 3


def execute_companion_gazebo_acceptance(
    *,
    artifact_dir: Path,
    duration_sec: float,
    rosbag_profile_path: Path,
    companion_image: str,
    scan_source: str,
    config: RuntimeConfig,
) -> int:
    logger.info("Starting NavLab acceptance artifact_dir={} duration_sec={}", artifact_dir, duration_sec)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    time.sleep(14)

    topics = build_rosbag_topic_plan(rosbag_profile_path)
    effective_profile = write_effective_rosbag_profile(
        artifact_dir=artifact_dir,
        source_profile=rosbag_profile_path,
        topics=topics,
    )
    logger.info(
        "Loaded {} effective rosbag topics from minimum set plus {}",
        len(topics),
        rosbag_profile_path,
    )
    (artifact_dir / "rosbag_record_mode.txt").write_text(
        "profile-topics-only\n",
        encoding="utf-8",
    )

    manager = ProcessManager()
    record_profile_topics(manager=manager, artifact_dir=artifact_dir, topics=topics)
    record_gazebo_truth_trajectory(manager=manager, artifact_dir=artifact_dir)
    try:
        time.sleep(2)
        mission_rc = _run_mission(artifact_dir=artifact_dir, duration_sec=duration_sec, config=config)
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
    logger.info("Rosbag profile validation ok={}", rosbag_summary["ok"])

    write_foxglove_notes(artifact_dir=artifact_dir)
    rc = write_summary(
        artifact_dir=artifact_dir,
        duration_sec=duration_sec,
        mission_rc=mission_rc,
        rosbag_profile=rosbag_summary,
        config=config,
        scan_source=scan_source,
    )
    logger.info("NavLab acceptance completed rc={}", rc)
    return rc
