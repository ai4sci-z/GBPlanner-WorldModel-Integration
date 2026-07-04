# X2 激光雷达协议级仿真设计

这份文档定义 NavLab 如何在 Gazebo 中模拟 YDLidar X2，同时让最终 `/scan`
尽量接近真实硬件链路。

目标不是“发布一个数值看起来合理的 `sensor_msgs/msg/LaserScan`”，而是：

```text
Gazebo 世界几何
  -> 理想 ray range
  -> YDLidar X2 三角测距协议字节流
  -> 虚拟串口
  -> 厂商 ydlidar_ros2_driver_node
  -> /scan
```

最终 `/scan` 必须由厂商 ROS 2 driver 发布。仿真器的职责是模拟 X2 串口原始
字节流，让厂商 SDK 正常完成协议解析、二级角度修正、过滤和 `LaserScan` 转换。

## 事实来源

判断优先级：源码 > 厂商文档 > 本地配置。

| 来源 | 用途 |
| --- | --- |
| `third_party/YDLidar-SDK/src/YDlidarDriver.cpp` | 三角协议包解析、距离缩放、二级角度修正 |
| `third_party/YDLidar-SDK/src/CYdLidar.cpp` | SDK scan 处理、范围过滤、固定点数逻辑、scan timing |
| `third_party/YDLidar-SDK/core/common/ydlidar_protocol.h` | 数据包结构、协议常量、node 表示 |
| `third_party/YDLidar-SDK/doc/Dataset.md` | 厂商 X2/X2L/X2N 型号表 |
| `third_party/ydlidar_ros2_driver/src/ydlidar_ros2_driver_node.cpp` | ROS 2 driver 参数和 `/scan` 发布逻辑 |
| `third_party/ydlidar_ros2_driver/params/X2.yaml` | 本地配置形状；与厂商型号表冲突时不作为仿真基准 |

## X2 厂商基准

协议级仿真应按厂商 SDK Dataset，而不是当前本地 `X2.yaml` 中冲突的默认值。

| 字段 | 值 | 依据 |
| --- | --- | --- |
| 型号族 | X2/X2L/X2N | 厂商 SDK Dataset |
| model code | `6` | 厂商 SDK Dataset；SDK 中与 X4 型号族共享编号 |
| lidar type | `TYPE_TRIANGLE` / `1` | 厂商 SDK 文档和本地 X2 profile |
| baudrate | `115200` | 厂商 SDK Dataset |
| sample rate | `3 KHz` | 厂商 SDK Dataset 和本地 X2 profile |
| scan frequency | `4-8 Hz PWM` | 厂商 SDK Dataset |
| 默认仿真频率 | `7 Hz` | 在厂商范围内选一个稳定默认值 |
| range | `0.10-8.0 m` | 厂商 SDK Dataset |
| single channel | `true` | 厂商 SDK Dataset 和本地 X2 profile |
| intensity | `false` | 厂商 SDK Dataset 和本地 X2 profile |
| support motor DTR | `true` | 厂商 SDK API table |

当前本地 `X2.yaml` 写了 `frequency: 10.0` 和 `range_max: 12.0`。这两个值不符合
厂商 X2/X2L/X2N 表，因此不能作为协议仿真的基准。仿真 launch profile 应使用
`4-8 Hz` 范围内的频率和 `range_max: 8.0`。

## 为什么做协议级仿真

可选仿真深度有三种：

| 方案 | 最终 `/scan` 发布者 | 保真度 | 结论 |
| --- | --- | --- | --- |
| 只用 Gazebo `/scan` | `ros_gz_bridge` | 只保证消息结构 | 不够 |
| Gazebo ray + 直接后处理 `/scan` | 自定义 sim node | 能验证数学模型 | 不是最终目标 |
| Gazebo ray + X2 串口协议包 + 厂商 driver | `ydlidar_ros2_driver_node` | 最接近真实软件链路 | 必须做 |

写 Gazebo plugin 读取 `RaySensor` 不是关键。`RaySensor` 给出的仍然是理想几何
距离。真正能提升保真度的是：让厂商 SDK 解码一条符合 X2 三角协议的字节流。

## 运行时架构

```text
Gazebo container
  gpu_lidar
  topic: /scan_ideal
  type: gz.msgs.LaserScan
        |
        v
Gazebo/sensor container
  ros_gz_bridge
  topic: /scan_ideal
  type: sensor_msgs/msg/LaserScan
        |
        v
Gazebo/sensor container
  x2_serial_emulator
  订阅: /scan_ideal
  创建: /tmp/navlab_x2 -> /dev/pts/N
  写入: YDLidar 三角协议包
        |
        v
Gazebo/sensor container
  ydlidar_ros2_driver_node
  port: /tmp/navlab_x2
  params: 修正后的 X2 厂商 profile
  发布: /scan
        |
        v
scan_features_publisher、SLAM、NavLab mission、rosbag、Foxglove
```

