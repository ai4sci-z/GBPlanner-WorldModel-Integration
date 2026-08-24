# worldmodel 理解(三):探索策略接口与 ROS2-GBPlanner 的精确接入点

> 状态:CURRENT(2026-07-07)
> 读者:要把 GBPlanner 从 ROS1 移植成 ROS2 原生节点、并直接接进 world-model 的人。
> 主题:探索策略如何插拔——`strategy=frontier_lite` 时内建 workflow 的完整契约,`strategy=external` 时外部规划器必须满足什么,以及 ROS2 原生 GBPlanner 的逐接口接入蓝图。
> 源码基准:`sources/world-model-源码/`(Windows 直读副本,**原版无 external 分支**)与 WSL `/home/ai4s/ws-clean/world-model/`(clean 分支,已应用我们的 external 补丁)。行号未加注 WSL 者均指 Windows 副本。

---

## 0. 一图流:插拔点在哪

策略是一个**字符串配置**,从 YAML 一路注入到 Python 运行时模板:

```
configs/tasks/exploration.yaml L20        strategy: frontier_lite      ← 实验期只改这一行
  → internal/config/types.go L430-432     ExplorationGateConfig.Strategy
  → internal/tasks/runtime_artifacts.go L834-848   explorationSpec() 映射
  → internal/tasks/helpers/runtime_specs.go L1098-1128  ExplorationWorkflowSpec(默认 frontier_lite)
  → internal/tasks/helpers/runtime_specs.go L1148-1169  ExplorationWorkflowRuntimeScript() 序列化为 SpecJSON
  → templates/python/exploration_workflow_runtime.py.tmpl L7  SPEC = json.loads(...)
```

- 配置入口:`orchestration/sim/configs/tasks/exploration.yaml:20`(`exploration_gate.strategy`);
- Go 侧类型:`orchestration/sim/internal/config/types.go:430-432`;
- Spec 默认值:`orchestration/sim/internal/tasks/helpers/runtime_specs.go:1113-1128` —— `Strategy:"frontier_lite"`、`ExplorationWindowSec:26.0`、`MotionSpeedMPS:0.10`、`MinAcceptedGoals:3`、`MinPathLengthM:0.35`、`ProbeTimeoutSec:35.0`,以及五个话题名(controller status、setpoint intent/output、slam odom、exploration status);
- 运行形态:`exploration-workflow` helper 作为独立容器 `navlab-exploration-workflow` 跑生成脚本 `exploration_workflow_runtime.py`(`orchestration/sim/internal/tasks/helpers/execution_plan.go:502-512`)。

**重要:world-model 没有"策略插件机制"。** `strategy` 字段在原版里只是写进 intent/status 的标签(模板 L151、L164、L194),运动模式是写死的三段 pattern。真正的插拔是我们加的 `external` 分支(见 §1.3):内建 workflow 判断 `strategy=="external"` 后整段让位,把 intent 总线和 status 话题的所有权交给外部进程。

---

## 1. 策略契约

### 1.1 `strategy=frontier_lite`:内建 workflow 自己发什么

文件:`orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl`。
主循环 ~10Hz(L86-115,`time.sleep(0.1)`),所有消息都是 `std_msgs/String` 装 JSON(L134-139 `string_msg`)。

#### 1.1.1 intent —— `/navlab/fcu/setpoint/intent`(话题名来自 SPEC,默认见 runtime_specs.go:1123)

运动 intent 由 `exploration_intent()` 生成(模板 L141-158),字段逐个列:

| 字段 | 类型 | 来源/值域(frontier_lite) |
|---|---|---|
| `linear_x_mps` | float | pattern 三段:`speed`=0.10、`speed*0.6`=0.06、`speed`=0.10(L142-146) |
| `linear_y_mps` | float | 恒 0.0(L142-146) |
| `yaw_rate_radps` | float | 三段:0.0、+0.20、-0.12(L142-146;注意 Spec 的 `YawRateRadPS=0.18` 只入 SpecJSON,pattern 并不使用它) |
| `ok` | bool | 恒 true(L149) |
| `source` | str | 恒 `"exploration_workflow"`(L150)——混流检测的关键指纹 |
| `strategy` | str | `SPEC["strategy"]`(L151) |
| `goal_id` | str | `frontier_lite_{n}`(L152) |
| `goal_index` | int | 0..min_goals-1(L153) |
| `uses_gazebo_truth_as_input` | bool | 恒 false(L154) |
| `odom_samples` | int | /slam/odom 计数(L155) |
| `path_length_m` | float | odom 累计路径(L156) |

