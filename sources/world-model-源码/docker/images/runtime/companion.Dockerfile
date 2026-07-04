ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

FROM ${ROS_BASE_IMAGE} AS companion-python-builder

COPY --from=ghcr.io/astral-sh/uv:0.11.16-python3.11-alpine /usr/local/bin/uv /usr/local/bin/uv

WORKDIR /workspace

ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/companion-venv

COPY navlab/pyproject.toml navlab/uv.lock /workspace/navlab/

RUN uv sync \
  --project /workspace/navlab \
  --frozen \
  --no-dev \
  --group companion \
  --no-install-project


FROM ${ROS_BASE_IMAGE} AS navlab-companion

ARG ROS_DISTRO=humble

ENV VIRTUAL_ENV=/opt/companion-venv
ENV PATH=/opt/companion-venv/bin:$PATH

RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update && \
  apt-get install -y --no-install-recommends \
    ros-${ROS_DISTRO}-ros-gz-bridge \
    ros-${ROS_DISTRO}-rosbag2-storage-mcap && \
  rm -rf /var/lib/apt/lists/*

COPY --from=companion-python-builder /opt/companion-venv /opt/companion-venv

WORKDIR /opt/navlab_ws

COPY navlab/common/interfaces/ydlidar_interfaces /opt/navlab_ws/navlab_interfaces/ydlidar_interfaces

RUN bash -lc "\
  source /opt/ros/${ROS_DISTRO}/setup.bash && \
  colcon --log-base /tmp/navlab_companion-log build \
    --base-paths navlab_interfaces \
    --packages-select ydlidar_interfaces \
    --build-base /tmp/navlab_companion-build \
    --install-base /opt/navlab_ws/install \
    --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3"
