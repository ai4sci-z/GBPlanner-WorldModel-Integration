#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros/${ROS_DISTRO:-humble}/setup.bash
if [[ -f /opt/navlab_sensor_ws/install/setup.bash ]]; then
  source /opt/navlab_sensor_ws/install/setup.bash
fi
set -u

python_bin="/opt/gazebo-sensor-venv/bin/python"

case "${X2_MODE:-runtime}" in
  runtime)
    exec "${python_bin}" -m navlab.sim.gazebo_sensor.cli --runtime
    ;;
  driver-smoke)
    exec "${python_bin}" -m navlab.sim.gazebo_sensor.cli \
      --driver-smoke \
      --duration-sec "${X2_SMOKE_DURATION_SEC:-15}" \
      --artifact-dir "${X2_ARTIFACT_DIR:-/artifacts/ros/x2_driver_smoke/manual}" \
      --startup-timeout-sec "${X2_STARTUP_TIMEOUT_SEC:-20}"
    ;;
  emulator)
    exec "${python_bin}" -m navlab.sim.gazebo_sensor.cli
    ;;
  *)
    echo "Invalid X2_MODE='${X2_MODE}'. Expected runtime, driver-smoke, or emulator." >&2
    exit 2
    ;;
esac
