# worldmodel 理解(二):运行时 ROS2 图与数据流

> [REFERENCE] 2026-07-07 精读产物。读者定位:**要把 GBPlanner 移植成 ROS2 原生节点并接进 world-model 的人**。
> 依据源码快照:`sources/world-model-源码\`(与 WSL `~/ws-clean/world-model` 上游基线一致;行号以该快照为准)。
> 注意:本快照是**上游原样**,不含本项目在 clean 分支上的修复(EKF yaw 源、IMU 回声等);凡涉及处会显式标注。
> 主线以 `exploration` 任务(`orchestration/sim/configs/tasks/exploration.yaml`)为例,这是 GBPlanner 要替换的 frontier_lite 所在的工作流。

---

## 0. 一句话总图

Gazebo 出传感 → ros_gz_bridge/自研 relay 进 ROS2 → cartographer 2D 出 `map→base_link` → 适配器变 `/slam/odom` → 兵分两路:
① **回灌**:`/external_nav/odom` → MAVLink ODOMETRY → ArduPilot EKF(飞控的位置估计来自 SLAM);
② **决策**:exploration_workflow 读 `/slam/odom` 出 intent(JSON)→ fcu_controller 双路下发(DDS `/ap/v1/cmd_vel` + MAVLink 位置 setpoint)→ SITL 动 → Gazebo 动 → 传感变 → 闭环。
GBPlanner 移植的落点就是替换"决策"框(intent 的生产者),其余链路原样复用。

---

## 1. 运行时进程/容器清单(exploration 任务)

编排器(Go)按 execution plan 起下列容器,全部 host 网络、同一 ROS_DOMAIN_ID、RMW=cyclonedds(`orchestration/sim/internal/tasks/runtime_specs.go:603-611`):

| 容器/服务 | 里面跑什么 | 关键出处 |
|---|---|---|
| `navlab-mavlink-router` | mavlink-routerd,listen `0.0.0.0:14550`,复制到 `127.0.0.1:14551/14552/14553` | `runtime_specs.go:387-431`;`orchestration/sim/config.toml:8-9` |
| `navlab-official-baseline` | **一容器四件套**:`ros2 launch ardupilot_gz_bringup iris_maze.launch.py ... use_dds_agent:=true`(= gz sim server + ArduPilot SITL + micro-ROS/DDS agent + 官方 ros_gz_bridge),外加 benewake 虚拟串口进程 | `runtime_specs.go:541-565`(launch 串在 L543/L564);SITL/GZ launch 默认值 `internal/config/defaults.go:34-36` |
| `navlab-official-maze-x2-sensor`(gazebo_sensor) | 自研传感 runtime:2D 雷达 vendor 协议仿真链 + 下视测距投影(见 §2.1) | `helpers/execution_plan.go:198-211`;`navlab/sim/gazebo_sensor/runtime.py:212-239` |
| `navlab-slam-backend` | `navlab.common.slam.cli launch --backend cartographer` → `navlab_slam_bringup.launch.py`(imu_bridge + 静态 TF×2 + cartographer_node + occupancy_grid + cartographer_adapter + external_nav_bridge) | `helpers/execution_plan.go:232-242`;launch 全文 `navlab/common/slam/ros/scenarios/navlab_slam_bringup/launch/navlab_slam_bringup.launch.py` |
| `navlab-fcu-controller` | 模板生成的 `fcu_controller_runtime.py`(唯一控制权属者) | `helpers/execution_plan.go:257-267`;模板 `helpers/templates/python/fcu_controller_runtime.py.tmpl` |
| `navlab-exploration-workflow` | 模板生成的 `exploration_workflow_runtime.py`(frontier_lite,**GBPlanner 替换点**) | `helpers/execution_plan.go:502-512`;模板 `exploration_workflow_runtime.py.tmpl` |
| `navlab-mavlink-external-nav` | `navlab.real.companion.nodes.external_nav`:ROS odom → MAVLink ODOMETRY,endpoint `udpin:0.0.0.0:14553` | `runtime_specs.go:444-459` |
| `navlab-height-estimator` | `navlab.real.companion.nodes.height_estimator`:`/rangefinder/down/range` → `/height/estimate` | `runtime_specs.go:494-505` |
| 探针/rosbag 容器 | exploration_probe、frame_contract_probe、`ros2 bag record`(mcap) | `helpers/execution_plan.go:513-529`、`642-662` |

MAVLink 端口拓扑(全 host 回环):

```
SITL ──udp──> :14550 mavlink-router ──复制──> 127.0.0.1:14551  fcu_controller(bootstrap+setpoint)
                                     ├──────> 127.0.0.1:14552  rangefinder FCU probe(defaults.go:108)
                                     └──────> 127.0.0.1:14553  mavlink_external_nav(EKF 回灌发送端)