停止 intent 由 `stop_intent()` 生成(L160-173):同上但三个速度字段恒 0,多一个 `reason` 字段(`waiting_for_controller` / `complete` / `shutdown`,L114、L99、L120),`goal_id="hold"`。

**"accepted_goals 纯时间驱动"的实锤**(基线 40% 达标率的根因):L106-108,`goal_index = min(int(ready_elapsed / segment_sec), min_goals-1)`,只要 controller ready 后时间流逝且 `odom_samples>0`,goals 就自动 +1——它不是"到达了某个空间目标",这是移植后做同口径对比时必须记住的口径差。

#### 1.1.2 status —— `/navlab/exploration/status`

`exploration_status()`(模板 L175-207)字段逐个列:

| 字段 | 含义 |
|---|---|
| `ok` | blockers 为空(L190) |
| `claim` | `"evaluated"`(ok)或 `"in_progress"`(L193) |
| `strategy` | SPEC 里的策略串(L194) |
| `accepted_goals` / `min_accepted_goals` | 见上;阈值默认 3(L176-177) |
| `path_length_m` / `min_path_length_m` | odom 积分(步长>1m 的跳变剔除,L58-64)/ 阈值 0.35(L178-179) |
| `motion_speed_mps` | SPEC 回显(L199) |
| `odom_samples` | int(L200) |
| `controller_ready` | bool,来自 controller status 的 `ok||ready`(L41-42) |
| `ready_elapsed_sec` | ready 起算秒数(L202) |
| `uses_gazebo_truth_as_input` | 恒 false(L203) |
| `evidence_source` | slam odom 话题名(L204) |
| `setpoint_intent_topic` | 回显(L205) |
| `blockers` | 四种:`controller_not_ready` / `slam_odom_missing` / `accepted_goals_below_min` / `path_length_below_min`(L181-189) |

#### 1.1.3 review 话题(五个,固定话题名,L71-75、L209-239)

`/navlab/exploration/goal`、`/coverage`、`/frontiers`、`/path`、`/markers`,都是 String JSON,只做证据回放用;rosbag 的 review 集合里点名它们(`helpers/rosbag_topic_sets.go:70-82`)。

### 1.2 平台侧谁消费这些话题(external 方必须喂饱的四张嘴)

**(a) fcu_controller 消费 intent → 双路下发**。`templates/python/fcu_controller_runtime.py.tmpl`:
- 订阅 `SPEC["setpoint_intent_topic"]`(String,depth 10);
- 回调只读三个运动字段;DDS `cmd_vel` 发布已禁用,避免双控制路;
- `send_mavlink_local_position_setpoint` 把 `linear_x/y` 视为机体系 FRD,按 FCU
  ATTITUDE yaw 旋到 NED,再积分 `SET_POSITION_TARGET_LOCAL_NED` 位置目标。
- adapter 使用 `/slam/odom` 的 map→base_link 姿态直接生成 body forward/right;
  不再从位置位移估计 map→NED 旋转。
- **B15 门**:MAVLink 主路在 bootstrap(GUIDED+arm+takeoff)完成前直接 return(L393 `if not bootstrap_ready(state): return`;`bootstrap_ready` 定义 L586-592)。起飞前 intent 不会进飞控。

**(b) fcu_controller 消费 status → landing 联动**。exploration 任务里 `TaskCompletionStatusTopic` 被接到 exploration status 话题(`internal/tasks/runtime_artifacts.go:162-168`);fcu 侧 `on_task_completion`(fcu 模板 L340-355)判定:`ok==true` **或**(`accepted_goals>=min` 且 `path_length_m>=min` 且 `blockers` 空)→ `task_completed=true` → `landing_status.ok`(L717-735)→ 主循环等 `completion_grace_sec` 后整个任务收尾(L516-524)。**也就是说:外部方把 status 的 ok 置 true 的那一刻,就是触发降落的那一刻**——这就是我们适配器早期把 ok 保守置 False、只报 `gate_ok_draft` 的原因(防误触发 landing)。

