from __future__ import annotations

import signal
import time
from collections.abc import Callable
from pathlib import Path

from navlab.common.logging import logger
from navlab.common.process_manager import ProcessManager
from navlab.sim.companion.runtime.config import RuntimeConfig


class CompanionLauncher:
    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._processes = ProcessManager()
        self._stopping = False

    def start(self) -> int:
        logger.info("Starting NavLab companion runtime")
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        self.start_configured_processes()
        while not self._stopping:
            time.sleep(1.0)
        self.stop()
        return 0

    def stop(self) -> None:
        self._processes.stop_all(timeout_sec=5)

    def _handle_signal(self, signum: int, _frame: object) -> None:
        logger.info("Received signal {}; stopping companion runtime", signum)
        self._stopping = True

    def _start(self, name: str, command: list[str]) -> None:
        self._processes.start_subprocess(name, command)

    def start_function(self, name: str, target: Callable[[list[str]], int | None], argv: list[str]) -> None:
        self._processes.start_function(name, target, argv)

    def start_configured_processes(self) -> None:
        config = self._config
        if config.world_markers.autostart:
            from navlab.sim.companion.nodes.world_markers import run as run_world_markers

            self.start_function(
                "world_marker_publisher",
                run_world_markers,
                config.world_markers.argv(),
            )
        if config.scan_features.autostart:
            from navlab.sim.companion.nodes.scan_features import run as run_scan_features

            self.start_function(
                "scan_features_publisher",
                run_scan_features,
                config.scan_features.argv(),
            )
        if config.gazebo_truth_bridge.autostart:
            self._start(
                "gazebo_truth_pose_bridge",
                config.gazebo_truth_bridge.command(),
            )
        if config.gazebo_truth_odom.autostart:
            from navlab.sim.companion.nodes.gazebo_truth_odom import run as run_gazebo_truth_odom

            self.start_function(
                "gazebo_truth_odom_publisher",
                run_gazebo_truth_odom,
                config.gazebo_truth_odom.argv(),
            )
        if config.pose_mirror.autostart:
            from navlab.real.companion.nodes.pose_mirror import run as run_pose_mirror

            self.start_function(
                "mavlink_gazebo_pose_mirror",
                run_pose_mirror,
                config.pose_mirror.argv(),
            )
        if config.imu_bridge.autostart:
            from navlab.real.companion.nodes.imu_bridge import run as run_imu_bridge

            self.start_function(
                "mavlink_imu_bridge",
                run_imu_bridge,
                config.imu_bridge.argv(),
            )
        if config.external_nav_sender.autostart:
            from navlab.real.companion.nodes.external_nav import main as run_external_nav_sender

            self.start_function(
                "mavlink_external_nav_sender",
                run_external_nav_sender,
                config.external_nav_sender.argv(),
            )
        if config.mission.autostart:
            from navlab.sim.companion.nodes.obstacle_mission import run as run_obstacle_mission

            self.start_function(
                "mavlink_obstacle_mission_controller",
                run_obstacle_mission,
                config.mission.argv(),
            )


def launch_companion(*, config_path: str | Path) -> int:
    logger.info("Loading NavLab runtime config from {}", config_path)
    return CompanionLauncher(RuntimeConfig.load(config_path)).start()