```
出处:`internal/config/defaults.go:9-10,157`;fcu 端点 `helpers/runtime_specs.go:279`;sender 端点 `tasks/runtime_specs.go:446`。

---

## 2. 全 topic 数据流图

### 2.1 传感链(gz → ROS)

```
                     Gazebo(iris_with_lidar 模型,lidar_3d 被替换成 lidar_2d:helpers/navlab_models.go:35)
                        │
     ┌──────────────────┼───────────────────────────┬─────────────────────────┐
     │gz /clock         │gz /lidar (2D LaserScan)   │gz /lidar/points(3D,预留) │gz /rangefinder/down/scan_ideal
     ▼                  ▼                           ▼                         ▼
 [官方bridge]      [gazebo_sensor 容器内自起        [官方bridge override       [gazebo_sensor 容器内自起
 /clock             parameter_bridge                 cloud_in                  parameter_bridge
 (override L2-6)    /lidar, frame:=laser_frame       (override L37-41)]        frame:=rangefinder_down_frame
                    (runtime.py:81-91)]                  │                     (runtime.py:94-104)]
                        │                                ▼                        │
                        │                    cloud_scan_projection            ├────────► range_projection
                        │                    订 cloud_in→发 /lidar            │          → /rangefinder/down/range (Range)
                        │                    (cloud_scan_projection.py:       │          → /rangefinder/down/status
                        │                     11,88,92)                       │          (range_projection.py:52-54,69-77)
                        ▼                                                     │
              x2_serial_emulator(订 /lidar,把 X2 vendor 字节流写进           └────────► benewake_tfmini_serial
              虚拟串口 /tmp/navlab_sim_x2)(cli.py:92)                                   (订 scan_ideal,写虚拟串口
                        │                                                                /tmp/navlab_benewake_tfmini)
                        ▼                                                                (benewake_tfmini_serial.py:250;
              ydlidar_ros2_driver(port=虚拟串口,frame_id=base_scan,                     official_baseline 里启动:
              use_sim_time:=true)→ /navlab/x2/vendor_scan                               tasks/runtime_specs.go:559-563)
              (vendor_profile.yaml.tmpl:3-5;runtime.py:132-145)                              │ SERIAL7(UART 协议 9)
                        │                                                                    ▼
                        ▼                                                          ArduPilot SITL RNGFND1_TYPE=20
              scan_time_normalizer(订 vendor_scan + /clock,重打 sim 时戳)         (parm 模板 L21-23,33-37)
              → /scan + /sim/x2/status                                              → EKF 高度源(EK3_SRC1_POSZ=2)
              (scan_time_normalizer.py:173-189)

 gz IMU ──[官方bridge override L27-31]──► /imu (sensor_msgs/Imu)
 gz model pose/odometry ──[override L12-26]──► /gazebo/model/odometry、/gazebo/tf、/gazebo/tf_static(仅诊断真值,禁止入控制链,helpers/slam.go:16-19)
