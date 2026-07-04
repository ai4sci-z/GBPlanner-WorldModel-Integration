# NavLab 统一降落流程设计

## 1. 背景

当前 hover / exploration / scan robustness 的完成口径更偏向“任务动作已经完成”：

```text
takeoff
  -> hover / motion / exploration / scan robustness
  -> final hold / final stop
  -> summary
```

这个口径对仿真调试够用，但对真机不够。现实任务不能只起飞和悬停；只要飞机离地，任务结束必须包含一个可观测、可验收、可回放的降落过程。

因此后续所有 built-in flight task 都应统一成：

```text
takeoff
  -> task body
  -> task finalization
  -> landing sequence
  -> landed + disarmed + motors safe
  -> summary
```

也就是说，acceptance 的完成条件不再是“最后 hover 住了”或“最后 stop 住了”，而是“已经安全降落并解除武装”。

## 2. 目标

统一降落流程要回答：

> 每个 built-in flight task 在完成自身目标后，是否能用同一套安全边界进入降落，并证明飞机最终处于 landed / disarmed / motors safe 状态？

核心目标：

- hover 任务：起飞、悬停、原地降落。
- P8 exploration：探索结束后先返回起飞原点附近，再降落。
- P12 scan robustness：扰动/scan 鲁棒性评价结束后在当前位置直接降落。
- 所有任务使用同一个 landing state machine 和 summary schema。
- 降落仍由唯一 FCU controller / FCU mode owner 执行，不新增第二个 `/ap/v1/cmd_vel` owner。
- Gazebo truth 只能作为诊断对照，不能作为降落控制、返航控制或 touchdown 判定的唯一来源。

## 2.1 P12 Runtime Contract 是前向标准

统一降落不是给 hover 单独做一条更弱的起降链路。当前实现应以后续已经完整跑通过的 P12 runtime contract 为标准，向前改造 hover 和 P8。

P12 已经证明过同一套 runtime 能完成：

```text
bootstrap
  -> SLAM / ExternalNav / FCU readiness
  -> hover-capable stabilized flight
  -> motion-capable task body
  -> scan robustness evaluation
```

因此 hover 起不来时，优先判断为“hover 还没有迁移到 P12 的完整 bootstrap / SLAM / ExternalNav / FCU contract”，而不是降低 hover 的 readiness 或改弱 Cartographer 配置。hover 只是最小 task body，不是最小 runtime contract。

统一原则：

- P12 的传感器、SLAM、ExternalNav、FCU readiness 口径是 built-in flight task 的收敛目标。
- hover 必须复用 P12/P8 的标准启动链路，只把 task body 缩短为起飞、悬停、原地降落。
- P8 必须复用同一标准启动链路，只在 task body 后增加 return-home intent。
- 不允许为了让 hover 先通过而关闭 P12/official baseline 依赖项，例如绕开标准 `/odometry`、降低 ExternalNav readiness、跳过 FCU local-position gate。
- 如果 hover 与 P12 的 runtime config 不一致，修 hover 的缺口；如果确实发现 P12 contract 过严或错误，必须先用 P12/P8 级别 artifact 证明，再统一修改所有 built-in flight task。

这也意味着 Stage 1 hover landing acceptance 的目标不是“能用任意简化链路起飞降落”，而是“P12 级别 runtime contract 下的最小 hover task 也能完成起飞、悬停、降落”。

## 2.2 Stage 1 必须覆盖 ideal 和 mild disturbance

Gazebo/SITL Stage 1 不是单一 nominal run。后续每个 built-in flight task 至少要有两类仿真 profile：

| simulation profile | 目的 | 通过含义 |
|---|---|---|
| `ideal` | 无额外 airframe disturbance 的标准 Gazebo/SITL | 证明 runtime、task body、landing sequence 的基础链路正确 |
| `realistic` | 轻量 P12 风格 disturbance，例如 mild motor bias / ESC lag / vibration 的保守组合 | 证明同一 task 在轻微倾斜或执行器扰动下仍能完成任务结束和安全降落 |

Stage 1 的完成条件必须按 task/profile 矩阵判定：

