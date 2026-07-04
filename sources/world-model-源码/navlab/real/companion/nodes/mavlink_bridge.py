from __future__ import annotations

import argparse
import os
import shlex
import signal
import site
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    children: list[subprocess.Popen[str]] = []
    stopping = False

    def stop_children(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGINT, stop_children)
    signal.signal(signal.SIGTERM, stop_children)

    env = _child_env(args.ros_distro)
    commands = _bridge_commands(args)
    try:
        children = [subprocess.Popen(command, env=env, text=True) for command in commands]  # noqa: S603
        while True:
            for child in children:
                rc = child.poll()
                if rc is not None:
                    if not stopping and rc != 0:
                        stop_children(signal.SIGTERM, None)
                        return rc
                    if all(item.poll() is not None for item in children):
                        return 0 if stopping else rc
            time.sleep(0.2)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                child.kill()


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NavLab's MAVLink bridge nodes for real prepare.")
    parser.add_argument("--ros-distro", default=os.environ.get("ROS_DISTRO", "humble"))
    parser.add_argument("--mavlink-endpoint", default="tcp:127.0.0.1:5760")
    parser.add_argument("--external-nav-odom-topic", default="/external_nav/odom")
    parser.add_argument("--mavlink-status-topic", default="/navlab/mavlink/status")
    parser.add_argument("--pose-mirror-status-topic", default="/navlab/pose_mirror/status")
    parser.add_argument("--local-position-pose-topic", default="/navlab/fcu/local_position_pose")
    parser.add_argument("--external-nav-status-topic", default="/mavlink_external_nav/status")
    parser.add_argument("--pose-topic", default="/navlab/fcu/mavlink_pose")
    parser.add_argument("--imu-topic", default="/imu/data")
    parser.add_argument("--imu-status-topic", default="/imu/status")
    parser.add_argument("--auto-ekf-source-set", action=argparse.BooleanOptionalAction, default=False)
    return parser.parse_args(argv)


def _bridge_commands(args: argparse.Namespace) -> list[list[str]]:
    return [
        _ros_python_command(
            args.ros_distro,
            [
                "/usr/bin/python3",
                "-m",
                "navlab.real.companion.nodes.pose_mirror",
                "--endpoint",
                args.mavlink_endpoint,
                "--pose-topic",
                args.pose_topic,
                "--pose-frame-id",
                "odom",
                "--map-frame-id",
                "map",
                "--odom-frame-id",
                "odom",
                "--sensor-base-frame-id",
                "base_link",
                "--replay-base-frame-id",
                "",
                "--disable-replay-static-tf",
                "--status-topic",
                args.pose_mirror_status_topic,
                "--mavlink-status-topic",
                args.mavlink_status_topic,
                "--imu-topic",
                args.imu_topic,
                "--imu-status-topic",
                args.imu_status_topic,
                "--imu-frame-id",
                "imu_link",
                "--imu-stamp-source-topic",
                "",
                "--allow-raw-imu",
                "--rate-hz",
                "20.0",
                "--stream-rate-hz",
                "20.0",
                *(_enabled_flag("--auto-ekf-source-set", args.auto_ekf_source_set)),
            ],
        ),
        _ros_python_command(
            args.ros_distro,
            [
                "/usr/bin/python3",
                "-m",
                "navlab.real.companion.nodes.external_nav",
                "--endpoint",
                args.mavlink_endpoint,
                "--odom-topic",
                args.external_nav_odom_topic,
                "--status-topic",
                args.external_nav_status_topic,
                "--local-position-pose-topic",
                args.local_position_pose_topic,
                "--use-fcu-roll-pitch",
            ],
        ),
    ]


def _enabled_flag(flag: str, enabled: bool) -> list[str]:
    return [flag] if enabled else []


def _ros_python_command(ros_distro: str, command: list[str]) -> list[str]:
    source_commands = []
    ros_setup = Path("/opt/ros") / ros_distro / "setup.bash"
    if ros_setup.exists():
        source_commands.append(f"source {shlex.quote(str(ros_setup))}")
    local_setup = Path("install/setup.bash")
    if local_setup.exists():
        source_commands.append(f"source {shlex.quote(str(local_setup))}")
    source_commands.append("exec " + shlex.join(command))
    return ["bash", "-lc", " && ".join(source_commands)]


def _child_env(ros_distro: str) -> dict[str, str]:
    env = dict(os.environ)
    python_paths = [str(Path.cwd()), *_site_package_paths()]
    existing = env.get("PYTHONPATH", "")
    if existing:
        python_paths.append(existing)
    env["PYTHONPATH"] = ":".join(dict.fromkeys(path for path in python_paths if path))
    env.setdefault("ROS_DISTRO", ros_distro)
    return env


def _site_package_paths() -> list[str]:
    paths: list[str] = []
    for fn in (site.getsitepackages,):
        try:
            paths.extend(fn())
        except Exception:
            pass
    user_site = site.getusersitepackages()
    if user_site:
        paths.append(user_site)
    return paths


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
