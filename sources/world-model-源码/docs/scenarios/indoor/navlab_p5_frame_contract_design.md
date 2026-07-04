# P5 Frame contract 自动验收设计

## 1. 目标

P5 的目标是在 P0-P4 已经建立官方 ArduPilot ROS2/Gazebo、X2 雷达、rangefinder/IMU、SLAM backend 和 FCU controller 基础上，把 frame 和坐标转换从“靠 Foxglove 里看起来差不多”收敛成可自动验收的契约。

P5 只回答：

> 当前系统的 ROS frame、MAVLink/ArduPilot frame、Gazebo world 诊断、scan 方向、yaw 正方向和各传感器安装 frame 是否一致，是否足以进入 P6 真实 SLAM hover gate。

P5 不回答 hover 是否稳定。这属于 P6。P5 也不做 forward/avoid/exploration，这些属于 P7/P8。

## 2. 为什么 P5 必须单独做

P4 已经证明唯一 controller 可以让 FCU 进入 GUIDED、arm、takeoff，并通过 `/ap/v1/cmd_vel` 输出 movement setpoint。但如果 frame contract 错了，后续 P6/P7 会出现很难定位的问题：

- Foxglove 里无人机和墙体看起来都在动；
- scan 方向和机头方向相反；
- `map -> odom -> base_link` 缺失或断开；
- `laser_frame`、`imu_link`、`rangefinder_down_frame` 没有挂到同一棵 TF tree；
- MAVLink NED 和 ROS ENU 转换符号反了；
- body FRD 和 ROS FLU 混用；
- yaw 正方向和 LaserScan 角度正方向不一致；
- SLAM `/odom`、FCU local position、Gazebo truth 诊断在同一个动作上方向相反；
- 后续 hover drift 看似是 SLAM 或控制问题，实际是 frame 错误。

P5 的意义是把“坐标系是否可信”提前验收。P5 通过后，P6 才能把 SLAM `/odom` 接进 ExternalNav hover gate，否则 P6 的漂移和发散没有诊断意义。

## 3. P5 范围

### 3.1 包含

P5 包含：

- 继续使用官方 `iris_maze` bringup 和官方 Iris 模型。
- 继续使用 P1 的 X2 `/scan` 链路。
- 继续使用 P2 的 down rangefinder 和 IMU 机制。
- 继续使用 P3 的 SLAM backend 输出 `/slam/odom`。
- 继续使用 P4 的唯一 FCU controller 和 `/ap/v1/cmd_vel` 输出通道。
- 固化 ROS frame contract：
  - `map`
  - `odom`
  - `base_link`
  - `imu_link`
  - `base_scan` 或 `laser_frame`
  - `rangefinder_down_frame`
- 固化 MAVLink/ArduPilot 到 ROS 的转换检查：
  - NED 到 ENU；
  - body FRD 到 ROS FLU；
  - yaw 正方向；
  - down rangefinder 方向。
- 自动检查 TF 连通性、parent 唯一、无循环、transform 年龄和 quaternion 合法性。
- 自动检查 `/scan` 角度方向、frame_id、有效距离比例和与固定墙体的几何一致性。
- 自动检查 FCU pose、SLAM `/odom`、Gazebo truth 诊断在同一个受控动作上的方向一致性。
- summary 记录 frame contract、检查结果、误差、blocker 和 artifact。
- rosbag 记录 P5 必需 topic，保证 Foxglove 可回放。

### 3.2 不包含

P5 不包含：

- 不替换 NavLab 8 字形 world。
- 不替换 NavLab 自定义机体模型。
- 不完成 P6 SLAM hover gate。
- 不要求 ExternalNav 已经进入 EKF。
- 不要求 hover drift 达到最终阈值。
- 不做 forward/back/yaw scan/avoid/exploration 任务。
- 不允许为了验证 frame 而 direct set pose。
- 不允许把 Gazebo truth 作为控制、规划或 ExternalNav 输入。

## 4. 目标架构

P5 目标架构是：

```text
official Gazebo/SITL baseline
  -> X2 scan + IMU + rangefinder
  -> SLAM backend /slam/odom
  -> FCU state + /ap/v1/pose/filtered + /ap/v1/twist/filtered
  -> Gazebo truth diagnostic only
  -> P5 frame probe
  -> TF graph validation
  -> scan geometry validation
  -> direction consistency validation
  -> artifact summary + rosbag
```

P5 probe 只能做诊断。它不能发布 movement setpoint，不能调用 Gazebo pose service，也不能把 Gazebo truth 转成控制输入。

## 5. Frame contract

### 5.1 ROS world frames

P5 采用 ROS 常规 ENU 口径：

```text
map:   固定世界/SLAM map frame
odom:  连续局部 odometry frame
base_link: 机体 ROS body frame，X 前、Y 左、Z 上
```

目标 TF 链：

```text
map
  -> odom
    -> base_link
      -> imu_link
      -> base_scan
      -> rangefinder_down_frame
```