```text
hover:             ideal pass + realistic pass
exploration / P8:  ideal pass + realistic pass
scan-robustness:   ideal pass + realistic pass + configured P12 robustness profiles
```

其中 `ideal` 不能替代 `realistic`，`realistic` 也不能替代 `ideal`。ideal 用来隔离基础链路问题，mild disturbance 用来避免 hover/P8 只在理想电机下通过、到了 P12 风格倾斜或扰动就失败。

summary 应显式记录当前仿真 profile，例如：

```json
{
  "acceptance_stage": "simulation",
  "simulation_profile": "realistic",
  "simulation_landing_claim": "evaluated",
  "real_landing_claim": "not_evaluated"
}
```

Go sim 的 task-level matrix 由 `navlab-sim stage1-matrix <task-id>` 生成。该命令消费多个 profile run 的 `summary.json`：

```bash
navlab-sim stage1-matrix hover \
  --summary artifacts/sim/hover/ideal/summary.json \
  --summary artifacts/sim/hover/realistic/summary.json \
  --output artifacts/sim/hover/stage1_profile_matrix.json
```

输出 schema 为 `navlab.orchestration.stage1_profile_matrix.v1`，必须包含 `required_profiles`、每个 profile 的 `artifact_dir` / `summary_path` / `ok` / `landing_claim` / `simulation_landing_claim`，并在任一 required profile 缺失或未通过时 `blocked=true`。

真机 Stage 2 的入口条件也要检查对应 task 的 Stage 1 profile matrix 已全部通过，而不是只检查某一个 Gazebo/SITL run。

## 3. 不做什么

- 不用 Gazebo `set_pose`、model reset 或 world reset 代替降落。
- 不让 exploration coordinator 或 scan robustness workflow 直接发布 `/ap/v1/cmd_vel`。
- 不把 final hover / final stop 当作任务完成。
- 不为了 hover 单独降低 P12 已经跑通的 SLAM / ExternalNav / FCU readiness 标准。
- 不把 ideal Gazebo 通过当作完整 Stage 1；mild disturbance 也必须通过。
- 不要求 P12 在扰动 profile 后再返航；P12 的完成动作是原地降落。
- 不把真机无法使用的 Gazebo contact/truth 当作唯一 touchdown 判据。
- 不在降落失败时静默标记 acceptance 通过。

## 4. Landing Policy

每个 flight task 必须显式选择 landing policy：

| task | landing policy | 行为 |
|---|---|---|
| `hover` | `land_in_place` | 悬停窗口结束后当前位置降落 |
| `exploration` / P8 | `return_home_then_land` | 返回 home pose 附近，稳定 hover 后降落 |
| `scan-robustness` / P12 | `land_in_place` | 当前扰动评价位置直接降落 |

建议配置：

```toml
[orchestration.landing]
enabled = true
default_policy = "land_in_place"
home_source = "post_takeoff_hover_pose"
home_radius_m = 0.35
pre_land_hold_sec = 2.0
max_return_home_duration_sec = 45.0
max_landing_duration_sec = 35.0
max_descent_rate_mps = 0.6
touchdown_altitude_m = 0.12
touchdown_vertical_speed_mps = 0.08
require_disarm = true
require_motors_safe = true
```

P8 可覆盖：

```toml
[orchestration.exploration_gate.landing]
policy = "return_home_then_land"
```

P12 可覆盖：

```toml
[orchestration.airframe_disturbance_gate.landing]
policy = "land_in_place"
```

## 5. Home Pose 定义

P8 需要“返回原点再降落”，这里的原点不是 Gazebo truth 中的 model pose，而是任务内部可用的 home pose。

建议 home pose 捕获时机：

```text
takeoff complete
  -> hover settle ok
  -> SLAM / ExternalNav / FCU local position healthy
  -> sample home pose
```

home pose 来源优先级：

1. FCU local pose / official equivalent filtered pose。
2. SLAM odom 在当前 mission frame 下的 pose。
3. 只作为诊断记录的 Gazebo truth pose。

正式返航控制不能用 Gazebo truth 作为目标来源。summary 可以同时记录 truth diagnostic，用来判断 sim 中返航误差，但不能把 truth 误差作为唯一通过条件。

home pose summary 示例：

