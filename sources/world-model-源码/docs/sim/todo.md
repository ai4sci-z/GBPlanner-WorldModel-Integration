# 仿真 TODO

这份清单只覆盖当前仿真主线，并明确区分：

- 已经做完、可以打勾验收的部分
- 还没做完、后续要继续推进的部分

当前主线已经不是旧版的固定原点探针方案，而是：

- Gazebo 中的可移动 `uav_start_marker` 挂载真实 lidar
- 原始 `/scan` 会跟着 UAV 一起运动
- 旧通用仿真 runtime 从 `/scan` 发布 `/scan_features`
- `/planner/cmd_vel` 由执行器消费
- 执行器内部额外保证 `front_min ~= 0.5 m` 时不再继续前进

## 当前状态总览

### 已完成

- [x] 默认世界固定为 `docker/worlds/uav_obstacle_5m.sdf`
- [x] 前方 `5 m` 障碍物世界已固定，障碍物宽面朝向 UAV
- [x] Gazebo 原始 `/scan` 已打通到 ROS2
- [x] lidar 已直接挂在可移动的 `uav_start_marker` 上，而不是固定原点探针
- [x] `/scan_features` 与 `/scan_nearest_point` 已自动发布
- [x] 下游 consumer 已优先消费 `/scan_features`
- [x] `/planner/cmd_vel` 执行器已打通到 Gazebo 可见 UAV 位姿
- [x] 原始 `/scan` 与 `/scan_features` 会随 UAV 前进同步变化
- [x] 执行器内部已增加 `0.5 m` 最小前向净空钳位
- [x] `/sim/log` JSON 日志 topic 已提供给 manual / auto 共用订阅
- [x] `auto` 模式的 `/sim/log.mission_state` 已收敛成稳定枚举
- [x] `auto` 模式默认会留下 mission rosbag，`manual` 模式默认不录制
- [x] 端到端已验证：`front_min` 从约 `5.0 m` 收敛到约 `0.5 m` 后停止前进
- [x] 已提供一个“goal 在障碍物后方”的 mission 样例，可稳定触发 `blocked_by_stop_guard`

### 还没做完

- [ ] 把 `SCAN_SOURCE=gazebo|real` 这类显式 source 切换机制收成稳定配置入口
- [ ] 把真实 YDLidar 驱动接入这条链路再跑一遍同口径验证，确认 `/scan -> /scan_features` 一致
- [ ] 把 `auto` 默认 rosbag 的目录级 metadata / `ros2 bag info` 可用性补一次验收并收口
- [x] 给旧 sim CLI 收成明确的 `manual|auto` 两种启动模式入口
- [x] `manual` 模式文档已补上 Foxglove 操作路径和 `/planner/cmd_vel` preset
- [ ] `manual` 模式下再做一次完整 Foxglove 人工遥控验收
- [x] `auto` 模式下支持加载一个航点 `yaml`，先按最小直线执行跑通
- [x] `auto` 模式到达终点后会输出 `mission_complete` 状态并自行收尾
- [ ] 接一个真正的 world model / planner，让上游控制替代当前最小 forward/stop 示例
- [ ] 决定是否还保留 `/sim/uav_pose` 作为纯调试 topic，并把其定位写死到文档

## P1：Gazebo Lidar 仿真输入

目标：让 Gazebo 世界输出真实可运动的 `/scan`，并与真实 YDLidar 驱动的 ROS2 契约对齐。

### P1.1 世界与障碍物布局

状态：已完成

- [x] `docker/worlds/uav_obstacle_5m.sdf` 是当前默认世界
- [x] 保留原点起点标记和 `+X` 路径标记
- [x] 固定障碍物前缘位于 `x=5`
- [x] 世界不依赖 SLAM ROS workspace

验收：

- [x] Gazebo 能加载世界
- [x] 障碍物位置明确可见
- [x] 世界文件不依赖 SLAM ROS workspace

### P1.2 可移动 UAV 上的真实 lidar

状态：已完成

- [x] 不再使用旧版固定原点 lidar rig 作为主线
- [x] lidar 已直接挂到 `uav_start_marker`
- [x] lidar frame 为 `laser_frame`
- [x] lidar topic 为 `/scan`
- [x] lidar 参数对齐当前仿真 README 中的 `/scan` 契约

验收：

- [x] lidar 随 UAV 一起移动
- [x] lidar 面向 `+X`
- [x] 原点时能看到约 `5 m` 前方障碍

### P1.3 Gazebo 到 ROS2 的 `/scan` bridge

状态：已完成

- [x] compose 中已有 Gazebo scan bridge
- [x] Gazebo lidar 已桥接为 ROS2 `/scan`
- [x] 消息类型为 `sensor_msgs/msg/LaserScan`
- [x] frame override 为 `laser_frame`

验收：

- [x] 启动仿真后 ROS2 能看到 `/scan`
- [x] `ros2 topic hz /scan` 稳定
- [x] 下游无需改 raw scan 消费代码即可读取 Gazebo `/scan`

### P1.4 `/scan_features` 主线验证

状态：已完成

- [x] `scan_features_publisher` 从原始 `/scan` 计算结构化特征
- [x] 发布 `/scan_features`
- [x] 发布 `/scan_nearest_point`
- [x] consumer 默认优先消费 `/scan_features`

验收：

- [x] 原点时 `/scan_features.front_min` 接近 `5.0 m`
- [x] UAV 前进时 `/scan_features.front_min` 持续减小
- [x] 同一套下游逻辑无需区分 Gazebo / real 的特征话题格式

