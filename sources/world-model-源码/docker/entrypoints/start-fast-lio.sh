#!/usr/bin/env bash
set -euo pipefail

# ROS setup scripts may reference unset tracing variables, so temporarily
# disable nounset while sourcing them.
set +u
source /opt/ros/${ROS_DISTRO:-humble}/setup.bash
if [[ -f /workspace/ros_ws/install/setup.bash ]]; then
  source /workspace/ros_ws/install/setup.bash
fi
set -u

CONFIG="/workspace/profiles/fast-lio/config.yaml"
CONFIG_DIR="$(dirname "${CONFIG}")"
CONFIG_FILE="$(basename "${CONFIG}")"
RVIZ="false"
echo "Starting FAST-LIO with ${CONFIG}"
exec ros2 launch fast_lio mapping.launch.py \
  config_path:="${CONFIG_DIR}" \
  config_file:="${CONFIG_FILE}" \
  rviz:="${RVIZ}"
