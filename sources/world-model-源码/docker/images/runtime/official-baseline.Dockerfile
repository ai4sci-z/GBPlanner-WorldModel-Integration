# syntax=docker/dockerfile:1.7

ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG GAZEBO_HEADLESS_IMAGE=navlab/gazebo-headless:${INFRA_TAG}

FROM ${GAZEBO_HEADLESS_IMAGE} AS navlab-official-baseline

ARG ROS_DISTRO=humble

ENV DEBIAN_FRONTEND=noninteractive
ENV GZ_VERSION=harmonic
ENV OFFICIAL_WS=/opt/navlab_official_ws
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=${JAVA_HOME}/bin:/opt/navlab_official_ws/src/Micro-XRCE-DDS-Gen/scripts:${PATH}

SHELL ["/bin/bash", "-lc"]

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update && \
    apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 install -y --no-install-recommends \
      build-essential \
      ccache \
      cmake \
      g++ \
      gawk \
      gcc \
      genromfs \
      git \
      openjdk-17-jdk-headless \
      libasio-dev \
      libgstreamer-plugins-base1.0-dev \
      libgstreamer1.0-dev \
      libopencv-dev \
      libtinyxml2-dev \
      libtool \
      libxml2-dev \
      libxslt1-dev \
      make \
      pkg-config \
      python3-colcon-common-extensions \
      python3-dev \
      python3-lxml \
      python3-numpy \
      python3-pexpect \
      python3-pip \
      python3-rosdep \
      python3-serial \
      python3-setuptools \
      python3-vcstool \
      python3-wheel \
      python3-yaml \
      rapidjson-dev \
      ros-${ROS_DISTRO}-cartographer-ros \
      ros-${ROS_DISTRO}-gps-msgs \
      ros-${ROS_DISTRO}-micro-ros-msgs \
      ros-${ROS_DISTRO}-nav2-bringup \
      ros-${ROS_DISTRO}-navigation2 \
      ros-${ROS_DISTRO}-robot-state-publisher \
      ros-${ROS_DISTRO}-ros-gz \
      ros-${ROS_DISTRO}-sdformat-urdf \
      ros-${ROS_DISTRO}-topic-tools \
      ros-${ROS_DISTRO}-twist-stamper \
      && python3 -m pip install --break-system-packages --no-cache-dir \
        dronecan \
        empy==3.3.4 \
        future \
        intelhex \
        MAVProxy \
        pymavlink \
      && rm -rf /var/lib/apt/lists/*

ARG ARDUPILOT_REF=master
ARG ARDUPILOT_ROS_REF=humble
ARG ARDUPILOT_GZ_REF=main
ARG ARDUPILOT_GAZEBO_REF=ros2
ARG ARDUPILOT_SITL_MODELS_REF=main
ARG MICRO_ROS_AGENT_REF=jazzy
ARG MICRO_XRCE_DDS_GEN_REF=v4.7.0

WORKDIR ${OFFICIAL_WS}/src

RUN --mount=type=cache,target=/root/.cache/git,sharing=locked \
    git clone --depth 1 --recurse-submodules --shallow-submodules \
      --branch "${ARDUPILOT_REF}" https://github.com/ArduPilot/ardupilot.git ardupilot && \
    git clone --depth 1 --branch "${ARDUPILOT_ROS_REF}" \
      https://github.com/ArduPilot/ardupilot_ros.git ardupilot_ros && \
    git clone --depth 1 --branch "${ARDUPILOT_GZ_REF}" \
      https://github.com/ArduPilot/ardupilot_gz.git ardupilot_gz && \
    git clone --depth 1 --branch "${ARDUPILOT_GAZEBO_REF}" \
      https://github.com/ArduPilot/ardupilot_gazebo.git ardupilot_gazebo && \
    git clone --depth 1 --branch "${ARDUPILOT_SITL_MODELS_REF}" \
      https://github.com/ArduPilot/SITL_Models.git ardupilot_sitl_models && \
    git clone --depth 1 --branch "${MICRO_ROS_AGENT_REF}" \
      https://github.com/micro-ROS/micro-ROS-Agent.git micro_ros_agent && \
    git clone --depth 1 --recurse-submodules --shallow-submodules \
      --branch "${MICRO_XRCE_DDS_GEN_REF}" \
      https://github.com/ardupilot/Micro-XRCE-DDS-Gen.git Micro-XRCE-DDS-Gen

COPY patches/ardupilot_gazebo_esc_lag.patch /tmp/navlab_ardupilot_gazebo_esc_lag.patch

RUN cd ardupilot_gazebo && \
    patch -p1 < /tmp/navlab_ardupilot_gazebo_esc_lag.patch

RUN --mount=type=cache,target=/root/.gradle,sharing=locked,id=official-baseline-gradle-java17 \
    cd Micro-XRCE-DDS-Gen && \
    ./gradlew --no-daemon assemble && \
    microxrceddsgen -help >/dev/null

RUN source /opt/ros/${ROS_DISTRO}/setup.bash && \
    colcon --log-base /tmp/navlab_official-log build \
      --base-paths \
        ardupilot/Tools/ros2 \
        ardupilot_ros \
        ardupilot_gz \
        ardupilot_gazebo \
        ardupilot_sitl_models/Gazebo \
        micro_ros_agent \
      --packages-select \
        ardupilot_msgs \
        micro_ros_agent \
        ardupilot_sitl \
        ardupilot_dds_tests \
        ardupilot_gazebo \
        ardupilot_sitl_models \
        ardupilot_gz_description \
        ardupilot_gz_gazebo \
        ardupilot_gz_application \
        ardupilot_gz_bringup \
        ardupilot_cartographer \
      --build-base /tmp/navlab_official-build \
      --install-base ${OFFICIAL_WS}/install \
      --cmake-args \
        -DCMAKE_BUILD_TYPE=RelWithDebInfo \
        -DPython3_EXECUTABLE=/usr/bin/python3

RUN source /opt/ros/${ROS_DISTRO}/setup.bash && \
    source ${OFFICIAL_WS}/install/setup.bash && \
    ros2 pkg prefix ardupilot_sitl && \
    ros2 pkg prefix ardupilot_gz_bringup && \
    ros2 pkg prefix ardupilot_cartographer && \
    ros2 pkg prefix micro_ros_agent && \
    ros2 pkg prefix cartographer_ros && \
    (command -v MicroXRCEAgent || command -v micro_ros_agent || \
      ros2 pkg executables micro_ros_agent | awk '{print $2}' | grep -Eq '^(MicroXRCEAgent|micro_ros_agent)$')

WORKDIR /workspace