```

要点:
- **`/scan` 不是 bridge 直出**,而是"ideal `/lidar` → vendor 串口协议仿真 → 真 ydlidar 驱动 → 时戳归一化"的硬件保真链;`/lidar` 与 `/scan` 是两个东西。
- 3D 点云口子**上游已预留**:`bridge_override.yaml.tmpl:37-41` 把 gz `/lidar/points` 桥成 ROS `cloud_in`;`cloud_scan_projection` 只在 3D 模型时把它压成 2D `/lidar`(GBPlanner 3D 接入即取 `cloud_in`/`/lidar/points` 这一路)。
- 下视测距**两路消费**:一路进 ROS(`/rangefinder/down/range`→height_estimator),一路走虚拟串口直接进 SITL(EKF 的 Z 源),互不依赖。
- bridge override 文件被 volume 挂载**顶替**官方 `iris_3Dlidar_bridge.yaml`(`tasks/runtime_specs.go:575-597`,目标路径 `helpers/navlab_models.go:14`)。

### 2.2 SLAM 链(cartographer 2D)

```
/scan (base_scan) ─────────────┐
/imu ──► navlab_slam_imu_bridge ──► /imu(输出;exploration 默认输入=输出,见 §5.6)
         (launch:219-235;节点默认值 navlab_slam_imu_bridge_node.cpp:19-28)
                               │
                               ▼
                    cartographer_node(2D)
                    remap: scan:=/scan, imu:=/imu,
                           /odom:=/cartographer/odometry_input(exploration 未用,lua use_odometry=false),
                           /tf:=/navlab/slam/tf   ← SLAM 动态 TF 与全局 /tf 隔离
                    (launch:325-344;隔离动机 launch:111-117)
                               │  /navlab/slam/tf 上发 map→base_link
                               ▼
                    navlab_cartographer_adapter_node
                    ├─ 只认 parent==map && child==base_link 的 TF(cpp:107-150、274-279)
                    ├─ 跳变/非法值门:max_tf_jump_m=2.0 等,拒绝则不出 odom(cpp:306-335)
                    ├─ 出 /slam/odom(nav_msgs/Odometry,header.frame_id=map,child=base_link;
                    │   z/roll/pitch 协方差打成 9999——2D SLAM 不测高,防下游当真,cpp:337-374 及注释 347-349)
                    ├─ 新鲜时按 10Hz 重发缓存 odom(cpp:77-83、396-404)
                    ├─ 接受的 TF 转发到全局 /tf(publish_global_tf,exploration=true:helpers/slam.go:92;hover=false:runtime_artifacts.go:119)
                    └─ 出 /navlab/slam/status(JSON on String,cpp:152-183)
                               │
     cartographer_occupancy_grid_node ──► /map(0.05m 栅格,launch:345-353;nav2 任务消费)
```

Cartographer lua(`navlab_cartographer_2d_real.lua`):`map_frame="map"`(L7)、`tracking_frame="imu_link"`(L8)、`published_frame="base_link"`(L9)、`provide_odom_frame=false`(L11)、`use_odometry=false`(L13)。即 cartographer 直接发布 `map→base_link`,**没有 odom 中间帧**。

### 2.3 external_nav 回灌链(SLAM → EKF)

```
/slam/odom(map→base_link,z 协方差 9999)          /height/estimate(JSON:z/vz/covariance/source_type)
        │                                                 ▲
        │                                        height_estimator ◄── /rangefinder/down/range
        ▼                                        (tasks/runtime_specs.go:494-505)
navlab_external_nav_bridge_node(slam_backend 容器内)
 ├─ 门:odom 新鲜/频率≥4Hz/frame 必须恰为 map→base_link(cpp:225-243、295-301;参数模板 L38-39)
 ├─ 门:slam 质量(跳变闩锁、可选 IMU/scan 几何可观测性,cpp:444-499)
 ├─ 门:height 必须新鲜且协方差≤4.0(require_height_for_output=true,参数模板 L8、L17)
 ├─ 出 /external_nav/odom:xy/yaw 取 SLAM,z/vz 用 height 覆盖(cpp:258-271;frame_id=external_nav)
 ├─ 出 /ap/tf(TFMessage odom→base_link,cpp:273-283)── ArduPilot DDS 外部里程计入口(设计路;实跑验证的是下面 MAVLink 路)
 └─ 出 /external_nav/status(大 JSON,cpp:599-701)
        │
        ▼
