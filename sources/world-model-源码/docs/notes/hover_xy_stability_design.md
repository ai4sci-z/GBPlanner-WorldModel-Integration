# Hover XY Stability Design Note

Date: 2026-06-23

## 背景

当前 hover FSM / landing pipeline 已经能完成任务体：

- `artifacts/sim/hover/20260623T090519Z/mission_summary.json`
  - `ok=true`
  - `mission_phase_state=S13 task_success`
  - `landing.ok=true`
  - `landing.blockers=[]`
- `artifacts/sim/hover/20260623T090829Z/mission_summary.json`
  - `ok=true`
  - `mission_phase_state=S13 task_success`
  - `landing.ok=true`
  - `landing.blockers=[]`

但是顶层 gate 在这两轮仍然 blocked：

- `hover_gazebo_model_horizontal_drift`
- `hover_xy_alignment_direction_mismatch`
- `hover_xy_evidence_disagreement`

这个问题不要和之前修复的 Foxglove replay `/scan`、`/map` display TF 混在一起。之前的修复主要解决 replay/display 坐标映射和 gate 对 ROS odometry topic 的错误投影；现在的问题是 live hover 窗口内多源 XY 证据实际漂移过大或方向不一致。

## 关键事实

三轮 run 使用相同 run config：

- `control_mode=hover_ideal`
- `gazebo_direct_pose=false`
- `simulation_profile=ideal`
- `stage_gate=hover`

通过轮：

| Run | Status | Gazebo drift | external_nav drift | SLAM corrected drift | FCU local drift | Mission |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `20260623T081943Z` | `TASK_STATUS_OK` | `0.069m` | `0.081m` | `0.099m` | `0.055m` | `S13 task_success` |

失败轮：

| Run | Status | Gazebo drift | external_nav drift | SLAM corrected drift | FCU local drift | Mission |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `20260623T090519Z` | `TASK_STATUS_BLOCKED` | `0.574m` | `0.488m` | `0.306m` | `0.143m` | `S13 task_success` |
| `20260623T090829Z` | `TASK_STATUS_BLOCKED` | `0.193m` | `0.340m` | `0.354m` | `0.137m` | `S13 task_success` |

结论：

- 不是阈值或 run config 突然变了。
- 不是 FSM / landing refactor 直接失败。
- 不是“每次 SLAM 都应该有这么大差异”。
- 是当前 live hover 稳定性没有被硬性控制到真机可用级别，且 SLAM/external_nav 偶发 jump 会污染 hover XY evidence。

## 不再混淆的三个问题

### 1. Replay/display TF 问题

症状：

- Foxglove 中 `/scan`、`/map` 看起来镜像、错位、叠图异常。

性质：

- 主要是 replay display TF、topic frame、Foxglove 可视化和 overlay 顺序问题。
- 修复这类问题不能证明 live hover 控制已经稳定在 `0.1m` 内。

### 2. Gate 投影误判问题

症状：

- `/external_nav/odom_candidate` 和 `/slam/odom_corrected` 原始 ROS XY 一致，但 gate 把其中一个当 MAVLink FRD 再投影，导致假 `hover_xy_alignment_direction_mismatch`。

已固化决策：

- ROS odometry topics，包括 `/external_nav/odom_candidate`、`/external_nav/odom`、`/slam/odom_corrected`，在 gate 中按 native ROS XY 比较。
- MAVLink FRD 投影只属于 MAVLink sender/protocol，不应该用于 rosbag evidence comparison。

验证：

- `artifacts/sim/hover/20260623T045927Z` 曾达到 `TASK_STATUS_OK`。

### 3. Live hover XY 稳定性问题

症状：

- 同样配置下，部分 run 的 Gazebo / SLAM / external_nav / FCU local XY drift 超过 `0.1m`。
- `20260623T090519Z` hover 末尾出现 `slam_quality=jump`、`slam_quality_reason=pose_or_yaw_jump`。
- mission summary 仍可能 `ok=true`，但顶层 gate blocked。

性质：

- 这是后续真正要修的稳定性问题。
- 不能靠放宽 gate、改 summary、改 replay display 来解决。

## 目标

后续修复目标是让 hover 在不使用 Gazebo truth 输入、不 direct pose cheat 的前提下稳定满足：

- Gazebo model hover-window horizontal drift `< 0.10m`。
- FCU local position hover-window drift `< 0.10m`。
- `/slam/odom_corrected` hover-window drift `< 0.10m`。
- `/external_nav/odom` hover-window drift `< 0.10m`。
- 多源 XY direction agreement 不出现镜像、反向、轴交换疑似。
- mission FSM 仍为 `S13 task_success`，landing 仍通过。

