#!/usr/bin/env bash
# M1: colcon build planner_msgs inside a ROS 2 Jazzy container.
# ros2_port is mounted read-only; we copy into the container FS to build
# (avoids symlink/permission issues on the Windows /mnt/c filesystem).
ROS2PORT=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/ros2_port
echo "=== host ros2_port: $ROS2PORT ==="
ls -R "$ROS2PORT/src" 2>/dev/null | head -30

docker run --rm -v "$ROS2PORT":/src:ro ros:jazzy-ros-base bash -lc '
  set -e
  source /opt/ros/jazzy/setup.bash
  mkdir -p /root/ws/src
  cp -r /src/src/* /root/ws/src/
  cd /root/ws
  echo "=== colcon build ==="
  colcon build 2>&1 | tail -30
  RC=${PIPESTATUS[0]}
  echo "COLCON_RC=$RC"
  [ "$RC" -ne 0 ] && exit "$RC"
  source install/setup.bash
  echo "=== ros2 interface show planner_msgs/srv/PlannerSrv ==="
  ros2 interface show planner_msgs/srv/PlannerSrv
  echo "=== ros2 interface show planner_msgs/msg/PlannerStatus ==="
  ros2 interface show planner_msgs/msg/PlannerStatus
  echo "=== all planner_msgs interfaces ==="
  ros2 interface list 2>/dev/null | grep planner_msgs
'
echo "DOCKER_RC=$?"
echo "=== DONE ==="
