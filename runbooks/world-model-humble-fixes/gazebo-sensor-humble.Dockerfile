ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

# NOTE(navlab-humble-fix 2026-07-03,第3版):
# 上游用 uv 造 /opt/gazebo-sensor-venv(uv 托管 Python 3.14)。在 humble(Py3.10)上这条路走不通:
#   坑#3 venv python 是悬空软链(uv python 没拷进最终镜像)→ 服务秒退;
#   坑#4 启动命令 source /opt/navlab_sensor_ws/install/setup.bash 因跳过 ydlidar colcon 而不存在 → 秒退;
#   坑#5 修完前两个后:venv Py3.14 无法 import humble 的 rclpy(C 扩展系 Py3.10)→
#         x2_serial_emulator/cloud_scan_projection/range_projection 全报 "requires ROS2 Python packages"。
# 本版方案:venv 改用【系统 Python3.10 + --system-site-packages】(直接可见 /opt/ros/humble 的 rclpy),
#   pip 装 navlab gazebo-sensor 依赖组(numpy 钉 <2.3:2.3+ 要 Py3.11)+ tomli(Py3.10 无 tomllib)+ pyserial。
#   不再需要 uv builder 阶段。

FROM ${ROS_BASE_IMAGE} AS navlab-gazebo-sensor

ARG ROS_DISTRO=humble
ENV VIRTUAL_ENV=/opt/gazebo-sensor-venv
ENV PATH=/opt/gazebo-sensor-venv/bin:$PATH

RUN apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 update && \
  apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    python3-venv \
    python3-pip \
    ros-${ROS_DISTRO}-ros-gz-bridge \
    ros-${ROS_DISTRO}-rosbag2-storage-mcap && \
  rm -rf /var/lib/apt/lists/*

# venv:系统 Py3.10 + 可见系统 site-packages(rclpy 等 ROS Python 包)
RUN python3 -m venv --system-site-packages /opt/gazebo-sensor-venv && \
  /opt/gazebo-sensor-venv/bin/pip install --no-cache-dir \
    --index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    "numpy<2.3" pymavlink PyYAML jinja2 loguru typer tomli pyserial

WORKDIR /opt/navlab_sensor_ws
COPY third_party/YDLidar-SDK /opt/navlab_sensor_ws/YDLidar-SDK
COPY third_party/ydlidar_ros2_driver /opt/navlab_sensor_ws/src/ydlidar_ros2_driver

# NOTE(navlab-humble-fix 2026-07-03,坑#6):运行时 X2 管线**必须**有 ydlidar_ros2_driver
#   (gz雷达→虚拟串口模拟X2硬件协议→真驱动读串口→/navlab/x2/vendor_scan→/scan),
#   之前"仿真不需要驱动、跳过构建"的假设是错的。humble 编译失败根因 = 上游用了
#   declare_parameter("name") 无默认值形式(humble 已移除)。最小补丁:把每处 declare 前
#   已赋默认值的同名变量作为默认值传入(语义不变);float 参数转 double(ROS2 参数无 float 型)。
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