真机判断标准：

- 不能只看 final displacement。
- 必须同时看 hover window 内的 span、max drift、RMS 或 equivalent stability metric。
- `horizontal_drift_m <= 0.1m` 但 `horizontal_span_m > 0.1m` 不能算真机稳定。

## 后续修复原则

### A. SLAM / external_nav 必须 fail-closed

当前问题：

- 当 `pose_or_yaw_jump` 出现时，external_nav / MAVLink external nav 可能继续传播不稳定 odometry。

目标行为：

- SLAM quality 出现 jump 时，external_nav 不应把跳变 odom 继续作为 healthy pose 发给 FCU。
- 可选策略：
  - 冻结上一帧 accepted pose，并把 status 标为 degraded / hold_last。
  - 直接停止发送 external nav pose，并让 FCU status 进入 not ready。
  - 等待连续稳定窗口后再恢复。

验收：

- 在 rosbag 中能看到 jump 被记录为 rejected，而不是直接进入 `/external_nav/odom`。
- `/mavlink_external_nav/status` 能反映 not ready / degraded。
- hover gate 不再因为 jump 后的 odom 污染而出现 `hover_xy_evidence_disagreement`。

### B. Hover acceptance 要从 end-to-end drift 升级到窗口稳定性

当前问题：

- mission body 主要看 selected hover evidence 的 drift；有些 run `horizontal_drift_m` 接近或小于 `0.1m`，但 `horizontal_span_m` 已经超过 `0.2m`。

目标行为：

- `hover_body_ok` 至少同时检查：
  - final displacement / drift
  - hover window horizontal span
  - z span
  - sample count and duration
  - optional RMS / percentile drift

验收：

- `horizontal_span_m > 0.1m` 时 mission summary 不应给出 misleading 的 strong pass。
- Gate 和 mission summary 对 hover 稳定性的语义一致。

### C. 控制闭环必须以 FCU/local pose 稳定性为中心

当前问题：

- `hover_ideal` 不是 Gazebo direct pose cheat；它仍通过 GUIDED / position setpoint / external nav 让 ArduPilot 控制。
- 如果 FCU local position 自身 drift 到 `0.13m~0.14m`，说明控制闭环或 EKF 输入仍不够稳。

需要检查：

- GUIDED position target 发送频率和 timeout。
- position target frame / type mask / yaw mask 是否稳定。
- ArduPilot position controller 参数是否足够约束 horizontal drift。
- EKF external nav 输入是否有 jump、delay、rate 抖动。
- 起飞后 hover anchor 捕获时机是否过早，是否应该等 FCU local pose 和 external nav 都进入 stable window 后再锁定 hold point。

验收：

- FCU local hover-window drift 连续多轮 `< 0.1m`。
- Gazebo model drift 与 FCU local drift 同向且量级接近。
- 若 FCU 稳而 SLAM 漂，定位问题归 SLAM/external_nav；若 Gazebo/FCU 同时漂，定位问题归控制。

### D. Gate 仍要保留严格性，不能为通过而放宽

不能做：

- 不能因为 blocked 就提高 drift threshold。
- 不能隐藏 `hover_xy_evidence_disagreement`。
- 不能把 Gazebo truth 作为 runtime input。
- 不能恢复 direct pose cheat。

可以做：

- 若 gate 窗口混入 landing 或 post-hover jump，应该修窗口选择。
- 若 gate 坐标投影误判，应该修坐标语义。
- 若 evidence source 低频或 stale，应该 fail closed 或降级，不应静默通过。

## 建议实施顺序

等当前 hover mission pipeline 重构收尾后，再按以下顺序修：

1. **诊断脚本**
   - 给每轮 summary 自动输出 per-source XY drift table。
   - 输出 hover window 内 max/span/final/RMS。
   - 明确区分 Gazebo、FCU local、SLAM corrected、external_nav odom。

2. **SLAM jump reject / external_nav fail-closed**
   - `pose_or_yaw_jump` 时不传播 unhealthy odom。
   - 增加状态和测试覆盖。

3. **Hover acceptance hardening**
   - mission summary 加 `horizontal_span_ok` 到真正 acceptance。
   - gate 和 mission summary 语义对齐。

4. **FCU/control tuning**
   - 检查 setpoint rate、GUIDED position target、EKF external-nav delay/rate。
   - 只在定位输入稳定后调控制参数。

