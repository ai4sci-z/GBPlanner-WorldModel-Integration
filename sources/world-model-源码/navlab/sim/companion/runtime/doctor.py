from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

from navlab.common.logging import logger

REQUIRED_ROS_PACKAGES = (
    "ydlidar_interfaces",
    "rosbag2_storage_mcap",
)
REQUIRED_PYTHON_MODULES = (
    "pymavlink",
    "navlab.real.companion.nodes.imu_bridge",
    "navlab.real.companion.nodes.pose_mirror",
    "navlab.real.companion.nodes.external_nav",
    "navlab.sim.companion.nodes.obstacle_mission",
)


def ros_pkg_present(name: str) -> bool:
    return (
        subprocess.run(
            ["ros2", "pkg", "prefix", name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def build_doctor_summary(*, image: str) -> dict[str, object]:
    ros_packages = {name: ros_pkg_present(name) for name in REQUIRED_ROS_PACKAGES}
    python_modules = {name: importlib.util.find_spec(name) is not None for name in REQUIRED_PYTHON_MODULES}
    return {
        "ok": all(ros_packages.values()) and all(python_modules.values()),
        "image": image,
        "ros2_available": shutil.which("ros2") is not None,
        "colcon_available": shutil.which("colcon") is not None,
        "ros_packages": ros_packages,
        "python_modules": python_modules,
        "blocked": False,
        "blocker": None,
    }


def write_doctor_summary(*, summary_file: Path, image: str) -> int:
    summary = build_doctor_summary(image=image)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    logger.info("Wrote doctor summary to {} ok={}", summary_file, summary["ok"])
    return 0 if summary["ok"] else 20
