# GBPlanner (gbplanner2) 参考环境 —— ROS1 Noetic
# 用途:P0/预研B 跑通官方 sim、看懂算法行为。与 world-model(ROS2)完全隔离。
# 修复记录(2026-06-29):上版手动 git clone gbplanner_ros + rosinstall 又拉一份 →
#   catkin 报"重复包 planner_msgs"。本版改为:不手动 clone,直接用官方
#   packages_https.rosinstall 在【工作区根】wstool init(其 local-name 自带 src/ 前缀),
#   一次性拉全部源码(gbplanner_ros 落在 src/exploration/ 下),避免重复。
FROM osrf/ros:noetic-desktop-full

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]

# ── 系统 + GBPlanner/voxblox/RotorS 依赖 ──
RUN apt-get update && apt-get install -y --no-install-recommends \
      git wget nano sudo \
      build-essential autoconf libtool \
      python3-catkin-tools python3-wstool python3-osrf-pycommon \
      libgoogle-glog-dev protobuf-compiler \
      ros-noetic-cmake-modules \
      ros-noetic-control-toolbox ros-noetic-mavlink ros-noetic-geographic-msgs \
      ros-noetic-octomap-msgs ros-noetic-octomap-ros ros-noetic-tf2-eigen \
      ros-noetic-joy ros-noetic-twist-mux ros-noetic-interactive-marker-twist-server \
    && rm -rf /var/lib/apt/lists/*

# ── 用官方 rosinstall 在工作区根一次性拉取全部源码 ──
#   rosinstall 的 local-name 形如 src/exploration/gbplanner_ros,故在 /root/gbp_ws 根运行。
WORKDIR /root/gbp_ws
RUN wget -O /tmp/packages.rosinstall \
      https://raw.githubusercontent.com/ntnu-arl/gbplanner_ros/gbplanner2/packages_https.rosinstall && \
    wstool init . /tmp/packages.rosinstall && \
    wstool update

# ── 编译(Release)──
RUN source /opt/ros/noetic/setup.bash && \
    catkin config -DCMAKE_BUILD_TYPE=Release && \
    catkin build

# ── 自动 source ──
RUN echo "source /opt/ros/noetic/setup.bash"    >> /root/.bashrc && \
    echo "source /root/gbp_ws/devel/setup.bash" >> /root/.bashrc

WORKDIR /root/gbp_ws
CMD ["bash"]

# 若仍有某包编译失败:进容器 `cd /root/gbp_ws && catkin build` 看报错,
# 多半是缺某 ros-noetic-* 包,apt 装上再 build。