**(c) exploration_probe 消费五个话题**。`helpers/runtime_specs.go:1137-1146`:probe 采样 `[controller_status, setpoint_output, exploration_status, slam_odom, /navlab/landing/status]`;probe 模板 `ros_probe.py.tmpl` 规则:
- String 状态话题若 payload 含 `ok` 字段则必须为 true 才算采样成功(L313-314 `string_payload_ok`、L58-64 `effective_sample_ok`);
- `/slam/odom` 有兜底:slam status 里 odom 证据为正即可(L62-77,即"slam.ready=False 不挡 gate"的机制);
- 任一必需话题不 ok → 进程 rc=20(L30、L44)→ gate 记 `probe_failed:exploration_probe:rc=20`(`internal/tasks/gate_evaluation.go:112-119`)与 `probe_output_not_ok`(L121-136),run 直接 `required probes failed`(`internal/tasks/runtime_runner.go:206`);
- 时限:probe 容器外层 90s(`internal/tasks/runtime_specs.go:277-279`),String 批采样内层用 SpecJSON 的 `ProbeTimeoutSec=35`(ros_probe.py.tmpl L10-13)。

**(d) gate 摘要与 rosbag**。gate 从 exploration status 里抽七个字段进 summary(`gate_evaluation.go:223-226`):`claim/strategy/accepted_goals/min_accepted_goals/path_length_m/min_path_length_m/motion_speed_mps`;rosbag 必录集合里包含 intent、setpoint output、exploration status、`/slam/odom`、`/scan`、`/map`、`/tf` 等(`helpers/rosbag_topic_sets.go:84-99`),缺流即 `rosbag_profile_failed`(gate_evaluation.go:138-143)。

### 1.3 `strategy=external`:让位给谁、外部方要发什么

**补丁**:`runbooks/world-model-jazzy/patch_external_strategy.py`(幂等,已应用到 WSL clean 分支;Windows 源码副本是原版、无此分支)。生效后模板在主循环前插入(WSL 版 L86-96):

```python
if str(SPEC.get("strategy", "")) == "external":
    # 内建 workflow 全程被动:不发 intent、不发 status、不发 review topics,
    # 只 spin 到 deadline,保证与外部规划器永不交错(去混流)。
    while rclpy.ok() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.02)
        time.sleep(0.2)
    ...
    return 0
```

**让位给谁**:任何在 `/navlab/fcu/setpoint/intent` 上发 JSON intent、并拥有 `/navlab/exploration/status` 的外部进程。当前 ROS2 出口是 `ros2_port/adapter/trajectory_to_intent.py`;桥接时代的 `integration/ros1_bridge/trajectory_to_intent_stage4.py` 只作历史对照,不得再宣称“零改动复用”。

**外部方必须发布什么才能过 gate**(对照 §1.2 四张嘴):

1. **intent**(String JSON):最少 `linear_x_mps/linear_y_mps/yaw_rate_radps`(fcu 只读这三个,fcu 模板 L372-375、L403-405);强烈建议带 `source`(唯一签名,适配器发 `"gbp_traj_to_intent"`,L286)与 `strategy`(L287),这是混流取证的依据;
2. **status**(String JSON):必须含 `ok`(probe 硬性要求)+ gate 摘要那七个字段;`ok=true` 即触发 landing(§1.2b),所以只在真达标时置位;
3. 其余三个探针话题(controller status、setpoint output、landing status、slam odom)由 fcu_controller/SLAM 自己发,外部方无需管。

**适配器的最终实现:严格 gate 五条件闩锁**(`trajectory_to_intent_stage4.py:294-304`,即 Review_016 §3.3 口径):

```python
if (not self.ok_latched and self.enabled and not self.killed
        and not self.mixed_flow and self.controller_ready
        and self.wp_done >= 3 and self.path_len >= 0.35
        and not blockers):
    self.ok_latched = True
```

