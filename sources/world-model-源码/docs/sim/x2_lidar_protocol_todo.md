# X2 激光雷达协议级仿真 TODO

这份 TODO 对应 `docs/sim/x2_lidar_simulation_design.md`。

目标：让 NavLab 仿真中的最终 `/scan` 来自厂商
`ydlidar_ros2_driver_node`，其输入来自一个根据 Gazebo ideal ray 生成的
YDLidar X2 虚拟串口字节流。

边界原则：X2 协议仿真属于 Gazebo/sensor runtime。虚拟串口 emulator、
`ydlidar_ros2_driver_node`、YDLidar SDK 和对应依赖只应安装并运行在
Gazebo/sensor 镜像内。companion、SLAM、SITL 等其他镜像不应该感知 X2 协议层，
它们只消费最终 `/scan`，最多在 rosbag/Foxglove 中查看 `/scan_ideal` 和
`/sim/x2/status` 作为调试 topic。

## 当前状态

- [x] Gazebo 已能发布随 UAV 运动的 ideal lidar scan。
- [x] `/scan_features` 已能消费 `sensor_msgs/msg/LaserScan`。
- [x] NavLab acceptance 已能记录 `/scan`、`/scan_features` 和 mission topics。
- [x] Gazebo ideal scan 已和最终厂商 `/scan` 分离。
- [x] 已有 X2 虚拟串口协议 emulator。
- [x] P3 synthetic smoke 中 `/scan` 已由 `ydlidar_ros2_driver_node` 发布。
- [x] X2 协议代码和依赖已收口到 Gazebo/sensor 专属 runtime。

## P0：锁定厂商规格和 profile

目标：固定 X2 厂商基准，避免继续沿用本地冲突参数。

### 任务

- [x] 新增 `docker/profiles/x2-vendor-sim.yaml`。
- [x] 使用 `range_min: 0.1`、`range_max: 8.0`、`sample_rate: 3`、`frequency: 7.0`。
- [x] 保持 `third_party/ydlidar_ros2_driver/params/X2.yaml` 不变。
- [x] 新增 X2 协议仿真模式配置入口。
- [x] 文档明确当前 `frequency: 10.0` 和 `range_max: 12.0` 不是厂商仿真基准。

### 验收

- [x] `docker/profiles/x2-vendor-sim.yaml` 存在，且是合法 ROS 2 params YAML。
- [x] profile 的 `port` 指向 `/tmp/navlab_x2`。
- [x] 文档明确协议模式下 `/scan` 必须由厂商 driver 输出。

## P1：三角协议 packet encoder

目标：先完成纯协议编码，不引入 ROS、Gazebo 或 PTY。

### 任务

- [x] 新增协议 encoder，并在 P1.5 迁移到 `navlab/sim/gazebo_sensor/x2/protocol.py`。
- [x] 定义 X2 常量：`PH`、`TRI_PACKMAXNODES`、缩放系数、命令字节。
- [x] 实现距离编码：`Si = int(range_m * 4000)`。
- [x] 实现角度编码：`encoded_angle = int(angle_deg * 64) << 1`。
- [x] 补齐 SDK 要求的 `FSA/LSA` check bit 和每圈第一包 `CT` zero/ring-start bit。
- [x] 实现与 SDK 一致的三角雷达二级角度修正 helper。
- [x] 实现 raw angle 反推：`raw_angle = ideal_angle - correction(distance)`。
- [x] 实现 checksum 编码。
- [x] 实现每包最多 `80` 点的 packet split。

### 验收

- [x] 单测验证 `PH/CT/LSN/FSA/LSA/CS/Si` 字节布局。
- [x] 单测验证 checksum 与厂商协议公式一致。
- [x] 单测验证编码距离能按 SDK 逻辑还原为米。
- [x] 单测验证 SDK 修正后的角度接近输入 ideal angle。

## P1.5：Gazebo/sensor 归属整理

目标：把 X2 仿真明确收口为 Gazebo/sensor runtime 的能力，避免 companion、
SLAM 或 SITL 镜像感知厂商协议和传感器内部实现。

### 任务

- [x] 新增 X2 专属代码目录：`navlab/sim/gazebo_sensor/x2/`。
- [x] 将早期协议 encoder 迁移或封装为
  `navlab/sim/gazebo_sensor/x2/protocol.py`。
- [x] 在 `navlab/sim/gazebo_sensor/x2/` 内保留后续 emulator、runtime、CLI 和配置读取代码。
- [x] 新增 Gazebo/sensor 镜像专用 dependency 定义，包含 `ydlidar_ros2_driver`、
  `YDLidar-SDK`、ROS 2 driver 运行依赖和 PTY/emulator 所需 Python 依赖。