协议仿真模式下，Gazebo 直出的 scan topic 不能再叫 `/scan`。它应叫
`/scan_ideal`，最终 `/scan` 只留给厂商 driver 输出。

X2 协议层只属于 Gazebo/sensor runtime。companion、SLAM、SITL 不安装
YDLidar SDK、`ydlidar_ros2_driver` 或虚拟串口 emulator；它们只通过 ROS graph
消费最终 `/scan`。

## 协议模型

X2 使用无 intensity 字节的三角协议。每个数据包格式为：

```text
PH   2 bytes  固定 0x55AA，线缆字节序为 AA 55
CT   1 byte   packet type 和 scan frequency
LSN  1 byte   本包采样点数量
FSA  2 bytes  第一个采样点角度
LSA  2 bytes  最后一个采样点角度
CS   2 bytes  校验和
Si   2 bytes  距离采样，重复 LSN 次
```

仿真器应这样编码，让 SDK 能按原逻辑解码：

```text
CT = int(scan_frequency_hz * 10) << 1
第一包 CT 低位置 1，作为 zero/ring-start 标记
LSN = 本包采样点数量
FSA = (int(first_raw_angle_deg * 64) << 1) | 0x01
LSA = (int(last_raw_angle_deg * 64) << 1) | 0x01
Si = int(range_m * 4000)
```

校验和：

```text
CS = PH ^ FSA ^ S1 ^ S2 ... ^ Sn ^ ((LSN << 8) | CT) ^ LSA
```

SDK 会在 `YDlidarDriver::parsePoints()` 中执行三角雷达二级角度修正：

```text
ca = atan(((21.8 * (155.3 - (d / 4.0))) / 155.3) / (d / 4.0)) * 180 / pi
a = a_raw + ca
range_m = d / 4000.0
```

因为 SDK 会自动加上 `ca`，仿真器从 Gazebo 理想角度生成 raw packet angle 时要反推：

```text
raw_angle_deg = ideal_angle_deg - ca(distance_raw)
```

这样厂商 driver 输出 `/scan` 后，角度会尽量回到 Gazebo 理想几何角度。

注意：SDK 在读取包头时会检查 `FSA/LSA` 低位 check bit。如果角度字段低位为 `0`，
包会被丢弃。SDK 也只有在收到 zero/ring-start 包时才会触发一圈数据解析，因此每圈
第一包的 `CT` 低位必须置 `1`。

## 虚拟串口行为

仿真器使用 pseudo terminal：

```text
master_fd, slave_fd = pty.openpty()
slave_path = os.ttyname(slave_fd)
symlink /tmp/navlab_x2 -> slave_path
```

厂商 driver 以 `115200` baud 连接 `/tmp/navlab_x2`。仿真器保持 master 端打开，
并按配置频率写入 X2 协议包。

### 命令处理

X2 是 single-channel。按当前 SDK 源码：

- `getHealth()` 在 `m_SingleChannel=true` 时本地返回成功。
- `getDeviceInfo()` 若没有观测到模组信息，会返回 fallback。
- `startScan()` 仍会发送 `LIDAR_CMD_SCAN`。

因此第一版仿真器至少要从 PTY master 读取命令字节，并处理：

| 命令 | 字节 | 行为 |
| --- | --- | --- |
| stop | `0x65` | 停止写入点云包 |
| scan | `0x60` | 开始写入点云包 |
| force scan | `0x61` | 开始写入点云包 |
| reset | `0x80` | 短暂停止，然后回到 idle |

如果后续要支持非 single-channel 或更严格 SDK 初始化，再补 health/device-info 响应。

## 采样和时序

按厂商 X2 基准：

```text
sample_rate = 3000 samples/sec
scan_frequency = 默认 7 Hz，可配置在 4-8 Hz
samples_per_scan = round(sample_rate / scan_frequency)
```

所以：

- `7 Hz` 时约 `429` 点/圈
- `8 Hz` 时约 `375` 点/圈
- `4 Hz` 时约 `750` 点/圈

因此不能硬编码 `361` 点。`361` 只描述当前 Gazebo ideal sensor 的采样配置，
不是 X2 协议仿真的真实点数。

三角协议单包最大点数：

```text
TRI_PACKMAXNODES = 80
```

每一圈流程：

1. 将 `/scan_ideal` 插值或重采样到 `samples_per_scan` 个 raw samples。
2. 在 raw X2 angle 和 Gazebo/ROS ideal angle 之间补偿厂商 driver 的 180 度输出偏置，
   保证最终 `/scan` 中 `0 deg` 是雷达/无人机正前方。