五组条件:① **去混流**——intent 总线上出现过任何 `source != gbp_traj_to_intent` 的消息即永久闩死(`mixed_flow`);② **takeoff/controller ready**——订 `/navlab/fcu/controller/status` 的 ok/ready;③ **诚实 accepted_goals**——`wp_done>=3`,只计"运动到达"的 waypoint,轨迹到手时已在阈值内的 wp 记 `wp_prereached` 不计数;④ **path 达标**——`path_len>=0.35`;⑤ **无运行 blocker**——包括 `killed/motion_disabled_fail_closed/no_odom/odom_frame_mismatch/invalid_map_orientation/no_trajectory/trajectory_max_age/trajectory_stale/frame_mismatch/no_fresh_fcu_yaw/invalid_body_command/slam_frozen`。`slam_frozen` 从连续非零命令或当前航点的 epoch 起算,连续 8s 内相对 epoch 起点的最大位移仍不足 2cm 才闩锁;不再用窗口首尾净位移,避免把换航点后的制动回撤误判为冻结。新轨迹或显式重新使能才可恢复。五条达成即闩锁,尾段轨迹变陈旧不回撤已达成事实。特别地,成功闩锁后 `/gbp/enable=false` 是撤销运动 lease、让 FCU 独占返航/LAND 的预期安全收尾;此后 `motion_disabled/trajectory_max_age/slam_frozen` 等只写入 `post_gate_blockers` 供诊断,不得反向把已完成 gate 标成 blocked。显式 `killed` 仍保留在 acceptance blockers 中。

**fail-closed 纪律**:默认 disabled,须向 `/gbp/enable` 发 `Bool(true)` 才动;`/gbp/kill` 一票永久禁;限速 `SPEED_MAX=0.08`、`YAW_RATE_MAX=0.30`;active trajectory 最长 120s,跟完后 15s 无新轨迹则 hold;trajectory 必须是 `map`,odom 必须是 `map→base_link`,两者任一不符都不运动。

**P1-2 实跑证据(2026-08-24)**:`20260824T075515.387084602Z` 固定
GBPlanner `887a420` 与 WorldModel `fd4296f`,adapter 只计入 3 个真实运动到达,
path=4.0871m,gate 最终 `blockers=[]`。FCU 实测返航到 0.32648m(<0.35m),
随后观测到 LAND ACK accepted、LAND mode、touchdown、disarm 和 motors-safe;
同一 run 的 summary 为 `TASK_STATUS_OK`,acceptance rc=0。该证据完成直连闭环,
不代表 M5-c 的多 run/oracle/frontier_lite 对比已完成。

---

## 2. ROS2 原生 GBPlanner 接入蓝图

桥接期已验证的链路(stage2.6/3.5/4/5 系列证据)换成 ROS2 原生后,数据流收缩为:

```
/slam/odom ──────────────┐
                          ├─→ [ROS2 gbplanner_node + voxblox] ─→ [ROS2 pci] ─→ /gbp/trajectory
wm/cloud3d(3D 点云)────┘                                                        │
                                                                                  ▼
                                                    trajectory_to_intent_stage4.py(零改动)
                                                                                  │
                                              /navlab/fcu/setpoint/intent + /navlab/exploration/status
                                                                                  │
                                                                   fcu_controller(平台自带,不动)
```

### 2.1 接口表(逐个标注消息类型/frame/频率/QoS)