mavlink_external_nav sender(navlab/real/companion/nodes/external_nav.py)
 ├─ 订 /external_nav/odom(ENU/FLU 语义,L37)
 ├─ 换系:ENU→LOCAL_FRD:x_frd=y_enu, y_frd=−x_enu, z_frd=−z_enu(L65-71);yaw_frd=π/2−yaw_enu(L74-75)
 ├─ 出 MAVLink v2 ODOMETRY(MAV_FRAME_LOCAL_FRD + BODY_FRD,MAV_ESTIMATOR_TYPE_VIO,20Hz,L33-36、字段表 L184-202)
 │   → udpin:0.0.0.0:14553 ← router ← SITL
 └─ 顺手把 FCU 的 LOCAL_POSITION_NED 镜像成 /navlab/fcu/local_position_pose(PoseStamped,L254-256、378-401)
        │
        ▼
ArduPilot EKF3:EK3_SRC1_POSXY=6(ExternalNav)、POSZ=2(RangeFinder)、VELXY=0、YAW=1(罗盘)、VISO_TYPE=1
(docker/profiles/navlab-sitl-external-nav.parm:19-24;同内容测试模板 helpers/templates/parm/official_external_nav.parm.tmpl:11-16)
⚠️ YAW=1 是本项目 stage5a 定位的发散根因,修复(YAW→6、COMPASS_USE→0、--no-align-yaw-to-fcu)在本项目 clean 分支,上游快照仍是旧值。见 §5.1。
```

### 2.4 控制链(intent → FCU 双路)

```
exploration_workflow(navlab_exploration_workflow 节点)
 ├─ 订 /navlab/fcu/controller/status(等 controller_ready,tmpl:38-48)
 ├─ 订 /slam/odom(累计 path_length,tmpl:50-65)
 ├─ 发 /navlab/fcu/setpoint/intent(std_msgs/String,JSON:
 │     {linear_x_mps, linear_y_mps, yaw_rate_radps, goal_id, strategy, ...},tmpl:141-158)
 │     未 ready 时发 stop intent(tmpl:113-114)
 └─ 发 /navlab/exploration/status + 5 个 review 话题(goal/coverage/frontiers/path/markers,tmpl:70-75)
        │ intent(JSON)
        ▼
fcu_controller(navlab_fcu_controller 节点;控制权唯一属主 /navlab/fcu/owner/status,tmpl:631-641)
 ├─ 启动即后台 MAVLink bootstrap:GUIDED→arm→takeoff(经 14551;tmpl:152-311)
 │    DDS 服务路(/ap/v1/prearm_check、mode_switch、arm_motors、experimental/takeoff)在此路线上明确不用
 │    (spec 定义 helpers/runtime_specs.go:290-293;跳过声明 tmpl:163-167)
 ├─ 位姿源:/slam/odom 优先(pose_source="slam_odom",tmpl:322-330);/ap/v1/pose/filtered 仅当
 │    require_slam_backend=false 时兜底(tmpl:314-320;默认 true:helpers/runtime_specs.go:333)
 ├─ 收 intent → MAVLink 单控制路(DDS cmd_vel 发布已禁用,仅保留计数):
 │    SET_POSITION_TARGET_LOCAL_NED(frame=MAV_FRAME_LOCAL_NED,type_mask=2552=仅位置+yaw;
 │        目标 = 当前 LOCAL_POSITION_NED + v×lookahead(2s),z 恒 = −takeoff_alt;tmpl:390-441)
 │        intent 的 (x,y) 按 FCU ATTITUDE yaw 从机体系 FRD 旋到 NED 后积分位置目标
 ├─ ready 时每 50ms 发 hold setpoint
 ├─ 订 /navlab/exploration/status 作为任务完成信号(接线:runtime_artifacts.go:162-168;判断:tmpl:340-355)
 └─ 发 status 面:/navlab/fcu/controller|setpoint/output|owner、/navlab/hover/status、/navlab/landing/status
      (tmpl:462-475;topic 名 helpers/runtime_specs.go:285-288、393-394)
        │
        ▼
