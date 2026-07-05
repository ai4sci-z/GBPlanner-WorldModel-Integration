ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

FROM ${ROS_BASE_IMAGE} AS gazebo-sensor-python-builder

COPY --from=ghcr.io/astral-sh/uv:0.11.16-python3.11-alpine /usr/local/bin/uv /usr/local/bin/uv

WORKDIR /workspace

ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/gazebo-sensor-venv

COPY navlab/pyproject.toml navlab/uv.lock /workspace/navlab/

RUN uv sync \
  --project /workspace/navlab \
  --frozen \
  --no-dev \
  --group gazebo-sensor \
  --no-install-project


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
COPY third_party/ydlidar_ros2_driver /opt/navlab_sensor_ws/src/ydlidar_ros2_driver

# NOTE(navlab-jazzy-fix 2026-07-05):上游 ydlidar 用 declare_parameter("name") 无默认值形式,
# Galactic+ rclcpp 已移除该重载(humble/jazzy 同坑)。最小补丁:把 declare 前已赋默认值的
# 同名变量作为默认值传入(语义不变);float 参数转 double(ROS2 参数无 float 型)。
# 与 runbooks/world-model-humble-fixes/gazebo-sensor-humble.Dockerfile 的 26 处 sed 一致。
RUN sed -i \
  -e 's/declare_parameter("port");/declare_parameter("port", str_optvalue);/' \
  -e 's/declare_parameter("ignore_array");/declare_parameter("ignore_array", str_optvalue);/' \
  -e 's/declare_parameter("frame_id");/declare_parameter("frame_id", frame_id);/' \
  -e 's/declare_parameter("baudrate");/declare_parameter("baudrate", optval);/' \
  -e 's/declare_parameter("lidar_type");/declare_parameter("lidar_type", optval);/' \
  -e 's/declare_parameter("device_type");/declare_parameter("device_type", optval);/' \
  -e 's/declare_parameter("sample_rate");/declare_parameter("sample_rate", optval);/' \
  -e 's/declare_parameter("abnormal_check_count");/declare_parameter("abnormal_check_count", optval);/' \
  -e 's/declare_parameter("intensity_bit");/declare_parameter("intensity_bit", optval);/' \
  -e 's/declare_parameter("fixed_resolution");/declare_parameter("fixed_resolution", b_optvalue);/' \
  -e 's/declare_parameter("reversion");/declare_parameter("reversion", b_optvalue);/' \
  -e 's/declare_parameter("inverted");/declare_parameter("inverted", b_optvalue);/' \
  -e 's/declare_parameter("auto_reconnect");/declare_parameter("auto_reconnect", b_optvalue);/' \
  -e 's/declare_parameter("isSingleChannel");/declare_parameter("isSingleChannel", b_optvalue);/' \
  -e 's/declare_parameter("intensity");/declare_parameter("intensity", b_optvalue);/' \
  -e 's/declare_parameter("support_motor_dtr");/declare_parameter("support_motor_dtr", b_optvalue);/' \
  -e 's/declare_parameter("debug");/declare_parameter("debug", b_optvalue);/' \
  -e 's/declare_parameter("angle_max");/declare_parameter("angle_max", static_cast<double>(f_optvalue));/' \
  -e 's/declare_parameter("angle_min");/declare_parameter("angle_min", static_cast<double>(f_optvalue));/' \
  -e 's/declare_parameter("range_max");/declare_parameter("range_max", static_cast<double>(f_optvalue));/' \
  -e 's/declare_parameter("range_min");/declare_parameter("range_min", static_cast<double>(f_optvalue));/' \
  -e 's/declare_parameter("frequency");/declare_parameter("frequency", static_cast<double>(f_optvalue));/' \
  -e 's/declare_parameter("invalid_range_is_inf");/declare_parameter("invalid_range_is_inf", invalid_range_is_inf);/' \
  -e 's/declare_parameter("m1_mode");/declare_parameter("m1_mode", i_v);/' \
  -e 's/declare_parameter("m2_mode");/declare_parameter("m2_mode", i_v);/' \
  -e 's/declare_parameter("m3_mode");/declare_parameter("m3_mode", i_v);/' \
  /opt/navlab_sensor_ws/src/ydlidar_ros2_driver/src/ydlidar_ros2_driver_node.cpp && \
  ! grep -q 'declare_parameter("[a-z_0-9]*");' /opt/navlab_sensor_ws/src/ydlidar_ros2_driver/src/ydlidar_ros2_driver_node.cpp

RUN bash -lc "\
  cmake -S YDLidar-SDK -B /tmp/ydlidar_sdk-build -DCMAKE_INSTALL_PREFIX=/usr/local && \
  cmake --build /tmp/ydlidar_sdk-build --target install -j\$(nproc) && \
  ldconfig && \
  source /opt/ros/${ROS_DISTRO}/setup.bash && \
  colcon --log-base /tmp/navlab_sensor-log build \
    --base-paths src \
    --packages-select ydlidar_ros2_driver \
    --build-base /tmp/navlab_sensor-build \
    --install-base /opt/navlab_sensor_ws/install \
    --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3"