## P2：最小运动闭环与真实接入边界

目标：保留一个最小可运行示例，但把主控制权让给未来 world model / planner。

### P2.1 最小 `cmd_vel` 执行闭环

状态：已完成（以 `forward + stop` 替代旧版 `hover-then-forward`）

- [x] `front_sector_consumer` 会输出 `/planner/cmd_vel`
- [x] `cmd_vel_executor` 会消费 `/planner/cmd_vel`
- [x] UAV 能沿 `+X` 前进
- [x] 当前不引入完整飞行动力学

验收：

- [x] `/planner/cmd_vel` 能驱动 Gazebo 中的可见 UAV
- [x] 前进过程中原始 `/scan` 的 `front_min` 会逐渐变小
- [x] 行为可重复运行

### P2.2 `0.5 m` 最小前向净空

状态：已完成

- [x] consumer 会在 `front_min <= stop_distance` 时切到 `stop`
- [x] 执行器内部也会按世界几何额外钳住前向位移
- [x] `manual` / `auto` 都可通过 `/sim/log` 观察 stop guard 相关状态
- [x] 当前阶段只保留最小 stop guard，不继续扩展复杂被动避障

当前参数：

- `avoid_distance = 1.0 m`
- `stop_distance = 0.5 m`（默认来自 `navlab/config.toml` 的 `[companion].stop_distance`）
- `forward_speed = 0.2 m/s`（示例值，可在 CLI 覆盖）

验收：

- [x] Gazebo 仿真下能稳定触发 `avoid_required`
- [x] Gazebo 仿真下能稳定触发 `stop`
- [x] 即使上游还在发 forward，UAV 也会停在 `front_min ~= 0.5 m`

### P2.3 `/scan` 与 `/scan_features` 的角色边界

状态：部分完成

- [x] SLAM / 基础 scan 契约仍以原始 `/scan` 为统一输入边界
- [x] 行为类下游当前优先消费 `/scan_features`
- [ ] 把 `gazebo|real` source 切换机制收成明确配置
- [ ] 把真实 YDLidar 驱动也跑到同样的 `/scan_features` 行为主线里再验一次

验收：

- [x] 行为类下游默认只依赖 `/scan_features`
- [x] 原始 `/scan` 仍保持与真实 YDLidar 驱动对齐的契约
- [ ] Gazebo 和 real 两种 source 可通过统一配置切换

### P2.4 真实 YDLidar 驱动接入边界

状态：部分完成

- [x] 仿真代码不依赖真实传感器工作空间内部实现
- [x] `/scan` 契约仍集中在 `docs/sim/README.md`
- [x] `/scan_features` 契约复用 `ydlidar_interfaces/msg/ScanFeatures`
- [ ] 真实 YDLidar 驱动接入时再跑一轮端到端验证

验收：

- [x] 文档已经区分 raw `/scan` 与结构化 `/scan_features`
- [x] 仿真代码不依赖真实传感器工作空间内部实现
- [ ] 真实接入时只替换传感器来源，不改行为类下游接口

### P2.5 旧 sim CLI 启动模式分层

状态：部分完成

- [x] 旧 sim CLI 提供显式 `--mode manual|auto`（或等价配置入口）
- [x] 当前主线不再启动常驻 `foxglove` bridge；批处理 acceptance 生成 rosbag/summary 后上传 Foxglove 云端查看
- [x] `manual` 模式不强绑当前最小 `front_sector_consumer` 自动前进逻辑
- [x] `auto` 模式支持读取航点 `yaml`
- [x] `auto` 模式第一版只做最小直线执行，不提前绑定 world model
- [x] `auto` 模式仍复用当前 `/scan -> /scan_features -> stop guard` 安全边界
- [x] `auto` 模式到达终点后会发布 `mission_complete` 并退出 mission runner
- [x] 起点支持显式 `start`，不写时默认原点
- [x] `auto` 模式默认录 rosbag，`manual` 模式默认不录

验收：

- [x] 用户能明确区分“我来开”与“按文件自动跑”两条入口
- [ ] 手动模式下可通过 Foxglove 远程控制 UAV 在 Gazebo 场景内运动
- [x] 自动模式下给定单段航点文件后，UAV 能按直线开始执行
- [x] 自动模式下到达终点后会在 `/sim/log` 发出 `mission_complete`
- [x] 自动模式下使用“障碍物后方 goal”样例时，会在 `/sim/log` 发出 `mission_state = blocked_by_stop_guard`
- [x] 两种模式都保留 `0.5 m` 最小前向净空保护
- [x] 当前阶段不要求 world model 参与这两种模式

## 结论

当前已经可以打勾确认的主线是：

- [x] Gazebo 中有一个会随 UAV 一起运动的真实 `/scan`
- [x] `/scan_features` 已经从这个真实 `/scan` 自动发布
- [x] 最小控制闭环可以把 UAV 推到障碍物前
- [x] `front_min ~= 0.5 m` 时 UAV 会稳定停住，不再继续往前

当前还没有打勾的主线是：

- [ ] 真实 YDLidar 驱动与 Gazebo 的统一 source 切换入口
- [ ] 真实 YDLidar 驱动的同口径 `/scan_features` 端到端验证
- [x] 旧 sim CLI 的 `manual|auto` 双模式入口
- [x] 自动模式的航点 `yaml` 最小直线执行
- [x] `/sim/log` 统一日志输出 topic
- [ ] world model / planner 正式接管 `/planner/cmd_vel`