```json
{
  "home_pose": {
    "source": "fcu_filtered_pose",
    "frame_id": "map",
    "x": 0.0,
    "y": 0.0,
    "z": 1.2,
    "yaw": 0.0,
    "sampled_after": "hover_settle",
    "uses_gazebo_truth_as_input": false
  }
}
```

## 6. 统一 Landing State Machine

所有任务复用同一套状态：

```text
task_body_complete
  -> landing_requested
  -> return_home_start?          # only return_home_then_land
  -> return_home_active?
  -> return_home_hold?
  -> pre_land_hold
  -> land_command_sent
  -> descent_monitoring
  -> touchdown_candidate
  -> landed_confirmed
  -> disarm_requested
  -> disarmed_confirmed
  -> motors_safe_confirmed
  -> landing_complete
```

失败状态：

```text
return_home_timeout
return_home_off_track
landing_command_rejected
descent_timeout
touchdown_not_confirmed
disarm_failed
motors_not_safe
landing_failsafe_triggered
landing_blocked
```

### 6.1 `land_in_place`

适用于 hover 和 P12：

```text
task_body_complete
  -> pre_land_hold
  -> land_command_sent
  -> descent_monitoring
  -> landed_confirmed
  -> disarmed_confirmed
  -> motors_safe_confirmed
```

P12 选择原地降落的原因：

- P12 评价的是扰动下 scan/SLAM contract，不是探索返航能力。
- 扰动 profile 后继续返航会引入新的 motion/exploration 变量，容易混淆 P12 判定。
- 真机上在扰动/异常风险较高时，保守策略应优先原地安全降落。

### 6.2 `return_home_then_land`

适用于 P8：

```text
exploration_complete
  -> stop exploration intent
  -> return_home intent
  -> bounded motion back to home pose
  -> home_radius hold
  -> pre_land_hold
  -> land_command_sent
  -> descent_monitoring
  -> landed_confirmed
  -> disarmed_confirmed
  -> motors_safe_confirmed
```

P8 选择返原点再降落的原因：

- exploration 是主动移动任务，任务结束点可能在 corridor / wall 附近。
- 返回 home pose 可以把“探索完成”和“安全收尾”变成可复现流程。
- Foxglove 回放中能清楚看到完整任务闭环：起飞、探索、返航、降落。

如果 P8 return home 失败，不能直接把 acceptance 标记通过。可以进入 emergency land-in-place，但 summary 必须记录：

```json
{
  "return_home": {
    "ok": false,
    "fallback_landing_policy": "emergency_land_in_place"
  },
  "landing": {
    "ok": true
  },
  "ok": false
}
```

这表示飞机安全落地了，但 P8 任务没有完整通过。

## 7. 控制边界

统一降落流程仍然遵守现有控制边界：

```text
task workflow / coordinator
  -> landing intent / return-home intent
  -> unique FCU controller
  -> official FCU command route
  -> FCU LAND / guided descent / disarm
```

禁止：

- workflow 直接发布 `/ap/v1/cmd_vel`。
- workflow 直接调用 Gazebo API 移动飞机。
- landing helper 绕过 FCU controller 直接抢占 setpoint owner。
- return home 使用 Gazebo truth 作为导航目标。

唯一允许直接控制飞机的组件仍是 FCU controller 或官方等价控制服务。

## 8. Landing Intent / Status Schema

建议新增或固化：

```text
/navlab/landing/intent
/navlab/landing/status
```

如果不新增 topic，也必须在现有 FCU controller status / task summary 中表达同等字段。

`landing/intent` 示例：

```json
{
  "task": "exploration",
  "policy": "return_home_then_land",
  "home_pose_source": "fcu_filtered_pose",
  "require_disarm": true,
  "reason": "task_body_complete"
}
```

`landing/status` 示例：

```json
{
  "state": "descent_monitoring",
  "policy": "land_in_place",
  "land_command_sent": true,
  "land_command_accepted": true,
  "altitude_m": 0.42,
  "vertical_speed_mps": -0.28,
  "touchdown_candidate": false,
  "landed": false,
  "armed": true,
  "motors_safe": false,
  "blockers": []
}
```

## 9. Touchdown / Landed 判定

