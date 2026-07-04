ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

FROM ${ROS_BASE_IMAGE} AS navlab-slam-cartographer

ARG ROS_DISTRO=humble

RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update && \
  apt-get install -y --no-install-recommends \
    ros-${ROS_DISTRO}-cartographer-ros && \
  rm -rf /var/lib/apt/lists/*

WORKDIR /opt/navlab_ws

COPY navlab/common/slam/ros /opt/navlab_ws/navlab_slam_ros
COPY navlab/common/interfaces/ydlidar_interfaces /opt/navlab_ws/navlab_interfaces/ydlidar_interfaces

RUN bash -lc "\
  source /opt/ros/${ROS_DISTRO}/setup.bash && \
  colcon --log-base /tmp/navlab_slam-log build \
    --base-paths navlab_slam_ros navlab_interfaces \
    --packages-select ydlidar_interfaces navlab_fake_odom navlab_slam_imu_bridge navlab_cartographer_adapter navlab_external_nav_bridge navlab_slam_bringup \
    --build-base /tmp/navlab_slam-build \
    --install-base /opt/navlab_ws/install \
    --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3"