5. **多轮稳定性验收**
   - 至少连续 3-5 轮 `just navlab-run hover`。
   - 每轮 `TASK_STATUS_OK`。
   - 每轮 Gazebo/FCU/SLAM/external_nav drift `< 0.1m`。
   - 每轮 landing PASS。

## 当前结论

当前可以说：

- hover FSM / landing pipeline 已经可运行到任务成功。
- P7.8 ownership refactor 不是这次 top-level blocked 的直接原因。
- hover live stability 还不能宣称真机级完成。

当前不能说：

- 不能说 hover task 整体已经完全完成。
- 不能说 SLAM 每轮都稳定。
- 不能说只要 replay 画面对了，真实 hover drift 就合格。

## 2026-06-23 复查：为什么有时过、有时不过

复查对象：

- pass: `20260623T045927Z`, `20260623T081943Z`, `20260623T123111Z`
- blocked: `20260623T090519Z`, `20260623T090829Z`, `20260623T120635Z`, `20260623T123615Z`

关键差异不是配置漂移，也不是 P7.9 package refactor：

- 所有复查 run 仍使用 hover + Cartographer + ExternalNav 链路。
- `hover_mission.runtime.log` 没有 import / traceback 类错误。
- P7.9 后的 `20260623T123111Z` 还能达到 `mission_summary.ok=true`、
  `mission_phase_state=S13 task_success`、`landing.ok=true`。
- 失败集中在 live XY evidence：Gazebo / FCU local / SLAM corrected /
  ExternalNav drift 或方向不一致。

### 复查表

| Run | Task | Mission | Hover hold | Mission drift | Mission span | Gazebo drift | ExternalNav drift | SLAM corrected drift | FCU local drift | mid-hover jump |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `20260623T045927Z` | OK | `S13 task_success` | `18.0s` | `0.018m` | `0.045m` | `0.032m` | `0.038m` | `0.042m` | `0.025m` | no |
| `20260623T081943Z` | OK | `S13 task_success` | `17.9s` | `0.032m` | `0.098m` | `0.069m` | `0.081m` | `0.099m` | `0.055m` | no |
| `20260623T090519Z` | BLOCKED | `S13 task_success` | `17.9s` | `0.100m` | `0.211m` | `0.574m` | `0.488m` | `0.306m` | `0.143m` | yes, at `t=45.815s` |
| `20260623T090829Z` | BLOCKED | `S13 task_success` | `18.0s` | `0.062m` | `0.266m` | `0.193m` | `0.340m` | `0.354m` | `0.137m` | no recorded bridge event, but high source drift |
| `20260623T123111Z` | BLOCKED | `S13 task_success` | `18.0s` | `0.017m` | `0.088m` | `0.076m` | `0.085m` | `0.120m` | `0.045m` | no; only XY direction gate remained |
| `20260623T123615Z` | BLOCKED | `S12 landing_complete` | `8.2s` | `0.167m` | `0.309m` | `0.756m` | `0.343m` | `0.422m` | `0.199m` | yes, at `t=36.477s` |

### 直接原因

`20260623T123615Z` 是最清楚的失败样本：

- Hover hold 从 `t=28.200s` 开始。
- ExternalNav 在 `t=36.477s` 报 `slam_quality_jump / pose_or_yaw_jump`。
- Hover FSM 在 `t=36.500s` 从 `S6 hover_hold` 退回 `S1 wait_nav_ready`。
- 约 `1.05s` 后以 `slam_quality_lost_after_airborne` 进入 `S_abort`。
- Landing suffix 正常完成，所以最终是 `S12 landing_complete`，不是 crash。

对应 probe 证据：

- `/external_nav/status` 最终为 `ready=false`, `slam_quality=jump`,
  `slam_quality_reason=pose_or_yaw_jump`。
- `slam_quality_report.max_observed_position_jump_m=1.767`，超过
  `max_position_jump_m=0.75`。
- `slam_quality_report.max_observed_yaw_jump_rad=3.119`，超过
  `max_yaw_jump_rad=0.75`，接近 180 度 yaw flip。
- Scan geometry 本身不是 missing：`scan_geometry_observable=true`，
  `hit_ratio=0.865`，`observed_quadrants=4`。

所以这轮不是“没有 scan / 没有 ExternalNav”，而是 Cartographer/scan-derived
pose 在 hover 中途出现了大幅 position/yaw jump，ExternalNav bridge 按设计
fail-closed，任务随后触发 airborne 后定位丢失保护。

`20260623T090519Z` 是另一类样本：

- Mission body 自己还能 `hover_complete`，因为最终 displacement 接近阈值：
  `horizontal_drift_m=0.0997m`。