真机和仿真都不能只靠单一信号。建议至少组合：

- FCU landed state 或 equivalent status。
- armed state 变为 false。
- rangefinder altitude 低于阈值并稳定。
- vertical speed 接近 0。
- command/state machine 进入 landing complete。
- motor output / actuator 状态进入 safe 或低输出。

仿真可额外记录 Gazebo contact / truth altitude 作为 diagnostic，但不能用它单独让 gate 通过。

通过条件示例：

```text
land_command_accepted == true
landing_duration_sec <= max_landing_duration_sec
rangefinder_altitude_m <= touchdown_altitude_m
abs(vertical_speed_mps) <= touchdown_vertical_speed_mps
armed == false
motors_safe == true
uses_gazebo_truth_as_input == false
```

## 10. Summary Schema

所有 flight task summary 增加：

```json
{
  "landing_claim": "evaluated",
  "landing": {
    "ok": true,
    "policy": "return_home_then_land",
    "state": "landing_complete",
    "home_pose_source": "fcu_filtered_pose",
    "return_home": {
      "required": true,
      "ok": true,
      "distance_to_home_m": 0.18,
      "duration_sec": 22.4
    },
    "land_command_accepted": true,
    "landing_duration_sec": 18.2,
    "touchdown_confirmed": true,
    "disarmed": true,
    "motors_safe": true,
    "uses_gazebo_truth_as_input": false,
    "blockers": []
  }
}
```

hover / P12 的 `return_home.required` 为 `false`。

如果任务 body 成功但 landing 失败：

```text
task_body.ok == true
landing.ok == false
summary.ok == false
```

如果 return home 失败但 emergency land-in-place 成功：

```text
return_home.ok == false
landing.ok == true
summary.ok == false
```

这保证“安全落地”和“任务完整通过”不会被混为一谈。

## 11. Rosbag Profile

所有 flight acceptance rosbag profile 应加入 landing 相关 required topic：

```text
required /navlab/landing/status
required /navlab/fcu/controller/status
required /ap/v1/status
required /ap/v1/pose/filtered
required /rangefinder/down/range
optional /navlab/landing/intent
optional /navlab/fcu/setpoint/intent
optional /navlab/fcu/setpoint/output
optional /odometry                         # diagnostic only in simulation
```

P8 额外需要：

```text
required /navlab/exploration/status
required /navlab/motion/status
```

P12 额外需要：

```text
required /navlab/airframe_disturbance/status
required /navlab/scan_stabilization/status
```

## 12. Real vs Sim 分流

### Simulation

simulation mode 可以记录更多 diagnostic：

- Gazebo truth altitude。
- contact/collision。
- model pose。
- simulated motor output。

但 simulation 降落仍必须走 FCU 控制路径，不允许用 Gazebo reset 代替。

### Real

real mode 必须更保守：

- 不允许自动返航穿越未知区域，除非 P8 return home safety gate 明确通过。
- landing command 必须走 FCU 支持的 LAND / guided descent / official equivalent。
- touchdown 判定优先用 FCU landed state、rangefinder、armed state 和 motor state。
- landing 失败时必须保留人工接管/kill switch 的操作边界，但 acceptance summary 仍标记失败。

## 13. 两阶段验收

统一降落流程必须分成两个阶段验收，顺序不能反过来：

```text
Stage 1: Gazebo/SITL acceptance
  -> hover / P8 / P12 landing policies all pass in simulation
  -> logs, rosbag, summary, blocker schema stable
  -> no Gazebo reset / set_pose / truth-control path

Stage 2: Real-machine acceptance
  -> only starts after Stage 1 passes
  -> same landing policy and summary schema
  -> stricter operator safety and manual takeover boundaries
```

### 13.1 Stage 1：Gazebo/SITL 验收

Stage 1 是所有任务的强制前置。任何真机测试前，必须先在 Gazebo/SITL 中完成：

- hover：`land_in_place` 通过。
- P8：`return_home_then_land` 通过。
- P12：`land_in_place` 通过。
- summary 中 `landing_claim=evaluated`。
- rosbag 可回放完整起飞、任务、返航或原地降落、解除武装。
- `uses_gazebo_truth_as_input=false`。
- 没有 Gazebo reset / direct set pose / truth-control shortcut。

