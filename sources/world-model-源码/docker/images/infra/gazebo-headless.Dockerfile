ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

FROM ${ROS_BASE_IMAGE} AS ardupilot-gazebo-build

ARG ROS_DISTRO=humble

ENV DEBIAN_FRONTEND=noninteractive
ENV GZ_VERSION=harmonic

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    && curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
      -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
      > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer1.0-dev \
    libgz-sim8-dev \
    libopencv-dev \
    rapidjson-dev \
    && rm -rf /var/lib/apt/lists/*

COPY third_party/ardupilot_gazebo /opt/ardupilot_gazebo
WORKDIR /opt/ardupilot_gazebo/build
RUN cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    && make -j"$(nproc)"

FROM ${ROS_BASE_IMAGE}

ARG ROS_DISTRO=humble

ENV DEBIAN_FRONTEND=noninteractive
ENV GZ_VERSION=harmonic
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/ardupilot_gazebo/build:/usr/lib/x86_64-linux-gnu/gz-sim-8/plugins
ENV GZ_SIM_RESOURCE_PATH=/opt/ardupilot_gazebo/models:/opt/ardupilot_gazebo/worlds

RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-${ROS_DISTRO}-ros-gz \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ardupilot-gazebo-build /opt/ardupilot_gazebo /opt/ardupilot_gazebo

RUN /bin/bash -lc 'source /opt/ros/${ROS_DISTRO}/setup.bash && gz sim --help >/dev/null'