- 但窗口 span 已经明显失败：`horizontal_span_m=0.211m`。
- Gate 看到 Gazebo / ExternalNav / SLAM / FCU local 全部漂或方向不一致，因此
  top-level blocked。
- `/external_nav/status` probe 同样记录 `max_observed_position_jump_m=1.968`、
  `max_observed_yaw_jump_rad=3.119`。

这解释了“有时可以，有时不行”：pass 轮只有启动早期 jump，随后 hover window
内没有再触发大跳变；fail 轮在 hover window 内或 hover 末尾又发生一次
Cartographer/ExternalNav pose/yaw jump，或者虽然没有 bridge event，窗口 span
和多源 XY 已经被漂移污染。

### 为什么会随机

当前链路是：

```text
scan / IMU / scan-reference prior
  -> Cartographer hover profile
  -> /slam/odom
  -> scan_reference_correction
  -> /external_nav/odom_candidate
  -> external_nav_bridge quality gate
  -> /external_nav/odom
  -> MAVLink ExternalNav
  -> ArduPilot EKF local position
  -> GUIDED hold setpoint controller
```

这条链路里有两个会导致 run-to-run 差异的点：

1. **Cartographer local pose 解算在 hover 场景里仍可能跳。**
   - 当前 hover profile 是 scan-led，`translation_weight=1`，
     `rotation_weight=10`，启用了 online correlative scan matching。
   - 官方 Cartographer tuning 文档也强调 scan matcher 和 prior 权重会影响
     是否“slip”；pure localization / online localization 还要求低延迟和实时处理。
   - 我们的 log 中 Cartographer scan rate 经常显示 pulsed at `~65%-70%`
     real time；这未必单独导致失败，但说明在线 localization margin 不大。

2. **ExternalNav fail-closed 会把跳变转成控制输入中断。**
   - ArduPilot 官方 Non-GPS / ExternalNav 文档要求外部位置估计持续以至少
     `4Hz` 送入 EKF；ODOMETRY 是推荐方式。
   - 当 bridge 检测到 `pose_or_yaw_jump` 后，`/external_nav/odom` 不再发布
     healthy output，MAVLink ExternalNav / FCU local readiness 随后变差。
   - 飞控此时仍在 GUIDED hold；如果 EKF local pose 已经跟着污染源漂移，
     Gazebo/FCU/SLAM/ExternalNav 的 XY evidence 就会出现不同方向或不同量级。

### 当前最可能的根因链

不是单一 threshold，而是定位链路不够稳定：

1. hover 起飞后，Cartographer/scan-reference 的 XY/yaw estimate 有时保持稳定，
   有时在 hover window 内产生大幅 position/yaw jump。
2. ExternalNav bridge 正确地检测 jump 并 fail-closed；这保护了真机安全，但会让
   hover mission 失去 ExternalNav readiness。
3. 如果 jump 发生在 hover hold 中段，mission 直接 abort 到 landing。
4. 如果 jump 发生在 hover 接近完成或 mission 没有把 span 作为 hard gate，
   mission 可能仍显示 `hover_complete`，但 top-level gate 会根据多源 XY span /
   drift / direction disagreement block。

因此“有时候可以”不是说明系统稳定，而是该轮没有在 hover window 里遇到足够大的
Cartographer/ExternalNav jump；“现在又不行”是同一随机/边界稳定性问题再次出现。

### 追加发现：source selector 的 fail-closed 语义不够硬

代码复查发现 `external_nav_source_selector.py` 的行为和服务名
`fail_closed_external_nav_source_selector` 不完全一致：

- 当 scan-reference 不可用、quality 不好、sign flip、非 hover correction phase
  或 status stale 时，`select_external_nav_source()` 返回
  `source="slam_passthrough"`。
- `_publish_status()` 只要 source 不是 `waiting` 就发布 `ready=true`。
- `_handle_slam_odom()` 无论 decision 是否带 blockers，都会发布
  `/external_nav/odom_candidate`。

对应测试也把这种行为固化了：

- `test_quality_bad_fails_closed_to_slam_passthrough`
- `test_stale_scan_status_fails_closed`
- `test_sign_flip_fails_closed`
- `test_non_hover_phase_fails_closed`

也就是说，当前所谓 fail-closed 实际是“scan-reference 不合格时退回
Cartographer SLAM passthrough”，不是“停止发布/hold last safe pose”。这在
Cartographer 本身稳定时能通过；一旦 Cartographer 出现 pose/yaw jump，selector
仍会把 jump 继续送到 `/external_nav/odom_candidate`，再由 ExternalNav bridge
后置检测并停发 `/external_nav/odom`。这解释了：