| # | 接口 | 消息类型 | frame | 频率 | QoS/备注 |
|---|---|---|---|---|---|
| 1 | `/slam/odom`(输入,直订) | `nav_msgs/Odometry` | `map` → child `base_link` | 连续(桥接期实测 run 收 604+ 条) | 订阅端用 `qos_profile_sensor_data`(适配器 L96、workflow 模板 L68 同款);ROS2 原生 gbplanner 把 `odometry` remap 到它,替代桥接期 `/wm/odom` |
| 2 | `wm/cloud3d`(输入,3D 点云) | `sensor_msgs/PointCloud2` | `lidar3d_frame`(SDF `gz_frame_id`,patch_lidar3d.py L55) | 5Hz(`update_rate`,L59) | 来源:我们加的 net-new 3D lidar(360×30 线,±30°,0.3–10m;`runbooks/world-model-jazzy/patch_lidar3d.py` L54-88),gz 话题 `/lidar3d/points` 经 ros_gz_bridge 出 ROS(patch B,L101-107;桥模板本体 `templates/yaml/bridge_override.yaml.tmpl`,cloud_in 前例在 L37-41)。voxblox 的 `pointcloud`/`cloud_in` 直订它,替代桥接期 `/wm/points` |
| 3 | TF:`map(world)→base_link` | tf2 | — | 与 odom 同步 | ROS1 桥接期由薄桥从 `/wm/odom` 广播 + `wm_planner.launch` 补静态 TF(L18-19:`world→navigation`、`base_link→…/velodyne`);ROS2 原生版需等效提供:从 `/slam/odom` 广播动态 TF,外加 `base_link→lidar3d_frame` 静态 TF(SDF 里传感器挂 base_link 上方 0.10m,patch_lidar3d.py L42) |
| 4 | `/gbp/trajectory`(输出) | `trajectory_msgs/MultiDOFJointTrajectory` | `map`(适配器 frame 校验 L189-190) | 事件式:每次规划触发一条(桥接期实测 19 条/run,stage26_evidence) | ROS1 版发布者是 pci 的 `command/trajectory`(`integration/ros1_bridge/wm_planner.launch:33` remap);ROS2 版保持同型同 frame 发到 `/gbp/trajectory` 即可。**粉线纪律:只接 pci 输出,绝不接 `/vis/*` 可视化话题**(发布者=pci 已实证) |
| 5 | `/navlab/fcu/setpoint/intent`(适配器→fcu) | `std_msgs/String`(JSON) | 速度语义:机体系 FRD;adapter 用 map→base_link yaw 把 map 速度转为 forward/right | 4Hz | 必须不低于 controller 的 `dt<=0.25s` 积分契约;downstream FCU yaw 由 `/mavlink_external_nav/status.fcu_attitude_age_ms` 证明 fresh;契约字段见 §1.3;depth 10 |
| 6 | `/navlab/exploration/status`(适配器→gate/landing) | `std_msgs/String`(JSON) | — | 4Hz 同拍 | `ok` 是 landing 扳机,见 §1.2b |
| 7 | `/gbp/enable`、`/gbp/kill`(操作面) | `std_msgs/Bool` | — | 一次性 | fail-closed 开关(适配器 L98-99) |
| 8 | `/navlab/fcu/controller/status`(适配器输入) | `std_msgs/String` | — | ~20Hz(fcu 主循环 L488-537,0.05s) | takeoff ready 证据(适配器 L100) |
| 9 | `/navlab/fcu/local_position_pose`(适配器输入) | `geometry_msgs/PoseStamped` | AP LOCAL_NED | 连续 | 提供 downstream 实际使用的 FCU NED yaw;adapter 同时以 status 校验其 ATTITUDE 源年龄 |

### 2.2 planner 栈本体(ROS1→ROS2 对应物)

桥接期的 `wm_planner.launch`(`integration/ros1_bridge/wm_planner.launch`)就是移植清单:gbplanner_node(odometry+pointcloud 两个输入 remap,L24-29)、voxblox(config 三件套 L12-15)、pci(L32-38,输出 command/trajectory + 两个 planner service)。ROS2 版需要等效的 launch:同样两个输入 remap(→ `/slam/odom`、`wm/cloud3d`)、同样的输出话题(→ `/gbp/trajectory`)、`automatic_planning` 服务(ROS1 是 `rosservice call /planner_control_interface/std_srvs/automatic_planning`,见 `runbooks/world-model-jazzy/stage5c_run.sh:42-46`;ROS2 对应 `ros2 service call`,或直接开 pci 自动模式免手动触发)。

**时钟**:桥接期 `use_sim_time=false` + 薄桥重打时间戳是为了 ROS1 侧 wall clock 自洽(wm_planner.launch L4-6、L10);ROS2 原生后应改回 `use_sim_time:=true` 直接吃 world-model 的 `/clock`(bridge_override.yaml.tmpl L2-6 有 clock 桥),时间戳不再需要任何改写。

### 2.3 适配器为什么零改动

适配器的输入输出全部是 ROS2 话题(它本来就跑在 jazzy 容器里,stage5c_run.sh L30-32),桥接期它的上游 `/gbp/trajectory` 是薄桥代发的;换成 ROS2 原生 pci 直发后,消息类型(`MultiDOFJointTrajectory`)、frame(`map`)、语义(waypoint 序列)都不变——适配器感知不到上游从"桥"换成了"原生节点"。唯一要确认的是原生 pci 发出的 `header.frame_id` 必须是 `map`(或改 launch remap/配置对齐),否则适配器 `frame_mismatch` blocker 拦截(L189-190)。

### 2.4 R_align 已退出控制链

第五次 M5 run `20260824T052332.574642383Z` 中,强制 det=+1 的单向量估计从
80° 漂到 172°、-150°、-75°,飞机移动 1.3911m 仍未到首航点。与第四次 bag
交叉核验后,位置数值关系近似 `NED=(map_y,map_x)`(det=-1),所以旧算法并非参数不佳,
而是模型类型错误。当前 adapter 使用标准姿态变换:
`forward=cosψ·vx_map+sinψ·vy_map`,`right=sinψ·vx_map-cosψ·vy_map`,其中
`ψ` 来自 `/slam/odom` 的 map→base_link orientation。fcu_controller 再用 fresh FCU
yaw 将 body FRD 转到 NED。任何 map 姿态无效或 FCU yaw 超龄时必须停住。