- [x] 确保 companion、SLAM、SITL 镜像不安装 X2 vendor driver 或 X2 emulator 依赖。
- [x] X2 runtime 只通过 ROS topic 暴露 `/scan`、`/scan_ideal`、`/sim/x2/status`。
- [x] 配置继续从 `navlab/config.toml` 的 `[gazebo_sensor.x2_protocol]` 读取，只由 Gazebo/sensor runtime 使用。

### 验收

- [x] `navlab/sim/gazebo_sensor/x2/` 是 X2 协议仿真的唯一代码归属。
- [x] Gazebo/sensor 镜像内能 import X2 protocol/runtime 模块。
- [x] companion 和 SLAM 镜像不需要 import X2 模块也能启动。
- [x] `docker compose config` 中 X2 相关环境变量或挂载只出现在 Gazebo/sensor 服务。
- [x] 文档明确其他镜像只消费 `/scan`，不感知虚拟串口或厂商协议。

## P2：虚拟串口 emulator

目标：提供一个看起来像 X2 串口设备的虚拟路径。

### 任务

- [x] 新增 `navlab/sim/gazebo_sensor/x2/emulator.py`。
- [x] 新增 Gazebo/sensor runtime CLI：`navlab/sim/gazebo_sensor/cli.py`。
- [x] 创建 PTY，并把 `/tmp/navlab_x2` symlink 到 slave path。
- [x] 从 PTY master 写入生成的 X2 packets。
- [x] 从 PTY master 读取厂商 driver 发来的命令字节。
- [x] 收到 `0x60` scan command 后开始写入点云包。
- [x] 收到 `0x61` force scan command 后开始写入点云包。
- [x] 收到 `0x65` stop command 后停止写入点云包。
- [x] 收到 `0x80` reset command 后短暂停止并回到 idle。
- [x] 在 `/sim/x2/status` 发布 emulator 状态。

### 验收

- [x] 启动 emulator 后会创建 `/tmp/navlab_x2`。
- [x] emulator 只在 Gazebo/sensor 容器内启动。
- [x] 字节消费者能从虚拟串口读到合法 X2 packets。
- [x] 发送 stop / scan 命令会改变 emulator 状态。
- [x] 状态中包含 source、frequency、sample rate、packet count、byte count。

## P3：厂商 driver smoke

目标：证明真实厂商 ROS 2 driver 能消费虚拟串口。

### 任务

- [x] 增加 Gazebo/sensor CLI 入口，用 synthetic static ranges 启动 emulator。
- [x] 在同一个 Gazebo/sensor 容器内启动 `ydlidar_ros2_driver_node` 并连接 `/tmp/navlab_x2`。
- [x] 确保 Gazebo/sensor 镜像中包含 `ydlidar_ros2_driver`。
- [x] 确保 companion、SLAM、SITL 镜像不包含或不依赖 `ydlidar_ros2_driver`。
- [x] 确保 driver 可以加载 `docker/profiles/x2-vendor-sim.yaml`。
- [x] 录制一个包含 `/scan` 和 `/sim/x2/status` 的小 rosbag。

### 验收

- [x] `ros2 topic list` 能看到 `/scan`。
- [x] `ros2 topic hz /scan` 至少 10 秒内非零且稳定。
- [x] `/scan.header.frame_id == "laser_frame"`。
- [x] `/scan.range_min == 0.1`。
- [x] `/scan.range_max == 8.0`。
- [x] `/scan` publisher 是 `ydlidar_ros2_driver_node`。
- [x] emulator 不发布 `/scan`。
- [x] companion/SLAM 容器只通过 ROS graph 看到 `/scan`，看不到 `/tmp/navlab_x2`。

## P4：接入 Gazebo ideal scan

目标：把 Gazebo ray data 转为 X2 串口字节，而不是直接作为 `/scan` 使用。

### 任务

- [x] 协议模式下把 Gazebo lidar topic 从 `/scan` 改成 `/scan_ideal`。
- [x] bridge `/scan_ideal` 为 `sensor_msgs/msg/LaserScan`。
- [x] 让 Gazebo/sensor 容器内的 `x2_serial_emulator` 订阅 `/scan_ideal`。
- [x] 将 ideal rays 插值到 `round(3000 / frequency)` 点/圈。
- [x] 按 `0.1-8.0 m` clamp ranges。
- [x] 无效 range 或丢点用 `0` 编码。
- [x] 加入可配置距离噪声和丢点模型。
- [x] rosbag 中保留 `/scan_ideal` 作为调试 topic。

### 验收

- [x] `/scan_ideal` 存在，并由 Gazebo/bridge 发布。
- [x] `/scan` 存在，并由 Gazebo/sensor 容器内的厂商 driver 发布。
- [x] UAV/lidar 在 Gazebo 中移动时，`/scan` 会变化。
- [ ] `/scan_features.front_min` 基于厂商 driver `/scan` 变化。
- [x] Foxglove 可同时查看 `/scan_ideal` 和 `/scan`。