3. 在编码前应用可选噪声、丢点、材质规则。
4. 按每包最多 `80` 点拆包。
5. 编码 `FSA`、`LSA`、`LSN`、`CT`、`Si`、`CS`。
6. 把 packet bytes 写入 PTY。

第一版可以按每圈 burst 写包。后续再做更接近 `115200` baud 的 byte pacing。

## Gazebo 配置

协议仿真模式下：

```xml
<sensor name="scan_ideal" type="gpu_lidar">
  <topic>/scan_ideal</topic>
  <update_rate>10</update_rate>
  ...
</sensor>
```

Gazebo ideal ray 的采样数可以保持较高，方便几何插值。最终 X2 点数和时序由
`x2_serial_emulator` 决定。Gazebo 的 range bounds 可以比 X2 宽，但 emulator
必须按 X2 厂商范围进行 clamp 或置 0。

## 修正后的厂商 driver profile

新增仿真专用 profile，不直接修改 third-party 文件：

```text
docker/profiles/x2-vendor-sim.yaml
```

建议内容：

```yaml
ydlidar_ros2_driver_node:
  ros__parameters:
    port: /tmp/navlab_x2
    frame_id: laser_frame
    ignore_array: ""
    baudrate: 115200
    lidar_type: 1
    device_type: 0
    sample_rate: 3
    abnormal_check_count: 4
    fixed_resolution: true
    reversion: true
    inverted: true
    auto_reconnect: true
    isSingleChannel: true
    intensity: false
    support_motor_dtr: true
    angle_max: 180.0
    angle_min: -180.0
    range_max: 8.0
    range_min: 0.1
    frequency: 7.0
    invalid_range_is_inf: false
```

注意：当前厂商 ROS 2 wrapper 读取了 `invalid_range_is_inf`，但源码里没有看到它在
填充 `scan_msg.ranges` 时被使用。实际输出里，SDK 过滤后的无效点更可能是 `0.0`。

## Rosbag 和 Foxglove 合约

需要同时记录 ideal 输出和厂商 driver 输出：

| Topic | 是否必须 | 用途 |
| --- | --- | --- |
| `/scan` | 必须 | 厂商 driver 输出的最终 scan |
| `/scan_ideal` | 推荐 | 和 Gazebo 几何做对比 |
| `/scan_features` | 必须 | 下游避障行为 |
| `/scan_nearest_point` | 必须 | 最近点回放和调试 |
| `/navlab/mission/status` | NavLab 必须 | 任务回放 |
| `/odom` | SLAM 必须 | 定位回放 |
| `/external_nav/odom` | SITL feedback 必须 | ExternalNav 回放 |

验收必须确认 `/scan` 存在，并且 publisher 是厂商 driver，而不是 emulator。

## 验收 Gate

### 协议单测 Gate

- 编码包包含正确的 `PH`、`CT`、`LSN`、`FSA`、`LSA`、`CS`、`Si`。
- SDK-equivalent decode 能还原距离。
- SDK-equivalent angle correction 后角度接近 Gazebo ideal angle。

### 虚拟串口 Gate

- emulator 创建 `/tmp/navlab_x2`。
- 厂商 driver 能打开虚拟串口。
- 厂商 driver 发布 `/scan`。
- `/scan` 至少 10 秒内有稳定消息计数。

### Gazebo 集成 Gate

- Gazebo 发布 `/scan_ideal`。
- emulator 消费 `/scan_ideal` 并写 X2 packets。
- 厂商 driver 发布 `/scan`。
- UAV/lidar 移动时，`/scan_features.front_min` 随之变化。

### NavLab Gate

- NavLab acceptance 记录 `/scan`、`/scan_ideal`、`/scan_features`、mission、
  localization 和 ExternalNav topics。
- Foxglove 回放能看到任务使用厂商 driver `/scan` 完成。
- `summary.json` 明确报告 scan source 为
  `x2_virtual_serial_vendor_driver`。

## 不做什么

- 最终链路中，emulator 不直接发布 `/scan`。
- 不修改 third-party SDK 或 driver，除非虚拟串口兼容性被证明无法绕过。
- 第一版不写 Gazebo plugin。
- 不模拟 USB 权限、udev、真实电机供电等物理问题。

## 未决问题

- 是否需要在 CT stream 中额外发模组 device-info packet，让 SDK 明确识别 X2/X2L。
- 是否需要严格按 `115200` baud 做 byte pacing，还是每圈 burst 写包就足够稳定。
- 默认 `frequency` 是固定 `7 Hz`，还是每次 acceptance 在 `4-8 Hz` 范围内抖动。
