#!/usr/bin/env bash
# gazebo-sensor humble 重建 v2:修 venv 悬空软链(uv 托管 python 未拷进最终镜像→服务启动即
# "No such file"→无 /scan)。用 runbooks 固化的 gazebo-sensor-humble.Dockerfile(含:跳过
# ydlidar colcon + COPY uv python)。构建独立进行,不影响正在跑的其他容器(如 gbplanner_ref)。
cd /home/ai4s/ws/world-model || exit 1
export DOCKER_BUILDKIT=1
DF=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-humble-fixes/gazebo-sensor-humble.Dockerfile
LOG=/home/ai4s/build_gazebo_sensor2.log
echo "BUILD gazebo-sensor v2 START $(date)" > "$LOG"
docker build --network=host \
  --build-arg HTTP_PROXY=http://127.0.0.1:7897 \
  --build-arg HTTPS_PROXY=http://127.0.0.1:7897 \
  --build-arg NO_PROXY=localhost,127.0.0.1,mirrors.aliyun.com,packages.ros.org,packages.osrfoundation.org,archive.ubuntu.com,security.ubuntu.com \
  --build-arg INFRA_TAG=humble-latest --build-arg ROS_DISTRO=humble \
  -f "$DF" -t navlab/gazebo-sensor:humble-latest . >> "$LOG" 2>&1
rc=$?
echo "GS2_EXIT=$rc $(date)" >> "$LOG"
# 真实产物自检:①venv python 能跑 ②venv python 能 import rclpy(坑#5 的关键验证)
if docker run --rm navlab/gazebo-sensor:humble-latest /opt/gazebo-sensor-venv/bin/python --version >> "$LOG" 2>&1; then
  echo "VENV_PYTHON=OK" >> "$LOG"
else
  echo "VENV_PYTHON=BROKEN" >> "$LOG"
fi
if docker run --rm navlab/gazebo-sensor:humble-latest bash -lc 'source /opt/ros/humble/setup.bash && /opt/gazebo-sensor-venv/bin/python -c "import rclpy, numpy, loguru, tomli, yaml, pymavlink; print(\"deps ok\")"' >> "$LOG" 2>&1; then
  echo "VENV_RCLPY=OK" >> "$LOG"
else
  echo "VENV_RCLPY=BROKEN" >> "$LOG"
fi
if docker run --rm navlab/gazebo-sensor:humble-latest bash -lc 'source /opt/ros/humble/setup.bash && source /opt/navlab_sensor_ws/install/setup.bash && ros2 pkg prefix ydlidar_ros2_driver' >> "$LOG" 2>&1; then
  echo "YDLIDAR_PKG=OK" >> "$LOG"
else
  echo "YDLIDAR_PKG=BROKEN" >> "$LOG"
fi
echo "DONE $(date)" >> "$LOG"
tail -7 "$LOG"