ArduPilot SITL(DDS agent 起在 official_baseline 内,use_dds_agent:=true,tasks/runtime_specs.go:564)
 /ap/v1/* 面:cmd_vel(入)、pose/filtered、twist/filtered、status、time(出)(helpers/runtime_specs.go:289-297)
        │ 电机 → Gazebo ArduPilotPlugin → 物理 → 传感 → 回到 §2.1
```

### 2.5 验收/证据面(与控制解耦)

- exploration_probe 订 `/navlab/fcu/controller/status`、`/navlab/fcu/setpoint/output`、`/navlab/exploration/status`、`/slam/odom`、`/navlab/landing/status`(`helpers/runtime_specs.go:1141-1146`)。
- frame_contract_probe 订 `/tf`、`/tf_static` + 6 个数据话题(`helpers/runtime_specs.go:484`;要求的 6 个 frame:`helpers/runtime_specs.go:443`)。
- rosbag 固定录制集含 `/ap/v1/pose|twist/filtered`、`/height/estimate`、`/slam/odom`、`/slam/odom_corrected` 等(`helpers/rosbag_topic_sets.go:6-27`)。
- 所有 status 话题都是 **JSON-on-std_msgs/String**——这是全库统一的状态总线风格,GBPlanner 侧新增 status 建议照抄此风格。

---

## 3. frame / TF 全景

| TF 边 | 谁发布 | 发到哪个 topic | 出处 |
|---|---|---|---|
| `map → base_link`(动态,SLAM 估计) | cartographer_node | **`/navlab/slam/tf`**(隔离话题,非全局 /tf) | launch remap `navlab_slam_bringup.launch.py:342`;隔离动机 L111-117 |
| `map → base_link`(动态,**过门后的**) | cartographer_adapter 转发 | 全局 `/tf`(exploration 开、hover 关) | cpp:376-384;开关 `helpers/slam.go:92` / `runtime_artifacts.go:119` |
| `base_link → base_scan`(静态,z=0.075077=官方 iris 雷达高) | tf2_ros static_transform_publisher | `/tf_static` | launch:236-259;laser_frame 实参=base_scan、z 值:`helpers/slam.go:103,162`、常量 L13 |
| `base_link → imu_link`(静态,恒等) | tf2_ros static_transform_publisher | `/tf_static` | launch:260-283 |
| `odom → base_link`(动态,给 AP 的) | navlab_external_nav_bridge | **`/ap/tf`**(专用话题,非 /tf) | cpp:273-283;parent/child 参数模板 L36-37 |
| 模型真值 pose | gz bridge | `/gazebo/tf`、`/gazebo/tf_static`(诊断专用) | bridge_override.yaml.tmpl:17-26 |

frame 语义速查:
- **`map`**:cartographer 的世界系,`/slam/odom` 与回灌位置全在此系。**它与 AP 的 NED 世界系差一个每次运行都不同的偏角 δ**(见 §5.1/§5.3)。
- **`odom`**:名存实亡的 legacy 帧——cartographer `provide_odom_frame=false`(lua L11),没有节点发布 `map→odom`;它只作为 `/ap/tf` 的 parent 名字出现(launch:165-169 自述 "Legacy odom frame used only by legacy TF mode")。**移植 GBPlanner 时不要假设存在 map→odom→base_link 标准链**。
- **`base_link`**:机体系(FLU);`/ap/v1/cmd_vel` 的 header 用它(fcu tmpl:371)。
- **`base_scan`**:2D 雷达帧(vendor 驱动 frame_id,vendor_profile.yaml.tmpl:5);`laser_frame` 是 gazebo_sensor 自己 bridge 的 ideal scan 用名(runtime.py:90),两者并存。
- **`imu_link`**:cartographer 的 tracking_frame(lua L8);IMU 消息 frame 由 imu_bridge 归一(默认沿用输入 frame,空则填 imu_link,cpp:84-86)。
- **`rangefinder_down_frame`**:下视测距(bridge override L42-46 + range_projection.py:71);frame contract 六帧之一(`helpers/runtime_specs.go:443`)。
- **`external_nav`**:`/external_nav/odom` 的 frame_id(bridge cpp:265),只是标签,不入 TF 树。
- TF 消费注意:`/tf_static` 是 transient_local(latched),后加入订阅者拿历史;`/gazebo/tf` 等 QoS 陷阱详见项目实测(B16,CURRENT_STATUS.md)——探针应做 publisher QoS 内省而非裸订阅。

---

## 4. 时钟:谁用 sim time,谁用 wall clock

| 组件 | 时钟 | 出处 |
|---|---|---|
| Gazebo → `/clock` | 桥出 sim 时钟 | bridge_override.yaml.tmpl:2-6 |
| slam_backend 全部节点(imu_bridge/cartographer/adapter/external_nav_bridge/静态TF) | `use_sim_time:=true`(launch 参数默认 true) | launch:38-42 及各 Node parameters |
| fcu_controller | `use_sim_time=True` 且开头**阻塞等 /clock**(≤5s);但内部超时/节拍全用 `time.monotonic()`(wall) | tmpl:20-23;deadline 例 tmpl:486-488 |
| exploration_workflow | 同上:声明 sim time(tmpl:18-21),**但窗口/goal 切换全部 wall clock**(`time.monotonic`,tmpl:82-90、105-108) | — |
| scan_time_normalizer | 显式订 `/clock`,把 vendor 驱动的 wall 时戳**重打成 sim 时戳**(它存在的目的) | scan_time_normalizer.py:175、277-279 |
| ydlidar_ros2_driver | `use_sim_time:=true`(但底层读串口是 wall,故需上面的 normalizer) | vendor_profile.yaml.tmpl:3;runtime.py:141-142 |
| external_nav_bridge 的"新鲜度"判断 | **std::chrono::steady_clock(wall)**——与消息 sim 时戳无关 | cpp:125、140-141 |
| cartographer_adapter 的"新鲜度"判断 | `now()`=节点时钟(sim time)——**与上一行口径不一致**,跨节点比较 age 时留神 | cpp:186-201 |
| 探针(slam_only_probe 等) | 不设 sim time,纯 wall(`time.monotonic`) | slam_only_probe.py.tmpl:52-53、106-107 |
| ArduPilot SITL | 自己的仿真调度;对 ROS 暴露 `/ap/v1/time` | topic 名 helpers/runtime_specs.go:289 |
| mavlink_external_nav sender | MAVLink time_usec 用 sender 单调钟(自述 `sender_monotonic_clock_us`) | external_nav.py:33 |

**给移植者的规则**:数据路(消息 stamp)统一 sim time;控制/门限逻辑上游习惯用 wall(monotonic)。GBPlanner ROS2 节点建议:消息处理用 node clock(受 use_sim_time 控制),watchdog 用 steady clock,并明确写进代码注释——上游两种口径混用已经埋过雷(见 §5.7)。

---

## 5. 已知语义坑位驻点(移植前必读)

以下均为本项目实测定位(stage5a 诊断:`runbooks/world-model-jazzy/stage5a_diagnosis.md`),此处按源码重述。

### 5.1 EKF 参考系打架:yaw 与位置不同源(上游最大坑)

上游默认参数:`EK3_SRC1_POSXY=6`(位置=ExternalNav,即 SLAM map 系)而 `EK3_SRC1_YAW=1`(yaw=罗盘,即物理世界系)(`docker/profiles/navlab-sitl-external-nav.parm:19-24`)。SLAM map 系的朝向由**开机瞬间机头方向**决定,与罗盘世界系差固定偏角 δ,每 run 不同。静止时无感;一运动,EKF 在两个参考系之间强行对齐("in-flight yaw alignment")→ 位置环正反馈 → 估计发散("stopped aiding"→"position lost",BIN 日志实证)。叠加雪上加霜的一刀:sender 默认 `--align-yaw-to-fcu`(把 FCU 自己的 yaw 喂回 FCU,循环自证;`tasks/runtime_specs.go:453`)。
**修复口径(本项目 clean 分支,上游快照未含)**:YAW 1→6、COMPASS_USE 全 0、`--no-align-yaw-to-fcu`;修复后实测漂移 0.25-0.4 m/s → 0.03 m/s。**移植 GBPlanner 后凡出现"固定方向逃逸",先查这组参数,不要先怀疑规划器。**

### 5.2 "胡萝卜"位置目标:命令速度≠实际速度

fcu_controller 的 MAVLink 主路不是速度控制,而是**位置目标外推**:`目标 = 当前位置 + v×lookahead(2s)`,z 恒定(tmpl:406-415)。后果:
- 实际速度由 AP 位置控制器增益决定(实测 ~0.3 m/s),**与 intent 里的速度幅值基本无关**;
- 目标点恒挂在机头前 ~固定距离("胡萝卜"),近距接近 waypoint 时目标会**越过** wp → 配合到达圈判定,出现绕 wp 极限环打圈(stage5a 第七跑实测 0.5m 圈);
- hold(v=0)不是刹停,是"目标=当前位置",有 0.5~1m 滑行。
GBPlanner 的轨迹跟踪若直接换算成 intent,必须把这层"位置外推"语义算进去(近距按距离比例减速,而不是恒速)。
还有一个频率契约:`send_mavlink_local_position_setpoint` 把每条 intent 积分到位置目标,
但 `dt=min(0.25, actual_dt)`。因此 producer 必须至少 4Hz;第六次 M5 证明 2Hz
会把 0.08m/s 目标推进实效折半。

### 5.3 NED/ENU/map:位置数值含反射,控制接口应走 body frame

- sender 侧 ENU→FRD:`x_frd=y_enu, y_frd=−x_enu, z_frd=−z_enu`(external_nav.py:65-71)是外部导航回灌的历史约定,不能拿来给当前 intent 做纯旋转标定。
- `ned_to_gazebo_pose` 对 xy **恒等**、只翻 z(stage5a §六)→ `/navlab/fcu/local_position_pose` 的 xy 是裸 NED,别当 ENU 用。
- 当前 fcu MAVLink 主路把 intent 定义为机体系 FRD,先按 FCU yaw 旋到 NED,再积分
  LOCAL_NED 位置目标。第四次 M5 run 实测 `yaw_fcu≈+90°`,漏掉该变换会产生约 90°
  命令误差。
第五次 M5 与第四次 bag 的位置/姿态对拍证明:`yaw_map≈0.2°`,`yaw_ned≈89.95°`,
位置数值近似 `NED=(map_y,map_x)`(det=-1)。因此纯旋转 `R_align` 模型在方法上错误。
结论:adapter 用 `/slam/odom` 的 map→base_link 姿态直接把 map 速度变成 body
forward/right,controller 再用 FCU yaw 变成 NED。downstream yaw 缺失或陈旧必须
fail-closed。ATTITUDE 的真实年龄取自
`/mavlink_external_nav/status.fcu_attitude_age_ms`;LOCAL_POSITION 仍在更新不等于 yaw 新鲜。

### 5.4 fcu_controller 双下发路语义分裂

当前同一份 intent 在语义上统一为机体系 FRD:MAVLink 路用 FCU yaw 旋到 NED 后积分;
DDS `cmd_vel` 实际发布已禁用,只保留计数字段,避免双路控制。早期“双下发语义分裂”
结论属于历史实现,不能用于当前适配器。

### 5.5 exploration 的 accepted_goals 是时间驱动的,不是空间验收

`goal_index = min(ready_elapsed/segment_sec, min_goals−1)`,只要有过 odom 样本就记 accepted(tmpl:105-108);26s 窗口÷3 goals(`helpers/runtime_specs.go:1116-1120`)。即 baseline 的"3/3 目标"**不代表到达了任何空间位置**——对比实验时不要把它当 GBPlanner 的同类指标(本项目基线达标率 40% 的根因即启动耗时蚕食此窗口)。

### 5.6 IMU 回声(exploration 默认接线)

默认 `IMUSourceTopic=/imu` 且输出 `IMUTopic=/imu`(`helpers/slam.go:88-89`)→ imu_bridge 订自己发的话题(launch:219-235,节点 cpp:19-24)。hover 任务专门劈开成 `/imu → /navlab/slam/imu`(`runtime_artifacts.go:117-118`),exploration 没劈。此为本项目"5 类真 bug"之一,clean 分支已修;读上游代码时注意这不是设计而是缺陷。

### 5.7 其他驻点(短)

- **`/rangefinder/down/range` 双发布者**:range_projection(真链,range_projection.py:52)与 fcu_controller(由 pose.z 合成的影子版,tmpl:469、535、840-854)同时发——消费端拿到的是混流。验收探针没炸只因两者数值接近;移植后加消费者时先确认要哪个源。
- **landing 在 exploration 任务是 claim 级**:fcu tmpl 的 landing_status 仅由 `pose 存在 + task_completed` 置 ok(tmpl:717-735),不发真实 LAND 指令;真降落逻辑在 hover/mission 管线(`navlab/common/companion/mission/`)。看到 `landing ok` 别当成"电机停了"。
- **`/cartographer/odometry_input` 在 exploration 是死话题**:lua `use_odometry=false`(L13),该口只在 hover 诊断链被 scan_reference 使用(`helpers/runtime_specs.go:710-717`)。
- **DDS 慢发现**:`/ap/v1/pose/filtered` 等 AP 话题对后加入订阅者可能要 ~29s 才完成 endpoint 匹配(本项目受控实验),探针要给发现预算;`ros2 topic echo`(CLI)对 rclpy 发布者可能收不到,**验收一律 rclpy 订阅**(项目实测教训,CURRENT_STATUS.md)。
- **诊断真值红线**:`/odometry`、`/gazebo/*` 只准进 rosbag/评估,不准进控制或 SLAM 输入(`helpers/slam.go:16-19` 命名即 Diagnostic;exploration status 里专门带 `uses_gazebo_truth_as_input:false` 字段自证,tmpl:154)。

---

## 6. GBPlanner ROS2 原生移植的接线清单

| GBPlanner 需要 | world-model 现成供给 | 备注 |
|---|---|---|
| 里程计(world 系) | `/slam/odom`(map→base_link,10Hz 缓存重发) | z 协方差 9999,3D 规划需另取高度(`/height/estimate` 或 AP pose) |
| 3D 点云 | `cloud_in`(gz `/lidar/points`,bridge 口子已预留,override L37-41) | 需把模型换回 lidar_3d(撤销 `navlab_models.go:35` 的替换)或改 override |
| 2D scan(可选) | `/scan`(vendor 保真链) | 频率 7Hz,别假设 10Hz |
| TF | `/tf` 上的 map→base_link(adapter 过门版)+ `/tf_static` 两条静态边 | 无 map→odom;传感帧见 §3 |
| 输出:轨迹/速度 | 折算成 intent JSON 发 `/navlab/fcu/setpoint/intent`(格式 tmpl:141-158) | 经 fcu_controller 双路下发;或长期方案:改 fcu_controller 增加轨迹接口 |
| 完成信号 | 发 `/navlab/exploration/status`(JSON,含 ok/accepted_goals/path_length_m/blockers,tmpl:175-207) | fcu_controller 以此触发 landing 链(runtime_artifacts.go:167) |
| 替换位置 | `exploration_workflow` 服务(容器 `navlab-exploration-workflow`,execution_plan.go:502-512);config 入口 `orchestration/sim/configs/tasks/exploration.yaml:20`(strategy) | 本项目已有 external 让位补丁与 `/gbp/*` 适配器先例(CURRENT_STATUS.md) |

坑位自查表(上线前逐条过):§5.1 EKF yaw 源已改 6?§5.2 近 wp 减速?§5.3 map↔NED 对齐策略?§5.4 只走一条下发路?§5.5 对比指标口径?§5.6 IMU 接线劈开?

---

*本文档所有行号基于 `sources/world-model-源码` 快照;若上游更新请以 `git blame` 校准。姊妹篇:worldmodel理解_1(编排与模板生成机制,若已存在)、`docs/桥接查证与执行计划_2026-07-06.md`(GBPlanner 桥接实操)、`runbooks/world-model-jazzy/stage5a_diagnosis.md`(EKF 根因链原始记录)。*