如果当前官方 baseline 只提供部分 TF，P5 acceptance 必须明确记录缺失项，并且不能把缺失 frame 的检查误标为通过。

### 5.2 MAVLink / ArduPilot frames

ArduPilot 和 MAVLink 常见 local frame 是 NED：

```text
NED X: North / forward world axis
NED Y: East / right world axis
NED Z: Down
```

ROS ENU 常见 world frame 是：

```text
ENU X: East
ENU Y: North
ENU Z: Up
```

P5 必须显式检查 NED/ENU 转换，而不是只检查 topic 存在。转换方向建议记录为：

```text
ros_x = ned_y
ros_y = ned_x
ros_z = -ned_z
```

如果实际 `/ap/v1/pose/filtered` 已由官方 ArduPilot ROS2 层输出 ROS-compatible frame，P5 summary 必须记录它的观测结果和来源，不能重复转换。

### 5.3 Body frames

ArduPilot body frame 常见口径是 FRD：

```text
FRD X: forward
FRD Y: right
FRD Z: down
```

ROS `base_link` 采用 FLU：

```text
FLU X: forward
FLU Y: left
FLU Z: up
```

P5 必须检查 body frame 转换符号：

```text
ros_body_x = fcu_body_x
ros_body_y = -fcu_body_y
ros_body_z = -fcu_body_z
```

## 6. 服务职责

### 6.1 Orchestration

负责：

- 提供 P5 doctor / acceptance task。
- 启动 P0-P4 已验证的 baseline、sensor、SLAM 和 controller。
- 启动 P5 frame probe。
- 生成 P5 runtime config。
- 收集 summary、rosbag profile、TF graph、topic list、日志和 Foxglove notes。

不负责：

- 发布运动 setpoint。
- 修改 TF 内容来让检查通过。
- 使用 Gazebo truth 作为控制输入。

### 6.2 Frame probe

负责：

- 读取 `/tf` 和 `/tf_static`。
- 构建 TF graph。
- 检查 frame parent 唯一、无循环、连通性和 transform 年龄。
- 检查 quaternion norm。
- 读取 `/scan`，验证 `header.frame_id`、角度方向、有效 range 和最近障碍方向。
- 读取 `/ap/v1/pose/filtered`、`/ap/v1/twist/filtered`、`/slam/odom`、Gazebo truth 诊断，比较方向一致性。
- 输出 `/navlab/frame_contract/status`。

不负责：

- 发布或修改 TF。
- 发布 `/scan`。
- 发布 FCU setpoint。
- 直接调用 Gazebo。

### 6.3 SLAM backend

负责：

- 输出 `/slam/odom`。
- 输出 `map -> odom` 或等价 TF。
- 保持 frame_id 和 child_frame_id 与 P5 contract 一致。

不负责：

- 用 Gazebo truth 修正 odom。
- 伪造 TF 来绕过 P5。

### 6.4 Gazebo truth diagnostic

负责：

- 只作为诊断对照。
- 提供机体在 Gazebo world 中的位置、姿态、速度或轨迹。

不负责：

- 进入 SLAM 输入。
- 进入 ExternalNav 输入。
- 进入 controller 规划或控制输入。

## 7. 检查项目

### 7.1 TF graph 检查

P5 必须检查：

- required frames 存在。
- `map -> odom -> base_link` 连通。
- `base_link -> imu_link` 连通。
- `base_link -> base_scan` 或 `base_link -> laser_frame` 连通。
- `base_link -> rangefinder_down_frame` 连通。
- 每个 child frame 只有一个 parent。
- TF graph 无循环。
- dynamic transform 最新年龄小于阈值。
- static transform quaternion norm 接近 1。

### 7.2 Scan 检查

P5 必须检查：

- `/scan.header.frame_id` 是 `base_scan` 或配置允许的 laser frame。
- LaserScan `angle_min < angle_max`。
- LaserScan `angle_increment` 符号与角度范围一致。
- `ranges` 有足够有效点。
- 最近障碍方向与当前机头方向和 world 几何一致。
- scan 不需要在 Foxglove 中手动旋转 180 度才能对齐。

如果 scan 方向和前进方向相反，P5 必须 blocked，并记录：

```json
{
  "blocker": "scan forward direction does not match base_link +X"
}
```

### 7.3 IMU 和 rangefinder 检查

P5 必须检查：

- `/imu.header.frame_id == imu_link` 或配置允许值。
- IMU frequency 大于阈值。
- `imu_link` 挂到 `base_link`。
- `/rangefinder/down/range.header.frame_id == rangefinder_down_frame`。
- rangefinder frame 的测距方向向下。
- rangefinder 读数与 Gazebo truth 高度诊断在阈值内一致。

### 7.4 方向一致性检查

P5 应使用一个很小的受控诊断窗口，而不是探索任务：

```text
takeoff/hold ready
  -> optional tiny forward intent
  -> optional tiny yaw intent
  -> final hold
```

这些 intent 必须经过 P4 controller，不能绕过唯一 setpoint owner。

检查内容：