最新证据：

- artifact：`artifacts/ros/navlab_companion_sitl_gazebo/20260604_143533/summary.json`
- `scan_source == "x2_virtual_serial_vendor_driver"`
- `/scan` message count：`810`
- `/scan_ideal` message count：`1156`
- `/sim/x2/status` message count：`231`
- `/scan` publisher：`ydlidar_ros2_driver_node`
- MCAP 抽样显示 `/scan` 最近有效距离从 `4.951m` 变化到 `2.951m`
- 注意：该旧包中的 `/scan_features.front_min` 采样为 `NaN`，需要用已修正 scan 方向后的新 acceptance 包复验。

## P5：NavLab/Gazebo runtime 集成

目标：让协议级 X2 成为严肃仿真的默认 scan 路径，同时保持传感器协议层只属于
Gazebo/sensor runtime。

### 任务

- [x] 增加 runtime 配置：`scan_source = gazebo_ideal | x2_virtual_serial`。
- [x] 协议模式启用时，从 Gazebo/sensor runtime 启动 `x2_serial_emulator`。
- [x] 从 Gazebo/sensor runtime 启动 `ydlidar_ros2_driver_node`。
- [x] NavLab orchestration 只负责选择是否启用 Gazebo/sensor X2 runtime，不直接启动 X2 节点。
- [x] 更新 rosbag profile，加入 `/scan_ideal` 和 `/sim/x2/status`。
- [x] 更新 acceptance summary，报告 scan source 和 `/scan` publisher。
- [x] 确保 SLAM 消费最终 `/scan`，不是 `/scan_ideal`。
- [x] 确保 mission 和 `/scan_features` 消费最终 `/scan`，不是 `/scan_ideal`。

### 验收

- [x] NavLab acceptance summary 中有 `scan_source = "x2_virtual_serial_vendor_driver"`。
- [x] Rosbag 包含 `/scan`、`/scan_ideal`、`/sim/x2/status` 和 `/scan_features`。
- [x] `/scan` publisher 是厂商 driver。
- [x] `/scan_features` message count 非零。
- [x] mission rosbag replay 显示任务使用厂商 driver `/scan` 完成。
- [ ] acceptance summary 证明 companion、SLAM、SITL 镜像没有 X2 vendor dependency。

最新证据：

- `rosbag_profile_summary.json` 中 `/scan_features` message count：`810`
- `summary.json` 中 `mission_consumes_final_scan == true`
- `summary.json` 中 `scan_features_consumes_final_scan == true`
- `summary.json` 中 `slam_consumes_final_scan == true`
- `summary.json` 中 `lidar_chain.x2_is_internal_to_sensor_runtime == true`

## P6：保真度标定

目标：协议链路跑通后，再提高 X2 物理特性逼真度。

### 任务

- [x] 在厂商支持的 `4-8 Hz` 范围内加入 scan-frequency jitter。
- [x] 加入距离相关噪声。
- [ ] 加入 invalid range、暗表面、高入射角等丢点规则。
- [ ] 在 Gazebo world markers 中加入可选材质标签，辅助 dropout 调参。
- [ ] 增加 `/scan_ideal` 和最终 `/scan` 的差异指标。
- [ ] 如果有真实 X2 rosbag，加入标定 fixture。

### 验收

- [x] 固定 seed 下噪声和丢点可复现。
- [ ] summary 中包含 mean range error、dropout rate、sample count。
- [ ] 标定配置写入 summary JSON 和 rosbag metadata。

## P7：可选完整命令响应

目标：如果 single-channel 最小仿真不够，再支持更完整的 SDK 命令流。

### 任务

- [ ] 实现 `LIDAR_CMD_GET_DEVICE_HEALTH` 响应。
- [ ] 实现 `LIDAR_CMD_GET_DEVICE_INFO` 响应。
- [ ] 如有必要，在 CT stream 中注入 module device-info packet。
- [ ] 增加 `isSingleChannel: false` 初始化路径测试。

### 验收

- [ ] driver 在显式 health/device-info 命令流下初始化成功。
- [ ] SDK 日志能报告预期型号信息。

## 最终完成标准

- [x] 仿真最终 `/scan` 由 `ydlidar_ros2_driver_node` 发布。
- [x] Gazebo ideal 输出分离为 `/scan_ideal`。
- [x] 虚拟串口 emulator 生成合法 X2 三角协议 packets。
- [x] X2 emulator 和 vendor driver 只在 Gazebo/sensor 镜像内运行。
- [x] companion、SLAM、SITL 只消费最终 `/scan`，不感知 `/tmp/navlab_x2` 或 X2 协议实现。
- [ ] NavLab rosbag 能回放 `/scan_ideal -> X2 emulator -> vendor /scan -> /scan_features -> mission`。
- [x] Foxglove notes 解释如何同时查看 ideal scan 和最终 vendor scan。
