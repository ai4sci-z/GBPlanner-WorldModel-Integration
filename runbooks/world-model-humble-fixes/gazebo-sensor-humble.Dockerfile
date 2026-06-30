ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

FROM ${ROS_BASE_IMAGE} AS gazebo-sensor-python-builder
COPY --from=ghcr.io/astral-sh/uv:0.11.16-python3.11-alpine /usr/local/bin/uv /usr/local/bin/uv
WORKDIR /workspace
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/gazebo-sensor-venv
COPY navlab/pyproject.toml navlab/uv.lock /workspace/navlab/
RUN uv sync --project /workspace/navlab --frozen --no-dev --group gazebo-sensor --no-install-project

FROM ${ROS_BASE_IMAGE} AS navlab-gazebo-sensor
ARG ROS_DISTRO=humble
ENV VIRTUAL_ENV=/opt/gazebo-sensor-venv
ENV PATH=/opt/gazebo-sensor-venv/bin:$PATH
RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update && \
  apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    ros-${ROS_DISTRO}-ros-gz-bridge \
    ros-${ROS_DISTRO}-rosbag2-storage-mcap && \
  rm -rf /var/lib/apt/lists/*
COPY --from=gazebo-sensor-python-builder /opt/gazebo-sensor-venv /opt/gazebo-sensor-venv
WORKDIR /opt/navlab_sensor_ws
COPY third_party/YDLidar-SDK /opt/navlab_sensor_ws/YDLidar-SDK
# NOTE(navlab-humble-fix 2026-06-29): 跳过 ydlidar_ros2_driver 的 colcon 构建。
#   原因:其 declare_parameter(无默认值形式)在 humble 的 rclcpp 下编译不过(模板推导失败)。
#   仿真用 gz gpu_lidar -> ros-gz-bridge,不需要 YDLidar 硬件驱动节点。
#   仅安装 YDLidar-SDK(C++ 库,编译正常),保留 ros-gz-bridge(仿真关键)。
RUN bash -lc "\
  cmake -S YDLidar-SDK -B /tmp/ydlidar_sdk-build -DCMAKE_INSTALL_PREFIX=/usr/local && \
  cmake --build /tmp/ydlidar_sdk-build --target install -j\$(nproc) && \
  ldconfig"