---

## 3. 与桥接期的差异清单(ROS2 原生后不再需要的东西)

| 桥接期组件 | 位置 | ROS2 原生后 |
|---|---|---|
| 自写薄桥两侧脚本(TCP:7601、3s ping 心跳、accept-timeout continue 修复) | `integration/ros1_bridge/thinbridge_ros1_side.py` / `thinbridge_ros2_side.py` | **删除**。DDS 原生互通,无 TCP 中转 |
| ROS1 noetic 容器 `gbplanner_ref`(roscore + gbp_ws)及 `docker exec` 包装 `E()` | `stage5c_run.sh:14`、L25 | **删除**。planner 栈跑进 jazzy 容器/宿主 |
| `/wm/odom`、`/wm/points` 中转话题 + 薄桥时间戳重写 | wm_planner.launch L21、L26 | **删除**。直订 `/slam/odom`、`wm/cloud3d` |
| 薄桥 TF 广播(world→base_link from /wm/odom) | thinbridge ROS1 侧 | **由 ROS2 节点自广播**(或 planner 直接用 odom 取位姿) |
| `use_sim_time=false` wall-clock 解耦 | wm_planner.launch L10 | **改回 sim time**,吃 `/clock` |
| ROS1 `rosservice call automatic_planning` 触发 | stage5c_run.sh L42-46 | **`ros2 service call`** 或 pci 自动模式 |
| 官方 ros1_bridge / zenoh 桥的判死结论(jazzy→foxy RMW bad_alloc;rosrust header mismatch) | 桥接查证文档 | **不再相关**(历史归档) |
| TCP 断连/重连监控与证据脚本 | stage2e~2k 系列 | **删除** |

**保留项(不是桥的锅,别顺手删)**:
- jazzy `ros2 topic echo` CLI 对 rclpy 发布者收不到的工具坑(stage2i 矩阵:rclpy→rclpy 60/60,rclpy→CLI 0)——**验收一律 rclpy 订阅**;
- DDS 慢发现(后加入订阅对 ArduPilot micro-ROS agent 匹配可达 ~29s)——probe 等待预算与容器时序不要收紧;
- 适配器全部 fail-closed 纪律与 body-frame 映射(§2.4);
- B15 门(fcu 起飞前不下发)、B16 probe 预算——都在 clean 分支主线里。

---

## 4. 迁移验收建议:M5 直连联跑复用哪些既有 harness

原则:**判定口径一个字不改,只把"桥"从被测系统里抽走**——这样 M5 的结果能与桥接期 5c 基线直接同表对比。

### 4.1 `stage5c_run.sh` 去桥版(建议命名 `m5_run.sh`)

以 `runbooks/world-model-jazzy/stage5c_run.sh` 为底,逐行改造:

**删**:
- L14 `E()`(ROS1 容器执行包装)、L25(thinbridge ROS1 侧)、L27-29(`thin_ros2` 容器);
- L23-24 `docker restart gbplanner_ref` + sleep(换成启动 ROS2 planner 栈容器)。

**换**:
- L42-46 三次 `rosservice call …/automatic_planning` → `ros2 service call`(同样保留三次触发节奏与 15s 间隔,或 pci 自动模式后整段删除);

**原样保留(这是验收的骨架)**:
- L16-17、L21:`sed` 把 exploration.yaml `strategy` 切到 `external` + `trap` 还原(配置入口不变);
- L30-32:`s4_adapter` 容器跑 `trajectory_to_intent_stage4.py`(零改动,§2.3);
- L33-35:`s5c_probe` 容器(rclpy 订阅式探针,规避 CLI 坑);
- L38:`go run ./cmd/navlab-sim run exploration --live-preflight`(被测系统入口不变);
- L41:`/gbp/enable` 使能(fail-closed 纪律不变);
- L50-67 判定段全部复用:`summary.json` 的 `task_status` + `gate.exploration` 七字段(对应 gate_evaluation.go:223-226)、`required probes failed` 抓取、`s4_adapter` 日志的 `GATE OK`/`WP REACHED` 计数、`s5c_probe` 的 §7.3 对齐表。

