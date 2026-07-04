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