- FCU pose 观察到的 forward 方向与 `base_link +X` 一致。
- SLAM `/slam/odom` 的相对位移方向与 FCU pose 一致。
- Gazebo truth 诊断方向与 FCU pose 一致。
- yaw 正方向与 TF 和 scan 角度方向一致。

如果 P5 不执行 movement，只能完成静态 frame contract；summary 必须写：

```json
{
  "direction_motion_claim": "not_evaluated"
}
```

## 8. Topic 和接口要求

P5 required topics：

```text
/tf
/tf_static
/ap/v1/time
/ap/v1/pose/filtered
/ap/v1/twist/filtered
/ap/v1/status
/ap/v1/cmd_vel
/scan
/imu
/rangefinder/down/range
/rangefinder/down/status
/slam/odom
/navlab/slam/status
/navlab/fcu/state
/navlab/fcu/controller/status
/navlab/fcu/setpoint/output
/navlab/fcu/owner/status
/navlab/frame_contract/status
```

P5 optional diagnostic topics：

```text
/clock
/map
/submap_list
/trajectory_node_list
/odometry
/external_nav/status
/navlab/x2/vendor_scan
/sim/x2/status
```

## 9. Summary 字段

P5 summary 建议：

```json
{
  "ok": false,
  "blocked": true,
  "blockers": [],
  "p5_frame_contract": {
    "claim": "frame_contract_evaluated",
    "tf": {
      "ok": false,
      "required_frames": [],
      "missing_frames": [],
      "parent_conflicts": [],
      "cycles": [],
      "latest_dynamic_age_sec": null
    },
    "scan": {
      "ok": false,
      "topic": "/scan",
      "frame_id": "base_scan",
      "forward_matches_base_link_x": false,
      "valid_range_ratio": null
    },
    "imu": {
      "ok": false,
      "frame_id": "imu_link",
      "rate_hz": null
    },
    "rangefinder": {
      "ok": false,
      "frame_id": "rangefinder_down_frame",
      "height_error_m": null
    },
    "direction_consistency": {
      "ok": false,
      "fcu_vs_slam_direction_match": null,
      "fcu_vs_truth_direction_match": null,
      "yaw_direction_match": null
    },
    "claims": {
      "hover_claim": "not_evaluated",
      "exploration_claim": "not_evaluated",
      "gazebo_truth_control_claim": false
    }
  },
  "rosbag_profile": {}
}
```

## 10. Rosbag 和 Foxglove

P5 rosbag 必须能让 Foxglove 回放 frame contract，而不是只保存最终结论。

Foxglove 回放口径：

- 3D 固定参考系优先使用 `map`。
- 如果 `map -> odom` 尚未稳定，P5 summary 必须记录原因，不应让用户靠切换 fixed frame 猜。
- 3D 面板显示 TF、`/scan`、FCU pose、SLAM `/slam/odom` 和 Gazebo truth diagnostic。
- Raw Messages 面板查看 `/navlab/frame_contract/status`。
- Plot 面板查看 TF age、rangefinder height error、scan nearest direction 和 direction consistency。
- P5 bag 不能被解释为 hover 完成 bag。

## 11. Acceptance 语义

P5 acceptance 必须通过以下条件：

- P0 official baseline healthy。
- P1 X2 `/scan` gate 不被破坏。
- P2 rangefinder/IMU gate 不被破坏。
- P3 SLAM backend `/slam/odom` 可用。
- P4 FCU controller 和唯一 owner 不被破坏。
- TF graph 连通且无 parent conflict。
- scan frame 和 scan 方向正确。
- IMU/rangefinder frame 正确。
- Gazebo truth 只作为诊断，不进入控制输入。
- rosbag required topics 全部有数据。

P5 blocked 条件：

- required frame 缺失。
- TF graph 有循环。
- child frame 有多个 parent。
- `base_link`、`imu_link`、laser frame 或 `rangefinder_down_frame` 不连通。
- `/scan` frame 不在 TF tree 中。
- `/scan` 前向方向与 `base_link +X` 不一致。
- rangefinder 方向不是向下。
- FCU pose、SLAM odom、Gazebo truth 诊断方向明显相反。
- direct set pose 出现。
- movement output 有多个 owner。

## 12. 推荐命令

建议命名：

```text
uv run --project orchestration python orchestration/main.py frame-contract-doctor
uv run --project orchestration python orchestration/main.py frame-contract-acceptance 90
```

doctor 只检查：

- 配置；
- required topics / frames 的预期 contract；
- runtime image 和依赖；
- rosbag profile；
- P0-P4 前置配置是否存在。

acceptance 才启动完整运行链路并输出 rosbag/summary。

## 13. P5 完成后才能进入什么

P5 完成后，可以进入：

- P6 真实 SLAM hover gate；
- P7 官方 maze 小范围运动 gate。

P5 未完成时，不应进入：

- P6 hover completion；
- P7 forward/back/yaw scan；
- P8 探索任务。

原因是后续所有任务都依赖同一套 frame contract。如果 frame 错了，任何 hover drift、避障方向和探索覆盖率都不可信。