Stage 1 允许使用 Gazebo truth、contact、model pose 做诊断，但只能写入 diagnostic 字段，不能参与控制、规划、返航目标、touchdown 通过判定。

Stage 1 summary 建议增加：

```json
{
  "acceptance_stage": "simulation",
  "simulation_landing_acceptance": {
    "ok": true,
    "backend": "docker",
    "runtime_mode": "simulation",
    "uses_gazebo_truth_as_input": false
  },
  "real_landing_acceptance": {
    "ok": false,
    "state": "not_started",
    "blocked_by": "simulation_acceptance_required"
  }
}
```

### 13.2 Stage 2：真机验收

Stage 2 只能在对应任务的 Stage 1 通过后开始。真机验收不是复用 Gazebo 成功结果，而是用同一套 landing policy / status / summary schema 在真实硬件上重新验证。

每次真机飞行前还必须先通过独立 real preflight doctor，设计见
`docs/scenarios/indoor/navlab_real_flight_preflight_doctor_design.md`。real preflight
doctor 只检查 `process + real` runtime 边界、真实 topic/source 和 operator safety
前置条件，不 arm、不 takeoff、不发布 movement setpoint。真机 flight task 必须引用
最新通过的 real preflight summary，不能用 `just navlab-hover` 的 Gazebo/SITL 结果或
X2 virtual serial 路径替代。

真机前置条件：

- 对应任务的 Stage 1 summary `ok=true`。
- Stage 1 rosbag 和 summary 已归档。
- real preflight doctor summary `ok=true`，且未超过有效窗口。
- 操作者确认安全场地、保护措施、manual takeover / kill switch。
- landing command 使用 FCU 支持的 LAND / guided descent / official equivalent。

Stage 2 summary 建议增加：

```json
{
  "acceptance_stage": "real",
  "simulation_landing_acceptance": {
    "ok": true,
    "artifact": "artifacts/..."
  },
  "real_landing_acceptance": {
    "ok": true,
    "runtime_mode": "real",
    "manual_takeover_available": true,
    "landing": {
      "ok": true,
      "touchdown_confirmed": true,
      "disarmed": true,
      "motors_safe": true
    }
  }
}
```

如果 Stage 1 未通过，Stage 2 必须 blocked：

```json
{
  "real_landing_acceptance": {
    "ok": false,
    "state": "blocked",
    "blockers": ["simulation_landing_acceptance_not_passed"]
  }
}
```

### 13.3 完成口径

任务的 landing 能力最终完成需要两个结论分开记录：

| claim | 含义 |
|---|---|
| `simulation_landing_claim=evaluated` | Gazebo/SITL 中已证明流程和 gate 语义 |
| `real_landing_claim=evaluated` | 真机中已证明同一流程可安全执行 |

Stage 1 通过不等于真机通过；Stage 2 未做时，真实能力必须标记为 `not_evaluated`。

## 14. 对各任务的影响

### Hover

当前 hover 不应只证明起飞和悬停，还要证明：

```text
takeoff -> hover hold -> land in place -> disarm
```

完成后 summary：

```json
{
  "hover_claim": "evaluated",
  "landing_claim": "evaluated",
  "landing": {
    "policy": "land_in_place",
    "ok": true
  }
}
```

### P8 Exploration

P8 任务完成顺序变成：

```text
takeoff
  -> hover ready
  -> motion ready
  -> exploration
  -> exploration complete
  -> return home
  -> home hold
  -> land
  -> disarm
```

P8 不再把 `final_hover` 当作完整成功。`final_hover` 只是进入 return-home/landing 前的中间状态。

### P12 Scan Robustness

P12 任务完成顺序变成：

```text
takeoff / replay setup
  -> disturbed scan robustness evaluation
  -> final hold / stop
  -> land in place
  -> disarm
```

P12 不要求返回 home，因为它不是 exploration mission。P12 的重点是扰动下 scan/SLAM contract；结束时当前位置安全降落即可。

## 15. 实现跟踪

实现任务、阶段验收和测试清单单独维护在：

- `docs/scenarios/indoor/todos/unified_landing_sequence_todo.md`