- 为什么 pass 轮能过：`slam_passthrough` 在该轮 hover window 内足够稳定。
- 为什么 fail 轮会突然不过：`slam_passthrough` 在 hover window 内发生 jump 或
  与 scan-reference 明显 disagreement。
- 为什么 `/external_nav/source_selector/status` 经常显示 `ready=true` 且
  `source=slam_passthrough`，同时 `blockers` 又包含
  `scan_reference_quality_not_good` / `scan_reference_xy_axes_not_allowed`。

这不是单纯的 Cartographer 参数问题；当前 source selector 策略也把不稳定
Cartographer 输出暴露给下游了。更准确的修复方向应是：

- hover phase 内 scan-reference 不合格时优先 `scan_reference_hold`，TTL 超时后
  进入 `not_ready` / stop publishing，而不是无限 `slam_passthrough`。
- source selector status 的 `ready` 应表示“输出可作为 ExternalNav 输入”，不能只看
  source 是否非 waiting。
- 若保留 `slam_passthrough`，至少要加 max step / max yaw step gate，并在
  `cartographer_scan_disagreement=true` 时 fail closed。
- tests 名称和断言要同步改掉，避免继续把 passthrough 误称为 fail-closed。

### 上网核对的外部依据

- ArduPilot Non-GPS Position Estimation:
  https://ardupilot.org/dev/docs/mavlink-nongps-position-estimation.html
  - ExternalNav 是给 EKF 的外部 position/velocity estimate。
  - 推荐 MAVLink `ODOMETRY`。
  - 外部估计消息应持续以 `4Hz` 或更高频率发送。
  - ODOMETRY `quality` 和 covariance 会影响 EKF 是否使用该估计。
- ArduPilot Guided Mode:
  https://ardupilot.org/copter/docs/ac2_guidedmode.html
  - companion computer 可以用 GUIDED 控制运动。
  - `GUID_OPTIONS` 可关闭 XY position / velocity stabilization；当前必须确认没有误设。
  - `GUID_TIMEOUT` 说明 offboard command cadence 对 GUIDED 控制有安全影响。
- ArduPilot Guided MAVLink commands:
  https://ardupilot.org/dev/docs/copter-commands-in-guided-mode.html
  - `SET_POSITION_TARGET_LOCAL_NED` 的 position / velocity / acceleration 三轴语义必须完整。
  - velocity/acceleration command 需要周期重发；位置 target 也不应在 hover 中长时间停发。
- Cartographer ROS tuning:
  https://google-cartographer-ros.readthedocs.io/en/latest/tuning.html
  - scan matcher prior 权重会影响 slippage。
  - online localization 需要低延迟，global SLAM 跟不上会让 drift 积累。
  - tuning 应针对平台和多组数据，而不是单个 bag。

### 下一步调查/修复建议

优先级从高到低：

1. **把 ExternalNav bridge 的 jump evidence 写进 summary。**
   - 当前 mission status history 只保留 `slam_quality_jump`，但没有带出
     `max_observed_position_jump_m` / `max_observed_yaw_jump_rad`。
   - 这会让失败原因看起来像普通 readiness loss，实际是 pose/yaw jump。

2. **在 hover gate 里输出 per-source timeline，而不是只输出 final vector。**
   - 当前 final vector 能说明方向不一致，但不能直接定位 jump 发生时间。
   - 需要输出 hover window 内每个 source 的 first/max/final、max step、yaw step。

3. **修 mission acceptance：`horizontal_span_ok` 必须参与 `hover_body_ok`。**
   - `20260623T090519Z` / `090829Z` 说明 final drift 可能过线，但窗口 span 已失败。
   - Mission 和 top-level gate 应对“稳定 hover”的语义一致。

4. **先修定位 fail-closed，再调控制。**
   - 如果 scan-reference status 已经 `quality_not_good` / inlier 低 / residual 高，
     source selector 不应继续让明显跳变的 `slam_passthrough` 污染 ExternalNav。
   - 可选：hover phase 内对 `/external_nav/odom_candidate` 增加 max-step / max-yaw-step
     gate，超限时 hold last good 或停止发布，让 bridge 不再先收到 jump。

5. **再做 Cartographer / scan-reference tuning。**
   - 检查 `translation_weight` / `rotation_weight` / `optimize_every_n_nodes` /
     correlative search window 是否导致偶发 yaw flip。
   - 目标是连续 3-5 轮没有 hover-window `pose_or_yaw_jump`，且 Gazebo/FCU/SLAM/
     ExternalNav drift 都 `<0.1m`。
