#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros/${ROS_DISTRO:-humble}/setup.bash
set -u

export LIBGL_ALWAYS_SOFTWARE=1
export GZ_SIM_RESOURCE_PATH="/workspace/worlds:/workspace/models${GZ_SIM_RESOURCE_PATH:+:${GZ_SIM_RESOURCE_PATH}}"
WORLD="${WORLD:-/workspace/worlds/empty_headless.sdf}"
echo "Starting Gazebo headless: ${WORLD}"
exec gz sim -s -r "${WORLD}"
