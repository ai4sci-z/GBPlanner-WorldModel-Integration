ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

FROM ${ROS_BASE_IMAGE} AS fast-lio-build-base

ARG ROS_DISTRO=humble

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-lc"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libeigen3-dev \
    libpcl-dev \
    ros-${ROS_DISTRO}-pcl-ros \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-sensor-msgs \
    ros-${ROS_DISTRO}-nav-msgs \
    libapr1-dev \
    && rm -rf /var/lib/apt/lists/*

FROM fast-lio-build-base

COPY third_party /tmp/third_party
RUN test -f /tmp/third_party/FAST_LIO/package.xml \
    || (echo "FAST-LIO source missing: add it at third_party/FAST_LIO before building this image" >&2; exit 2)
RUN test -f /tmp/third_party/livox_ros_driver2/build.sh \
    || (echo "livox_ros_driver2 source missing: add it at third_party/livox_ros_driver2 before building this image" >&2; exit 2)
RUN test -f /tmp/third_party/Livox-SDK2/CMakeLists.txt \
    || (echo "Livox-SDK2 source missing: add it at third_party/Livox-SDK2 before building this image" >&2; exit 2)

WORKDIR /tmp/third_party/Livox-SDK2
RUN mkdir -p build \
    && cd build \
    && cmake .. \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig

WORKDIR /workspace/ros_ws/src

RUN cp -a /tmp/third_party/FAST_LIO /workspace/ros_ws/src/fast_lio
RUN cp -a /tmp/third_party/livox_ros_driver2 /workspace/ros_ws/src/livox_ros_driver2
RUN cp -f /workspace/ros_ws/src/livox_ros_driver2/package_ROS2.xml /workspace/ros_ws/src/livox_ros_driver2/package.xml \
    && cp -rf /workspace/ros_ws/src/livox_ros_driver2/launch_ROS2 /workspace/ros_ws/src/livox_ros_driver2/launch

WORKDIR /workspace/ros_ws
RUN test -f /usr/local/lib/liblivox_lidar_sdk_shared.so \
    || (echo "Livox-SDK2 shared library missing after build: expected /usr/local/lib/liblivox_lidar_sdk_shared.so" >&2; exit 3)
RUN test -f /usr/local/include/livox_lidar_api.h \
    || (echo "Livox-SDK2 headers missing after build: expected /usr/local/include/livox_lidar_api.h" >&2; exit 3)

RUN set +u \
    && source /opt/ros/${ROS_DISTRO}/setup.bash \
    && set -u \
    && colcon build --symlink-install --packages-select livox_ros_driver2 fast_lio --cmake-args -DROS_EDITION=ROS2 -DDISTRO_ROS=jazzy
