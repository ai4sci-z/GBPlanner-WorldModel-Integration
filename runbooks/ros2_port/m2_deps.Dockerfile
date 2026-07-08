# M2 voxblox ROS2 deps image (mirrors GabrieleSantangelo/voxblox-ros2
# docker/Dockerfile.base @243dc3e, the only Jazzy-CI-proven recipe).
# NOTE: do NOT rosdep install this workspace - package.xml still carries
# ROS1-era keys (gflags_catkin/glog_vendor/libpcl-all); explicit list only.
ARG ROS_DISTRO=jazzy
FROM ros:${ROS_DISTRO}

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y \
    build-essential cmake git pkg-config \
    libdw-dev libelf-dev \
    libeigen3-dev \
    libgflags-dev libgoogle-glog-dev \
    libboost-all-dev \
    libpcap-dev libpcl-dev \
    libprotobuf-dev protobuf-compiler \
    qtbase5-dev \
 && apt-get install -y \
    ros-${ROS_DISTRO}-backward-ros \
    ros-${ROS_DISTRO}-cv-bridge \
    ros-${ROS_DISTRO}-geometry-msgs \
    ros-${ROS_DISTRO}-interactive-markers \
    ros-${ROS_DISTRO}-pcl-conversions \
    ros-${ROS_DISTRO}-pcl-ros \
    ros-${ROS_DISTRO}-pluginlib \
    ros-${ROS_DISTRO}-rclcpp \
    ros-${ROS_DISTRO}-rviz-common \
    ros-${ROS_DISTRO}-rviz-default-plugins \
    ros-${ROS_DISTRO}-rviz-ogre-vendor \
    ros-${ROS_DISTRO}-rviz-rendering \
    ros-${ROS_DISTRO}-sensor-msgs \
    ros-${ROS_DISTRO}-std-srvs \
    ros-${ROS_DISTRO}-tf2 \
    ros-${ROS_DISTRO}-tf2-eigen \
    ros-${ROS_DISTRO}-tf2-geometry-msgs \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-rviz2 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /ws
CMD ["bash"]
