ARG BASE_IMAGE=voxblox_ros2_deps:jazzy

FROM ${BASE_IMAGE} AS builder
SHELL ["/bin/bash", "-lc"]
WORKDIR /work
COPY src /work/src
RUN source /opt/ros/jazzy/setup.bash \
    && export MAKEFLAGS="-j$(nproc)" \
    && colcon build --merge-install --executor sequential \
         --cmake-args -DCMAKE_BUILD_TYPE=Release

FROM ${BASE_IMAGE}
ARG CYCLONEDDS_VERSION=2.2.3-1noble.20260615.123728
ARG FEAT_COMMIT=unknown
LABEL org.opencontainers.image.source="https://github.com/ai4sci-z/GBPlanner-WorldModel-Integration" \
      org.opencontainers.image.revision="${FEAT_COMMIT}" \
      org.opencontainers.image.description="GBPlanner ROS 2 Jazzy M5 runtime"
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         "ros-jazzy-rmw-cyclonedds-cpp=${CYCLONEDDS_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /work/install /ws/install
WORKDIR /ws
CMD ["sleep", "infinity"]