### 4.2 验收阶梯(复用既有口径,逐级升压)

1. **M5-smoke(= stage4c 口径)**:先按 `stage4c_external.sh` 的验收跑一遍——窗口内无任何 `source=exploration_workflow` 的 intent(去混流)+ intent 带 GBP 签名 + takeoff ok + odom path 增长 ≥0.10m 可归因;证据文件对标 `stage4c_external_evidence.txt`;
2. **M5-gate(= stage5a 口径)**:适配器五条件闩锁 `GATE OK latched`(§1.3)+ run 级 `TASK_STATUS_OK`、blockers 空;对标 `stage5a_gate_evidence*.txt`;诊断参考 `runbooks/world-model-jazzy/stage5a_diagnosis.md`;
3. **M5-batch(= stage5c 口径)**:同口径 ≥6 run(对标 v2 批跑的冻结口径),逐 run 指标表(accepted_goals/path/GATE OK/probe 结果),与 frontier_lite 基线(EKF 修复后 6-run)和桥接版 GBPlanner 批跑同表三方对比;
4. **3D 对照(可选,= stage5b 口径)**:lidar3d FOV ±30° vs ±5° 双跑,验证 trajectory 真随 3D 输入变化。

### 4.3 已知坑位提醒(全部有既有证据可查)

- probe 时限:exploration_probe 外层 90s(runtime_specs.go:277-279)、String 采样 35s(Spec `ProbeTimeoutSec`);ROS2 planner 栈启动慢的话把它拉起放在 `navlab-sim run` 之前(stage5c_run.sh 的容器先行启动顺序就是为此);
- `ok=true` 即触发 landing(§1.2b):新栈调试期先别让适配器 latch(不发 `/gbp/enable` 即可,fail-closed 天然挡住);
- 混流闩锁是单向的:只要 workflow 让位不彻底(external 分支没生效、yaml 没切到 external、或还原 trap 提前触发),`mixed_flow` 一旦置位整个 run 作废——跑前用 `stage4c_envcheck.sh` 同款检查确认模板补丁与 yaml 状态;
- 频率适配:pci 事件式 one-shot 出轨迹,adapter 只保留最新一条且以 4Hz 生成 intent。WorldModel controller 每条 intent 的积分 `dt` 上限为 0.25s,低于 4Hz 会按比例丢失目标推进速度。active trajectory 最长 120s,覆盖 90s 验收窗;跟完后 15s 无新轨迹才 hold。

---

## 附:本文引用的关键文件清单

| 文件 | 角色 |
|---|---|
| `sources/world-model-源码/orchestration/sim/configs/tasks/exploration.yaml` | 策略配置入口(L20) |
| `…/internal/config/types.go` | ExplorationGateConfig(L430+) |
| `…/internal/tasks/runtime_artifacts.go` | spec 映射(L834-848)、landing 联动接线(L162-168) |
| `…/internal/tasks/helpers/runtime_specs.go` | ExplorationWorkflowSpec 与默认值(L1098-1128)、probe/脚本生成(L1137-1169) |
| `…/internal/tasks/helpers/execution_plan.go` | workflow 容器与 probe 计划(L489-540) |
| `…/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl` | 策略运行时(frontier_lite 契约;WSL clean 分支 L86-96 为 external 分支) |
| `…/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl` | intent 消费双路(L357-441)、task_completion→landing(L340-355、L516-524) |
| `…/internal/tasks/helpers/templates/python/ros_probe.py.tmpl` | probe ok 判定(L58-64、L313-314) |
| `…/internal/tasks/gate_evaluation.go` | gate blockers(L101-143)、exploration 摘要(L223-226) |
| `…/internal/tasks/helpers/rosbag_topic_sets.go` | 必录/回放话题(L70-99) |
| `integration/ros1_bridge/trajectory_to_intent_stage4.py` | 外部策略的现成出口(五条件 L294-304;契约 L284-321) |
| `integration/ros1_bridge/wm_planner.launch` | ROS1 planner 栈=移植清单 |
| `runbooks/world-model-jazzy/patch_external_strategy.py` | external 分支补丁 |
| `runbooks/world-model-jazzy/patch_lidar3d.py` | 3D lidar + 点云桥补丁 |
| `runbooks/world-model-jazzy/stage5c_run.sh` | M5 验收 harness 底版 |
