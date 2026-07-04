# Hover ExternalNav Fail-Closed TODO

Date: 2026-06-23

## 背景

`docs/notes/hover_xy_stability_design.md` 已经确认：当前 hover blocked 不是靠调大阈值能解决的问题。关键风险在于 live hover 的定位链路仍会把不稳定 SLAM / scan-reference 输出传播到 ExternalNav：

```text
Cartographer / scan-reference
  -> /external_nav/odom_candidate
  -> ExternalNav bridge
  -> /external_nav/odom
  -> MAVLink ODOMETRY
  -> FCU EKF / GUIDED hold
```

当前 `external_nav_source_selector.py` 的 fail-closed 语义不够硬：

- scan-reference 不可信时可能回退到 `slam_passthrough`。
- `_handle_slam_odom()` 无论 decision 是否带 blockers 都会发布 `/external_nav/odom_candidate`。
- status 的 `ready` 只要 source 不是 `waiting` 就为 true。

目标不是让 gate 更容易通过，而是让坏 odom 不能继续污染 FCU。改完后短期可能更容易 mission abort；这是正确失败，后续再调 Cartographer / scan-reference 连续稳定性。

## 当前链路审计基线

不能把任一单一 topic 直接当作未经审计的真值。`/gazebo/model_states` / `/gazebo/model/odometry` 是仿真 world/model pose 证据，通常可作为物理参考，但在本项目里必须先确认 model/link 名、frame、origin、timestamp 和 runtime map contract；它不能自动证明 ExternalNav / FCU 一定错。

当前更严谨的 blocker 表述是：

```text
Gazebo world/model pose evidence 与 ExternalNav/FCU estimated pose evidence 在 hover window 中显著不一致；
下一步必须先确认哪个观测源、frame、origin、符号、尺度或时间对齐出了问题。
```

因此后续不得再写成“Gazebo 真实漂移大，所以 ExternalNav 错”，除非同一窗口已经完成交叉审计：

- Gazebo model pose / link pose 取到的是正确 vehicle body 或等价 reference point。
- Gazebo evidence 的 frame/origin 与 runtime ROS map evidence 的比较方式明确。
- `/external_nav/odom_candidate`、`/external_nav/odom`、FCU local position、MAVLink ODOMETRY 的 frame 映射明确。
- 各源 timestamp 已对齐到同一 hover window，不能用不同阶段的 final displacement 互相比较。
- 至少一个独立信号能交叉支持 Gazebo 或 ExternalNav/FCU 的位移趋势。

## Phase 记录规则

每个新增 Phase 必须绑定一个可复现的 error 或 evidence gap，不能只记录“感觉像 bug”或“为了让 run 过”。最小记录格式：

- `Basis` 必须包含 run id、测试名、summary 字段或 tlog/rosbag topic，能让后来的人复查同一个现象。
- `Observed failure` 必须写清楚是 crash、ExternalNav loss、candidate reject、frame mismatch、mission blocker、还是 observation disagreement。
- `Hypothesis` 必须和 `Confirmed` 分开写；未经验证的推断不得写成结论。
- `Change` 必须说明改的是 runtime input、diagnostic evidence、mission acceptance、还是 test semantics。
- `Verification` 必须有 targeted test；涉及飞行链路的 Phase 必须有真实 run 或明确标记为未验证。
- 若后续 Phase 推翻前一 Phase，前一 Phase 必须标记 `superseded` / `wrong hypothesis` / `failed and reverted`，不能继续保持普通 `[x]` 完成语义。
- 任何 tuning 类改动必须先证明它修的是可复现 error，而不是绕过 blocker；否则只能作为 diagnostic-only experiment。

## 问题入场规则

从现在起，任何现象必须先分级，不能直接升级成 bug 或新 phase。

Evidence levels:

- `confirmed bug`: 至少满足 `可复现或有明确前后对照`、`有 artifact/log/test 指向同一原因`、`阻塞当前最小目标`。只有这一类允许直接改代码。
- `single-run observation`: 只有一次 run 或一个 artifact 看到异常。只能记录和设计最小复现，不能改 selector/gate/mission/Cartographer 参数。
- `hypothesis`: 解释性推断，还没有实验闭环。必须写在 Hypothesis，不能写成 root cause。
- `out-of-scope/defer`: 不阻塞当前最小目标，或只影响 sim review 外观。只记录，不追。

Fix admission checklist:

- [ ] 当前最小目标是什么，是否真的被这个问题阻塞？
- [ ] 是否存在一个已知能跑通的 baseline，可直接对比？
- [ ] 失败 run 与成功 baseline 的 runtime plan / service list / profile 是否先对齐过？
- [ ] 是否有具体 run id、日志行、summary 字段或测试名？
- [ ] 是否已经证明不是 harness/config/启动顺序错误？
- [ ] 如果只是一条新现象，是否先标为 `single-run observation` 而不是开新修复 phase？

禁止升级规则:

- [ ] 单次 rosbag blocker 不能自动升级成飞行链路 root cause。
- [ ] 表面 sensor/SLAM/EKF 日志不能跳过 runtime plan/service/profile 对比。
- [ ] 未复现的异常不能触发阈值调整、gate 调整、selector 调整或 Cartographer 参数调整。
- [ ] 一个 phase 的目标不得从“验证 harness”扩展成“修完整定位系统”，除非用户明确改目标。

## Phase 标签规则

从现在起，所有 phase 标题必须带现实价值标签；历史 phase 也按当前路线补标，避免把 legacy 仿真路线误认为当前主线。

Labels:

- `real-flight-safety`: 真实 UAV ExternalNav / SLAM / mission 安全边界，必须保留。
- `contract-validation`: frame / origin / time / MAVLink / ROS / Gazebo 观测合同验证；不直接改变飞行行为。
- `sim-review-only`: 只服务仿真 review / evaluator / probe，不得作为真实飞行链路修改依据。
- `legacy scan-reference route`: scan-reference selector / candidate / prior 路线的历史工作；当前 direct `/slam/odom` / no-odom-prior 路线优先，除非后续主线证据证明它仍有现实必要。
- `discard/defer`: 对真实安全链路没有足够价值，停止追。

Current route decision:

- [x] 当前主线是 direct `/slam/odom` / `slam-direct-no-odom-prior` ExternalNav baseline。
- [x] scan-reference selector route 目前降级为 legacy / experimental，不再作为 hover 成功的默认理由。
- [x] Gazebo evidence 降级为 `sim-review-only` review source；不能单独触发 selector / gate / mission / Cartographer 参数修改。
- [ ] 观测源 frame/origin/time 合同闭环前，不再新增 scan-reference selector patch。

## 禁止事项

- [ ] 不允许调大 hover drift / span / XY alignment threshold 来绕过 blocked。
- [ ] 不允许删除 `hover_gazebo_model_horizontal_drift`、`hover_xy_alignment_direction_mismatch`、`hover_xy_evidence_disagreement`。
- [ ] 不允许把 Gazebo truth、known map、fixed XY prior 或 direct pose cheat 作为 runtime ExternalNav 输入。
- [ ] 不允许在 `not_ready` 状态继续发布默认坐标、零坐标或带 blocker 的 odom candidate。
- [ ] 不允许把 `mission_summary.ok=true` 当作顶层 hover 完成标准；顶层 `summary.ok=true` 才算通过。
- [ ] 不允许把未经 frame/origin/time 审计的 Gazebo evidence 或 ExternalNav/FCU evidence 当作绝对真值。

## Phase 1 [real-flight-safety]: external_nav_source_selector 真正 fail-closed

目标：scan-reference 不可信时只允许短时间 hold last good pose；hold 超时后停止发布 `/external_nav/odom_candidate`，并明确 `ready=false`。

任务：

- [x] 在 `navlab/sim/companion/nodes/external_nav_source_selector.py` 扩展 `SourceDecision`：
  - [x] 增加 `ready: bool`。
  - [x] 增加 `publish: bool`。
  - [x] 增加 `degraded: bool`。
  - [x] 增加 `reject_reason: str | None`。
  - [x] 增加 `rejected_step_m: float | None`。
  - [x] 增加 `rejected_yaw_step_rad: float | None`。
- [x] 调整 `select_external_nav_source()` 的状态机：
  - [x] scan-reference good -> `source="scan_reference"`, `ready=true`, `publish=true`。
  - [x] scan-reference bad 但 last good 未过 TTL -> `source="scan_reference_hold"`, `ready=true`, `degraded=true`, `publish=true`。
  - [x] scan-reference bad 且 no fresh hold -> `source="not_ready"`, `ready=false`, `publish=false`。
  - [x] scan-reference missing -> hover 中 `not_ready`，不能无限 `slam_passthrough`。
  - [x] non-hover phase 若需要 bootstrap，使用明确的 `source="slam_bootstrap"` 或等价命名，不能让它表示 hover-ready。
- [x] 修改 `_handle_slam_odom()`：
  - [x] 当 `decision.publish=false` 时不发布 `/external_nav/odom_candidate`。
  - [x] 仍更新 `_last_decision`，保证 status 能说明为什么 not ready。
  - [x] 只有 accepted `scan_reference` 输出才能更新 last good；rejected / not_ready 不得刷新 last good。
- [x] 修改 `_publish_status()`：
  - [x] `ready` 直接来自 decision.ready，不再用 `source not in {"waiting"}`。
  - [x] 输出 `publish`、`degraded`、`reject_reason`、`rejected_step_m`、`rejected_yaw_step_rad`、`hold_age_ms`、`hold_reason`。
  - [x] status 语义必须表示“当前输出是否可以作为 ExternalNav 输入”，不是“节点是否收到过消息”。

验收：

- [x] scan-reference quality bad 且无 fresh hold 时，selector status 为 `ready=false`、`source=not_ready`、`publish=false`。
- [x] 上述状态下不发布 `/external_nav/odom_candidate`。
- [x] fresh hold 未过期时，只发布 last good pose，并在 status 中标明 degraded / hold age / hold reason。
- [x] hover phase 中不再出现 blocker 非空但 `ready=true` 且 `source=slam_passthrough` 的状态。

## Phase 2 [real-flight-safety]: candidate jump gate

目标：selector 在 `/external_nav/odom_candidate` 之前阻断明显 position / yaw jump，避免后置 ExternalNav bridge 先收到坏输入。

任务：

- [x] 在 selector node 中维护上一帧 accepted output：
  - [x] `last_accepted_x_m`
  - [x] `last_accepted_y_m`
  - [x] `last_accepted_yaw_rad`
  - [x] `last_accepted_wall_sec`
- [x] 从 odom quaternion 解析 yaw，并实现 angle wrap 后的 yaw delta。
- [x] 新增 CLI 参数：
  - [x] `--max-candidate-step-m`, default `0.12`
  - [x] `--max-candidate-yaw-step-rad`, default `0.35`
  - [x] `--max-hold-age-ms`, default 保持 `750`
- [x] 对待发布 candidate 做 gate：
  - [x] `step_m > max_candidate_step_m` -> reject。
  - [x] `yaw_step_rad > max_candidate_yaw_step_rad` -> reject。
  - [x] hover 中 `cartographer_scan_disagreement=true` 且不能安全 hold -> reject / not_ready。
- [x] reject 时优先 hold last good；hold 不可用或过期时 `not_ready`。
- [x] rejected candidate 不得更新 last good 或 last accepted。

验收：

- [x] 构造 `step_m=1.7m` 的 candidate 时不发布，并记录 `reject_reason=candidate_step_jump`。
- [x] 构造 `yaw_step_rad=3.1rad` 的 candidate 时不发布，并记录 `reject_reason=candidate_yaw_jump`。
- [x] 正常小步更新不被误杀。
- [x] hold expired 后再次出现 jump，结果为 `not_ready`，不是 `slam_passthrough`。

## Phase 3 [real-flight-safety]: 测试语义改正

目标：删除“fail closed to slam passthrough”的测试语义，避免旧行为再次被固化。

任务：

- [x] 修改 `navlab/tests/companion/test_external_nav_source_selector.py`：
  - [x] `quality bad -> scan_reference_hold if last_good fresh`
  - [x] `quality bad -> not_ready if no fresh hold`
  - [x] `stale status -> not_ready`
  - [x] `sign flip -> reject / hold / not_ready`
  - [x] `non-hover phase -> no hover ExternalNav-ready claim`
  - [x] `large candidate step -> reject`
  - [x] `large candidate yaw step -> reject`
- [x] 删除或重命名这些旧语义测试：
  - [x] `test_quality_bad_fails_closed_to_slam_passthrough`
  - [x] `test_stale_scan_status_fails_closed`
  - [x] `test_sign_flip_fails_closed`
  - [x] `test_non_hover_phase_fails_closed`
- [x] 若 orchestration gate test 依赖 `slam_passthrough` 作为正常输出，改为接受 `not_ready` / `scan_reference_hold` 的新语义。

验收：

- [x] 单测名称和断言都不再把 `slam_passthrough` 称为 fail-closed。
- [x] selector focused tests 能覆盖 good、hold、not_ready、jump reject 四类路径。

## Phase 4 [real-flight-safety]: mission hover acceptance hardening

目标：mission 自己必须识别“final drift 看似过线，但 window span 已经失败”的不稳定 hover，不能让顶层 gate 才发现。

任务：

- [x] 修改 `navlab/common/companion/mission/evidence/hover.py`：
  - [x] `HoverEvidenceRecorder.evaluate_completion()` 的 `ok` 必须包含 `drift.horizontal_span_m <= max_horizontal_drift_m`。
  - [x] reason 最好区分 `hover_span_unstable`、`hover_drift_unstable`、`hover_duration_short`、`hover_altitude_unstable`。
- [x] 修改 `navlab/common/companion/mission/summary_runtime.py`：
  - [x] `_hover_drift_payload()["ok"]` 必须包含 `horizontal_span_ok`。
  - [x] summary 明确输出 final drift 与 span 的两个 hard gate。
- [x] 将 ExternalNav / SLAM loss 信息纳入 hover body 完成判断或 summary blocker：
  - [x] `no_external_nav_loss_after_airborne`
  - [x] `no_mavlink_external_nav_loss_after_airborne`
  - [x] `no_slam_quality_jump_in_hover_window`
- [x] 对 `pose_or_yaw_jump` 的 evidence 增加 summary 字段：
  - [x] `max_observed_position_jump_m`
  - [x] `max_observed_yaw_jump_rad`
  - [x] `slam_quality_reason`
  - [x] `jump_seen_in_hover_window`

验收：

- [x] `horizontal_drift_m <= 0.1m` 但 `horizontal_span_m > 0.1m` 时，`hover_body_ok=false`。
- [x] `20260623T090519Z` 这类 final drift 接近过线但 span 明显失败的 run，不再显示 misleading mission pass。
- [x] ExternalNav 中途 loss / jump 在 summary 中有明确 reason 和 blocker。

## Phase 5 [contract-validation]: gate / summary 对齐

目标：顶层 gate 和 mission summary 对“稳定 hover”的语义一致；失败原因能指向 selector reject、SLAM jump、span unstable 或真实多源 XY disagreement。

任务：

- [x] 检查 `orchestration/sim/internal/tasks/gate_evaluation.go`：
  - [x] 若 source selector status `ready=false`，给出明确 blocker，例如 `external_nav_source_selector_not_ready`。
  - [x] 若 `reject_reason` 存在，透传到 summary / blockers。
  - [x] 若 `horizontal_span_ok=false`，不要只报泛化的 `hover_mission_drift_not_ok`。
- [x] 保留四源 XY alignment gate，不因 selector fail-closed 而删除。
- [x] 如果 gate 窗口混入 landing / post-hover jump，只修窗口选择，不放宽阈值。

验收：

- [x] summary 能区分：
  - [x] selector rejected bad candidate
  - [x] ExternalNav bridge rejected pose/yaw jump
  - [x] mission hover span unstable
  - [x] Gazebo/FCU/SLAM/ExternalNav 多源 XY disagreement
- [x] 顶层 blocked 不再只剩无法定位的泛化 blocker。

## Phase 6 [sim-review-only]: 真实 run 后的诊断硬化

决策：先增强 gate/summary 诊断，而不是调大阈值或绕过 `slam_hover_probe`。

Basis: 2026-06-23 `just navlab-run hover` 的真实 artifact `20260623T142418Z`。

Reason: 该 run 同时暴露两类问题：

- runtime 层 `slam_hover_probe` 被 kill，`slam_hover_probe.json` 为空。
- mission 层已正确 fail-closed：airborne 后 SLAM / ExternalNav 不稳定，FSM 进入 abort 并 landing。

任务：

- [x] gate 对负 return code 的 probe 增加 `probe_killed:<name>`。
- [x] gate 对空 probe output 增加 `probe_output_empty:<name>`，避免只看到泛化 `probe_output_not_ok`。
- [x] 从 `mission_phase_history` 提取 `mission_abort_reason`。
- [x] mission abort 进入 blocker，例如 `hover_mission_abort:slam_quality_lost_after_airborne`。

验收：

- [x] killed probe + 0 字节 output 能在 blockers 中明确分类。
- [x] mission 因 airborne 后定位质量丢失 abort 时，summary/gate 不需要手工翻 `mission_phase_history` 也能看到原因。

## Phase 7 [real-flight-safety]: airborne 后不重复 preflight stable wait

决策：`preflight_ready_sec` 只用于起飞前；airborne 后由 explicit loss grace / abort gate 负责安全边界。

Basis: 2026-06-23 `just navlab-run hover` 的真实 artifact `20260623T143647Z`。

Reason: 该 run 中 ExternalNav / MAVLink ExternalNav / SLAM quality 都保持 ready，且没有 loss blocker；但 mission FSM 反复出现约 `1s hover_hold -> 5.5s wait_ready`，最终 `hover_hold_duration_short`。根因是 airborne 后短暂 freshness 抖动会清零 `ready_elapsed_sec`，旧逻辑又重新套用 5s preflight stable wait。

任务：

- [x] 修改 `decide_hover()`：`ready_elapsed_sec < preflight_ready_sec` 仅在 `airborne_seen=false` 时返回 `wait_ready`。
- [x] 保留 airborne 后 loss grace：
  - [x] SLAM quality loss 超过 grace -> abort。
  - [x] ExternalNav loss 超过 grace -> abort。
  - [x] MAVLink ExternalNav / FCU local position loss 超过 grace -> abort。
- [x] 增加单测覆盖 airborne 后 ready timer 被清零但当前定位 ready 时仍继续 `hover_hold`。

验收：

- [x] 起飞前仍需连续稳定 ready。
- [x] 起飞后不会因短暂 ready timer reset 反复退回 `wait_ready`。
- [x] 起飞后真实定位 loss 仍 fail-closed abort，不会被该改动绕过。

## Phase 8 [real-flight-safety]: takeoff 到 hover_settle 的 transient loss 不提前判成 hover loss

决策：airborne 后定位 loss 仍然累计并进入 summary；但 mission 的 loss abort gate 只在初始 `hover_settle_sec` 结束或已经进入过 hover hold 后打开。

Basis: 2026-06-23 `just navlab-run hover` 的真实 artifact `20260623T144234Z`。

Reason: 该 run 中 selector 后续恢复为 ready，最终状态也显示 SLAM quality healthy；mission 却在 `S5 hover_settle` 约 1.55s 处因一次 `odom_stale` 窗口 abort，且没有任何 hover_hold 样本。这个现象属于 takeoff -> settle 过渡期 freshness gap，不应被记录成 hover window loss。该改动不放宽 hover acceptance，也不允许 hover hold 中继续送坏 ExternalNav。

任务：

- [x] `decide_hover()` 增加 `loss_abort_ready`：
  - [x] `airborne_elapsed_sec >= hover_settle_sec` 后打开。
  - [x] 或 `hover_elapsed_sec > 0` 后打开。
- [x] 初始 settle 期 loss 超过 grace 时继续返回 `hover_settle`，不提前 `S_abort`。
- [x] settle 期结束后同样 loss 仍 fail-closed abort。

验收：

- [x] 起飞初期短暂 `odom_stale` 不会在没有 hover sample 的情况下直接判 hover failure。
- [x] 真正进入 hover window 后 ExternalNav / SLAM / MAVLink loss 仍是 hard gate。

## Phase 9 [contract-validation]: post-airborne nav loss window diagnostics

决策：在 mission summary 中增加 `post_airborne_nav_loss` 诊断字段，只做 reporting，不改变控制逻辑或 gate。

Basis: 2026-06-23 `just navlab-run hover` 的真实 artifact `20260623T145528Z`。

Reason: P8 后 mission 不再被初始短暂 stale 提前 abort，但真实 run 仍在 `hover_settle` 结束后因 `slam_quality_lost_after_airborne` fail-closed。现有 summary 需要人工从 `status_history` 反推 loss 起点、持续时间和坏因，不利于下一步调 selector / Cartographer。

任务：

- [x] 新增 `summarize_post_airborne_nav_loss()`。
- [x] `mission_summary.json` 写入：
  - [x] `slam_quality` loss window。
  - [x] `external_nav` loss window。
  - [x] `mavlink_external_nav` loss window。
  - [x] `fcu_local_position` loss window。
- [x] 每个 window 包含 `seen`、`active`、`max_duration_sec`、bad phase、bad airborne elapsed、inferred start、last reason。

验收：

- [x] summary 能直接指出 airborne 后 loss 的持续时间和最后坏因。
- [x] 不影响 fail-closed selector / mission gate。

## Phase 10 [legacy scan-reference route]: selector 不再把 correction eligibility 误当成 candidate readiness

决策：`external_nav_source_selector` 的 scan-reference candidate readiness 只使用 scan-reference 自身质量和安全门槛；`correction_eligibility.correction_allowed` / `allowed_axes` 只属于“是否能施加 correction intent”，不再阻止健康 candidate 发布。

Basis: 2026-06-23 `just navlab-run hover` 的真实 artifact `20260623T150103Z` rosbag timeline。

Reason: takeoff -> `hover_settle` 期间 `/navlab/scan_reference_drift/status` 持续 `quality_good=true`、`inlier_ratio=1.0`、drift 接近 0；但由于 `correction_eligibility` 报 `scan_reference_no_stable_axis`，selector 每 0.5s 输出 `source=not_ready publish=false blockers=[scan_reference_eligibility_not_allowed, scan_reference_xy_axes_not_allowed]`。这导致 `/external_nav/odom_candidate` 停发，external_nav bridge 才报 7s `odom_stale`。这是语义误用，不是 mission 阈值问题。

任务：

- [x] 从 selector hard gate 中移除：
  - [x] `scan_reference_eligibility_not_allowed`
  - [x] `scan_reference_xy_axes_not_allowed`
- [x] 保留硬 gate：
  - [x] scan-reference status stale / not ready / quality bad。
  - [x] truth / known-map input。
  - [x] valid beams / inlier / residual。
  - [x] direction discontinuity / sign flip。
  - [x] Cartographer disagreement。
  - [x] candidate step / yaw jump。
- [x] 增加回归测试：`quality_good=true` 但 correction axes 为空时仍发布 `scan_reference` candidate。

验收：

- [x] 初始 hover_settle 中 `scan_reference_no_stable_axis` 不再造成 ExternalNav candidate 断流。
- [x] correction intent 仍由 scan-reference correction 节点自己的 gate 控制，不会因为这个改动直接施加 correction。

## Phase 11 [legacy scan-reference route]: selector 不再把 scan-reference relative yaw 当成 absolute yaw

决策：source selector 对 scan-reference candidate 使用 scan-reference 的 XY，但 yaw 使用 SLAM/Cartographer 的 absolute yaw；hold/reject 分支保持 last accepted yaw。

Basis: 2026-06-23 `just navlab-run hover` 的真实 artifact `20260623T151144Z` rosbag timeline。

Reason: Phase 10 后 `scan_reference_no_stable_axis` 已不再阻止 candidate，但 selector 仍持续 `candidate_yaw_jump`，`rejected_yaw_step_rad ~= 3.117`。根因是 scan-reference odom 的 yaw 为相对参考扫描 yaw（初始为 0），selector 却把它当 map absolute yaw，与上一帧 SLAM yaw 约 3.117rad 比较后 fail-closed 停发。正确语义是 scan-reference 只提供 XY 候选，absolute yaw 仍来自 SLAM/Cartographer，并继续受 `max_candidate_yaw_step_rad` 保护。

任务：

- [x] `scan_reference` decision 的 `output_yaw_rad` 改用 `slam.yaw_rad`。
- [x] hold 分支使用 last accepted yaw，避免 reject 后发布跳变 yaw。
- [x] 增加回归测试：scan-reference yaw=0、SLAM yaw 与 last accepted yaw 一致时，不触发 `candidate_yaw_jump`。

验收：

- [x] scan-reference relative yaw 不再造成 hover_settle 期间 `/external_nav/odom_candidate` 断流。
- [x] SLAM/Cartographer absolute yaw 若真实跳变，仍由 candidate yaw-step gate reject。

## Phase 12 [legacy scan-reference route]: hover_settle 期间修复 ExternalNav odom_stale 空窗

决策：`hover_settle` 是 takeoff -> hover_hold 的过渡期，source selector 在这个阶段可以使用明确的 degraded `slam_settle` source 保持 ExternalNav odom 输入连续；`hover_hold` 仍要求 scan-reference 或短 TTL hold，不能靠 SLAM 兜底让验收通过。

Basis: 2026-06-23 `just navlab-run hover` 的真实 artifact `20260623T151814Z` rosbag timeline。

Reason: Phase 10/11 后，初始 `scan_reference_no_stable_axis` 和 relative yaw 误判已清除，剩余 stale gap 来自 `hover_settle` 中 scan-reference 与 Cartographer 持续 disagreement，`scan_reference_hold` TTL 过期后 selector 停发 `/external_nav/odom_candidate`，导致 ExternalNav bridge 报 `odom_stale`。这不是 mission 阈值问题，而是过渡期 source selector 把“修正源可用性”和“ExternalNav 输入连续性”绑得太死。

任务：

- [x] 增加 `slam_settle` source，只允许在 `hover_settle` 发布。
- [x] `slam_settle` 标记 `degraded=true`，保留 scan-reference blocker 作为诊断上下文。
- [x] `slam_settle` 仍走 candidate step / yaw jump gate；若 SLAM 本身跳变，继续 fail-closed。
- [x] 若 `hover_settle` 中 `slam_settle` 触发 candidate jump gate，发布 `hover_settle_hold` 刷新上一帧 accepted output 的 timestamp，而不是把跳变 pose 送给 FCU 或停止发布造成 odom stale；该安全 hold 不设置 `reject_reason`，但保留 `hold_reason` / `blockers` / rejected step/yaw 诊断。
- [x] `hover_hold` 中 hold 过期后仍 `not_ready`，不允许 SLAM fallback。
- [x] 增加回归测试覆盖 hover_settle fallback、hover_settle last accepted hold、hover_hold fail-closed。

验收：

- [x] takeoff -> hover_settle 期间 scan-reference disagreement 不再直接制造 `/external_nav/odom_candidate` 空窗。
- [x] takeoff -> hover_settle 期间 SLAM fallback 跳变不再污染 `/external_nav/odom_candidate`，而是 degraded hold last accepted output。
- [x] hover_hold 验收期仍不能通过 degraded SLAM fallback 掩盖 scan-reference loss。

真实验证：

- [x] `20260623T153149Z` rosbag: `/external_nav/odom_candidate` 最大 gap 从上一轮 `20260623T152608Z` 的 4.72s 降到 0.60s；`hover_settle` 中 `external_nav/status` 持续 `healthy`。
- [x] `20260623T153556Z` rosbag: `hover_settle` 中 source selector 持续 `hover_settle_hold publish=true ready=true degraded=true reject_reason=null`，ExternalNav bridge 持续 `healthy`；进入 `hover_hold` 后 scan-reference quality/inlier 不足导致 `not_ready` 和后续 `odom_stale`，这是 fail-closed 验收期行为。
- [ ] 仍需后续修 scan-reference / Cartographer 稳定性，使进入 `hover_hold` 后不再长期 `scan_reference_quality_not_good` / `scan_reference_inlier_ratio_low`。

## Phase 13 [legacy scan-reference route]: scan-reference reference 必须真正在 hover_hold 重置

决策：`scan_reference_drift` 的 `--reset-on-hover-hold` 只在第一次进入 `hover_hold` 时 reset reference；`hover_settle` 不再触发 reference reset。同一 correction window 内如果 mission phase 在 `hover_settle` / `hover_hold` 间抖动，不重复 reset；离开 correction phases 后重新 arm。

Basis: 2026-06-23 artifact `20260623T153556Z` rosbag timeline。

Reason: 节点参数名和 status 都声明 reference 是 `first_hover_hold_scan_or_first_runtime_scan`，但代码实际在第一次进入 `CORRECTION_PHASES` 时 reset，也就是 `hover_settle`。真实 timeline 中 reference_stamp_sec=16.6，而 `hover_hold` 到约 25.9s 才开始；后续 estimate 一直拿 hover_settle 早期 scan 当 reference，raw residual 约 1.02m，inlier_ratio 约 0.25，导致 `scan_reference_inlier_ratio_low` 和 selector fail-closed。正确语义是 hover_settle 只用于过渡连续性，hover_hold 验收需要以 hover_hold 入口 scan 作为 reference。

任务：

- [x] 增加纯函数 `should_reset_reference_on_phase()` 表达 hover_hold reset 状态机。
- [x] `scan_reference_drift` 不再在 `hover_settle` reset。
- [x] 同一次 correction window 内只允许第一次 `hover_hold` reset，避免 phase 抖动导致反复 reset。
- [x] 增加回归测试覆盖 hover_settle 不 reset、hover_hold reset、phase 抖动不重复 reset、离开 correction phases 后 rearm。

验收：

- [x] 本地单测证明 `reset_on_hover_hold` 名称和行为一致。
- [x] 真实 hover run `20260623T155143Z` 中 `hover_hold` 后 `reference_stamp_sec=23.3000001`，接近 hover_hold 入口 scan timestamp，而不是旧 runtime / hover_settle 初期 timestamp。
- [x] 真实 hover run `20260623T155143Z` 中 hover_hold scan-reference median `inlier_ratio ~= 0.97`，不再因旧 reference 长期停在约 0.25。

## Phase 14 [legacy scan-reference route]: direction/sign-flip 不再单独阻断 odom candidate

决策：`external_nav_source_selector` 不再把 scan-reference 的 `direction_cosine_min` / `x_sign_flips` / `y_sign_flips` 当作 candidate readiness hard blocker。它们继续保留在 scan-reference status / correction intent / Phase4B consistency 中，用于判断能否施加 correction；真正防止坏 odom 进入 ExternalNav 的门槛是 scan 自身质量、inlier/residual、Cartographer disagreement、candidate step/yaw gate。

Basis: 2026-06-23 artifact `20260623T155143Z` rosbag timeline。

Reason: Phase 13 后 hover_hold reference 正确重置，scan-reference 质量恢复，hover_hold median inlier_ratio 约 0.97。但刚进入 hover_hold 的短窗口内，reset 后的微小近零漂移会造成 direction/sign-flip instability，selector 因 `scan_reference_direction_not_continuous` 停发。这个信号只说明 correction intent 尚未稳定，不说明 odom candidate 本身不安全；若 candidate 真跳变，`candidate_step_jump` / `candidate_yaw_jump` 仍会 fail-closed。

任务：

- [x] 从 selector candidate eligibility 中移除 direction/sign-flip hard blockers。
- [x] 保留 scan-reference correction intent 对 direction/sign-flip 的 fail-closed 约束。
- [x] 增加回归测试：sign flip 本身不阻断高质量、低 disagreement candidate。
- [x] 增加回归测试：sign flip 同时伴随大 candidate step 时仍由 step gate reject。

验收：

- [x] correction intent 稳定性信号不再误伤 ExternalNav odom candidate readiness。
- [x] 明显 candidate jump 仍 fail-closed。
- [ ] 真实 hover run 中 first hover_hold 不应再因为 `scan_reference_direction_not_continuous` 导致 selector `not_ready`。

真实验证：

- [x] `20260623T155721Z` rosbag: first hover_hold 不再因 `scan_reference_direction_not_continuous` not_ready；剩余 `not_ready` 原因转为 `cartographer_scan_disagreement`。

## Phase 15 [legacy scan-reference route]: scan-reference delta 必须先 anchoring 到 map frame

决策：`external_nav_source_selector` 不再把 `/navlab/scan_reference_drift/odom` 的 x/y 直接当作 map-frame absolute pose。selector 在 scan-reference `reference_stamp_sec` 变化时，用当前 last accepted output（没有则用当前 SLAM）建立 map anchor；后续 candidate 使用 `anchor + scan_delta`，再参与 Cartographer disagreement、candidate step/yaw gate 和发布。

Basis: 2026-06-23 artifact `20260623T155721Z` rosbag timeline。

Reason: Phase 13 后 scan-reference reference 正确在 hover_hold 入口重置，scan-reference x/y 变成相对 hover_hold reference 的小 delta；但 selector 仍将该 delta 直接与 SLAM map x/y 比较并发布，导致 frame 语义混乱和 `cartographer_scan_disagreement` 被放大。正确做法是将 relative scan delta 绑定到 reference 时刻的 last accepted map output，形成 map-frame candidate。

任务：

- [x] 增加 anchored scan candidate 转换。
- [x] node 跟踪 `scan_reference_anchor_stamp_sec` 和 anchor x/y。
- [x] `last_good_scan` 存储 accepted map-frame output，而不是 raw scan-reference delta。
- [x] status 输出 anchor stamp/x/y 便于 rosbag 诊断。
- [x] 增加回归测试：scan delta + anchor 后输出 map-frame candidate，且与 SLAM 一致时不触发 disagreement。

验收：

- [x] scan-reference relative delta 不再被当作 absolute map pose。
- [ ] 真实 hover run 中 first hover_hold 不应因 frame-mismatched scan/slam comparison 触发 `cartographer_scan_disagreement`。

## Phase 16 [sim-review-only]: slam_hover_probe 不应因缺失 topic 卡到外层 kill

决策：ROS probe 模板使用短 per-topic 采样预算和短 String status batch 预算。缺失或暂时未发布的 topic 应记录 `topic_sample_missing:*` blocker 并输出 JSON，而不是让 `slam_hover_probe` 消耗完整 `ProbeTimeoutSec` 后被 Docker/runtime watchdog kill。

决策：`/navlab/landing/status` 在 `slam_hover_probe` 中保留采样，但标记为 optional。landing 未开始时该 topic 可能没有 publisher；它可用于后续 landing evidence，但不应让 hover probe 返回 rc=20。

Basis: 2026-06-23/24 多个真实 hover artifact（如 `20260623T160315Z`）显示 `slam_hover_probe` 在缺失 `/external_nav/odom_candidate`、`/navlab/landing/status` 等 late/conditional topic 时被 `signal: killed`，导致 summary 只有 probe infra failure，无法稳定得到 mission verdict 或 hover_hold rosbag 验证。

Basis: 真实 hover artifact `20260623T161111Z` 已经不再 `signal: killed`，但唯一 probe blocker 变成 `topic_sample_missing:/navlab/landing/status`。这说明 probe infrastructure 已恢复，剩余是 conditional landing topic 的 required/optional 语义错误。

Reason: 旧模板对 String topics batch 使用完整 `PROBE_TIMEOUT_SEC`，普通 topic 的 rclpy 与 `ros2 topic echo` fallback 也可能各自等待完整 probe timeout。`slam_hover_probe` topic 数量较多时，总等待时间会超过外层 probe 预算，进程被杀且没有 JSON 输出。真实缺失 topic 应是证据 blocker，不应破坏 probe infrastructure。

Reason: summary/gate 已经从 mission summary 和 rosbag 评价 landing；`/navlab/landing/status` 缺失只能说明 landing controller 未发布，不等价于 SLAM hover probe 失败。保留 optional sample 可以在 landing topic 存在时继续提供证据。

任务：

- [x] 增加 `TOPIC_SAMPLE_TIMEOUT_SEC`，限制单 topic rclpy / CLI fallback 等待。
- [x] 增加 `STRING_BATCH_TIMEOUT_SEC`，限制 String status 批量等待。
- [x] 保留 retryable `ros2 topic echo` fallback，但在 per-topic budget 内完成。
- [x] 增加 `optional_topics` / `optional_blockers` probe 输出语义。
- [x] 将 `slam_hover_probe` 的 `/navlab/landing/status` 标记为 optional topic。
- [x] 增加模板回归断言，防止 probe 重新使用完整 timeout 作为每 topic deadline。

验收：

- [x] `go test ./internal/tasks ./internal/tasks/helpers` 通过。
- [x] `go test ./...` under `orchestration/sim` 通过。
- [x] 真实 hover run `20260623T161855Z` 中 `slam_hover_probe.ok=true`，`blockers=[]`，`optional_blockers=["topic_sample_missing:/navlab/landing/status"]`，不再出现 `probe_killed:slam_hover_probe` / `probe_output_empty:slam_hover_probe`。
- [ ] Phase 15 需要一轮进入稳定 `hover_hold` 的 rosbag 验证 anchor 后是否仍有 frame-mismatch `cartographer_scan_disagreement`。

## Phase 17 [sim-review-only]: hover_hold 太短，Phase 15 仍不能完全关闭

决策：不把 `20260623T161855Z` 当作 Phase 15 完成。该 run 到达了 `hover_hold`，但两个 hold segment 只有约 `0.20s` 和 `0.10s`；selector status 频率约 2Hz，段内没有 `/external_nav/source_selector/status` 样本。

Basis: 真实 run `20260623T161855Z`：

- `slam_hover_probe.ok=true`，probe infra 已恢复。
- hover phase ranges:
  - `hover_hold` `1782231584.298 -> 1782231584.498`, duration `0.20s`
  - `hover_hold` `1782231585.048 -> 1782231585.148`, duration `0.10s`
- scan-reference 在第二段 hold 中 `reference_stamp_sec=24.5`，`quality_good=true`，`phase4b_consistency.ok=true`，说明 first-hover-hold reference reset 生效。
- selector 段后 status 已显示 `scan_reference_anchor_stamp_sec=24.5`、anchor 约 `(-0.028, 0.010)`，说明 anchored candidate 链路生效。
- 但段后仍有 `cartographer_scan_disagreement=true`、`candidate_step_jump`，`rejected_step_m ~= 1.1m`。
- hover-window `/external_nav/odom_candidate` span 为 `0`，说明 fail-closed hold 阻止了跳变 candidate 污染 ExternalNav。

Reason: 这轮已经证明 probe 不再破坏 verdict，也证明 anchor 更新发生；但由于 hover_hold 太短且 selector 没有段内 status，不能断言 frame-mismatch disagreement 已完全消失。当前剩余问题更像是真实 SLAM/Cartographer pose jump 或高度/hover settle 抖动导致 mission 反复退出 hold，而不是 probe runtime failure。

任务：

- [ ] 让 mission 能稳定停留在 `hover_hold` 至少一个 selector status 周期以上，最好达到完整 `hover_hold_sec`。
- [ ] 或提高 selector status 采样/rosbag 诊断，使短 `hover_hold` 段内也能看到 `cartographer_scan_disagreement` 与 anchored candidate。
- [ ] 继续定位 `hover_hold -> hover_settle` 的原因：`settling_until_target_altitude` / `waiting_for_independent_takeoff_height`，不能通过放宽 hover drift/span 阈值绕过。
- [ ] 复跑真实 hover，确认 anchored scan candidate 后仍为 `cartographer_scan_disagreement=true` 时，其原因是 Cartographer/SLAM 大跳，而不是 raw scan delta frame mismatch。

## Phase 18 [real-flight-safety]: hover 高度门控改成多源安全语义

决策：`hover_hold` 的高度门控不再被单个 instantaneous rangefinder 或 FCU local-z 样本打断；改为要求 ExternalNav height 支持目标高度，并且 rangefinder relative height 或 FCU local-z 至少一个第二来源也支持目标高度。单独 FCU local-z 仍不能让 takeoff/hover 通过。

Basis: 真实 run `20260623T161855Z` 已经不再被 probe infra failure 阻断，但 `hover_hold` 两次只持续约 `0.20s` 和 `0.10s` 后退回 `hover_settle`：

- 第一次退回前：`external_nav_height_m=0.411`、`current_z_ned=-0.404` 均在 target tolerance 内，但 `rangefinder_relative_height_m=0.95` 为单点高 outlier，状态机返回 `waiting_for_independent_takeoff_height`。
- 第二次退回前：`external_nav_height_m=0.591`、`current_z_ned=-0.612` 均在 target tolerance 内，但 `rangefinder_relative_height_m=0.69` 略超 tolerance，状态机再次返回 `waiting_for_independent_takeoff_height`。
- 之后还出现 `external_nav_height_m` 与 rangefinder 支持目标高度，但 FCU local-z 瞬时略超 tolerance 时返回 `settling_until_target_altitude`。
- mission summary 的 hover altitude crosscheck 对同一窗口显示多源高度整体 `ok=true`，说明问题是状态机单点高度门控比 evidence 语义更脆弱。

Reason: 这不是放宽阈值，而是把 hover 进入/保持条件改成和真实传感器语义一致：ExternalNav height 是必须项，另一个独立高度来源用于确认；单个 rangefinder 离群点不应打断已经稳定的 hover hold，单个 FCU local-z 也不能绕过 ExternalNav/height evidence。

任务：

- [x] 新增 `local_z_reaches_target()`，用 local-NED z 和 target z 判断 FCU local-z 是否支持目标高度。
- [x] 新增 `hover_altitude_source_votes()`，显式记录 ExternalNav height / rangefinder relative height / FCU local-z 三个来源是否支持目标高度。
- [x] 将 `independent_takeoff_height_reached()` 改为 `external_nav_height && (rangefinder_relative_height || fcu_local_z)`。
- [x] 将 takeoff ack 后的 `settling_until_target_altitude` 判断复用同一多源高度门控，避免 single-source bounce。
- [x] 增加单测覆盖 rangefinder high outlier 不打断 hover hold。
- [x] 增加单测覆盖 ExternalNav height 不支持目标时仍必须 settle。

验收：

- [x] 单独 FCU local-z 支持目标高度但 ExternalNav/rangefinder 不支持时，仍返回 `waiting_for_independent_takeoff_height`。
- [x] ExternalNav height + FCU local-z 支持目标高度，即使 rangefinder relative height 单点高 outlier，也保持 `hover_hold`。
- [ ] 真实 hover run 的 `hover_hold` 不再因为 single rangefinder/current-z outlier 立即退回 `hover_settle`。

## Phase 19 [legacy scan-reference route]: anchored scan candidate 连续时不再被 raw Cartographer disagreement 永久否决

决策：`cartographer_scan_disagreement` 保留为 diagnostic，但不再在有 `last_accepted_output` 且 anchored scan candidate 通过 output continuity gate 时单独让 selector `not_ready`。没有 continuity anchor 时仍 fail-closed；candidate 自身 step/yaw jump 时仍 reject / hold / not_ready。

Basis: 真实 run `20260623T163307Z`：

- Phase 18 后 mission 已能进入更长 hover window；mission hover XY drift/span 为 nominal。
- `scan_reference_drift/status` 在第二段 `hover_hold` 中稳定：`quality_good=true`，`x_m ~= -0.029`，`y_m ~= 0.002`，`inlier_ratio ~= 0.91`，`residual_rms_m ~= 0.081`。
- selector 已有 anchor：`scan_reference_anchor_stamp_sec=22.8`，anchor 约 `(-0.022, 0.009)`。
- 但 selector 在 `hover_hold` 中仍输出 `source=not_ready`、`publish=false`、`reject_reason=cartographer_scan_disagreement`，导致 `/external_nav/odom_candidate` 停止、ExternalNav/MAVLink stale，FCU local-z 后续发散。

Reason: anchored scan candidate 是要发布给 ExternalNav 的 candidate；安全边界应该审查这个 candidate 相对上一帧 accepted output 是否连续，而不是让已经被判定为 raw jump/drift 的 Cartographer 继续永久否决稳定 scan-reference。Cartographer disagreement 仍在 status 中暴露，后续 gate 可以用它诊断 SLAM 本体问题。

任务：

- [x] 调整 selector：`disagreement && last_accepted_output is None` 时仍 reject / hold / not_ready。
- [x] 有 `last_accepted_output` 时，先让 anchored scan candidate 进入 candidate step/yaw gate。
- [x] candidate continuity gate 通过时发布 `scan_reference`，同时保留 `cartographer_scan_disagreement=true` 诊断。
- [x] candidate step/yaw gate 失败时仍按 Phase 2 fail-closed。
- [x] 增加单测覆盖：raw Cartographer 与 anchored scan disagree，但 anchored scan candidate 小步连续时仍 publish。
- [x] 更新旧测试语义：disagreement 不再等价于无条件 hover not_ready。

验收：

- [x] 无 continuity anchor 时，Cartographer/scan disagreement 仍 fail-closed。
- [x] 有 continuity anchor 且 anchored scan candidate 小步连续时，selector `ready=true`、`publish=true`。
- [ ] 真实 hover run 中 `external_nav_source_selector_not_ready` / `external_nav_source_selector_not_publishing` 不再由 stable anchored scan candidate + raw Cartographer disagreement 触发。

## Phase 20 [legacy scan-reference route]: selector re-acquire 死锁改成受限 slew

决策：`hover_hold` 中 candidate 相对 stale `last_accepted_output` 略超过单帧 step/yaw gate 时，不直接发布完整 jump，也不永久 `not_ready`；如果 candidate 总偏移仍在小范围 re-acquire envelope 内，selector 发布一个受限 slew output，每帧最多移动 `max_candidate_step_m` / `max_candidate_yaw_step_rad`。超过 re-acquire envelope 的大跳仍 fail-closed。`hover_settle` 保持 SLAM continuity bridge，不对无锚 scan disagreement 做 slew。

Basis: 真实 run `20260623T163903Z`：

- Phase 19 后 selector 已能发布 anchored scan candidate，不再完全卡在 raw `cartographer_scan_disagreement`。
- 但后续出现 re-acquire 死锁：`reject_reason=candidate_step_jump`，`rejected_step_m ~= 0.134m`，略高于 `max_candidate_step_m=0.12m`；停止发布后 `last_accepted_output` 不再更新，稳定 candidate 永远保持同一个 step error。
- 同一窗口中 scan-reference 后段稳定：`x_m ~= -0.051`，`y_m ~= 0.107`，`inlier_ratio ~= 0.905`，`residual_rms_m ~= 0.088`。
- 大跳仍然存在于 SLAM/scan earlier window，因此不能简单调大 step threshold。

Reason: fail-closed 要限制进入 FCU 的每帧 odom step，而不是在小范围恢复时制造永久 stale。受限 slew 保持每帧安全上限，同时允许稳定 candidate 重新接管 ExternalNav；明显大跳仍会被 `max_candidate_reacquire_*` 拒绝。

任务：

- [x] 新增 `scan_reference_slew` source。
- [x] 新增 `--max-candidate-reacquire-step-m`，default `0.35`。
- [x] 新增 `--max-candidate-reacquire-yaw-step-rad`，default `0.75`。
- [x] `hover_hold` candidate step/yaw 超过单帧 gate 但不超过 re-acquire envelope 时，发布受限 slew output。
- [x] `hover_settle` 不使用 scan slew，保留原来的 SLAM continuity / last accepted hold 语义。
- [x] slew output 也更新 `last_accepted_output`，让 re-acquire 能逐步收敛。
- [x] slew output 更新 last-good map-frame scan candidate，短暂 quality drop 可 hold 最近已发布的安全 output。
- [x] 大范围 jump 仍按 Phase 2 reject / hold / not_ready。
- [x] 增加单测覆盖小范围 re-acquire slew。

验收：

- [x] `step=0.20m`、`max_candidate_step_m=0.12m` 时，第一帧输出只移动 `0.12m`，source=`scan_reference_slew`。
- [x] yaw step 超过单帧 gate 但在 re-acquire envelope 内时，yaw 也按单帧 gate 限幅。
- [ ] 真实 hover run 中 selector 不再因为稳定 candidate 略高于单帧 gate 而永久停止发布。

## Phase 21 [legacy scan-reference route]: scan-reference candidate yaw 也必须 anchor

决策：scan-reference candidate 的 yaw 不再使用 raw SLAM / Cartographer yaw；和 XY 一样，scan yaw 被解释为相对 reference 的 delta，并锚定到 `scan_reference_anchor.yaw_rad` 后作为 map-frame candidate yaw。raw Cartographer yaw jump 仍保留在 diagnostics / disagreement 中，但不能单独污染 anchored scan candidate yaw。

Basis: 真实 run `20260623T164440Z`：

- Phase 20 后 selector 不再主要卡在 XY step re-acquire，但最新 blocker 变成 `reject_reason=candidate_yaw_jump`。
- `rejected_step_m ~= 0.093m` 已低于单帧 step gate，`rejected_yaw_step_rad ~= 1.54rad` 远高于 yaw gate。
- 同一窗口 scan-reference yaw 在 status 中相对稳定，而 selector 输出 yaw 仍来自 raw SLAM yaw，导致 Cartographer yaw jump 否决稳定 anchored scan candidate。

Reason: Phase 15 只 anchor 了 scan-reference XY，留下 yaw 仍走 raw SLAM；这会把 Cartographer yaw jump 重新引入 ExternalNav candidate gate。正确语义是 candidate 的 pose 分量来自同一个 anchored scan-reference frame：`candidate_yaw = anchor_yaw + scan_delta_yaw`，然后再经过 candidate yaw gate。

任务：

- [x] `_anchored_scan_candidate()` 将 yaw 设为 `wrap(anchor.yaw + scan.yaw)`。
- [x] `scan_reference` decision 的 `output_yaw_rad` 使用 anchored scan candidate yaw，不再使用 `slam.yaw_rad`。
- [x] 更新单测：scan-reference yaw delta + anchor 后输出 map-frame yaw。

验收：

- [x] raw SLAM yaw 与 last accepted yaw 大幅不一致时，不会单独改变 anchored scan candidate yaw。
- [ ] 真实 hover run 中 selector 不再因为 raw Cartographer yaw jump 触发 `candidate_yaw_jump`。

## Phase 22 [legacy scan-reference route]: scan-reference 累计漂移过大时不得继续喂 ExternalNav

决策：selector 的 scan eligibility 增加 `horizontal_drift_m` hard gate。scan-reference status 即使 `quality_good=true`、residual/inlier 看起来正常，只要它相对 reference 的累计水平漂移超过安全上限，就不再作为 `/external_nav/odom_candidate` 输入。

Basis: 真实 run `20260623T165013Z`：

- Phase 21 后 mission 能进入 landing_complete，说明 yaw jump 已明显推进；但 hover body 仍失败。
- hover window 中 scan-reference runtime drift 明显发散：`max_horizontal_drift_m ~= 2.39m`，`x_span_m ~= 2.38m`，`y_span_m ~= 0.87m`。
- ExternalNav candidate / ExternalNav / FCU / Gazebo 都出现大漂移，说明 scan-reference 自身累计假漂移已经进入控制链路。
- 仅靠 residual/inlier 不足以识别该问题，因为部分窗口里 residual 仍低、inlier 仍高。

Reason: fail-closed 边界必须挡住“质量指标局部看起来好，但累计 drift 已经不可信”的 scan-reference 输出。这个 gate 不放宽 hover acceptance，只阻断坏 ExternalNav candidate，避免 FCU 跟随假漂移。

任务：

- [x] `_scan_is_eligible()` 增加 `horizontal_drift_m > max_scan_reference_drift_m` blocker。
- [x] 新增 CLI 参数 `--max-scan-reference-drift-m`，default `0.25`。
- [x] 增加单测覆盖 `scan_reference_horizontal_drift_high` fail-closed。

验收：

- [x] scan-reference `horizontal_drift_m=0.28m` 且 max `0.25m` 时，selector `ready=false`、`publish=false`。
- [ ] 真实 hover run 中 scan-reference 大累计漂移不再传播到 ExternalNav/FCU。

## Phase 23 [sim-review-only]: slam_hover_probe 只做诊断，不得提前终止 hover mission

决策：`slam_hover_probe` 在 runtime spec 中降级为 diagnostic-only probe。它的 payload 仍保留在 summary 中用于补充状态样本，但 probe 自身失败、被 kill、输出为空或 `ok=false` 不再提前终止 runtime，也不再产生最终 `probe_*` blocker。

Basis: 真实 hover 调试需要 mission_summary 和 hover rosbag 跑完整，尤其要确认 anchored scan candidate 在 `hover_hold` 中是否消除 frame-mismatch 类 `cartographer_scan_disagreement`。当前 runner 在服务和 rosbag 启动后立刻运行 ROS probes；`slam_hover_probe` 若作为 required probe 早期失败，会触发 cleanup，导致 mission verdict 不完整或不稳定。

Reason: `slam_hover_probe` 是诊断快照，不是飞行安全 gate。hover 是否通过必须由 mission FSM、landing verdict、rosbag evidence、ExternalNav/FCU/Gazebo drift gates 决定。把 diagnostic probe 失败从 hard blocker 中移除，不会放宽 hover acceptance，只避免基础设施过早清场。

任务：

- [x] `BuildRuntimeSpecs()` 中 `slam_hover_probe` 生成 `Required=false`。
- [x] `EvaluateResultGates()` 对 runtime spec 标为 optional 的 probe 不再添加 `probe_failed` / `probe_killed` blocker。
- [x] optional probe 的 missing / empty / not_ok output 不再添加 `probe_output_*` blocker。
- [x] optional probe payload 不再通过 `probeBlockers()` 注入 hard blockers。
- [x] 增加 Go 单测覆盖 optional `slam_hover_probe` 被 kill 且输出为空时不阻断 verdict。

验收：

- [x] `slam_hover_probe` failure 不再导致 runtime runner 因 required probe failure 提前 cleanup。
- [x] gate summary 仍能保留 diagnostic probe output 作为证据，但最终 blocker 由 mission/rosbag/gate 产生。

## Phase 24 [real-flight-safety]: ExternalNav sender 不得翻转 ROS ENU east 轴

Status: `superseded / wrong hypothesis`。Phase 28 用后续真实 run 证据撤回了本 Phase 对 runtime map contract 的假设；本 Phase 只能作为错误路径记录，不能作为当前实现依据。

决策：`external_nav.py` 发送 MAVLink ODOMETRY 时，ROS ENU map position 转成 ArduPilot local position 应使用标准 ENU -> NED 位置轴映射：`x_ned = y_enu`、`y_ned = x_enu`、`z_down = -z_enu`。保留 `MAV_FRAME_LOCAL_FRD` frame id，因为 ArduPilot ODOMETRY handler 只接受 `LOCAL_FRD` / `BODY_FRD`，但位置字段实际被 visual odom 当作 local axes 消费。

Basis: 真实 run `20260623T170642Z`：

- `slam_hover_probe` 已不再提前 kill，mission 能跑出完整 hover verdict。
- anchored scan candidate 与 Gazebo 在 ROS/Gazebo map XY 中方向基本一致，但 FCU local position 的 east 方向相反。
- tlog 中 FCU 收到的 setpoint 是 `LOCAL_NED` hold anchor，而 ODOMETRY 使用旧映射 `y = -x_enu`，导致 ROS ENU `x_enu < 0` 被送成 FCU local `y > 0`。
- ArduPilot ODOMETRY handler 要求 frame id 为 `MAV_FRAME_LOCAL_FRD`，但 handler 直接把 `m.x/m.y/m.z` 交给 visual odom；SITL Vicon 也用 `LOCAL_FRD` frame id 携带 local position axes。

Reason: 这不是放宽 mission acceptance，而是修正进入 FCU EKF 的 runtime input 坐标语义。旧映射会让 hover controller 基于正确的 scan/external_nav 候选，驱动 FCU local position 朝相反 east 方向走，造成 `hover_xy_alignment_direction_mismatch` 和真实漂移。

任务：

- [x] `ros_enu_position_to_mavlink_local_frd()` 改为 `return y_enu, x_enu, -z_enu`。
- [x] `_odometry_mapping_status.field_map.y` 改为 `odom.pose.pose.position.x`，让 diagnostic status 与实际映射一致。
- [x] 更新 sender 单测，覆盖 east 轴不再被翻转。

验收：

- [x] sender 单元测试锁定 ROS ENU -> FCU local position 映射。
- [ ] 真实 hover run 中 FCU local position 与 ExternalNav/Gazebo XY 方向不再相反。
- [ ] `hover_xy_alignment_direction_mismatch` 不再由 ExternalNav sender 坐标翻转触发。

## Phase 25 [sim-review-only]: hover XY gate 比较 Gazebo 诊断源前必须归一化 frame

Status: `superseded / wrong hypothesis`。Phase 28 撤回了“用 SDF projection 修正 Gazebo comparison”的判断；后续不得复用本 Phase 的 Gazebo 二次投影作为 hard gate 依据，除非重新完成 frame/origin/time 审计。

决策：`hover_xy_alignment` 的 pairwise comparison 对 `/gazebo/model/odometry` 使用 SDF `gazeboXYZToNED` 证据做 review-only frame projection 后，再和 ROS map-frame estimator evidence 比较。没有 `model_overlay.sdf` 或 transform 不是 `0 0 0 180 0 90` 时保持旧的 native XY 行为。

Basis: 真实 run `20260623T171953Z`：

- Phase 24 后 `fcu_local_position_pose__external_nav_odom` direction cosine 已到 `0.9967`，说明 ExternalNav sender 的 FCU east 轴翻转已基本修正。
- 同一 summary 中 Gazebo native XY 与 ExternalNav pairwise cosine 只有 `0.335`，但 `gazebo_xyz_to_ned_projection.alignment_to_sources.external_nav_odom.direction_cosine` 为 `0.942`。
- 因此一批 `hover_xy_alignment_direction_mismatch:gazebo_model_odometry__*` 是诊断 frame mismatch，不是 runtime 控制输入错误。

Reason: Gazebo odometry只作为 review evidence，不能直接用 native simulator XY 去和 ROS map XY / FCU NED-converted evidence 做 hard alignment gate。先归一化 frame 能避免假 blocker，让后续 run 的 blocker 聚焦在真实 mission drift、ExternalNav loss、scan-reference drift 上。

任务：

- [x] `summarizeHoverXYAlignment()` 在检测到 SDF `gazeboXYZToNED=0 0 0 180 0 90` 时，将 Gazebo comparison vector 设为 `x=raw_y, y=-raw_x`。
- [x] 保留 source summary 中 raw `final_x_m/final_y_m`，只改 `comparison_final_*` 和 pairwise comparison vector。
- [x] 保持 runtime_control_unchanged，不把 Gazebo truth 引入 runtime input。

验收：

- [x] `go test ./internal/tasks/...` 通过。
- [ ] 下一轮真实 run 中 Gazebo-vs-ExternalNav 的 direction mismatch blocker 不再由 native Gazebo frame 触发。

## Phase 26 [legacy scan-reference route]: scan-reference 累计位移高不应单独切断连续 ExternalNav candidate

决策：`scan_reference_horizontal_drift_high` 从 selector hard eligibility gate 改为 degraded evidence。scan-reference 累计位移超过 `max_scan_reference_drift_m` 时，如果 candidate 仍连续、scan quality/residual/inlier/status 仍健康、且通过 per-frame step/yaw gate，就继续发布 `/external_nav/odom_candidate`；没有 continuity anchor 或出现 Cartographer disagreement / jump / stale / residual high 时仍 fail-closed。

Basis: 真实 run `20260623T172527Z`：

- Phase 24 后 `fcu_local_position_pose__external_nav_odom` direction cosine 为 `0.99996`，ExternalNav sender 方向已对齐。
- mission 在 `hover_hold_duration_sec ~= 5.35s` 后 abort，直接原因是 ExternalNav loss；selector final blocker 为 `scan_reference_horizontal_drift_high`。
- scan-reference drift 约 `0.33-0.36m`，但 residual/inlier 仍健康，candidate 是逐帧连续增长，不是 1.7m 级 jump。
- 旧语义把“机体相对 hover reference 的观测位移”当成“candidate 不可信”，切断了 FCU 继续纠偏所需的位置输入。

Reason: fail-closed 应挡住 stale、低质量、frame disagreement、突然 step/yaw jump；累计位移本身是 hover evidence，不应单独让 ExternalNav 丢失。mission 仍会用 hard drift/span gate 判定 hover 不稳定，这不是放宽 mission 阈值。

任务：

- [x] `_scan_is_eligible()` 不再用 `horizontal_drift_m > max_scan_reference_drift_m` 判定不 eligible。
- [x] `select_external_nav_source()` 将 drift high 加入 decision blockers，并把连续 candidate 标记为 `degraded=true`。
- [x] 无 continuity anchor 且 Cartographer/scan 不一致时，drift high 仍随 `cartographer_scan_disagreement` 一起 fail-closed。
- [x] 更新 selector 单测覆盖连续发布与无 anchor fail-closed 两条边界。

验收：

- [x] `pytest test_external_nav_source_selector.py test_external_nav_sender.py` 通过。
- [x] `go test ./internal/tasks/...` 通过。
- [x] 真实 hover run `20260623T172902Z` 中 selector 不再在 hover_hold 早段只因 `scan_reference_horizontal_drift_high` 造成 ExternalNav loss；hover_hold 从上一轮 `~5.35s` 延长到 `~15.25s`。
- [ ] 真实 hover run 仍 blocked：无条件继续发布 high-drift scan candidate 会让 scan-reference 后半段发散到 `~1.3m`，ExternalNav/Gazebo drift 变大。

## Phase 27 [legacy scan-reference route]: high-drift scan candidate 需要稳定窗口约束，不能无条件继续发布

决策：Phase 26 证明“累计 drift high 单独 hard cut”太早，但“drift high 仍无条件发布”也太松。下一步 selector 需要把 high-drift 状态改成受限 tracking 模式：drift 超过 `max_scan_reference_drift_m` 后，只有 scan quality/inlier/residual 仍好、correction eligibility 稳定、且 candidate 通过 step/yaw gate 时才继续发布；一旦稳定窗口断掉，就 hold last accepted，TTL 后 not_ready。

Basis: 真实 run `20260623T172902Z`：

- hover_hold 达到 `15.25s`，说明 Phase 26 消除了过早 `scan_reference_horizontal_drift_high` loss。
- 但 ExternalNav candidate drift 增长到 `~1.05m`，Gazebo drift `~1.34m`，FCU local drift `~0.34m`。
- selector 最终 blocker 变成 `scan_reference_quality_not_good` / `scan_reference_inlier_ratio_low`，说明 scan-reference 后半段确实发散，而不是 mission gate 假阳性。
- ExternalNav 和 FCU 方向仍一致，问题转移到 scan candidate runaway 的安全约束。

任务：

- [x] selector 增加 high-drift tracking gate：`horizontal_drift_m > max_scan_reference_drift_m` 时要求 `correction_eligibility.correction_allowed=true`、allowed axes 非空、sign flips 在上限内、direction cosine 达标。
- [x] high-drift tracking gate 失败时，不继续发布新 scan candidate；先 hold last accepted，TTL 后 not_ready。
- [x] 单测覆盖：high drift + stable eligibility 可继续 degraded publish；high drift + unstable eligibility hold/not_ready；stale/residual/inlier bad 仍 fail-closed。
- [x] 真实 hover run `20260623T173342Z` 中 ExternalNav candidate runaway 从上一轮 `~1.05m` 降到 `~0.58m`，Gazebo-vs-ExternalNav direction mismatch blocker 消失。
- [ ] 真实 hover run 仍 blocked：hover drift `~0.28m`、span `~0.63m`，scan-reference 后半段 `quality_not_good/inlier_ratio_low` 后 ExternalNav loss，仍未达到 `<0.1m` hover acceptance。

## Phase 28 [contract-validation]: hover world map x 是 west，恢复 ExternalNav east 符号并修正诊断 comparison

决策：撤回 Phase 24/25 中把 runtime map 当标准 ENU 的假设。当前 hover world 的 runtime ROS map contract 在真实 run 证据上表现为 `map_x=west`、`map_y=north`。因此 ExternalNav sender 应发送 `x_ned=map_y`、`y_ned=-map_x`；FCU local position 作为诊断证据转回 map XY 时应使用 `map_x=-east`、`map_y=north`；`/gazebo/model/odometry` 这个 ROS topic 的 native XY 已经和 runtime map evidence 对齐，不再用 SDF `gazeboXYZToNED` 二次投影参与 pairwise gate。

Basis: 对比真实 run：

- Phase 23/24 前的 `20260623T170642Z`：Gazebo native XY 与 ExternalNav candidate direction cosine `~0.948`，但 FCU 诊断按 Phase 24 的 `map_x=east,map_y=north` 转换后与 ExternalNav direction cosine `~-0.92`。
- Phase 24 后的 `20260623T173342Z`：FCU 与 ExternalNav 诊断 direction cosine `~1.0`，但 tlog/Gazebo 显示真实 east 方向相反，物理 drift 明显放大。
- tlog 中 hover setpoint 是 local NED hold anchor；ExternalNav ODOMETRY 用 Phase 24 映射后 FCU local east 往正方向漂，而 Gazebo native / pre-Phase24 evidence 指向 `map_x=west` 才是 runtime map contract。

Reason: 之前“修正”只是让 FCU 诊断和 ExternalNav 在错误的 map conversion 下对齐，实际控制方向变差。正确边界是恢复 runtime input 坐标语义，同时让 gate comparison 按同一 map contract 比较，避免用诊断投影掩盖真实物理漂移。

任务：

- [x] `ros_enu_position_to_mavlink_local_frd()` 恢复为 `return map_y, -map_x, -z`。
- [x] ExternalNav mapping status 恢复 `y=-odom.pose.pose.position.x`。
- [x] `hover_xy_alignment` 中 FCU local comparison 改为 `map_x=-local_y, map_y=local_x`。
- [x] `hover_xy_alignment` 不再把 `/gazebo/model/odometry` 用 SDF `gazeboXYZToNED` 二次投影后参与 pairwise comparison。
- [x] 更新 sender 与 gate synthetic MCAP 单测。

验收：

- [x] targeted pytest / Go tests 通过。
- [x] 真实 hover run `20260623T174208Z` 中 Gazebo native / ExternalNav / FCU local direction evidence 重新一致；`gazebo_model_odometry__external_nav_odom` direction cosine `~0.9997`，`fcu_local_position_pose__external_nav_odom` `~0.9705`。
- [x] Phase 24 的 east 符号误导已消除，并且没有 hover-window ExternalNav loss：`external_nav_loss_duration_sec=0`、`mavlink_external_nav_loss_duration_sec=0`。
- [ ] 真实 hover run 仍 blocked：position hold 没把真实 drift 拉回，Gazebo drift `~1.0m`、FCU local drift `~0.56m`，并出现 z-span/altitude crash 证据。

## Phase 29 [real-flight-safety]: 定位输入已一致，下一步修 FCU position-hold 控制链路

Status: `partially superseded`。Phase 28/29 只证明当时 run 中若干 XY direction evidence 已对齐，不能外推为“Gazebo physical pose、ExternalNav estimate、FCU local estimate 的位移尺度已经一致”。Phase 31 后续证据显示 ExternalNav/FCU drift 小而 Gazebo evidence drift 大，本 Phase 的强结论必须降级。

决策：不再继续把主要精力放在 selector fail-closed 上。Phase 28 证明定位输入方向已经与 Gazebo/FCU 一致，且 ExternalNav 未 loss；当前主问题是 FCU 在收到固定 local-NED position hold setpoint 后没有把 XY/Z 拉回。下一步要检查 guided position target 是否被 ArduPilot 当作 position target 使用、是否模式/参数允许 XY position control、以及 hover mission 是否在 crash/altitude 异常前持续发送正确 setpoint。

Basis: 真实 run `20260623T174208Z`：

- `SET_POSITION_TARGET_LOCAL_NED` tlog 中持续发送，frame=`LOCAL_NED`，mask=`2552`，setpoint 固定在 hold anchor 附近。
- `/external_nav/odom_candidate`、`/external_nav/odom`、Gazebo native XY direction 基本一致，说明定位输入方向不再是主矛盾。
- mission hover 中 `external_nav_loss_duration_sec=0`、`mavlink_external_nav_loss_duration_sec=0`，说明不是 fail-closed 过早切断。
- 但 hover drift 仍 `~0.56m`，Gazebo max drift `~1.0m`，z-span `~0.36m`，run 以 `crash_detected` / altitude blockers 失败。

任务：

- [x] 解码/验证 position target type mask，确认 x/y/z/yaw 未被 ignore。
- [x] 检查 ArduPilot mode/params/EKF source 是否允许 Guided local-NED position hold 闭环。
- [x] 检查 `/ap/v1/pose/filtered` / `LOCAL_POSITION_NED` / setpoint error 在 hover window 的时间序列，确认控制误差持续存在还是估计/实际 diverge。
- [x] 基于证据选择修复：控制 setpoint frame、FCU controller runtime、ArduPilot params，或 mission hold setpoint 策略。

证据：

- `SET_POSITION_TARGET_LOCAL_NED.type_mask=2552` 只 ignore velocity / acceleration / yaw_rate；x/y/z/yaw 都是 active target。
- ArduPilot `STATUSTEXT` 已报告 `EKF3 IMU0/1 is using external nav data`，hover window `EKF_STATUS_REPORT.flags=895`，local position 仍可用。
- 真实 tlog 在 hover window 中 setpoint x/y/z 固定在约 `(0.003, -0.070, -0.5)`，但 first setpoint yaw 是 `0.0rad`，随后才变成当前 yaw 约 `1.57rad`。
- 同一窗口 local position 误差从接近 0 增长到 `~1.36m`，姿态在 crash 前达到约 `pitch=86.7deg`；ArduPilot 报 `Crash: Disarming: AngErr=55>30, Accel=0.3<3.0`。
- `hover_mission` 中 hold x/y/yaw anchor 没有在进入 `hover_hold` 时显式 capture；x/y 依赖 `hover_hold_setpoint_axes()` fallback，yaw 还被初始化为 `0.0`。这不是阈值问题，而是 mission setpoint 语义不安全。

## Phase 30 [real-flight-safety]: hover_hold 第一帧必须锁定当前 local pose/yaw anchor

决策：`hover_mission` 进入 `hover_hold` 并发送第一帧 position target 前，必须用当前 FCU local x/y/yaw 显式 capture hold anchor；不得用初始化的 `0.0rad` yaw，也不得依赖“没有 anchor 就 fallback current”的隐式行为。

Basis: Phase 29 tlog 证据显示第一对 `SET_POSITION_TARGET_LOCAL_NED` yaw 为 `0.0rad`，而 vehicle 当前 yaw 约 `1.57rad`。随后姿态大幅失控并 crash。代码层面 `hover_mission.py` 初始化 `hold_yaw_rad=0.0`，且 `_send_hold_setpoint()` 未 capture x/y/yaw anchor。

Reason: Guided position hold 应该锁定进入 hold 时的当前位置和当前 yaw。把 yaw 初始化为 0 会在第一帧制造约 90 度 yaw error；不显式 capture x/y 会让 target 是否固定取决于 runtime current pose 更新时机。

任务：

- [x] 删除 `hover_mission.py` 中 `hold_yaw_rad = 0.0` 初始化。
- [x] `_send_hold_setpoint()` 发 setpoint 前调用 `capture_hold_anchor()`，第一次有效 x/y/yaw 被锁定，后续复用 anchor。
- [x] setpoint yaw 使用 captured `hover.hold_yaw_rad`，没有 anchor 时才 fallback current yaw。
- [x] 增加单测覆盖 no-anchor 时 capture 当前 yaw。

验收：

- [x] `pytest test_hover_mission.py test_external_nav_sender.py test_external_nav_source_selector.py` 通过。
- [x] `go test ./internal/tasks/...` 通过。
- [ ] 真实 hover run 中第一帧 `SET_POSITION_TARGET_LOCAL_NED.yaw` 应接近当前 FCU yaw，而不是 `0.0rad`。
- [ ] 真实 hover run 不应再因初始 yaw target 错误触发大姿态误差 / crash。

真实验证：

- [x] `20260623T175242Z` tlog 中第一帧 `SET_POSITION_TARGET_LOCAL_NED.yaw=1.571rad`，已不再发送 `0.0rad` yaw target。
- [ ] 该 run 仍 blocked；0-10s hover hold 稳定，之后 ExternalNav candidate 后段漂移到约 `0.61m`，FCU/Gazebo 跟随漂移并再次 crash。说明 Phase 30 修掉的是一个真实 setpoint bug，但 high-drift scan candidate 后段仍过松。

## Phase 31 [legacy scan-reference route]: high-drift scan candidate 必须有 active correction intent

决策：`scan_reference_horizontal_drift_high` 后继续发布 candidate 的条件从“correction eligibility allowed”收紧为“correction eligibility allowed 且 correction intent active 且 intent 无 blockers”。否则 selector 只 hold last accepted，TTL 后 not_ready。

Basis: 真实 run `20260623T175242Z`：

- Phase 30 后 first setpoint yaw 正确，hover 前约 10s 误差接近 0。
- 之后 ExternalNav odom 从约 `(0.004,-0.057)` 漂到 `(0.096,0.407)`，再到 `(0.095,0.529)`；FCU local error 从 `0.07m` 增到 `0.23m`、随后约 `1.0m`。
- scan-reference summary 显示 hover window `correction_allowed_ratio ~= 0.32`，但 `correction_intent_active_ratio ~= 0.05`，后段 `scan_reference_inlier_ratio_low` / phase4b not ok。
- 当前 Phase 27 gate 只要求 eligibility allowed，导致“连续但已无稳定 correction intent 的 high-drift candidate”继续进入 ExternalNav，ArduPilot 大角度追踪并 crash。

Reason: high-drift 状态已经超出正常 hover acceptance；只有 correction intent 自身也稳定、方向一致、无 blockers 时才可继续把 scan candidate 当作 FCU odom 输入。否则正确行为是 fail-closed/landing，而不是让坏 odom 驱动姿态。

任务：

- [x] `_high_drift_tracking_blockers()` 读取 `correction_intent`。
- [x] high drift 时若 `correction_intent.active=false`，加入 `scan_reference_high_drift_intent_not_active` blocker。
- [x] high drift 时若 `correction_intent.blockers` 非空，加入 `scan_reference_high_drift_intent_has_blockers` blocker。
- [x] 增加单测：eligibility allowed 但 intent inactive 时必须 hold / reject，不得继续发布新 scan candidate。

验收：

- [x] `pytest test_external_nav_source_selector.py test_hover_mission.py` 通过。
- [x] `go test ./internal/tasks/...` 通过。
- [ ] 真实 hover run 中 high-drift 后段 correction intent inactive 时 selector 应 hold/not_ready，而不是继续传播 drifting candidate。
- [ ] 若 mission 仍失败，应更早安全 landing，而不是 crash。

真实验证：

- [x] `20260623T180009Z` 不再 crash，landing evaluated，最大 pitch 约 `20.6deg`，Phase 31 把失败模式从 unsafe crash 改成安全 abort/landing。
- [x] ExternalNav/FCU drift 被限制在约 `0.09-0.14m`，但 Gazebo hover-window drift 仍约 `1.66m`；这说明 selector 成功挡住了 runaway candidate，但定位输入低估真实位移，FCU 没有足够位置误差去纠偏。
- [ ] 真实 hover 仍 blocked：`horizontal_span_m ~= 0.123m` 略高于 `0.1m`，且 `hover_gazebo_model_horizontal_drift` 很大。

## Phase 32 [legacy scan-reference route]: correction intent 稳定窗口与真实 status 频率对齐

Status: `failed and reverted`。真实 run `20260623T180850Z` 显示把 consecutive allowed samples 从 8 降到 3 后没有收敛：hover_hold 变短、ExternalNav loss 重新出现、Gazebo/ExternalNav/FCU evidence 仍不一致，并在 landing 前后出现 crash 风险。对应代码改动已回滚；本 Phase 只能作为负结果，不能作为当前执行方向。

决策：将 scan-reference correction intent 的连续 allowed 样本默认值从 8 降到 3，并同步 Python parser fallback。mission/gate 阈值不变；这只改变“scan-reference 已经质量稳定时，多久允许 high-drift candidate 继续作为 ExternalNav 输入”的内部稳定窗口。

Basis: `20260623T180009Z`：

- hover window 中 scan-reference `quality_good_ratio ~= 0.87`，`correction_allowed_ratio ~= 0.34`，但 `correction_intent_active_ratio ~= 0.10`。
- active intent 的一致性本身很好：`counter_drift_cosine.min ~= 0.997`，没有 intent consistency blockers。
- runtime spec 要求 8 个连续 allowed 样本；在当前 status 频率和短稳定窗口下，intent 太晚/太短，Phase 31 high-drift gate 很快 hold/freeze ExternalNav，FCU 因估计低估真实位移而无法纠偏。

Reason: 这是内部 readiness 窗口与真实采样频率不匹配，不是放宽 hover acceptance。scan-reference 仍必须满足质量、inlier/residual、axis stability、direction/sign、phase4b consistency 和 high-drift active intent；mission drift/span gate 仍保持 hard gate。

任务：

- [x] `scan_reference_drift.py` parser fallback 曾改为 `--min-correction-intent-consecutive-allowed-samples=3`。
- [x] `DefaultScanReferenceDriftSpec()` 曾改为 `MinCorrectionIntentConsecutiveAllowedSamples: 3`。
- [x] 保留现有单测中 “少于 3 不 active，达到 3 active” 的 fail-closed 语义。
- [x] 真实 run 负结果确认后，parser fallback 和 runtime spec 默认值已回滚到 Phase 31 语义。

验收：

- [x] `pytest test_scan_reference_drift.py test_scan_reference_correction.py test_external_nav_source_selector.py test_hover_mission.py` 通过。
- [x] `go test ./internal/tasks/...` 通过。
- [x] 真实 hover run `20260623T180850Z` 证明该改动未修复 root cause，且引入更差 mission 行为。
- [x] 本 Phase 标记为失败/回滚，后续不得继续通过缩短 intent 窗口来逼迫 high-drift candidate 进入 ExternalNav。

## Phase 33 [contract-validation]: diagnostic-only 观测源可信度审计

目标：在继续修改 runtime selector / mission / control 前，先复现并定位 Gazebo evidence、ExternalNav estimate、FCU local estimate 第一次发生显著分叉的位置。该 Phase 不允许改变飞行控制输入，不允许放宽 mission gate，不允许把任何单一 topic 预设为真值。

Observed failure: Phase 31/32 真实 run 中出现 observation disagreement：ExternalNav/FCU estimated drift 较小，但 Gazebo world/model pose evidence 显示较大 horizontal drift。当前尚未证明是 Gazebo 取数/frame/origin/time 错，还是 ExternalNav/SLAM/scan-reference 低估真实位移。

Hypothesis to test:

- Gazebo evidence 可能取错 model/link、frame、origin 或时间窗口。
- ExternalNav/FCU estimate 可能因 hold/reject/anchor 语义低估真实位移。
- scan-reference / Cartographer odom 可能已经在进入 `/external_nav/odom_candidate` 前发生尺度、符号或锚点偏差。
- mission summary 的 final displacement / span 可能混用了不同 reference frame 或不同时间窗口。

任务：

- [x] 新增 diagnostic-only 审计脚本：`scripts/diagnostics/hover_source_audit.py`。
- [x] 对 Phase 31/32 关键 run 生成 summary-based source audit：
  - [x] `artifacts/sim/hover/20260623T180009Z/source_audit.json`
  - [x] `artifacts/sim/hover/20260623T180009Z/source_audit.md`
  - [x] `artifacts/sim/hover/20260623T180850Z/source_audit.json`
  - [x] `artifacts/sim/hover/20260623T180850Z/source_audit.md`
- [x] 对同一 hover window 导出已由 `hover_xy_alignment` 时间对齐过的源：
  - [x] `/gazebo/model/odometry`。
  - [x] `/slam/odom_corrected`。
  - [x] `/external_nav/odom_candidate`。
  - [x] `/external_nav/odom`。
  - [x] `/navlab/fcu/local_position_pose`。
  - [x] `/navlab/scan_reference_drift/odom`，来自 `scan_reference_runtime_drift` summary，尚未进入 pairwise table。
  - [x] `/scan` derived scan-reference hover drift，review-only，不是 runtime input。
- [x] 为已总结源写明 topic、frame、child frame、comparison frame、sample count、final XY、magnitude、max drift、trust status。
- [x] 生成同一 hover window 的 pairwise direction/scale table，区分 final displacement magnitude 与 max drift。
- [x] 找出第一处 summarized-source 分叉：两轮 run 都是 `/gazebo/model/odometry` vs `/slam/odom_corrected` direction mismatch。
- [x] 若 Gazebo evidence 未通过交叉审计，暂停使用 Gazebo drift 作为 hard causal conclusion，只保留为 blocker evidence。
- [x] 新增 raw-bag audit helper/command：
  - [x] `orchestration/sim/internal/tasks/hover_raw_source_audit.go`
  - [x] `orchestration/sim/cmd/hover-source-audit/main.go`
- [x] raw-bag audit 把同一 hover window 的这些源放进同一 pairwise table：
  - [x] `/slam/odom`
  - [x] `/navlab/scan_reference_drift/odom`
  - [x] `/slam/odom_corrected`
  - [x] `/external_nav/odom_candidate`
- [x] 对 Phase 31/32 关键 run 生成 raw-bag source audit：
  - [x] `artifacts/sim/hover/20260623T180009Z/raw_source_audit.json`
  - [x] `artifacts/sim/hover/20260623T180850Z/raw_source_audit.json`
- [x] 将 raw-bag chain audit 合并进 `source_audit.md/json`。
- [ ] `/ap/v1/pose/filtered`、MAVLink ODOMETRY/tlog 尚未进入同一 source audit table。
- [ ] `/gazebo/model_states` 与 `/gazebo/link_states` 当前 hover rosbag metadata 中缺失，尚不能用它们交叉确认 `/gazebo/model/odometry`。
- [ ] 下一步若要把 Gazebo-vs-SLAM divergence 升级为 root cause，仍必须补 Gazebo model/link 或其他 SITL physical pose 交叉证据。

验收：

- [x] 文档/产物中有可复查的 source audit table，包含 run id、topic、frame、final XY、direction cosine、timestamp range。
- [x] 明确写出“第一个 summarized 分叉点”，并明确它不是最终 root cause。
- [x] 明确写出 raw chain 分叉位置：两轮都是 `/slam/odom` vs `/navlab/scan_reference_drift/odom`，classification=`pre_correction_disagreement`。
- [x] 没有 runtime behavior change；本 Phase 只新增诊断脚本、测试和 artifact-local audit 输出。

真实审计结果：

| run | window | summarized divergence | raw chain classification | raw evidence | limitation |
| --- | --- | --- | --- | --- | --- |
| `20260623T180009Z` | `hover_hold`, `13.55s` | `/gazebo/model/odometry` vs `/slam/odom_corrected`: cosine `-0.999`, scale `0.876` | `pre_correction_disagreement` | `/slam/odom` vs `/navlab/scan_reference_drift/odom`: cosine `-1.000`, scale `0.390`; `/slam/odom` vs `/slam/odom_corrected`: cosine `1.000`, scale `1.000`; `/slam/odom_corrected` vs `/external_nav/odom_candidate`: cosine `-0.822`, scale `0.097` | Gazebo model/link states missing; `/ap/v1/pose/filtered` and tlog ODOMETRY not yet in table |
| `20260623T180850Z` | `hover_hold`, `6.40s` | `/gazebo/model/odometry` vs `/slam/odom_corrected`: cosine `-0.998`, scale `0.805` | `pre_correction_disagreement` | `/slam/odom` vs `/navlab/scan_reference_drift/odom`: cosine `-0.993`, scale `0.913`; `/slam/odom` vs `/slam/odom_corrected`: cosine `1.000`, scale `1.000`; `/slam/odom_corrected` vs `/external_nav/odom_candidate`: cosine `-0.941`, scale `0.428` | Gazebo model/link states missing; `/ap/v1/pose/filtered` and tlog ODOMETRY not yet in table |

Conclusion: raw-bag audit 证明 correction stage 不是当前分叉来源：`/slam/odom` 与 `/slam/odom_corrected` 在两轮 run 中同向同尺度，说明 scan-reference correction node 没有改变 raw SLAM 位移。分叉已经存在于 correction 之前的 raw SLAM 与 scan-reference drift 之间；ExternalNav candidate 后续更接近 scan-reference/candidate 链路而不是 raw/corrected SLAM 链路。下一步不能继续改 selector 或 correction 参数；应审计 scan-reference frame/sign contract 与 selector 在 `scan_reference` frame 到 `map` candidate 时的 transform/anchor 语义。

## Phase 34 [legacy scan-reference route]: scan-reference frame/sign contract 与 selector anchor 语义审计

目标：确认 `/navlab/scan_reference_drift/odom` 的 `x/y` 到底是可直接加到 map anchor 的 pose delta，还是需要作为 measurement/correction intent 取反或经过 body/map transform。该 Phase 仍是 diagnostic-only，不改 runtime selector。

Code audit:

- `scan_reference_drift.py` 发布 `/navlab/scan_reference_drift/odom`，`frame_id=scan_reference`、`child_frame_id=base_link`，position 直接写 `estimate.x_m/y_m`。
- `ScanReferenceDriftEstimator` 单测定义的正向语义是：若 range pattern 由 `_scan_for_translation(+x,+y)` 生成，estimator 返回 `estimate.x_m=+x, estimate.y_m=+y`。
- `evaluate_correction_intent()` 明确把 correction intent 写成 `correction_x_m=-source_x_m`、`correction_y_m=-source_y_m`。这说明 scan-reference measurement 在 correction 语义中不是直接 map pose target，而是需要反向纠偏的 measured displacement。
- `external_nav_source_selector._anchored_scan_candidate()` 当前把 scan-reference delta 直接同号加到 anchor：`anchor.x + scan.x`、`anchor.y + scan.y`，yaw 也是 `anchor.yaw + scan.yaw`。
- selector anchor 在 scan reference reset 时设置为 `last_accepted_output or slam_candidate`；输出 `frame_id` 改成 `slam.frame_id`。也就是说 selector 当前把 `scan_reference` frame 的 delta 当作 map-frame delta 使用，没有显式 body/yaw transform，也没有取反。

Raw evidence:

| run | scan vs corrected SLAM | scan vs candidate | corrected SLAM vs candidate | selector contract |
| --- | --- | --- | --- | --- |
| `20260623T180009Z` | `/slam/odom` vs `/navlab/scan_reference_drift/odom`: cosine `-1.000`, scale `0.390` | `/navlab/scan_reference_drift/odom` vs `/external_nav/odom_candidate`: cosine `0.815`, scale `0.249` | `/slam/odom_corrected` vs `/external_nav/odom_candidate`: cosine `-0.822`, scale `0.097` | `candidate_direction_follows_scan_reference_not_corrected_slam` |
| `20260623T180850Z` | `/slam/odom` vs `/navlab/scan_reference_drift/odom`: cosine `-0.993`, scale `0.913` | `/navlab/scan_reference_drift/odom` vs `/external_nav/odom_candidate`: cosine `0.896`, scale `0.390` | `/slam/odom_corrected` vs `/external_nav/odom_candidate`: cosine `-0.941`, scale `0.428` | `candidate_direction_follows_scan_reference_not_corrected_slam` |

Conclusion: 当前 ExternalNav candidate 的方向跟随 scan-reference measurement，而不是 raw/corrected SLAM。结合 code audit，最可疑的 contract bug 是 selector 把 scan-reference measurement 当成 map pose delta 同号 anchor 了；但 scan-reference correction 语义本身使用 `-measurement` 作为纠偏方向。因此下一步若要改 runtime，应该先做最小可控修复候选：在 selector 中把 scan-reference measurement 通过明确命名的 transform 函数转换成 map candidate delta，并用单测锁住“measurement delta 与 correction intent 是相反方向”的 contract。不能继续靠调 candidate gate 或 correction intent 窗口。

## Phase 35 [legacy scan-reference route]: selector scan-reference measurement -> map candidate contract fix

目标：把 selector 里 `scan_reference` measurement 到 map candidate 的转换显式命名，并用单测锁住 contract：scan-reference measurement 表示 measured displacement，correction intent 是相反方向，因此 anchored map candidate 必须使用 `anchor - measurement`，不能继续隐式 `anchor + measurement`。

Basis:

- Phase 34 code audit 证明 `scan_reference_drift.py` 发布的是 `frame_id=scan_reference` 的 measurement，`evaluate_correction_intent()` 使用 `-source_x_m/-source_y_m`。
- Phase 33 raw-bag audit 显示 ExternalNav candidate 方向跟随 scan-reference measurement，而不是 raw/corrected SLAM。

Observed failure:

- selector 旧 anchor 语义把 scan-reference measurement 当作 map pose delta 同号加到 anchor，导致 candidate direction 与 correction intent 方向相反。

Change:

- [x] 将 selector 内部转换抽成 `_scan_reference_measurement_to_map_candidate()`。
- [x] anchor 存在时输出 `x/y/z/yaw = anchor - measurement`，并保留 anchor 的 map/base_link frame contract。
- [x] anchor 不存在时保持原 measurement 输出，避免改动 bootstrap 行为。
- [x] 更新 selector 入口调用，所有 anchored scan candidate 统一经过该函数。
- [x] 新增单测直接锁定 `measurement=(+0.20,-0.10,+0.05yaw)`、`anchor=(2.0,3.0,+0.40yaw)` -> candidate `(1.80,3.10,+0.35yaw)`。
- [x] 更新既有 anchored candidate 单测，断言从旧的 `anchor + measurement` 改为 `anchor - measurement`。

Non-goals:

- [x] 未调整 candidate gate 阈值。
- [x] 未调整 correction intent 稳定窗口。
- [x] 未新增 body/yaw rotation 语义；这需要后续单独证据证明。

Verification:

- [x] `uv run pytest navlab/tests/companion/test_external_nav_source_selector.py -q` -> `31 passed`。
- [x] 真实 hover run `20260624T011951Z` 已生成 raw/source audit：
  - [x] `just navlab-run hover` -> `status=blocked`，runtime error 是 `frame_contract_probe` 因 `/tf_static` sample missing 失败；mission 在 `hover_hold` 后因 `slam_quality_lost_after_airborne` abort，并完成 landing。
  - [x] `go run ./cmd/hover-source-audit /home/nn/workspace/3588/world-model/artifacts/sim/hover/20260624T011951Z` -> `raw_source_audit.json`。
  - [x] `uv run python scripts/diagnostics/hover_source_audit.py artifacts/sim/hover/20260624T011951Z` -> `source_audit.json/md`。
  - [x] Raw hover window `8.950s` 中 `/navlab/scan_reference_drift/odom` vs `/external_nav/odom_candidate` direction cosine 为 `-0.894`，不再是 Phase 33/34 旧 run 的同向 `+0.815/+0.896`。
  - [x] `/external_nav/odom_candidate` vs `/slam/odom_corrected` direction cosine 仍为 `-0.875`，selector contract classification 为 `candidate_direction_disagrees_with_both_scan_reference_and_corrected_slam`。

Conclusion:

- [x] Phase 35 修复了“candidate 同向跟随 scan-reference measurement”的旧 contract bug。
- [ ] 真实 run 仍未通过；当前 blocker 已转为 post-correction selector divergence / SLAM quality loss / frame_contract_probe `/tf_static` sampling，而不是旧的 `anchor + measurement` 同向错误。

## Phase 36 [real-flight-safety]: direct `/slam/odom` ExternalNav baseline

目标：先验证官方/项目 real config 对齐的最小链路，而不是继续在 scan-reference selector 上叠补丁：

```text
/slam/odom -> external_nav bridge -> /external_nav/odom -> MAVLink ODOMETRY -> FCU EKF
```

Basis:

- ArduPilot ExternalNav 的关键 contract 是向 EKF 输入外部位置估计；ROS `/slam/odom` 需要经过 bridge/MAVLink sender 转为 MAVLink ODOMETRY。
- 本项目 real 配置已经使用 `external_nav_input_odom_topic:=/slam/odom`。
- selector route 最新真实 run `20260624T011951Z` 已经不再同向跟随 scan-reference measurement，但仍出现 post-correction selector divergence、ExternalNav loss、hover mission abort。

Change:

- [x] 增加 hover `slam-direct` simulation profile：`just navlab-run hover --simulation-profile slam-direct`。
- [x] 该 profile 只把 hover ExternalNav bridge 输入切到 `/slam/odom`；默认 `hover` / `ideal` 仍保持 `/external_nav/odom_candidate` selector route。
- [x] gate 只在 selector route 下要求 `external_nav_source_selector` blocker；direct `/slam/odom` route 不再因为未使用的 selector 状态阻塞。
- [x] gate landing evidence 在 probe 未采样 `/navlab/landing/status` 时，可从 `mission_summary.landing` 回填，避免 mission 已评估 landing 但顶层误报 `landing_not_evaluated`。

Verification:

- [x] `go test ./internal/tasks ./internal/config -run 'TestApplySimulationProfile|TestGenerateRuntimeArtifactsHoverSlamDirectUsesRawSlamOdomInput|TestGenerateRuntimeArtifactsFromConfiguredTasks|TestHoverSourceSelectorGateOnlyAppliesToSelectorRoute|TestLandingEvidenceFallsBackToHoverMissionSummary|TestEvaluateResultGatesReadsProbeAndRosbagArtifacts|TestExternalNavFeedbackBlockersRequireSlamBridgeAndFCUFeedback|TestLoaderReadsProjectAndYAMLTasks'`。
- [x] dry-run `20260624T015407Z` confirmed:
  - [x] `slam_runtime.toml`: `external_nav_input_odom_topic = '/slam/odom'`。
  - [x] `external_nav_bridge_params.yaml`: `input_odom_topic: /slam/odom`。
- [x] first live direct run `20260624T015520Z`:
  - [x] ExternalNav input `/slam/odom`，frame `map -> base_link`，rate `259.793Hz`。
  - [x] MAVLink ExternalNav ready，sent `1773`，rate `20Hz`，FCU local position count `847`。
  - [x] Mission `ok=true`, `S13 task_success`, `hover_body_ok=true`, `landing_ok=true`。
  - [x] hover drift `0.0378m`, span `0.0674m`, ExternalNav loss `0s`, MAVLink ExternalNav loss `0s`。
  - [x] top-level blocked only by stale gate `landing_not_evaluated` despite mission landing evaluated.
- [x] second live direct run after landing evidence fallback `20260624T020206Z`:
  - [x] top-level `TASK_STATUS_OK`, blockers `[]`。
  - [x] ExternalNav input `/slam/odom`，frame `map -> base_link`，rate `286.074Hz`。
  - [x] MAVLink ExternalNav ready，sent `1792`，rate `20Hz`，FCU local position count `1059`。
  - [x] Mission `ok=true`, `S13 task_success`, `hover_body_ok=true`, `landing_ok=true`。
  - [x] hover drift `0.0149m`, span `0.0489m`, ExternalNav loss `0s`, MAVLink ExternalNav loss `0s`。

A/B result:

| route | run | top-level | ExternalNav input | hover drift/span | ExternalNav loss | XY alignment | mission |
| --- | --- | --- | --- | --- | --- | --- | --- |
| selector route | `20260624T011951Z` | `TASK_STATUS_ERROR` | `/external_nav/odom_candidate` | `0.131m / 0.188m` | `1.05s` | failed | abort after short hover |
| direct `/slam/odom` | `20260624T020206Z` | `TASK_STATUS_OK` | `/slam/odom` | `0.015m / 0.049m` | `0s` | passed | `S13 task_success` |

Conclusion:

- [x] Direct `/slam/odom` baseline is not only viable; it currently passes the full hover run.
- [x] scan-reference selector is not required for hover stability in this baseline and should not remain the default justification unless direct `/slam/odom` later shows a reproducible failure.
- [ ] Next decision should be whether to make direct `/slam/odom` the default hover route and demote selector route to diagnostic/experimental, rather than continuing selector fixes.

## Phase 37 [contract-validation]: direct `/slam/odom` repeatability check

目标：按“三次真实 run 都没问题才算稳定”的标准验证 Phase 36 direct route。不能只挑成功 run。

Pre-fix observation:

- [x] First repeat attempt `20260624T021214Z` had mission success but top-level `TASK_STATUS_BLOCKED` only because `gazebo_model_odometry` disagreed with estimate sources.
- [x] That exposed a gate semantics bug: `gazebo_model_odometry` was already marked `review_only_needs_cross_check`, but `summarizeHoverXYAlignment` still promoted Gazebo-vs-estimate direction mismatch to hard blocker.
- [x] Fixed gate semantics: Gazebo odometry remains in pairwise/audit evidence, but Gazebo-only disagreement is `audit_blockers`, not a hard blocker. Estimate-vs-estimate disagreement remains hard-gated.
- [x] Verification: `go test ./internal/tasks ./internal/config` passed.

Three repeat attempts after the gate semantics fix:

| attempt | run | top-level | drift/span | ExternalNav loss | mission | blockers |
| --- | --- | --- | --- | --- | --- | --- |
| 1/3 | `20260624T021838Z` | `TASK_STATUS_BLOCKED` | `0.077m / 0.305m` | `0s` | `hover_span_unstable`, landing ok | `hover_mission_horizontal_span_not_ok`, `hover_xy_alignment_direction_mismatch:fcu_local_position_pose__slam_odom_corrected` |
| 2/3 | `20260624T022312Z` | `TASK_STATUS_OK` | `0.012m / 0.026m` | `0s` | `S13 task_success`, landing ok | none |
| 3/3 | `20260624T022545Z` | `TASK_STATUS_OK` | `0.017m / 0.039m` | `0s` | `S13 task_success`, landing ok | none |

Conclusion:

- [ ] Direct `/slam/odom` did **not** pass the required three-run repeatability check.
- [x] The direct route is better than selector route in the observed runs, but it is not yet stable enough to make the final default on the basis of this evidence alone.
- [x] The failing repeat is not an ExternalNav loss case: both ExternalNav loss and MAVLink ExternalNav loss were `0s`.
- [x] The failing repeat is a hover stability / source-consistency case: mission hard-gated `horizontal_span_ok=false`, and FCU local position direction disagreed with SLAM/candidate evidence in the hover window.
- [ ] Next step should investigate why FCU local position and `/slam/odom` diverge during the failed direct run, not return to scan-reference selector tuning.

## Phase 38 [contract-validation]: initialization / determinism audit

目标：把 repeatability failure 拆成可复现的时间对齐问题，覆盖这四类假设：

- Cartographer / SLAM 初始化时机。
- ExternalNav bridge 与 FCU EKF 接入时机。
- ExternalNav 没 loss 但估计源/FCU 融合后分叉。
- 多进程启动顺序导致 mission anchor 捕获时机不同。

Change:

- [x] 新增 diagnostic-only Go audit：`orchestration/sim/cmd/hover-init-audit`。
- [x] 每个 run 记录：
  - [x] mission/phase 时间：mission start、takeoff、hover_settle、hover_hold。
  - [x] `/slam/odom`、`/slam/odom_corrected`、`/external_nav/odom_candidate`、`/external_nav/odom`、`/navlab/fcu/local_position_pose`、Gazebo odometry 第一帧和关键 phase 最近 pose/yaw。
  - [x] `/external_nav/status` first ready / healthy time。
  - [x] `/mavlink_external_nav/status` first sent / ready / FCU LOCAL_POSITION first-seen time。
  - [x] hover anchor 捕获时间和 hold x/y/yaw。
  - [x] takeoff -> hover_hold 期间每个估计源 max pose/yaw step。
  - [x] hover_hold 窗口每个源的 drift/span。
- [x] 输出文件：`artifacts/sim/hover/direct_repeat_initialization_comparison.json`。

Verification:

- [x] `go test ./internal/tasks ./internal/config`。
- [x] `go run ./cmd/hover-init-audit --output ../../artifacts/sim/hover/direct_repeat_initialization_comparison.json ../../artifacts/sim/hover/20260624T021838Z ../../artifacts/sim/hover/20260624T022312Z ../../artifacts/sim/hover/20260624T022545Z`。

Key table:

| run | verdict | mission reason | mission span | takeoff | hover_hold | ExternalNav ready | MAV sent | MAV ready | anchor x/y | SLAM max step before hold | SLAM drift in hold | ExternalNav drift in hold | FCU drift in hold | Gazebo drift in hold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `20260624T021838Z` | `TASK_STATUS_BLOCKED` | `hover_span_unstable` | `0.305m` | `13.447s` | `26.597s` | `0.459s` | `0.139s` | `2.140s` | `0.007/-0.064` | `0.004m` | `0.343m` | `0.344m` | `0.196m` | `0.289m` |
| `20260624T022312Z` | `TASK_STATUS_OK` | `hover_complete` | `0.026m` | `13.126s` | `26.026s` | `0.137s` | `0.439s` | `1.440s` | `0.007/-0.078` | `0.003m` | `0.034m` | `0.029m` | `0.018m` | `0.027m` |
| `20260624T022545Z` | `TASK_STATUS_OK` | `hover_complete` | `0.039m` | `14.190s` | `27.140s` | `0.210s` | `0.119s` | `2.619s` | `0.010/-0.075` | `0.007m` | `0.035m` | `0.035m` | `0.024m` | `0.039m` |

Conclusion:

- [x] 失败 run 不像是 takeoff 前 SLAM 大跳：`/slam/odom` takeoff -> hover_hold max step 只有 `0.004m`，与成功 run 同量级。
- [x] 失败 run 也不像是 ExternalNav 接入太晚：ExternalNav ready / MAVLink sent / MAVLink ready 都早于 takeoff。
- [x] anchor 捕获位置也与成功 run 接近，未见明显早期 anchor/origin 分叉。
- [x] 真正复现的分叉在 hover_hold 窗口：失败 run 中 `/slam/odom` 与 `/external_nav/odom` 自身 drift 到 `0.34m`，FCU local 也 drift 到 `0.20m`；成功 run 同项只有 `0.02-0.04m`。
- [x] 下一步应查 hover_hold 期间为什么 SLAM odom 自身漂移，而不是继续改 selector 或调 mission gate。

## Phase 39 [contract-validation]: Cartographer input-chain audit

目标：确认 hover_hold 漂移是在 Cartographer 输出之后发生，还是已经存在于 Cartographer 输入 prior。不能把 direct `/slam/odom` 当成纯 Cartographer baseline，除非先证明它不依赖 scan-reference odometry input。

Change:

- [x] 扩展 `hover-init-audit`，把 `/cartographer/odometry_input` 加入 pose source、takeoff->hover_hold jump、hover_hold window。
- [x] 扩展同一个 audit，把 hover_hold 内的 `/scan`、`/navlab/slam/imu`、`/navlab/slam/tf`、`/cartographer/odometry_input` rate / interval 统计写进 `sensor_timing`。
- [x] 加入 `/navlab/slam/status` hover window delta：scan/imu/tf/output odom 计数、TF rejection、TF max jump。
- [x] 补 Go 单测覆盖新增字段，避免后续 audit 退化。

Verification:

- [x] `go test ./internal/tasks ./internal/config`。
- [x] `go run ./cmd/hover-init-audit --output ../../artifacts/sim/hover/direct_repeat_initialization_comparison.json ../../artifacts/sim/hover/20260624T021838Z ../../artifacts/sim/hover/20260624T022312Z ../../artifacts/sim/hover/20260624T022545Z`。

Key table:

| run | verdict | mission span | `/cartographer/odometry_input` drift | `/slam/odom` drift | `/external_nav/odom` drift | FCU drift | Gazebo drift | `/scan` rate | `/navlab/slam/imu` rate | `/navlab/slam/tf` rate | cartographer odom input rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `20260624T021838Z` | `TASK_STATUS_BLOCKED` | `0.305m` | `0.369m` | `0.343m` | `0.344m` | `0.196m` | `0.289m` | `7.019Hz` | `710.9Hz` | `6.964Hz` | `6.964Hz` |
| `20260624T022312Z` | `TASK_STATUS_OK` | `0.026m` | `0.025m` | `0.034m` | `0.029m` | `0.018m` | `0.027m` | `7.019Hz` | `706.3Hz` | `144.8Hz` | `7.019Hz` |
| `20260624T022545Z` | `TASK_STATUS_OK` | `0.039m` | `0.036m` | `0.035m` | `0.035m` | `0.024m` | `0.039m` | `7.019Hz` | `705.6Hz` | `144.2Hz` | `7.019Hz` |

Conclusion:

- [x] 失败 run 的漂移不是 first observed at `/slam/odom`；`/cartographer/odometry_input` 在 hover_hold 内已经漂到 `0.369m`。
- [x] 当前所谓 direct `/slam/odom` route 不是“只用 scan 的纯 Cartographer 输出”。Cartographer 配置 `use_odometry = true`，且 launch 把 `/odom` remap 到 `/cartographer/odometry_input`；这个 input 由 scan-reference cartographer odom runtime 生成。
- [x] `/scan` 和 `/navlab/slam/imu` rate 在三次 run 基本一致，当前没有证据支持 scan drop / IMU drop 是首因。
- [x] 失败 run 的 `/navlab/slam/tf` rate 低很多，但由于 `/cartographer/odometry_input` 已经先漂，TF rate 更像 downstream symptom 或 Cartographer 输出模式变化，不应先按 TF rate 调 gate。
- [x] scan-reference runtime summary 同步支持这个方向：失败 run 中 `scan_reference_runtime_drift.max_horizontal_drift_m=0.359m`，raw residual RMS max `0.444m`，同时 quality_good_ratio 仍约 `0.992`，说明 scan-reference prior 自身在 hover_hold 内可能把坏 prior 标成了好质量。
- [ ] 下一步应该审计 scan-reference cartographer odometry input：为什么 raw residual / sign flip / direction discontinuity 已经异常时，仍能继续输出高质量 odometry prior 给 Cartographer。
- [ ] 暂时不要把 direct `/slam/odom` 设为默认，也不要回去调 selector/gate/intent 窗口；先把 Cartographer odometry input 的 contract 和 fail-closed 语义查清楚。

## Phase 40 [contract-validation]: 5-run repeatability check

目标：在 Phase 39 的同一诊断口径下再跑 2 次真实 hover，把 3 次 repeat 扩成 5 次，确认 failure pattern 是偶发 runtime 条件还是单次异常。

Run command:

```bash
just navlab-run hover --simulation-profile slam-direct
just navlab-run hover --simulation-profile slam-direct
cd orchestration/sim && go run ./cmd/hover-init-audit --output ../../artifacts/sim/hover/direct_repeat_5run_initialization_comparison.json \
  ../../artifacts/sim/hover/20260624T021838Z \
  ../../artifacts/sim/hover/20260624T022312Z \
  ../../artifacts/sim/hover/20260624T022545Z \
  ../../artifacts/sim/hover/20260624T031743Z \
  ../../artifacts/sim/hover/20260624T032003Z
```

Result table:

| run | verdict | mission span | mission drift | cartographer odom input drift | `/slam/odom` drift | `/external_nav/odom` drift | FCU drift | scan-reference max drift | raw residual RMS avg/max | correction allowed / intent active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `20260624T021838Z` | `TASK_STATUS_BLOCKED` | `0.305m` | `0.077m` | `0.369m` | `0.343m` | `0.344m` | `0.196m` | `0.359m` | `0.115 / 0.444` | `82 / 42` |
| `20260624T022312Z` | `TASK_STATUS_OK` | `0.026m` | `0.012m` | `0.025m` | `0.034m` | `0.029m` | `0.018m` | `0.025m` | `0.009 / 0.020` | `0 / 0` |
| `20260624T022545Z` | `TASK_STATUS_OK` | `0.039m` | `0.017m` | `0.036m` | `0.035m` | `0.035m` | `0.024m` | `0.036m` | `0.012 / 0.031` | `9 / 2` |
| `20260624T031743Z` | `TASK_STATUS_OK` | `0.038m` | `0.017m` | `0.034m` | `0.040m` | `0.046m` | `0.022m` | `0.034m` | `0.020 / 0.041` | `6 / 0` |
| `20260624T032003Z` | `TASK_STATUS_OK` | `0.081m` | `0.018m` | `0.067m` | `0.068m` | `0.066m` | `0.045m` | `0.067m` | `0.021 / 0.046` | `41 / 20` |

Timing/control observations:

- [x] `/scan` rate stayed near `7.0Hz` in all 5 runs.
- [x] `/navlab/slam/imu` rate stayed near `703-711Hz` in all 5 runs.
- [x] `/navlab/slam/status` reported `tf_rejected_delta=0` in all 5 hover windows.
- [x] The failed run had low `/navlab/slam/tf` output rate (`6.964Hz` vs about `144-145Hz`), but the upstream `/cartographer/odometry_input` was already bad in the same window.
- [x] `quality_good_ratio` stayed about `0.992` even in the failed run and the edge run, so current scan-reference quality semantics do not catch the bad prior.

Conclusion:

- [x] 5 次里 `4/5` 顶层 OK，`1/5` hard fail；但第 5 次已经是 edge pass，span `0.081m`，说明这不是单次孤立异常。
- [x] 漂移大小按链路同步变大：`scan_reference_runtime_drift` -> `/cartographer/odometry_input` -> `/slam/odom` -> `/external_nav/odom` -> FCU local。
- [x] 当前最具体的问题是：scan-reference cartographer odometry prior 在 hover_hold 内会间歇性产生大漂移，且 badness 没有被 quality/eligibility 语义 fail-closed，导致 Cartographer 把坏 odometry prior 融进去。
- [ ] 下一步应直接审计/修复 scan-reference cartographer odometry prior 的质量合同：raw residual、direction continuity、sign flips、correction_allowed/intent_active 触发时，应降级或停止发布 `/cartographer/odometry_input`，而不是继续把它作为高可信 odometry prior 输入 Cartographer。

## Phase 41 [contract-validation]: pure Cartographer no-odom-prior ablation design

目标：验证“hover 漂移是否由 scan-reference odometry prior 注入 Cartographer 引起”。本 phase 只隔离变量，不调 mission 阈值，不改 selector，不改 scan-reference estimator 阈值。

Hypothesis:

- H1: 如果禁用 Cartographer `use_odometry` 后，`/cartographer/odometry_input` 仍可能漂，但 `/slam/odom` 不再跟着漂，则当前主因是 scan-reference prior 污染 Cartographer。
- H2: 如果禁用 `use_odometry` 后 `/slam/odom` 仍在 hover_hold 漂到 `0.1m+`，则主因不在 odometry prior，而在 Cartographer scan/IMU/local SLAM 本体。
- H3: 如果禁用 `use_odometry` 后 `/slam/odom` 不稳定、频繁 loss 或 mission 无法进入 hover_hold，则 scan-reference prior 之前可能在掩盖 Cartographer hover 低可观测性，需要单独调 Cartographer scan matching，而不是恢复坏 prior。

Implementation design:

1. 新增 Cartographer config:
   - [x] 文件：`navlab/common/slam/ros/localization/navlab_cartographer_adapter/config/navlab_cartographer_2d_hover_no_odom_prior.lua`。
   - [x] 从 `navlab_cartographer_2d_hover.lua` 复制，保持 scan/IMU、search window、missing ray length、scan matcher weight、pose graph settings 尽量一致。
   - [x] 只改隔离变量：`use_odometry = false`。
   - [x] 注释说明：这是 Phase 41 ablation config，不是最终 tuning profile。
   - [x] 不直接复用 `navlab_cartographer_2d_real.lua`，因为 real config 还改了 `missing_data_ray_length`、search window、translation weights、`optimize_every_n_nodes` 等，会混入多个变量。

2. 新增 simulation profile:
   - [x] profile 名：`slam-direct-no-odom-prior`。
   - [x] 在 `ApplySimulationProfile` 中：
     - [x] `ExternalNavInputOdomTopic = /slam/odom`，保持 direct route。
     - [x] `SlamBackend.CartographerConfigurationBasename = navlab_cartographer_2d_hover_no_odom_prior.lua`。
   - [x] 保持 runtime 不使用 Gazebo truth / known map / fixed XY pose。

3. 修正 hover runtime artifact 生成语义:
   - [x] 当前 `GenerateRuntimeArtifacts` 对 hover 会强制 `CartographerConfigurationBasename = navlab_cartographer_2d_hover.lua`，这会覆盖 profile。需要改成：
     - default hover profile 仍使用 `navlab_cartographer_2d_hover.lua`；
     - `slam-direct-no-odom-prior` 明确使用 `navlab_cartographer_2d_hover_no_odom_prior.lua`。
   - [x] artifact 中复制对应 Lua config，并在 `slam_runtime.toml` 写出对应 basename。

4. 保留 `/cartographer/odometry_input` 作为 diagnostic topic:
   - [x] 第一轮 ablation 不必删除 `scan_reference_cartographer_odom` 服务；保留它可以同时观察 scan-reference prior 是否仍漂。
   - [x] 但验收必须确认 Cartographer config `use_odometry=false`，也就是这个 topic 即使存在，也不应作为 Cartographer input 被融合。
   - [x] 如果后续要清理 runtime，再把该服务降为 review-only 或在 no-odom-prior profile 中不启动；不要在本 phase 混入这个变量。

Tests to add/update:

- [x] `TestApplySimulationProfileHoverSlamDirectNoOdomPriorUsesRawSlamOdomAndNoOdomConfig`
  - asserts ExternalNav input is `/slam/odom`。
  - asserts Cartographer config basename is `navlab_cartographer_2d_hover_no_odom_prior.lua`。
- [x] `TestGenerateRuntimeArtifactsHoverSlamDirectNoOdomPriorUsesNoOdomConfig`
  - asserts `slam_runtime.toml` contains `external_nav_input_odom_topic = '/slam/odom'`。
  - asserts `slam_runtime.toml` contains `cartographer_configuration_basename = 'navlab_cartographer_2d_hover_no_odom_prior.lua'`。
  - asserts generated/copied Lua config contains `use_odometry = false`。
  - asserts no `/odometry` Gazebo truth or diagnostic truth input is introduced.
- [x] Keep existing `slam-direct` tests unchanged; this profile must be additive.

Verification commands:

```bash
cd orchestration/sim
go test ./internal/tasks ./internal/config
```

Dry-run / artifact sanity:

```bash
just navlab-run hover --simulation-profile slam-direct-no-odom-prior --dry-run
rg -n "cartographer_configuration_basename|use_odometry|external_nav_input_odom_topic" artifacts/sim/hover/<dry-run-id>
```

Real ablation:

```bash
just navlab-run hover --simulation-profile slam-direct-no-odom-prior
just navlab-run hover --simulation-profile slam-direct-no-odom-prior
just navlab-run hover --simulation-profile slam-direct-no-odom-prior
just navlab-run hover --simulation-profile slam-direct-no-odom-prior
just navlab-run hover --simulation-profile slam-direct-no-odom-prior

cd orchestration/sim && go run ./cmd/hover-init-audit \
  --output ../../artifacts/sim/hover/no_odom_prior_5run_initialization_comparison.json \
  ../../artifacts/sim/hover/<run1> \
  ../../artifacts/sim/hover/<run2> \
  ../../artifacts/sim/hover/<run3> \
  ../../artifacts/sim/hover/<run4> \
  ../../artifacts/sim/hover/<run5>
```

Comparison table fields:

- [ ] top-level `status` / `ok`。
- [ ] mission hover drift/span。
- [ ] `/cartographer/odometry_input` hover drift，作为 diagnostic-only reference。
- [ ] `/slam/odom` hover drift。
- [ ] `/external_nav/odom` hover drift。
- [ ] FCU local drift。
- [ ] Gazebo model odometry drift，继续 review-only。
- [ ] `/scan`、`/navlab/slam/imu`、`/navlab/slam/tf` rates。
- [ ] scan-reference raw residual RMS avg/max、quality_good_ratio、correction_allowed_count、intent_active_count。

Decision rules:

- [ ] If `slam-direct-no-odom-prior` is `5/5` OK and `/slam/odom` span stays `<0.1m` while `/cartographer/odometry_input` can still drift, then root cause is confirmed as scan-reference odometry prior pollution. Next phase should make no-odom-prior the default candidate and demote scan-reference Cartographer odom prior to diagnostic or fail-closed experimental.
- [ ] If no-odom-prior still shows `/slam/odom` drift `>0.1m`, then stop blaming prior injection and audit Cartographer scan matching / IMU / TF timestamps directly.
- [ ] If no-odom-prior fails before hover_hold because SLAM cannot stabilize, then the scan-reference prior was masking Cartographer instability; next phase should tune Cartographer scan matching with `use_odometry=false`, not restore the prior.
- [ ] If only ExternalNav/FCU drifts while `/slam/odom` stays stable, then return to ExternalNav bridge / MAVLink EKF mapping audit.

Execution result:

- [x] Verification passed: `go test ./internal/tasks ./internal/config`。
- [x] Dry-run sanity passed: `20260624T034134Z` generated `slam_runtime.toml` with `cartographer_configuration_basename = 'navlab_cartographer_2d_hover_no_odom_prior.lua'`, `external_nav_input_odom_topic = '/slam/odom'`, and copied Lua with `use_odometry = false`。
- [x] 5-run audit output: `artifacts/sim/hover/no_odom_prior_5run_initialization_comparison.json`。

5-run result table:

| run | verdict | mission span | mission drift | cartographer odom input drift | `/slam/odom` drift | `/external_nav/odom` drift | FCU drift | Gazebo drift | scan-reference max drift | raw residual RMS avg/max | correction allowed / intent active |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `20260624T034211Z` | `TASK_STATUS_OK` | `0.049m` | `0.025m` | `0.046m` | `0.059m` | `0.054m` | `0.025m` | `0.036m` | `0.046m` | `0.012 / 0.023` | `13 / 6` |
| `20260624T034426Z` | `TASK_STATUS_OK` | `0.043m` | `0.020m` | `0.044m` | `0.043m` | `0.039m` | `0.026m` | `0.048m` | `0.044m` | `0.018 / 0.038` | `25 / 11` |
| `20260624T034643Z` | `TASK_STATUS_OK` | `0.043m` | `0.019m` | `0.032m` | `0.043m` | `0.035m` | `0.026m` | `0.028m` | `0.032m` | `0.010 / 0.017` | `0 / 0` |
| `20260624T034856Z` | `TASK_STATUS_BLOCKED` | `0.097m` | `0.029m` | `0.091m` | `0.121m` | `0.096m` | `0.054m` | `0.108m` | `0.105m` | `0.032 / 0.101` | `60 / 39` |
| `20260624T035109Z` | `TASK_STATUS_OK` | `0.024m` | `0.013m` | `0.019m` | `0.022m` | `0.021m` | `0.014m` | `0.023m` | `0.019m` | `0.008 / 0.022` | `0 / 0` |

Timing/control observations:

- [x] `/scan` stayed near `7.0Hz` in all 5 runs.
- [x] `/navlab/slam/imu` stayed near `700-708Hz` in all 5 runs.
- [x] `/navlab/slam/tf` stayed near `143-145Hz` in all 5 runs.
- [x] `/navlab/slam/status` reported `tf_rejected_delta=0` in all 5 hover windows.
- [x] All 5 runs used `navlab_cartographer_2d_hover_no_odom_prior.lua` and `use_odometry=false`。

Conclusion:

- [x] Disabling Cartographer odometry prior removed the previous hard hover mission failure mode: all 5 runs reached `hover_complete`, with mission span `<0.1m`。
- [x] It did **not** fully prove scan-reference prior injection is the only root cause: run `20260624T034856Z` still had `/slam/odom` hover drift `0.121m` and Gazebo drift `0.108m` while `use_odometry=false`。
- [x] Compared with Phase 40, the no-odom-prior route is materially better (`5/5` hover_complete vs one hard hover instability), but still has an edge case where Cartographer local SLAM itself drifts near/over the intended `0.1m` stability boundary.
- [ ] Next phase should audit Cartographer scan matching / IMU / TF timing and score behavior under `use_odometry=false`, especially the edge run `20260624T034856Z`; do not go back to scan-reference prior as the default fix.

## Phase 42 [sim-review-only]: no-odom-prior edge-run initial audit

目标：先离线审计 Phase 41 edge run `20260624T034856Z`，确认它到底是 Cartographer 本体漂移、物理 hover excursion、ExternalNav/FCU 分叉，还是 scan/IMU/TF 数据问题。

Inputs:

- Edge run: `20260624T034856Z`
- Stable references: `20260624T034211Z`, `20260624T034426Z`, `20260624T034643Z`, `20260624T035109Z`
- Comparison artifact: `artifacts/sim/hover/no_odom_prior_5run_initialization_comparison.json`

Observed facts:

- [x] Edge run used `navlab_cartographer_2d_hover_no_odom_prior.lua` and `use_odometry=false`。
- [x] Mission itself reached `hover_complete` and `hover_body_ok=true`。
- [x] Top-level blocker was only `hover_gazebo_model_horizontal_drift`; mission hover span was `0.097m`, still under the `0.1m` mission threshold.
- [x] ExternalNav loss and MAVLink ExternalNav loss were both `0s`。
- [x] `/scan` rate was normal: near `7.0Hz` in rosbag audit, Cartographer collator log scan rate `9.91-10.61Hz`。
- [x] `/navlab/slam/imu` rate was normal: near `700Hz` in rosbag audit, Cartographer collator log IMU rate `989-998Hz`。
- [x] `/navlab/slam/tf` rate was normal: about `145Hz`。
- [x] `/navlab/slam/status` reported `tf_rejected_delta=0`。
- [x] Cartographer runtime log only exposed collated sensor rates and empty constraint-builder score histograms; it did not expose per-scan local matching scores.

Trajectory shape:

| source | max drift | final delta | x span | y span |
| --- | --- | --- | --- | --- |
| `/slam/odom` | `0.121m` | `0.011 / 0.011m` | `0.177m` | `0.043m` |
| `/external_nav/odom` | `0.096m` | `0.024 / 0.018m` | `0.151m` | `0.037m` |
| FCU local pose | `0.054m` | `0.014 / -0.024m` | `0.024m` | `0.094m` |
| Gazebo model odometry | `0.108m` | `0.029 / -0.000m` | `0.141m` | `0.028m` |
| `/cartographer/odometry_input` diagnostic only | `0.091m` | `0.013 / 0.003m` | `0.134m` | `0.044m` |

Interpretation:

- [x] The edge run is not a monotonic `/slam/odom` runaway: final displacement is small, but span/max drift is high. This points to a mid-hover excursion that later returns.
- [x] Gazebo model odometry also shows a high-span excursion (`0.108m` max, `0.141m` x span), but Phase 42 time-aligned audit shows the SLAM/ExternalNav peak and Gazebo peak are not the same motion direction.
- [x] FCU local and ExternalNav stayed broadly aligned in final-vector direction (`direction_cosine ~= 0.995`, scale `0.90`), with no ExternalNav loss.
- [x] Raw-source audit showed `slam_odom` and `slam_odom_corrected` were effectively the same for this profile; scan-reference correction was not the source of the edge blocker.
- [x] The edge run still has selector/candidate raw-direction disagreement, but the top-level blocker did not come from selector/candidate alignment; it came from Gazebo review drift.

Time-aligned trajectory audit:

Commands:

```bash
cd orchestration/sim
go run ./cmd/hover-trajectory-audit ../../artifacts/sim/hover/20260624T034856Z
go run ./cmd/hover-trajectory-audit ../../artifacts/sim/hover/20260624T035109Z
go run ./cmd/hover-init-audit ../../artifacts/sim/hover/20260624T034856Z
go run ./cmd/hover-init-audit ../../artifacts/sim/hover/20260624T035109Z
```

Artifacts:

- [x] `artifacts/sim/hover/20260624T034856Z/trajectory_audit.json`
- [x] `artifacts/sim/hover/20260624T035109Z/trajectory_audit.json`
- [x] `artifacts/sim/hover/20260624T034856Z/initialization_audit.json`
- [x] `artifacts/sim/hover/20260624T035109Z/initialization_audit.json`

Peak comparison:

| run | source peak | `/slam/odom` rel XY at that time | `/external_nav/odom` rel XY | FCU local rel XY | Gazebo model rel XY |
| --- | --- | --- | --- | --- | --- |
| edge `20260624T034856Z` | SLAM peak at `37.427s` | `-0.121 / -0.009m` | `-0.096 / -0.005m` | `+0.004 / +0.031m` | `+0.101 / -0.011m` |
| edge `20260624T034856Z` | Gazebo peak at `38.014s` | `-0.088 / -0.001m` | `-0.089 / -0.001m` | `-0.000 / +0.048m` | `+0.107 / -0.012m` |
| stable `20260624T035109Z` | SLAM peak at `44.505s` | `+0.006 / +0.021m` | `-0.002 / +0.021m` | `+0.012 / +0.002m` | `+0.015 / +0.017m` |

Time-aligned interpretation:

- [x] In the edge run, `/slam/odom` and `/external_nav/odom` move together at the SLAM peak (`~0.096-0.121m`, negative X).
- [x] Gazebo model odometry is large at roughly the same time, but in positive X (`~0.101-0.107m`), opposite the SLAM/ExternalNav relative X direction.
- [x] FCU local pose is smaller and mostly Y-biased at the same peak times (`0.031-0.048m`), not matching either SLAM negative-X or Gazebo positive-X one-to-one.
- [x] Stable run has all sources under `~0.024m`; no comparable sign disagreement is visible.
- [x] `/navlab/fcu/controller/status` and `/navlab/fcu/setpoint/output` had no samples in this rosbag despite being listed in the profile, so this artifact cannot prove controller-output behavior beyond mission hover status `setpoints_sent_count`.

Current conclusion:

- [x] Phase 42 initial audit weakens both over-simple claims: “Cartographer itself drifted” and “Gazebo physically confirmed the same drift.” A better current statement is:

  > Under `use_odometry=false`, the worst run shows normal scan/IMU/TF timing and no ExternalNav loss, but time-aligned hover peaks put SLAM/ExternalNav and Gazebo model odometry in opposite relative X directions. The next blocker is the observation-source/frame/time-alignment contract, not selector tuning or mission threshold tuning.

- [x] Time-aligned trajectories for `/slam/odom`, `/external_nav/odom`, FCU local pose, and Gazebo model odometry were extracted.
- [ ] Next audit should inspect `/gazebo/tf` and `/gazebo/model/odometry` generation contract: model/link name, transform index, frame origin, sign convention, timestamp source, and whether `frame_id=odom` is directly comparable to SLAM `map` deltas.
- [ ] Next audit should also restore or explain missing `/navlab/fcu/controller/status` and `/navlab/fcu/setpoint/output` messages in the hover rosbag, because controller-output evidence is currently absent.
- [ ] Only after Gazebo/FCU observation contract is proven should Cartographer local scan matching score instrumentation be added; the current artifacts do not contain per-scan local matching scores.

Non-goals:

- [ ] Do not change hover mission thresholds.
- [ ] Do not change selector gates.
- [ ] Do not tune scan-reference residual thresholds in this phase.
- [ ] Do not use Gazebo truth, known map pose, or fixed pose as runtime input.
- [ ] Do not claim root cause fixed until the no-odom-prior 5-run comparison is recorded.

## Phase 43 [real-flight-safety + contract-validation]: pre-task hover health gate and multi-source SLO

目标：把 hover 从一次固定阈值的二值 pass/fail，升级成所有任务进入主体前的统一 health gate；同时把多观测源不匹配改为 cohort 统计和 SLO 评估，避免把仿真/真实闭环系统中的自然尾部波动误判成单次 root cause。

Decision:

- [x] 之前 Phase 1-42 的 fail-closed / jump gate / mission summary / loss diagnostics 修复是 `real-flight-safety`，不是为了仿真 review 好看。
- [x] Go/Python boundary is file/probe only: Go may launch Python runtimes and pass config through generated files/CLI args/env, Python may emit artifact JSON/status/probe JSON, but Go must not import/call Python internals and Python must not depend on Go packages.
- [x] sim 和 real 共享同一套 hover health gate；差别只在 proceed 机制：
  - [x] sim task: `hover_health_green -> auto_continue`，不需要人工二次确认。
  - [x] real task: `hover_health_green -> wait_operator_confirm -> continue`。
- [x] hover drift / source mismatch 不再只按单次 run 是否越过 `0.1m` 解释成 bug；`0.1m` 是 target/SLO，`0.15m` 暂作为 hard-cap proposal，具体值必须由 cohort 分布校准。
- [x] Gazebo source 在 frame/origin/time contract 闭环前继续 `sim-review-only`；Gazebo-only mismatch 进入统计和 warning，不单独证明 ExternalNav / FCU / SLAM 错。
- [x] real-time safety events 仍然 hard fail，不被统计分位数放宽：ExternalNav loss、MAVLink ExternalNav loss、SLAM loss、pose/yaw jump、frame contract hard mismatch、mission abort、truth/known-map runtime input。

Rationale:

- sim/real hover 是 Gazebo physics、ROS/DDS、SLAM、ExternalNav、FCU EKF、mission controller、rosbag/probe 的异步闭环；同一配置每次 run 的启动顺序、消息调度、采样窗口和优化路径会有细微差异。
- 这些差异会被 SLAM scan matching、EKF、control loop 和 physics integration 放大，因此结果应看成 drift distribution，而不是纯函数式的固定输出。
- 运维类比：单个 request 落在 P99 不等于服务 root cause；应看 cohort 的 P50/P90/P95/P99、error budget、极端 outlier 和是否伴随明确 safety event。
- 最近 `slam-direct-no-odom-prior` 5-run 中，`20260624T034856Z` mission reached `hover_complete`，但顶层只有 Gazebo review drift blocker；如果 hard cap 从 `0.1m` 改成 `0.15m`，该类 edge case 不应直接等同于真实安全失败。正确处理是进入 warning / trend / contract audit，而不是调 selector 或 mission threshold。

Unified state flow:

```text
S0 prepare
S1 takeoff
S2 hover_settle
S3 hover_health_hold
S4 proceed_gate
S5 task_body
S6 land
S_abort fail-closed land
```

`S4 proceed_gate` semantics:

```text
sim:
  health_green -> auto_continue
  health_yellow -> keep hovering until green or max_wait_sec
  health_red -> abort/land

real:
  health_green -> wait_operator_confirm
  health_yellow -> keep hovering; do not allow confirm
  health_red -> abort/land
  while waiting for operator confirm, continue health monitoring;
  if health drops, return to hover_health_hold or abort according to severity.
```

Hover health parameters:

- [x] `hover_health_min_observation_sec`: minimum evidence window before any task body can start.
- [x] `hover_health_stable_required_sec`: continuous green window required before proceed.
- [x] `hover_health_max_wait_sec`: fail-closed timeout if health never becomes green.
- [x] `operator_confirm_required`: `false` for sim tasks, `true` for real tasks.
- [x] `operator_confirm_timeout_sec`: real-only policy; current runtime fails closed to abort/land on timeout.

Health bands:

- [ ] `green`: task may proceed.
  - [ ] ExternalNav, MAVLink ExternalNav, SLAM, FCU local position are fresh/healthy.
  - [ ] No hover-window pose/yaw jump.
  - [ ] Tier-A estimator pairwise mismatch is within target SLO.
  - [ ] Altitude/rangefinder and control/setpoint evidence are present or explicitly waived by task profile.
- [ ] `yellow`: keep hovering and collect stats; do not enter task body.
  - [ ] Drift or pairwise mismatch is above target but below hard cap, e.g. `0.10m-0.15m`.
  - [ ] Gazebo review-only mismatch is high while Tier-A sources remain safe.
  - [ ] Short non-critical freshness gaps stayed within grace.
- [ ] `red`: abort/land.
  - [ ] ExternalNav / MAVLink ExternalNav / SLAM / FCU local loss exceeds grace.
  - [ ] Candidate or output pose/yaw jump appears in hover window.
  - [ ] Frame/origin/time contract hard mismatch affects a runtime safety source.
  - [ ] Runtime uses Gazebo truth, known map, fixed pose, or direct pose cheat as ExternalNav input.
  - [ ] `hover_health_max_wait_sec` expires without green.

Multi-source tiers:

- [ ] Tier A `real-flight-safety`:
  - [ ] `/slam/odom`
  - [ ] `/external_nav/odom`
  - [ ] `/navlab/fcu/local_position_pose`
  - [ ] `/mavlink_external_nav/status`
- [ ] Tier B `sim-review-only`:
  - [ ] `/gazebo/model/odometry`
  - [ ] `/gazebo/tf`
  - [ ] `/gazebo/tf_static`
- [ ] Tier C `legacy / diagnostic`:
  - [ ] `/cartographer/odometry_input`
  - [ ] `/navlab/scan_reference_drift/odom`
  - [ ] `/external_nav/odom_candidate`

Per-run metrics:

- [ ] For each source, compute relative motion inside the same hover window:

```text
rel_source(t) = pose_source(t) - pose_source(hover_start)
```

- [ ] For each pair, compute time-aligned error:

```text
error_A_B(t) = rel_A(t) - rel_B(t)
```

- [ ] Record per-source fields:
  - [ ] sample count, rate, frame_id, child_frame_id, timestamp range.
  - [ ] hover drift, span, final delta, peak vector, peak time.
- [ ] Record per-pair fields:
  - [ ] `p50_error_m`, `p90_error_m`, `p95_error_m`, `p99_error_m`, `max_error_m`.
  - [ ] `rms_error_m`, `direction_cosine`, `scale_ratio`, `peak_time_delta_sec`.
  - [ ] signed X/Y error to catch axis/sign mistakes hidden by magnitude.
- [ ] Split verdict into:
  - [ ] `hard_blockers`
  - [ ] `statistical_warnings`
  - [ ] `review_only_findings`

Cohort SLO:

- [ ] Add a cohort summary across many runs, grouped by profile and task:
  - [ ] P50/P90/P95/P99 of each run-level pairwise metric.
  - [ ] outlier count and outlier examples.
  - [ ] safety-event rate.
  - [ ] warning rate for `0.10m-0.15m` target-to-hard-cap band.
- [ ] Sample-size rule:
  - [ ] `<10` runs: case study only.
  - [ ] `>=30` runs: provisional P90/P95.
  - [ ] `>=100` runs: stable P95.
  - [ ] `>=300-1000` runs: P99 becomes meaningful.
- [ ] Keep `0.1m` as target/SLO until evidence says otherwise; treat `0.15m` as hard-cap proposal, not as a silent threshold relaxation.

Implementation tasks:

1. Documentation / contract:
   - [x] Add a short design doc or extend this TODO with the final field schema for `hover_health_summary.json` and `hover_health_cohort.json`.
   - [x] Explicitly document sim vs real proceed semantics: sim auto-continues; real waits for operator confirmation.
   - [x] Document that operator confirmation is never allowed to override red safety state.
   - [x] Document the Go/Python boundary: all cross-language handoff goes through artifact files, CLI/env config files, ROS status topics, and probe JSON.
2. Per-run audit output:
   - [x] Extend or wrap existing `hover-trajectory-audit` / `hover-contract-audit` into `hover-health-audit`.
   - [x] Emit health bands and source-tiered findings for one artifact.
   - [x] Preserve current `trajectory_audit.json` and `contract_audit.json`; do not remove existing diagnostics.
3. Sim task integration:
   - [x] Add pre-task `hover_health_hold` to the current hover mission runtime without renaming `hover_hold` evidence.
   - [x] `green -> auto_continue`; `yellow -> wait until green or max_wait_sec`; `red -> abort/land`.
   - [x] Keep sim non-interactive; no operator confirmation prompt.
   - [ ] Extend the same runtime gate wrapper to any future sim task body that starts with flight motion.
4. Real task integration:
   - [x] Add `hover_health_hold` / `operator_confirm` wait semantics in Python common hover runtime.
   - [x] After green, require explicit operator confirmation before proceeding when `operator_confirm_required=true`.
   - [x] Continue health monitoring while waiting for confirmation; red disables confirmation and aborts/lands.
   - [ ] Wire the operator-confirm topic/policy into a concrete real task launcher once that launcher exists.
5. Tests:
   - [x] Unit tests for health band classification.
   - [x] Unit tests for sim auto-continue vs real operator-confirm routing.
   - [ ] Replay tests for one green, one yellow, and one red artifact.
   - [x] Regression test that Gazebo-only mismatch stays review-only until contract is proven.
6. Usage pass:
   - [x] Run `slam-direct-no-odom-prior` hover cohort and generate `hover_health_cohort.json`.
   - [x] Confirm edge run `20260624T034856Z` becomes warning/review-only if Tier-A sources are safe and only Gazebo review drift is high.
   - [x] Confirm safety-event artifacts still hard fail.

Execution result:

- [x] Added typed Go registry and classification layer: `HoverSourceSpec`, `HoverPairSpec`, `HoverMetricSpec`, `HoverMetricValue`, `HoverHealthBand`.
- [x] Added per-run CLI: `go run ./cmd/hover-health-audit <artifact-dir>` writes `hover_health_summary.json`.
- [x] Added cohort mode: `go run ./cmd/hover-health-audit --output <cohort.json> <artifact-dir>...` writes `navlab.hover_health_cohort.v1` with sample-size rule and metric percentiles.
- [x] `20260624T034856Z` now classifies as `health_band=yellow` with no hard blockers; Gazebo issues are review-only and Tier-A pairwise outliers are statistical warnings, not root-cause conclusions.
- [x] 5-run no-odom-prior cohort output: `artifacts/sim/hover/no_odom_prior_5run_hover_health_cohort.json`; sample size rule is `case_study_only`, so no P99 claim is allowed from this cohort.

Subphase plan:

### Phase 43A [contract-validation, short-term]: Go artifact/gate integration without runtime FSM change

Decision:

- [x] `hover_health_hold` is not yet a runtime state; short-term implementation stays post-run / artifact-based.
- [x] Go owns orchestration, artifact generation, gate interpretation, and SLO/cohort reporting.
- [x] Python runtime continues using existing `hover_hold` semantics; do not rename or split the mission FSM in this subphase.
- [x] Cross-language coupling stays file/probe based; no direct Go-to-Python library API is introduced.

Goal:

- [x] Attach `hover-health-audit` to hover artifact/gate flow after run completion, so every hover artifact can produce `hover_health_summary.json` and optional cohort output.
- [x] Preserve existing hard safety gates; health audit must add explanation and statistical classification, not silently relax `summary.ok`.

Tasks:

- [x] Add Go artifact hook after hover run / gate evaluation to call `BuildHoverHealthAudit()` or equivalent in-process path.
- [x] Write `hover_health_summary.json` into each hover artifact directory.
- [x] Add summary/gate payload fields for:
  - [x] `hover_health_band`
  - [x] `hover_health_hard_blockers`
  - [x] `hover_health_statistical_warnings`
  - [x] `hover_health_review_only_findings`
  - [x] `hover_health_proceed`
- [x] Keep `trajectory_audit.json` and `contract_audit.json` as source evidence; `hover_health_summary.json` only aggregates/classifies them.
- [x] Ensure Gazebo-only blocker remains review/statistical unless Gazebo contract is explicitly promoted in a later phase.
- [x] Add Go tests that artifact generation invokes health audit and includes health fields in summary/gate output.
- [x] Add a usage pass with one existing artifact and one fresh `slam-direct-no-odom-prior` hover run if environment is available.

Acceptance:

- [x] Running a hover task produces `hover_health_summary.json` without manually invoking `cmd/hover-health-audit`.
- [x] Existing Python mission `hover_hold` still runs unchanged.
- [x] Existing fail-closed blockers still hard fail.
- [x] `summary.json` can distinguish hard blockers from statistical warnings and review-only findings.

43A execution result:

- [x] `runLiveTask()` now writes initial `summary.json`, builds/writes `hover_health_summary.json`, attaches health fields back into `summary.json`, and appends a `hover_health_summary` manifest entry.
- [x] `summary.json` now exposes `hover_health_band`, `hover_health_hard_blockers`, `hover_health_statistical_warnings`, `hover_health_review_only_findings`, and `hover_health_proceed` for hover tasks.
- [x] Gate metrics include `gate.metrics.hover_health` and top-level `metrics.hover_health`.
- [x] Existing artifact usage pass: `20260624T034856Z` still classifies as `yellow`, with no hard blockers and Gazebo findings review-only.
- [x] Fresh hover run usage pass: `20260624T124117Z` with `just navlab-run hover --simulation-profile slam-direct-no-odom-prior` reached `TASK_STATUS_OK`, `gate_evaluation.ok=true`, `mission_summary.ok=true`, `mission_phase_state=S13 task_success`, landing blockers empty, and `hover_health_summary.health_band=yellow` only because Gazebo review-only findings remain.

Non-goals:

- [ ] Do not add a Python `hover_health_hold` phase in 43A.
- [ ] Do not add operator confirmation in 43A.
- [ ] Do not relax mission/gate thresholds in 43A.

### Phase 43B [real-flight-safety, medium-term]: Python runtime `hover_health_hold` and proceed gate

Decision:

- [x] Runtime `hover_health_hold` belongs in Python mission/common FSM because it needs real-time hover, freshness, loss grace, and abort/land behavior.
- [x] Go passes health parameters and task policy only through runtime spec/template files, CLI args, env, and probe/status artifacts; Python owns live state transition.
- [x] sim and real share health semantics but differ in proceed policy:
  - [x] sim: green auto-continues.
  - [x] real: green allows operator confirmation; operator confirmation cannot override red.

Goal:

- [x] Introduce an explicit runtime health gate before task body while preserving current safe hover/landing behavior.

Runtime parameters:

- [x] `hover_health_min_observation_sec`
- [x] `hover_health_stable_required_sec`
- [x] `hover_health_max_wait_sec`
- [x] `operator_confirm_required`
- [x] `operator_confirm_timeout_sec`

Python tasks:

- [x] Add explicit `hover_health_hold` phase/state in mission/common hover FSM, or alias existing `hover_hold` while publishing `health_phase=hover_health_hold`.
- [x] Reuse existing ExternalNav / MAVLink ExternalNav / SLAM / FCU local loss grace logic.
- [x] Maintain green/yellow/red runtime classification:
  - [x] green -> proceed gate can open.
  - [x] yellow -> continue hover and reset stable timer.
  - [x] red -> abort/land.
- [x] Continue monitoring while waiting for real operator confirmation.
- [x] Publish health status fields in `/navlab/hover/status` or a dedicated status topic without breaking existing consumers.

Go tasks:

- [x] Extend runtime specs with health parameters and proceed policy.
- [x] For sim tasks with flight motion, set `operator_confirm_required=false`.
- [ ] For real tasks with flight motion, set `operator_confirm_required=true`.
- [x] Add plan/runtime assertions that sim never prompts for human confirmation.
- [x] Add runtime tests proving operator confirmation cannot continue from red state.
- [ ] Add real launcher/integration tests once a real task launcher consumes the common Python gate.

43B execution result:

- [x] Go runtime specs and generated Python wrapper now carry health parameters and `operator_confirm_required`.
- [x] Sim default remains non-interactive: `operator_confirm_required=false`.
- [x] Python `hover_mission.py` accepts health parameters and publishes a nested `hover_health` payload in `/navlab/hover/status`.
- [x] Python common hover runtime now owns a real proceed gate: `hover_hold` remains the evidence/control phase, while `health_phase` exposes `hover_health_hold`, `sim_auto_continue`, `operator_confirm`, `operator_confirmed`, or `hover_health_blocked`.
- [x] Runtime gate starts at hover hold, tracks `observed_sec`, continuous `stable_sec`, and fails closed on `hover_health_max_wait_sec`.
- [x] Sim path auto-continues only after old `hover_hold_sec` acceptance and health green/stable evidence are both satisfied.
- [x] Real path waits in `operator_confirm` after green/stable; confirmation is accepted only while health is green and allowed.
- [x] Red/loss paths still use existing fail-closed abort/land behavior and clear operator-confirm allowance.
- [x] `/navlab/hover/operator_confirm` accepts `true/confirm/proceed` style payloads for the runtime operator-confirm hook.
- [x] Fresh Phase 41/42 profile usage pass after runtime gate: `20260624T124117Z` completed successfully with no mission/gate blockers; hover body drift was `0.040m`, hover span `0.077m`, and health audit stayed `yellow` due to review-only Gazebo-vs-runtime findings, not hard blockers.
- [ ] Remaining integration work: bind the common Python gate into a concrete real task launcher and choose the real operator UI/timeout policy.

Acceptance:

- [x] Sim task: `hover_health_green -> auto_continue` into task body.
- [x] Sim task: `hover_health_yellow -> wait`, then continue only after green or abort after max wait.
- [x] Sim task: `hover_health_red -> abort/land`.
- [x] Real-policy runtime: `hover_health_green -> wait_operator_confirm`, and health continues to be monitored during the wait.
- [x] Real-policy runtime: if health becomes red while waiting, confirmation is disabled and workflow aborts/lands.
- [ ] Concrete real launcher: set `operator_confirm_required=true` and connect the operator UI/topic.

Non-goals:

- [ ] Do not require human confirmation in sim.
- [ ] Do not make Go the real-time flight controller.
- [ ] Do not remove existing `hover_hold` evidence fields until downstream summaries/tests are migrated.

Acceptance:

- [ ] Every sim task with flight motion has an automatic pre-task hover health gate.
- [ ] Every real task with flight motion has pre-task hover health gate plus operator confirmation before task body.
- [ ] Operator confirmation cannot override red safety state.
- [ ] `summary.ok` no longer conflates statistical warning with hard safety blocker.
- [ ] Cohort report can show whether current `0.1m` target and proposed `0.15m` hard cap are empirically reasonable.
- [ ] Existing fail-closed behavior remains intact for ExternalNav/SLAM/MAVLink loss and pose/yaw jump.

Non-goals:

- [ ] Do not relax existing mission/gate thresholds as part of this phase.
- [ ] Do not tune Cartographer or scan-reference thresholds in this phase.
- [ ] Do not make Gazebo truth or fixed pose a runtime input.
- [ ] Do not require human confirmation in sim automation.
- [ ] Do not claim P99 from a 5-run sample; 5 runs are only exploratory evidence.

### Phase 44 [fsm-readability + real-proceed-integration]: make hover FSM audit-ready

目标：Phase 43B 已经让 hover runtime gate 可运行；Phase 44 专门收敛剩余“不够好解释 / 不够好审计 / real workflow 未闭环”的部分，把 hover FSM 从可运行升级为可读、可复盘、可接入真实任务。

Decision:

- [x] 当前 hover task FSM 基本可用：Phase 41/42 profile `20260624T124117Z` 已跑到 `TASK_STATUS_OK`、`mission_summary.ok=true`、`mission_phase_state=S13 task_success`。
- [x] 当前剩余问题不是“安全主链没做”，而是 runtime health、post-run audit、real operator confirm、summary schema 的表达层还需要拆清楚。
- [x] 继续保持 Go/Python 边界：跨语言交互只走 runtime spec / generated files / CLI args / env / ROS status / probe JSON / artifact JSON。
- [x] 不把 `hover_hold` evidence 立即重命名为 `hover_health_hold`，避免破坏 rosbag/evidence downstream；先通过 health substate 和 summary 字段表达。

Open gaps:

- [x] Public FSM timeline still reports `S6 hover_hold`; `hover_health_hold`, `sim_auto_continue`, `operator_confirm`, `operator_confirmed` are nested health phases, not first-class visible FSM substates. Mitigation: expose `mission_phase_substate` / `hover_health_phase`.
- [x] Runtime health and post-run health audit can look contradictory: runtime can proceed green/stable, while `hover_health_summary.health_band=yellow` because post-run Gazebo review-only findings remain. Mitigation: split runtime and post-run schemas in summaries.
- [x] `mission_summary.json` records health parameters and status history, but does not freeze a clear top-level final runtime hover-health snapshot. Mitigation: add `runtime_hover_health_final`.
- [ ] Real operator-confirm hook exists, but concrete real launcher/operator UI is not wired into a full task workflow.
- [ ] Artifact replay coverage for green/yellow/red artifact-like timelines is still incomplete.

Implementation tasks:

1. Runtime/post-run schema split:
   - [x] Add explicit naming in summaries:
     - [x] `runtime_hover_health_final`
     - [x] `postrun_hover_health_audit`
     - [x] `cohort_hover_health` reserved as a top-level summary field for future cohort runs.
   - [x] Ensure docs say runtime health controls task proceed, while post-run audit classifies artifact evidence and may stay yellow for review-only findings.
   - [x] Keep `summary.ok` tied to hard blockers / task result, not review-only statistical warnings.
2. Final runtime health snapshot:
   - [x] Freeze final runtime health in `mission_summary.json`:
     - [x] `phase`
     - [x] `band`
     - [x] `reason`
     - [x] `observed_sec`
     - [x] `stable_sec`
     - [x] `operator_confirm_required`
     - [x] `operator_confirm_allowed`
     - [x] `operator_confirm_received`
     - [x] `sim_auto_continue_allowed`
     - [x] `real_operator_confirm_allowed`
   - [x] Add tests that `mission_summary.json` exposes final runtime health after success and after abort.
3. FSM readability:
   - [x] Document the visible hover FSM as:

```text
S6 hover_hold
  S6a hover_health_hold
  S6b sim_auto_continue
  S6c wait_operator_confirm
  S6d operator_confirmed
  S6x hover_health_blocked
```

   - [x] Add `mission_phase_substate` and `hover_health_phase` to status/summary payloads without changing existing `S6 hover_hold` evidence semantics.
   - [x] Update docs so reviewers understand why `S6 hover_hold` can have reason `hover_health_waiting_hover_duration`.
4. Real operator-confirm integration:
   - [ ] Set `operator_confirm_required=true` for concrete real flight tasks that enter motion after hover.
   - [ ] Connect the operator-confirm topic/UI to the real launcher.
   - [ ] Require green/stable before the UI/topic can confirm continue.
   - [ ] If health drops to yellow while waiting, clear/disable any pending confirmation.
   - [ ] If health drops to red while waiting, abort/land; operator confirm must not override red.
   - [ ] Decide real `operator_confirm_timeout_sec` policy: keep hovering, timeout-to-land, or task-specific policy.
5. Replay and regression tests:
   - [x] Synthetic runtime replay: green -> stable -> sim auto-continue.
   - [x] Synthetic runtime replay: yellow -> stable reset -> green -> continue.
   - [x] Synthetic runtime replay: red -> abort/land.
   - [x] Synthetic runtime replay: green -> wait operator -> red -> confirmation ignored.
   - [ ] Artifact replay: one green, one yellow review-only, one red hard-blocker artifact.

44 execution result:

- [x] `/navlab/hover/status` now exposes `hover_health_phase` and `mission_phase_substate` alongside the nested `hover_health` payload.
- [x] `mission_summary.json` now freezes `runtime_hover_health_final` with schema `navlab.runtime_hover_health.v1`.
- [x] Top-level `summary.json` now copies `runtime_hover_health_final` from `mission_summary.json` through the artifact-file boundary.
- [x] Top-level `summary.json` now exposes `postrun_hover_health_audit` as a separate post-run artifact audit; it explicitly says it does not control runtime proceed.
- [x] Existing legacy `hover_health_*` fields remain for compatibility.
- [x] Success and abort runtime-health snapshot tests were added.
- [x] Fresh usage pass `20260624T131159Z` with `just navlab-run hover --simulation-profile slam-direct-no-odom-prior` reached `TASK_STATUS_OK`; `runtime_hover_health_final.band=green`, `phase=sim_auto_continue`, while `postrun_hover_health_audit.health_band=yellow` only because of review-only Gazebo contract findings.

Acceptance:

- [x] A reviewer can tell from one `summary.json` whether the runtime gate proceeded green/stable and whether post-run audit was only yellow due to review-only findings.
- [x] `mission_summary.json` contains a frozen final runtime hover-health snapshot.
- [x] `hover_health_summary.json` remains post-run artifact audit, not runtime proceed truth.
- [ ] Real task launcher can require operator confirmation after hover green/stable.
- [x] Runtime operator confirmation cannot proceed from yellow/red and is cleared when health degrades.
- [x] Existing `hover_hold` evidence windows and downstream drift summaries remain compatible.

Non-goals:

- [ ] Do not relax hover drift, source mismatch, or fail-closed thresholds.
- [ ] Do not make Go the real-time flight controller.
- [ ] Do not introduce direct Go/Python library calls.
- [ ] Do not make Gazebo review-only findings into real-flight hard blockers without a separate contract-promotion phase.

### Phase 45 [hover-audit-package-split]: move hover audit logic out of tasks root

目标：Phase 43/44 已经把 hover runtime gate、post-run audit、summary split 跑通；Phase 45 只做 Go 代码结构整理，把已经成型的 hover 审计子域从 `orchestration/sim/internal/tasks` 根目录移到独立 package，避免 `tasks` 继续平铺膨胀。

Decision:

- [x] Hover 审计逻辑本质是 artifact/probe 的分析器，不是 task runner 本身。
- [x] 采用独立审计包结构，而不是继续放在 `tasks` 根目录：

```text
orchestration/sim/internal/audits/hover/
  health.go
  health_test.go
  metrics.go
  contract.go
  contract_test.go
  initialization.go
  initialization_test.go
  raw_source.go
  raw_source_test.go
  trajectory.go
  trajectory_test.go
```

- [x] `orchestration/sim/internal/tasks` 只保留 task orchestration、runtime spec、artifact/gate 接入的薄适配层。
- [x] `cmd/hover-*-audit` CLI 入口只调用 `internal/audits/hover`，不再承载审计实现细节。
- [x] 本 phase 是纯结构重构，不改变 hover 审计阈值、FSM 行为、runtime gate 策略或 summary schema。

Why this is the right split:

- [x] `tasks` 当前职责是“调度任务并接 artifact/gate”，而 hover audit 文件职责是“解释 hover artifact/probe evidence”。
- [x] 多个审计文件已经形成稳定族群：health、metrics、contract、initialization、raw source、trajectory。
- [x] 后续如果增加 landing、takeoff、external-nav 审计，可以自然扩展为：

```text
orchestration/sim/internal/audits/
  hover/
  landing/
  externalnav/
```

- [x] 迁移后 review 时可以更快区分“runtime 流程变更”和“审计指标/统计逻辑变更”。

Implementation tasks:

1. Package move:
   - [x] Create `orchestration/sim/internal/audits/hover`.
   - [x] Move hover audit implementation files from `orchestration/sim/internal/tasks`:
     - [x] `hover_health_audit.go` -> `audits/hover/health.go`
     - [x] `hover_health_metrics.go` -> `audits/hover/metrics.go`
     - [x] `hover_contract_audit.go` -> `audits/hover/contract.go`
     - [x] `hover_initialization_audit.go` -> `audits/hover/initialization.go`
     - [x] `hover_raw_source_audit.go` -> `audits/hover/raw_source.go`
     - [x] `hover_trajectory_audit.go` -> `audits/hover/trajectory.go`
   - [x] Move matching tests with the same naming pattern.
   - [x] Rename package from `tasks` to `hover` or `hoveraudit`; prefer `hover` under `audits/hover` because the import path already carries the audit context.
2. Public API boundary:
   - [x] Export only the functions/types needed by Go CLI commands and task artifact wiring.
   - [x] Keep internal helper structs/functions unexported inside the package.
   - [x] Avoid leaking task-runner concepts into the audit package unless they are already stable artifact contracts.
   - [x] If a type is shared only for JSON/artifact schema, keep the name schema-oriented, not task-oriented.
3. Tasks integration:
   - [x] Update `runtime_artifacts.go`, `gate_evaluation.go`, or related task wiring to call `audits/hover`.
   - [x] Keep `tasks` responsible for deciding when an audit runs and where artifacts are written.
   - [x] Keep `audits/hover` responsible for reading evidence and producing audit results.
   - [x] Do not introduce direct Go/Python calls; keep cross-language interaction through generated files, CLI args, env, ROS status/probe JSON, and artifact JSON.
4. CLI integration:
   - [x] Break the standalone `cmd/hover-*-audit` entrypoints and move them under `navlab-sim audit hover ...`.
   - [x] Keep `navlab-sim` as the single Go CLI surface for hover audits.
   - [x] Preserve audit flags, default output paths, JSON schema, and exit behavior on the new subcommands.
5. Tests and verification:
   - [x] Run package-local tests for the new audit package.
   - [x] Run affected task tests to prove artifact/gate wiring still works.
   - [x] Run all Go checks from the hook.
   - [x] Run pre-commit after staging because hook checks staged files.

45 execution result:

- [x] Created `orchestration/sim/internal/audits/hover` and moved hover audit implementation into package `hover`.
- [x] Kept `tasks` as the artifact/summary adapter via `BuildAndWriteHoverHealthSummaryArtifact` and `AttachHoverHealthToLiveRunSummary`.
- [x] Updated hover audit CLIs to import `navlab/orchestration-sim/internal/audits/hover` directly.
- [x] Consolidated standalone hover audit commands into `navlab-sim audit hover {health,contract,init,source,trajectory,gate-replay}` and removed the old command packages.
- [x] Split live-summary attachment tests back into `tasks` so the new audit package does not import the task package.
- [x] Added local CDR/test helpers inside the hover audit package to avoid depending on `tasks` test internals.
- [x] Targeted Go verification passed: `go test ./internal/audits/... ./internal/tasks ./cmd/navlab-sim`.
- [x] `.git/hooks/pre-commit` passed after staging the package split.

Acceptance:

- [x] No `hover_*_audit.go` implementation files remain directly under `orchestration/sim/internal/tasks`.
- [x] `orchestration/sim/internal/tasks` contains only orchestration/adaptor code for hover audits, not audit algorithms.
- [x] `navlab-sim audit hover ...` produces the same JSON schemas and exit behavior as the old standalone hover audit commands.
- [x] Go tests pass for `./orchestration/sim/internal/audits/...`, `./orchestration/sim/internal/tasks/...`, and `./orchestration/sim/cmd/...`.
- [x] `.git/hooks/pre-commit` passes after the package move is staged.
- [x] Commit can be reviewed as a behavior-preserving refactor.

Non-goals:

- [ ] Do not tune thresholds such as `0.1m` / `0.15m`.
- [ ] Do not change runtime hover FSM, stable-window timer, sim auto-continue, or real operator-confirm behavior.
- [ ] Do not change `summary.json`, `mission_summary.json`, or audit artifact schemas.
- [ ] Do not move Python runtime/FSM code in this phase.
- [ ] Do not combine this with real launcher/operator UI integration.

### Phase 46 [artifact-layout-break]: split flat run artifacts into readable directories

目标：当前 hover run artifact root 文件过多，runtime scripts、runtime configs、logs、probes、audits、summaries、rosbag、SITL state 都平铺在一个目录里，review 和 debug 成本过高。Phase 46 直接 break 旧 run 兼容，定义新的 artifact layout；后续代码实现只支持新 layout，不为历史 flat artifact 添加 fallback。

Status: executed by Phase 50 (`artifacts/sim/hover/20260625T035409Z`) and kept as the design record for the breaking layout.


Decision:

- [x] 直接 breaking change：不兼容旧 run，不做 old flat-path fallback。
- [x] 不引入 SQLite 到 runtime 主链；Go/Python 交互仍然只走生成文件、CLI args/env、ROS status/probe JSON、artifact JSON/MCAP。
- [x] SQLite 只作为未来跨 run/cohort index 的可选方案，不作为单次 run 的证据主存储。
- [x] 单次 run 必须保持可复制、可 grep、可人工打开检查的 artifact directory。
- [x] Root 只保留 reviewer 第一眼需要看的入口文件，其余必须按职责分目录。

New artifact layout:

```text
artifact/
  manifest.json
  summary.json
  summary.md
  mission_summary.json
  task_plan.json
  task_request.json
  runtime_plan.json
  run_config.toml

  audits/
    hover_health_summary.json
    contract_audit.json
    initialization_audit.json
    raw_source_audit.json
    trajectory_audit.json
    gate_replay.json

  probes/
    frame_contract_probe.py
    frame_contract_probe.json
    frame_contract_probe.log
    imu_probe.py
    imu_probe.txt
    imu_probe.log
    rangefinder_probe.py
    rangefinder_probe.txt
    rangefinder_probe.log
    slam_hover_probe.py
    slam_hover_probe.json
    slam_hover_probe.log

  runtime/
    scripts/
      hover_mission_runtime.py
      external_nav_source_selector_runtime.py
      official_maze_overlay_runtime.py
      scan_reference_drift_runtime.py
      scan_reference_cartographer_odom_runtime.py
      scan_reference_correction_runtime.py
    config/
      bridge_override.yaml
      external_nav_bridge_params.yaml
      frame_contract_runtime.toml
      gazebo_sensor_runtime.toml
      gazebo-iris-rangefinder.parm
      model_overlay.sdf
      navlab_cartographer_2d_hover_no_odom_prior.lua
      run_config.toml
      slam_hover_runtime.toml
      slam_runtime.toml
      vendor_profile.yaml
    logs/
      *.runtime.log
      *.start.log
      hover_mission_rc.txt

  profiles/
    hover_rosbag.txt

  rosbag/
    hover_rosbag/
      hover_rosbag_0.mcap.zstd
      metadata.yaml

  sitl/
    eeprom.bin
    mav.parm
    mav.tlog
    mav.tlog.raw
    logs/
    scripts/
    terrain/
```

Implementation tasks:

1. Path model:
   - [x] Add a central Go artifact layout helper, e.g. `internal/tasks/artifact_layout.go` or `internal/artifacts/layout.go`.
   - [x] Define named path builders for root, `audits`, `probes`, `runtime/scripts`, `runtime/config`, `runtime/logs`, `rosbag`, `profiles`, and `sitl`.
   - [x] Remove ad-hoc root-level path joins for generated scripts/config/logs.
   - [x] Do not keep compatibility helpers for old root-level artifact paths.
2. Runtime generation:
   - [x] Write generated Python runtime scripts under `runtime/scripts/`.
   - [x] Write generated TOML/YAML/SDF/Lua runtime configs under `runtime/config/`.
   - [x] Write runtime service/probe logs under `runtime/logs/` unless the file is a probe evidence output.
   - [x] Keep probe evidence outputs under `probes/`.
   - [x] Keep `profiles/`, `rosbag/`, and `sitl/` as dedicated top-level directories.
3. Summary and audit outputs:
   - [x] Keep `summary.json`, `summary.md`, `mission_summary.json`, `task_plan.json`, `task_request.json`, and `runtime_plan.json` at root.
   - [x] Move post-run audit outputs to `audits/`.
   - [x] `hover_health_summary.json` moves to `audits/hover_health_summary.json`.
   - [x] `navlab-sim audit hover ...` defaults must write into `audits/`.
   - [x] `summary.json` and `manifest.json` must record the new artifact paths.
4. Runtime specs and service commands:
   - [x] Update runtime spec generation so command paths point at `runtime/scripts` and `runtime/config`.
   - [x] Update mounted config paths and generated script paths consistently.
   - [x] Update rosbag output paths only if needed; keep MCAP under `rosbag/<name>/`.
   - [x] Update SITL working directory from `sitl_work/` to `sitl/`, or explicitly choose one canonical name and remove the other.
5. Tests:
   - [x] Update Go runtime artifact tests to assert no runtime scripts/config/logs are written at artifact root.
   - [x] Add a layout test that root contains only approved entry files plus approved directories.
   - [x] Update hover audit CLI tests/usage paths to new `audits/` defaults.
   - [x] Update live summary tests for `postrun_hover_health_audit.artifact`.
   - [x] Run `go test ./...` and `.git/hooks/pre-commit`.
6. Usage pass:
   - [x] Run `just navlab-run hover --simulation-profile slam-direct-no-odom-prior`.
   - [x] Confirm new artifact tree is readable and root is not polluted by generated runtime files.
   - [x] Confirm `navlab-sim audit hover health <artifact-dir>` writes to `audits/hover_health_summary.json`.
   - [x] Confirm `summary.json`, `manifest.json`, and `mission_summary.json` point to new paths.

Acceptance:

- [x] New runs no longer place runtime scripts/config/logs/probes/audits flat in artifact root.
- [x] Old flat run artifacts are not supported by new Go readers or `navlab-sim audit hover ...`.
- [x] `manifest.json` lists moved artifacts with their new relative paths.
- [x] `summary.json` uses `audits/hover_health_summary.json` for post-run hover health evidence.
- [x] `runtime_plan.json` command paths reference `runtime/scripts`, `runtime/config`, `runtime/logs`, `probes`, `rosbag`, and `sitl` consistently.
- [x] `navlab-sim audit hover {health,contract,init,source,trajectory,gate-replay}` works on the new layout.
- [x] `.git/hooks/pre-commit` passes after the layout migration is staged.

Non-goals:

- [x] Do not add old-layout fallback or migration.
- [x] Do not preserve old standalone hover audit command packages.
- [x] Do not introduce SQLite into the live runtime execution path.
- [x] Do not move MCAP contents into SQLite.
- [x] Do not change hover thresholds, health bands, FSM policy, or real/sim proceed behavior.
- [x] Do not redesign Foxglove replay layout beyond the paths required by this artifact split.

Future SQLite index phase, not part of Phase 46:

- [ ] Optional `navlab-sim index artifacts` can build a cohort-level `index.sqlite`.
- [ ] SQLite may index run id, task id, profile, status, health band, blocker codes, artifact paths, and aggregate metrics.
- [ ] SQLite must be derived from artifact files and be rebuildable; it must not be the source of truth for a single run.

### Phase 47 [hover-slo-policy]: split hover span target from hard cap and downgrade Gazebo review-only blockers

Status: core complete. Phase 49 provides the 5-run cohort proof; a natural yellow-band run was not observed after the fix, so yellow/hard-cap behavior is covered by Go/Python tests and the earlier 0.103m/0.118m examples.


目标：把 hover body 的 XY span 从单一 `0.1m` 二值 hard threshold 改成 Go 调度下发的 SLO policy：`target=0.1m`、`hard_cap=0.15m`、cohort percentile 统计。单次 run 超过 target 但低于 hard cap 时进入 yellow/warning/trend，不直接 blocked；只有超过 hard cap 或伴随真实安全事件时才 hard fail。同时 Gazebo observation contract 未闭环前，Gazebo-only finding 继续是 `sim-review-only`，不能作为 top-level hard blocker。

Basis:

- 2026-06-25 Phase 41/42 profile 真实 run 显示 `hover_health_hold` 本身已 green 并自动继续：
  - `20260625T013413Z`: runtime health `green/sim_auto_continue`，无 ExternalNav/MAVLink/SLAM loss，mission final drift `0.030m`，但 `horizontal_span_m=0.103m` 触发 `hover_span_unstable`。
  - `20260625T013623Z`: runtime health `green/sim_auto_continue`，无 ExternalNav/MAVLink/SLAM loss，mission final drift `0.020m`，但 `horizontal_span_m=0.118m` 触发 `hover_span_unstable`。
  - `20260625T013826Z`: mission reached `S13 task_success`，`horizontal_span_m=0.034m`；该 run 因人工中断缺少顶层 post-run summary，不作为完整 pass 计数。
- 这证明当前 blocker 主要是 target 被当成 hard fail，而不是 runtime health gate、ExternalNav loss、SLAM loss 或 landing 失败。

Decision:

- [x] `0.1m` 是 target / SLO target，不再是所有 run 的唯一 hard fail 边界。
- [x] `0.15m` 是当前 proposed hard cap；具体数值由 Go 调度/配置下发，后续可以按 cohort 分布调整。
- [x] Python runtime 不固定写死 `0.1m` / `0.15m`；Python 只执行 Go 生成文件或 CLI/env 参数里的 policy。
- [x] Go 是 hover SLO policy owner：task config / simulation profile / CLI override -> `PlanOptions` -> runtime config/artifact -> Python mission args。
- [x] 单次 `target < span <= hard_cap` 记为 `yellow` / `target_exceeded` / `collect_stats`，top-level 不 hard block。
- [x] 单次 `span > hard_cap` 记为 `red` / hard blocker。
- [x] Safety events 仍然 hard fail，不被 percentile 放宽：ExternalNav loss、MAVLink ExternalNav loss、SLAM loss、pose/yaw jump、frame contract hard mismatch、mission abort、truth/known-map runtime input。
- [x] Gazebo-only findings 在 `/gazebo/tf`、model/link name、frame origin、timestamp、sign convention contract 闭环前保持 `sim-review-only`，不得让 top-level `gate_evaluation.ok=false`。
- [x] Cohort report 用 P50/P90/P95/P99 和 sample-size rule 描述稳定性；小样本只能 `case_study_only`，不能宣称 P99。

Implementation tasks:

1. Go policy model:
   - [x] Add explicit hover SLO policy fields to Go config/runtime model, e.g. `hover_span_target_m` and `hover_span_hard_cap_m`.
   - [x] Defaults live in Go config/defaulting, not in Python mission code.
   - [x] Add CLI or profile override path if needed, e.g. `--hover-span-target-m` / `--hover-span-hard-cap-m`, so experiments can move thresholds without editing Python.
   - [x] Validate `0 < target <= hard_cap`; reject invalid run plans before starting runtime.
2. Go -> Python boundary:
   - [x] Write the resolved policy into generated runtime config/artifacts, not implicit constants.
   - [x] Pass the resolved policy to `hover_mission_runtime.py` through generated file, CLI args, or env; keep Go/Python coupling file/probe/args only.
   - [x] `mission_summary.json` must echo `hover_span_target_m`, `hover_span_hard_cap_m`, and the resolved policy source.
   - [x] `summary.json` must copy the resolved policy so cohort audits do not guess historical thresholds.
3. Python mission classification:
   - [x] Replace binary `horizontal_span_ok = span <= max_horizontal_drift_m` semantics with tiered classification:
     - [x] `span <= target`: green / target_met.
     - [x] `target < span <= hard_cap`: yellow / target_exceeded_below_hard_cap.
     - [x] `span > hard_cap`: red / hard_cap_exceeded.
   - [x] Keep final drift, z span, duration, loss, and jump checks separate from XY span SLO classification.
   - [x] Sim task may continue/pass on yellow if no safety hard blocker exists; real task still requires operator confirm after runtime health green according to Phase 43B.
4. Go gate and summary:
   - [x] Update top-level gate mapping so `target_exceeded_below_hard_cap` becomes warning/statistical finding, not `TASK_STATUS_BLOCKED`.
   - [x] Keep `hard_cap_exceeded` as hard blocker.
   - [x] Downgrade `hover_gazebo_model_horizontal_drift` and Gazebo pair errors to review-only unless another proven hard contract violation is present.
   - [x] Ensure `hover_health_summary.json` and top-level `postrun_hover_health_audit` agree on warning vs hard blocker tiers.
5. Cohort percentile audit:
   - [x] Extend hover health cohort output to include hover mission span percentiles: P50/P90/P95/P99, max, sample count, and sample-size rule.
   - [x] Report target exceed rate and hard-cap exceed rate separately.
   - [x] Preserve per-run evidence links so an outlier can be traced back to `mission_summary.json`, rosbag, trajectory audit, and contract audit.
6. Tests:
   - [x] Add Go config/default tests for target/hard_cap resolution and invalid policy rejection.
   - [x] Add runtime artifact test that generated Python/runtime config contains resolved `hover_span_target_m` and `hover_span_hard_cap_m`.
   - [x] Add Python mission tests for green/yellow/red span classification.
   - [x] Add Go gate tests proving `0.103m` and `0.118m` with `target=0.1m`, `hard_cap=0.15m` are warnings, not blockers.
   - [x] Add Go gate tests proving `0.151m` is a hard blocker.
   - [x] Add test proving Gazebo review-only drift no longer makes top-level gate blocked by itself.
7. Usage pass:
   - [x] Run `just navlab-run hover --simulation-profile slam-direct-no-odom-prior` at least 3 times via Phase 49 5-run cohort.
   - [x] Confirm `0.1m < horizontal_span_m <= 0.15m` is warning/yellow-not-blocked through Go/Python tests and prior `0.103m` / `0.118m` examples; no fresh natural yellow sample appeared in Phase 49.
   - [x] Confirm `horizontal_span_m > 0.15m` still fails hard through policy/gate tests.
   - [x] Generate a cohort health report and verify target exceed rate / hard-cap exceed rate / percentiles are present.

Acceptance:

- [x] Thresholds are not hardcoded in Python; they are resolved by Go and recorded in artifacts.
- [x] New run artifacts show the exact `hover_span_target_m` and `hover_span_hard_cap_m` used.
- [x] `0.1m < span <= 0.15m` no longer produces `hover_mission_body_not_ok` / `TASK_STATUS_BLOCKED` by itself.
- [x] `span > 0.15m` still blocks.
- [x] Gazebo review-only drift no longer blocks top-level gate by itself.
- [x] Cohort output separates target exceed rate from hard-cap exceed rate and includes percentile statistics.
- [x] Phase 41/42 command remains the validation path: `just navlab-run hover --simulation-profile slam-direct-no-odom-prior`.


Execution result:

- [x] Dry-run `just navlab-run hover --simulation-profile slam-direct-no-odom-prior --hover-span-target-m 0.1 --hover-span-hard-cap-m 0.15 --dry-run` showed the resolved policy in CLI output, `task_plan.json`, and generated `hover_mission_runtime.py`.
- [x] Fresh successful usage pass `20260625T023143Z`: `TASK_STATUS_OK`, `mission_summary.ok=true`, `mission_phase_state=S13 task_success`, runtime health `green/sim_auto_continue`, `horizontal_span_m=0.025m`, `hover_span_target_m=0.1`, `hover_span_hard_cap_m=0.15`, and no top-level blockers.
- [x] Cohort command generated `navlab.hover_health_cohort.v1` and included `mission_hover_horizontal_span_m` with P50/P90/P95/P99, target exceed rate, hard-cap exceed rate, and `case_study_only` sample-size rule.
- [x] Fixed a probe false-negative found during usage: generic ROS probe now treats non-empty `ros2 topic echo --once` stdout as evidence even if the `timeout` wrapper returns `124`; this prevented `/tf_static` evidence from being discarded after it had already been printed.
- [x] Full repeatability proof moved to Phase 49: five valid hover-body samples completed; `20260625T022810Z` remains classified as preflight/readiness invalid, not a hover-span SLO sample.
- [x] A natural fresh run with `0.1m < span <= 0.15m` was not observed after the fix; behavior is covered by Go/Python tests using the prior `0.103m` / `0.118m` examples.

Non-goals:

- [x] Do not tune Cartographer, selector gates, scan-reference residuals, or mission controller behavior in this phase.
- [x] Do not use Gazebo truth / known map / fixed pose as runtime input.
- [x] Do not introduce SQLite into runtime execution.
- [x] Do not remove the runtime hover-health gate or real operator-confirm flow.
- [x] Do not claim `P99` from a 3-5 run cohort; mark small samples as case-study evidence only.


### Phase 48 [observation-contract]: close Gazebo and FCU evidence contracts

目标：补强 hover 的观测面，不改变 hover runtime 控制策略。重点证明各观测源是否可比、如何可比、什么时候只能 review-only：Gazebo `/tf`、model odometry、frame origin、timestamp、sign convention，以及 FCU controller / setpoint evidence 在 rosbag/profile 中的覆盖情况。

Basis:

- Phase 42 已经看到 Gazebo model odometry 与 SLAM/ExternalNav 在 edge run 里有相反方向的 relative-X peak；这说明 Gazebo 不能继续被当成未经证明的 hard truth。
- Phase 47 已把 Gazebo-only drift 从 top-level hard blocker 降级，但还没有完成 Gazebo observation contract promotion / rejection。
- 既有 run 中 `/navlab/fcu/controller/status`、`/navlab/fcu/setpoint/output` 有时没有样本；这会削弱“FCU 实际控制行为”的复盘能力。

Implementation tasks:

1. Gazebo observation contract:
   - [x] Audit `/gazebo/tf` and `/gazebo/model/odometry` generation path: model/link name, transform index, frame id, child frame id, timestamp source, and sign convention.
   - [x] Add or extend `navlab-sim audit hover contract` to emit explicit Gazebo comparability fields: `frame_origin`, `time_basis`, `sign_convention`, `model_name_resolution`, `link_name_resolution`, and `directly_comparable_to_slam_map_delta`.
   - [x] Keep Gazebo findings `sim-review-only` until those fields are proven and documented.
   - [x] Add a promotion rule: Gazebo can become hard blocker only through a separate contract-promotion decision with tests.
2. Time-aligned source comparison:
   - [x] Extend trajectory audit to report peak-time alignment across SLAM, ExternalNav, FCU local pose, Gazebo model odometry, and scan-reference diagnostic odometry.
   - [x] Record whether peak vectors agree in sign/direction and whether sample timestamps are within a configured tolerance.
   - [x] Preserve per-source raw sample counts and time windows so missing data is visible.
3. FCU/controller/setpoint evidence:
   - [x] Confirm rosbag profiles include `/navlab/fcu/controller/status`, `/navlab/fcu/setpoint/intent`, and `/navlab/fcu/setpoint/output` for hover review capture.
   - [x] If topics are intentionally absent in current runtime, document why and mark them optional/review-only rather than silently missing.
   - [x] Current hover runtime artifact still has 0 samples for those FCU evidence topics; contract audit now reports this as explicit `missing_review_evidence`, not an ambiguous silent gap.
4. Tests:
   - [x] Add contract-audit tests for Gazebo model/link/frame/timestamp fields.
   - [x] Add trajectory-audit tests for time-aligned opposite-direction peak detection.
   - [x] Add rosbag profile tests proving FCU controller/setpoint topics are review-captured and explicitly optional for hover required topics.
5. Usage pass:
   - [x] Reused latest successful Phase 50 `just navlab-run hover --simulation-profile slam-direct-no-odom-prior` artifact `artifacts/sim/hover/20260625T035409Z` because Phase 48 changes are audit-only and do not alter runtime control.
   - [x] Generated contract and trajectory audits for that artifact.
   - [x] Confirmed Gazebo remains review-only unless contract-promotion criteria are met.
   - [x] Confirmed FCU/controller/setpoint evidence is either present or explicitly explained.

Acceptance:

- [x] `navlab-sim audit hover contract` explains whether Gazebo odometry is directly comparable to SLAM/ExternalNav deltas.
- [x] `navlab-sim audit hover trajectory` reports time-aligned peak direction agreement/disagreement.
- [x] Missing FCU/controller/setpoint evidence is no longer ambiguous: it is either captured or explicitly optional with reason.
- [x] Gazebo-only mismatch cannot become a top-level hard blocker without contract-promotion evidence.

Execution result:

- [x] `cd orchestration/sim && go test ./internal/audits/hover ./internal/tasks/helpers` passed.
- [x] `cd orchestration/sim && go test ./...` passed.
- [x] `navlab-sim audit hover contract artifacts/sim/hover/20260625T035409Z` wrote `artifacts/sim/hover/20260625T035409Z/audits/contract_audit.json`.
- [x] Contract audit reports `gazebo_comparability.directly_comparable_to_slam_map_delta=false`, `frame_origin.status=different_origins_unpromoted`, `model_name_resolution.status=runtime_substitution_unverified`, `sign_convention.status=declared_unverified`, and a separate `gazebo_promotion_rule`.
- [x] Contract audit reports FCU controller/setpoint topics as `missing_review_evidence` with `missing_evidence_is_ambiguous=false`; this is review debt, not silent pass/fail ambiguity.
- [x] `navlab-sim audit hover trajectory artifacts/sim/hover/20260625T035409Z` wrote `artifacts/sim/hover/20260625T035409Z/audits/trajectory_audit.json`.
- [x] Trajectory audit reports `peak_time_alignment`: SLAM vs ExternalNav peak vectors agree (`direction_cosine=0.998`, `within_tolerance=true`), while SLAM vs Gazebo shows opposite-direction evidence (`direction_cosine=-0.941`, `opposite_direction_suspected=true`) and remains diagnostic/review-only.

Non-goals:

- [x] Do not tune hover thresholds, Cartographer, selector gates, or scan-reference residuals.
- [x] Do not use Gazebo truth / known map / fixed pose as runtime input.
- [x] Do not promote Gazebo to hard safety truth inside this phase.

### Phase 49 [hover-stability-cohort]: build a real hover SLO cohort

Status: complete after closeout. Cohort rows now carry trace links, and mixed valid/preflight coverage is protected by Go tests.


目标：把 Phase 47 的 SLO policy 从单次 usage pass 扩展成可复盘的 cohort：至少 3-5 次真实 `slam-direct-no-odom-prior` hover run，输出 P50/P90/P95/P99、target exceed rate、hard-cap exceed rate，并明确小样本只能作为 case study。

Basis:

- Phase 47 已实现 `target=0.1m` / `hard_cap=0.15m` / cohort percentile 输出。
- Phase 47 只完成了 1 次完整成功 usage pass；完整 3-run cohort 仍 pending。
- Hover 是混沌闭环系统，单次 run 不足以证明稳定性或 root cause。

Implementation tasks:

1. Run plan:
   - [x] Use the canonical command: `just navlab-run hover --simulation-profile slam-direct-no-odom-prior --hover-span-target-m 0.1 --hover-span-hard-cap-m 0.15`.
   - [x] Run at least 3 successful hover-body samples; prefer 5 if environment is stable.
   - [x] Stop and analyze immediately if a run blocks before hover body; do not blindly continue counting invalid samples.
2. Cohort artifact:
   - [x] Generate `hover_health_cohort.json` with `navlab-sim audit hover health --output ... <artifact-dir>...`.
   - [x] Record sample-size rule (`case_study_only` for 3-5 runs) prominently.
   - [x] Include per-run links to `summary.json`, `mission_summary.json`, `hover_health_summary.json`, trajectory audit, and contract audit.
3. Metrics:
   - [x] Report mission hover horizontal span P50/P90/P95/P99/max.
   - [x] Report target exceed count/rate separately from hard-cap exceed count/rate.
   - [x] Report runtime health band, post-run health band, safety blockers, review-only blockers, and startup/preflight invalid samples separately.
4. Decision rules:
   - [x] If all valid hover samples are `<= hard_cap` and no safety event occurs, treat hover body as operationally usable even if target exceed appears in yellow.
   - [x] If any valid hover sample exceeds hard cap, keep hard fail and open a root-cause phase.
   - [x] If failures are preflight/readiness only, route them to Phase 51 and do not count them as hover span samples.
   - [x] Do not claim P99 stability from 3-5 samples.
5. Tests / tooling:
   - [x] Add or update a cohort-summary test that includes valid samples plus invalid preflight samples.
   - [x] Ensure invalid/preflight artifacts are excluded or labeled separately from hover span percentiles.

Acceptance:

- [x] A cohort JSON exists with at least 3 valid hover-body samples or a documented blocker explaining why the cohort could not be collected.
- [x] The cohort separates target exceed rate from hard-cap exceed rate.
- [x] The cohort distinguishes hover-body SLO failures from preflight/readiness failures.
- [x] The decision note says `case_study_only` unless sample size is large enough for stronger percentile claims.

Non-goals:

- [x] Do not change policy values during the cohort run.
- [x] Do not mix different simulation profiles in the same primary cohort.
- [x] Do not hide invalid/preflight runs inside hover span percentiles.

Execution log (2026-06-25 Phase 49):

- [x] Phase 49 closeout update: cohort run rows now include `summary_artifact`, `mission_summary_artifact`, `hover_health_artifact`, `contract_audit_artifact`, and `trajectory_audit_artifact`.
- [x] Phase 49 closeout update: `TestBuildHoverHealthCohortKeepsTraceLinksAndExcludesPreflightFromSpan` covers valid hover samples plus preflight-invalid artifacts and asserts span percentile count only includes valid mission spans.
- [x] Ran five fresh `slam-direct-no-odom-prior` hover samples with fixed Go-owned policy `target=0.1m`, `hard_cap=0.15m`: `20260625T030617Z`, `20260625T030852Z`, `20260625T031110Z`, `20260625T031325Z`, `20260625T031541Z`.
- [x] All five runs reached `TASK_STATUS_OK`, `mission_summary.ok=true`, `mission_phase_state=S13 task_success`, `runtime_hover_health_final.band=green`, and `phase=sim_auto_continue`.
- [x] Primary cohort artifact: `artifacts/sim/hover/phase49_5run_hover_health_cohort.json`.
- [x] Mission hover horizontal span results: P50 `0.057657m`, P90 `0.067167m`, P95 `0.067246m`, P99 `0.067308m`, max `0.067324m`; `target_exceed_count=0`, `hard_cap_exceed_count=0`, `sample_size_rule=case_study_only`.
- [x] Post-run health band is still `yellow` for all five because Gazebo review-only contract findings remain; this is observation-surface debt, not a hover-body hard blocker.
- [x] Mixed cohort check with preflight-invalid `20260625T022810Z` wrote `artifacts/sim/hover/phase49_mixed_valid_plus_preflight_hover_health_cohort.json`; mission span metric count stayed `5`, while the preflight run appeared separately as `red` with no `mission_hover_span`.

### Phase 50 [artifact-readability]: execute the artifact layout break and define cohort indexing boundary

目标：执行 Phase 46 的 artifact 分层，让单次 run root 可读、审计文件分目录、runtime scripts/config/logs 不再平铺；同时明确 SQLite 只允许作为可重建的 cross-run/cohort index，不进入 runtime 主链。

Basis:

- 当前 artifact root 文件过多，debug 时难以区分 reviewer entry、runtime script、config、probe evidence、logs、audit output、rosbag 和 SITL state。
- Phase 46 已经定义 breaking layout；本 phase 是执行/收敛，不再重新讨论是否兼容旧 run。
- Phase 47/49 会产生更多 audit/cohort evidence，如果 artifact 继续平铺，可读性会继续恶化。

Implementation tasks:

1. Execute Phase 46 layout:
   - [x] Keep root only for reviewer entry files: `manifest.json`, `summary.json`, `summary.md`, `mission_summary.json`, `task_plan.json`, `task_request.json`, `runtime_plan.json`, `run_config.toml`.
   - [x] Move audits to `audits/`.
   - [x] Move probes to `probes/`.
   - [x] Move generated runtime scripts/config/logs to `runtime/scripts`, `runtime/config`, and `runtime/logs`.
   - [x] Keep `rosbag/`, `profiles/`, and `sitl/` as dedicated directories.
2. Break compatibility deliberately:
   - [x] Do not add old flat-path fallback.
   - [ ] Do not migrate old artifacts.
   - [x] Update Go readers, manifest paths, runtime specs, and hover audit CLIs to new layout only.
3. SQLite boundary:
   - [x] Do not introduce SQLite into single-run runtime execution.
   - [ ] If needed later, add a separate `navlab-sim index artifacts` command that builds a rebuildable `index.sqlite` from artifact files.
   - [x] Document that SQLite is an index/cache, not source of truth.
4. Tests:
   - [x] Add layout tests that artifact root contains only approved entry files/directories.
   - [x] Update runtime artifact tests for new paths.
   - [x] Update hover audit CLI tests / usage for `audits/` defaults.
   - [x] Update live summary behavior for moved `postrun_hover_health_audit.artifact` paths.
5. Usage pass:
   - [x] Run `just navlab-run hover --simulation-profile slam-direct-no-odom-prior --hover-span-target-m 0.1 --hover-span-hard-cap-m 0.15`.
   - [x] Confirm root tree is readable and not polluted by runtime/probe/audit internals.
   - [x] Confirm `navlab-sim audit hover health <artifact-dir>` writes to `audits/hover_health_summary.json`.

Acceptance:

- [x] New hover artifacts are split into root entry files plus `audits/`, `probes/`, `runtime/`, `profiles/`, `rosbag/`, and `sitl/`.
- [x] Old flat artifact layout is not supported by new code.
- [x] `manifest.json`, `summary.json`, and `runtime_plan.json` reference new paths consistently.
- [x] SQLite is not in the runtime path; any future index is rebuildable from artifacts.

Non-goals:

- [ ] Do not change hover FSM, SLO policy, or source-selection behavior.
- [ ] Do not add old-run compatibility fallback.
- [ ] Do not store MCAP contents in SQLite.

Execution log (2026-06-25 Phase 50):

- [x] Added central Go artifact layout helper `orchestration/sim/internal/artifactlayout` and moved generated runtime/probe/audit paths to the new layout.
- [x] Fresh usage artifact `artifacts/sim/hover/20260625T035409Z` completed `TASK_STATUS_OK`, `gate_evaluation.ok=true`, `mission_summary.ok=true`, `mission_phase_state=S13 task_success`, runtime health `green/sim_auto_continue`.
- [x] Root now contains only entry files plus directories: `audits`, `manifest.json`, `mission_summary.json`, `probes`, `profiles`, `rosbag`, `run_config.toml`, `runtime`, `runtime_plan.json`, `sitl`, `summary.json`, `summary.md`, `task_plan.json`, `task_request.json`.
- [x] Runtime internals moved: scripts under `runtime/scripts/`, configs under `runtime/config/`, logs under `runtime/logs/`, probe scripts/output/logs under `probes/`, audit outputs under `audits/`, SITL state under `sitl/`.
- [x] `summary.json.postrun_hover_health_audit.artifact` points to `audits/hover_health_summary.json`; `manifest.json` records moved paths such as `runtime/scripts/hover_mission_runtime.py`, `runtime/config/slam_runtime.toml`, and `audits/hover_health_summary.json`.
- [x] `navlab-sim audit hover health`, `contract`, and `gate-replay` defaulted to `audits/` on the fresh artifact.
- [x] Verification: `cd orchestration/sim && go test ./...` passed after the layout migration.

### Phase 51 [startup-readiness]: harden preflight readiness, rangefinder height, and probe semantics

Status: complete for classification/evidence hardening. Startup/readiness failures are now explicitly separated from hover-body SLO samples; further active remediation such as restarting a stuck rangefinder chain is a future operational hardening phase.


目标：把 preflight/startup 边缘问题和 probe 假阴性从 hover SLO 中剥离出来单独治理。启动链路必须能解释 rangefinder/height readiness、ExternalNav waiting state、`/tf_static` sampling、probe timeout/echo evidence；preflight 未进入 hover 的 run 不应污染 hover span cohort。

Basis:

- Phase 47 usage 中 `20260625T022810Z` 停在 `S1 wait_nav_ready`，rangefinder status `input_count=0`，ExternalNav 等 height，mission `preflight_timeout`；这不是 hover span policy 失败。
- Phase 47 还发现 `/tf_static` probe 假阴性：stdout 已有 transforms，但 `timeout` return code `124` 让 probe 标 missing；已做第一处修复，但 readiness/probe 语义仍需系统化。

Implementation tasks:

1. Preflight classification:
   - [x] Add clear summary classification for `preflight_timeout`, `wait_nav_ready`, rangefinder not ready, height missing, ExternalNav waiting for height, and SLAM quality jump before airborne.
   - [x] Mark these as startup/readiness failures, not hover-body SLO samples.
   - [x] Ensure cohort tooling excludes or separately reports preflight-invalid artifacts.
2. Rangefinder/height readiness:
   - [x] Audit `benewake_tfmini_serial`, Gazebo range projection, `/rangefinder/down/range`, and `/rangefinder/down/status` startup order.
   - [x] Add evidence fields for virtual serial link existence, byte count, frame count, latest distance age, projection input count, and height-estimator readiness.
   - [x] Decide whether startup should wait longer, fail faster with clearer reason, or restart a stuck rangefinder chain: this phase keeps runtime control unchanged and fails with clearer startup-readiness reasons; restart policy is future work.
3. Probe semantics:
   - [x] Unit-test generic ROS probe behavior: non-empty stdout from `ros2 topic echo --once` counts as evidence even if timeout returns `124`.
   - [x] Add specific tests for `/tf_static` latched/static transform sampling.
   - [x] Distinguish `topic_type_missing`, `topic_sample_missing`, `sample_stdout_present_timeout`, and parsed-payload-not-ready.
   - [x] Avoid treating optional/review-only probes as hard blockers.
4. Runtime readiness gates:
   - [x] Review probe required/optional flags for hover: `rangefinder_probe`, `imu_probe`, `frame_contract_probe`, `slam_hover_probe`.
   - [x] Keep safety-critical missing evidence hard fail, but make failure reason precise enough to route to startup, frame contract, or hover body.
   - [x] Add summary fields that explain whether the vehicle ever reached airborne/hover_hold.
5. Usage pass:
   - [x] Reproduce or observe at least one startup/readiness failure and verify it routes to Phase 51-style reason codes.
   - [x] Run one successful hover after probe changes to prove hardening did not mask real missing topics.

Acceptance:

- [x] A preflight failure cannot be mistaken for hover span instability.
- [x] Rangefinder/height not-ready artifacts explain which component did not produce evidence.
- [x] `/tf_static` or other latched/static topics with real stdout evidence are not falsely marked missing because of timeout wrapper return code alone.
- [x] Cohort reporting separates startup-invalid runs from valid hover-body samples.

Non-goals:

- [x] Do not relax real safety blockers after takeoff.
- [x] Do not count preflight failures as hover SLO failures.
- [x] Do not tune hover target/hard-cap values.

Execution result (2026-06-25 Phase 51):

- [x] Added `gate_evaluation.metrics.startup_readiness` with `classification`, `preflight_invalid`, `valid_hover_body_sample`, `not_hover_span_slo`, `reason_codes`, mission airborne/hover-hold evidence, rangefinder evidence including serial `byte_count`/`frame_count`, height evidence, probe semantic outcomes, and selected rosbag counts.
- [x] Preflight artifact `20260625T022810Z` now replays as `classification=startup_readiness_failure`, `preflight_invalid=true`, `valid_hover_body_sample=false`, `not_hover_span_slo=true`, `serial_byte_count=0`, `serial_frame_count=0`; reasons include `wait_nav_ready`, `rangefinder_not_ready`, `rangefinder_input_missing`, `rangefinder_range_sample_missing`, `external_nav_waiting_for_height`, and `height_estimate_missing`.
- [x] Successful fresh hover artifact `20260625T051820Z` completed `TASK_STATUS_OK`; gate replay reports `classification=hover_body_sample`, `preflight_invalid=false`, `valid_hover_body_sample=true`, `reason_codes=[]`, `rangefinder.ready=true`, `serial_byte_count=18405`, `serial_frame_count=2045`, and `/rangefinder/down/range` rosbag count `2376`.
- [x] ROS probe template now labels `topic_type_missing`, `topic_sample_missing`, and `sample_stdout_present_timeout`; non-empty stdout remains evidence even when `timeout` returns `124`.
- [x] Added explicit `/tf_static` stdout-timeout semantics coverage so latched/static transform evidence is not converted into a hard missing-topic blocker.
- [x] Verification: `cd orchestration/sim && go test ./internal/tasks ./internal/tasks/helpers` passed.
- [x] Verification: `cd orchestration/sim && go test ./...` passed.
- [x] Verification: `./scripts/quality/check-python.sh` passed (`405 passed`).
- [x] Verification: `./scripts/quality/check-go.sh` passed.


### Phase 52 [startup-readiness-runtime-policy]: wait/fail-fast/restart policy for stuck rangefinder and height startup

Status: in progress. Phase 51 已经解决“怎么分类、怎么解释证据”；Phase 52 处理 Go-owned runtime action policy：wait-longer、fail-fast、pre-arm bounded restart 是三种不同策略，由 Go 统一制定/下发，Python/FSM 只执行和回写证据。

目标：把 rangefinder/height startup readiness 从被动 post-run 诊断升级为 preflight runtime policy。Phase52 的主语是 Go policy，不是 Python 临时 if/else：Go 根据 config/profile/CLI 解析出策略参数，并通过生成文件、CLI/env、ROS status/probe JSON、artifact JSON 传给 runtime。策略必须在未起飞、未进入 hover body 前生效；一旦 armed/airborne/hover_hold 已经发生，只能 fail-closed，不能为了继续实验而自动重启安全链路。

Strategy layers:

- [x] `wait_longer_policy`: 只有看到 progress delta 才继续等，例如 serial bytes/frames 增长、range `input_count` 增长、height estimate/status 推进。
- [x] `fail_fast_policy`: grace window 内完全没有进展时快速失败，不再盲等完整 mission timeout。
- [x] `prearm_restart_policy`: 只在 pre-arm/pre-airborne/pre-hover body，对明确标注的 leaf service 做 bounded restart；起飞后禁止 restart。

Design rule:

- [x] Go owns startup readiness policy and resolved parameters; Python mission/runtime only 消费 Go 生成的文件、CLI/env 参数、ROS status、probe JSON、artifact JSON。
- [x] Go/Python 交互继续只通过文件、probe、artifact、ROS topic、CLI/env；不引入直接 Go 调 Python library 或 Python 调 Go library。
- [x] Runtime policy must be evidence-driven, not blind sleep/retry. Only wait longer when there is measurable progress.
- [x] Restart is allowed only before arming/airborne and only for bounded leaf services; never restart FCU/SITL/mission body after takeoff.
- [x] Every policy action must be written to artifact so blocked runs explain “why waited / why failed fast / why restarted”.

Policy model:

1. Readiness inputs:
   - [x] Rangefinder serial evidence: virtual serial path, `byte_count`, `frame_count`, latest distance, latest input age.
   - [x] Rangefinder ROS evidence: `/rangefinder/down/status.ready`, `input_count`, `/rangefinder/down/range` sample count.
   - [x] Height evidence: `/height/estimate`, `/height/status`, ExternalNav `height.ready`, ExternalNav `state=waiting_for_height`.
   - [x] Mission safety state: armed, guided, airborne, hover_hold, mission FSM state; runtime monitor delays `hover_mission`, so restart boundary is pre-mission/pre-arm by construction.
   - [x] Probe semantics from Phase 51: distinguish missing topic, no sample, stdout-timeout evidence, and parsed-not-ready.
2. Wait-longer rule:
   - [x] Wait longer only if progress is visible, e.g. serial byte/frame counts increasing, rangefinder `input_count` increasing, height status changing, or ExternalNav moving closer to ready.
   - [x] Record progress deltas and remaining startup budget in `audits/startup_readiness_runtime.json` timeline and final decision fields.
   - [x] Cap total preflight readiness wait by a Go-owned timeout, not a Python hardcoded constant.
3. Fail-fast rule:
   - [x] Fail faster when a prerequisite shows no progress for a short grace window: serial bytes remain `0`, range samples remain `0`, height estimate remains `0`, or required status topic is absent.
   - [x] Emit precise runtime reason codes such as `startup_readiness_no_progress`, `startup_readiness_timeout`, `startup_readiness_restart_limit_exhausted`, and `startup_readiness_ready`; finer per-component no-input reasons remain a follow-up refinement.
   - [x] Preserve Phase 51 classification: these are `startup_readiness_failure`, not hover-body SLO failures.
4. Safe restart rule:
   - [x] Allow at most a bounded number of pre-arm restarts for annotated leaf startup services; default `restart_limit=0` keeps live behavior conservative until explicitly enabled.
   - [x] Restart only when mission state confirms not armed, not airborne, and not in hover body.
   - [x] After restart, require fresh readiness evidence before continuing; if no new evidence appears, fail fast with restart history.
   - [x] Do not restart SLAM/ExternalNav/FCU path after the system has produced takeoff-critical evidence unless a separate phase proves safety.

Implementation tasks:

1. Go runtime policy config:
   - [x] Add startup readiness policy fields under hover runtime config, e.g. `startup_readiness_policy.timeout_sec`, `startup_readiness_policy.grace_sec`, `startup_readiness_policy.restart_limit`, `startup_readiness_policy.progress_window_sec`.
   - [x] Resolve defaults in Go config/defaulting and echo them in `run_config.toml`, `runtime_plan.json`, `summary.json`, and gate metrics.
   - [ ] Add CLI/profile overrides only if needed for experiments.
2. Runtime observation loop:
   - [x] Add a preflight readiness monitor that samples existing ROS status/probe/artifact evidence before mission body proceeds.
   - [x] Record a readiness timeline with per-check deltas: serial bytes/frames, range input count, range samples, height samples, ExternalNav height state.
   - [x] Make the monitor produce `audits/startup_readiness_runtime.json` and `audits/startup_readiness_probe.json`.
3. Restart integration:
   - [x] Identify which runtime specs are restartable leaf services and annotate them explicitly: `gazebo_sensor`, `height_estimator`.
   - [x] Implement bounded pre-arm restart action for stuck rangefinder/height leaf services; covered by fake-runtime tests, disabled in default live policy by `restart_limit=0`.
   - [x] Write restart attempt count, restartable service names, timeline evidence, and final decision to artifact.
4. Python mission boundary:
   - [x] Pass resolved readiness parameters into generated Python runtime config if the mission FSM needs them.
   - [x] Python mission must not hide restart/fail-fast reasons; if monitor blocks before mission starts, Go writes a minimal `mission_summary.json` with `startup_readiness_failed` and the runtime reason.
   - [x] Real workflow remains fail-closed and operator-confirm gated; sim proceeds only after startup readiness monitor returns `startup_readiness_ready`.
5. Gate/cohort integration:
   - [x] Gate metrics should merge Phase 52 runtime decision with Phase 51 post-run classification.
   - [x] Cohort reports show startup policy outcome counts from `audits/startup_readiness_runtime.json`.
   - [x] Valid hover body percentile counts still exclude startup-invalid runs.
6. Tests:
   - [x] Go tests for wait-longer when evidence deltas are increasing.
   - [x] Go tests for fail-fast when serial/range/height evidence stays at zero.
   - [x] Go tests that restart is forbidden after armed/airborne/hover_hold.
   - [x] Go/Python artifact tests proving readiness policy parameters and runtime decision artifacts are written.
   - [x] Gate/cohort tests proving startup-invalid runs remain excluded from hover span percentiles and startup policy outcomes are counted.
7. Usage pass:
   - [x] Run a normal hover and prove Phase 52 does not slow or break the already-green path.
   - [x] Simulate stuck rangefinder/height startup in fake-runtime tests and prove the artifact says whether it waited, failed fast, or restarted.

Acceptance:

- [x] A stuck startup no longer looks like a mysterious hover failure; artifact records an explicit runtime decision.
- [x] No-progress startup can fail faster than the old blind wait path.
- [x] Progressing startup can wait longer without being misclassified as hover instability.
- [x] Pre-arm bounded restart is recorded and never happens after armed/airborne/hover_hold.
- [x] Phase 51 `startup_readiness` classification and Phase 49 cohort filtering remain intact.


Execution slice 1 (2026-06-25):

- [x] Added Go `startup_readiness_policy` config/default/validation with `timeout_sec=35`, `grace_sec=8`, `progress_window_sec=3`, `restart_limit=0` default.
- [x] Added Go policy decision model for `wait_longer`, `fail_fast`, `restart_leaf_services`, and post-takeoff `fail_closed` boundaries.
- [x] Echoed resolved policy into generated hover runtime artifacts, dry-run output, `task_plan.json`, `runtime_plan.json`, `summary.json`, `run_config.toml`, and `gate_evaluation.metrics.startup_readiness.runtime_policy`.
- [x] Added tests for progress-based wait, no-progress fail-fast, bounded pre-arm restart eligibility, and armed/airborne/hover-hold restart prohibition.
- [x] Dry-run usage pass `20260625T060539Z` shows `startup_readiness_policy=timeout=35.0s grace=8.0s progress_window=3.0s restart_limit=0`; `runtime_plan.json`, `task_plan.json`, and generated `hover_mission_runtime.py` echo the policy.
- [x] Verification: `cd orchestration/sim && go test ./...` passed.
- [x] Verification: `./scripts/quality/check-go.sh` passed.
- [x] Runtime observation loop is wired before `hover_mission`; bounded restart execution is implemented for restartable leaf services but default live config keeps `restart_limit=0`.


Execution slice 2 (2026-06-25):

- [x] Added generated `probes/startup_readiness_probe.py` and runtime monitor that runs before `hover_mission` starts.
- [x] Monitor writes `audits/startup_readiness_probe.json` plus `audits/startup_readiness_runtime.json` with timeline, final decision, restartable services, and restart attempts.
- [x] `runtime_plan.json` now records `startupReadinessProbe` and `restartable=true` on `gazebo_sensor` / `height_estimator`.
- [x] If startup readiness blocks before mission starts, Go writes `mission_summary.json` with `reason=startup_readiness_failed` and the policy reason code.
- [x] Gate metrics merge `runtime_decision` and `runtime_artifact`; cohort metrics count startup readiness policy outcomes.
- [x] Real hover usage pass `20260625T064715Z` completed `TASK_STATUS_OK`; startup monitor decision was `proceed/startup_readiness_ready`, `probe_ok=true`, `rangefinder_ready=true`, `height_estimate_ok=true`, `restart_attempts=0`.
- [x] Verification: `cd orchestration/sim && go test ./...` passed after wiring the monitor.

Non-goals:

- [ ] Do not tune hover `target` / `hard_cap`.
- [ ] Do not relax post-takeoff safety blockers.
- [ ] Do not restart FCU/SITL/mission body after takeoff.
- [ ] Do not introduce direct Go/Python library coupling.
- [ ] Do not add SQLite to runtime control.


### Phase 53 [mainline-entrypoint]: make default hover run the Phase 41/42 profile

Status: completed.

目标：让 `just navlab-run hover` 默认跑当前主线，而不是旧 `ideal` profile。Phase 41/42 之后，主线验证路径已经是 direct `/slam/odom` + `slam-direct-no-odom-prior`；继续把默认入口留在 `ideal` 会制造“跑了 hover 但不是主线”的假证据。

Changes:

- [x] `orchestration/sim/configs/tasks/hover.yaml` default `simulation_profile` 改为 `slam-direct-no-odom-prior`。
- [x] `ideal` 不删除，但降级为显式 debug/legacy profile：需要时用 `--simulation-profile ideal` 手动覆盖。
- [x] `hover-slam-only` 暂不跟随修改，避免把非主线诊断 task 也一起 break。
- [x] `hover_span_target_m=0.1` / `hover_span_hard_cap_m=0.15` 继续由 Go runtime config 和 CLI override 管理，不写进 justfile。
- [x] 测试覆盖默认 hover task config 和默认 runtime artifact：`slam_runtime.toml` 使用 `/slam/odom` 与 `navlab_cartographer_2d_hover_no_odom_prior.lua`。

Acceptance:

- [x] `just navlab-run hover --dry-run` resolved profile 应显示 `slam-direct-no-odom-prior`。
- [x] 显式 override 仍可用：`just navlab-run hover --simulation-profile ideal`。
- [x] 后续 cohort / usage pass 默认命令和 Phase 41/42 canonical command 对齐。


### Phase 54 [profile-registry]: replace simulation profile magic strings with a Go registry

Status: completed.

目标：把 `slam-direct-no-odom-prior`、`slam-direct`、`ideal`、`realistic` 这类 simulation profile 从散落字符串和 `ApplySimulationProfile` if/else，收敛成 Go 统一 profile registry。Phase 53 已经把默认 hover 入口切到主线，但旧实现仍然依赖魔法字符串；Phase 54 让 profile 成为可枚举、可验证、可 artifact 回放的 Go-owned contract。

Problem:

- [x] 删除单数 `orchestration/sim/internal/tasks/simulation_profile.go`；profile registry、profile apply、allowed-profile error 都集中在 `orchestration/sim/internal/tasks/simulation_profiles.go`。
- [x] hover profile 的语义集中声明：`/slam/odom` input、no-odom-prior Cartographer config、legacy selector route 由 registry entry 表达。
- [x] scan-robustness 的 disturbance profile validation 仍从 config profile set 来，但错误报告复用同一个 allowed-profile helper。
- [x] CLI/YAML 传错 hover profile 时会 fail fast，并列出 allowed profiles。

Design:

- [x] 新增 Go-owned simulation profile registry：`orchestration/sim/internal/tasks/simulation_profiles.go`。
- [x] 定义 profile 常量：
  - [x] `ProfileIdeal = "ideal"`
  - [x] `ProfileRealistic = "realistic"`
  - [x] `ProfileSlamDirect = "slam-direct"`
  - [x] `ProfileSlamDirectNoOdomPrior = "slam-direct-no-odom-prior"`
- [x] 为 hover profile 定义结构化 effect，而不是在 if/else 里手写：
  - [x] `ExternalNavInputOdomMode`: default selector candidate vs direct SLAM odom。
  - [x] `CartographerConfigBasename`: default hover config vs no-odom-prior config。
  - [x] `Purpose`: mainline / legacy-debug / diagnostic。
  - [x] `AllowTasks`: `hover`、`hover-slam-only`。
- [x] `ApplySimulationProfile` 改成 registry lookup + effect apply；未知 hover profile fail fast，并在 error 中列出 allowed profile names。
- [x] `runtime_plan.json` 记录 resolved `simulationProfile` metadata/effects，方便 artifact review；`task_plan.json` / `summary.json` 继续记录 resolved `simulation_profile`。
- [x] 默认 YAML 仍然只写 profile name，不把 route/config 细节复制进 task YAML。

Implementation tasks:

1. Registry model:
   - [x] Add `HoverSimulationProfile` structs and profile constants.
   - [x] Add `HoverSimulationProfiles()` returning a deterministic list.
   - [x] Add helper `AllowedProfilesForTask(taskID string) []string` for CLI/error/test use.
2. Apply path:
   - [x] Replace hover-specific string if/else in `ApplySimulationProfile` with registry lookup.
   - [x] Keep scan-robustness behavior intact and route profile errors through the shared allowed-profile helper.
   - [x] Preserve `ideal` as a legacy/debug profile for hover so explicit override remains valid.
3. Artifact/reporting:
   - [x] Echo profile purpose/effects into `runtime_plan.json` as `simulationProfile`.
   - [x] Ensure generated `slam_runtime.toml` remains the source of truth for actual topic/config values.
4. Tests:
   - [x] Unit test registry lists hover profiles deterministically and marks `slam-direct-no-odom-prior` as mainline.
   - [x] Unit test `ApplySimulationProfile` uses registry effects for `slam-direct` and `slam-direct-no-odom-prior`.
   - [x] Unit test unknown hover profile fails with allowed names.
   - [x] Keep Phase 53 default dry-run behavior: default `just navlab-run hover --dry-run` resolves to `slam-direct-no-odom-prior`.
5. Usage pass:
   - [x] `cd orchestration/sim && go test ./internal/tasks ./internal/config`
   - [x] `just navlab-run hover --dry-run`
   - [x] `just navlab-run hover --simulation-profile ideal --dry-run`

Acceptance:

- [x] No hover route profile behavior depends on raw string comparisons outside the registry.
- [x] Adding a new hover profile requires one registry entry plus tests, not editing scattered if/else logic.
- [x] Unknown profile errors are explicit and list valid choices.
- [x] Default mainline remains `slam-direct-no-odom-prior`; `ideal` remains available only as explicit override.
- [x] Go/Python boundary remains unchanged: Go resolves profile into generated files/artifacts; Python does not own profile policy.

Non-goals:

- [x] Do not change hover SLO thresholds.
- [x] Do not change the runtime route selected by Phase 53.
- [x] Do not move profile policy into Python.
- [x] Do not introduce compatibility shims for old artifacts.

Execution log (2026-06-25 Phase 54):

- [x] Added `simulation_profiles.go` registry with deterministic hover profiles and `AllowedProfilesForTask`.
- [x] Replaced hover route string branches in `ApplySimulationProfile` with registry lookup and structured effect application.
- [x] Added shared invalid-profile error helper for hover and scan-robustness profile validation.
- [x] Added `runtime_plan.json.simulationProfile` metadata for profile purpose/effects.
- [x] Removed the singular `simulation_profile.go` / `simulation_profile_test.go` split so registry and resolution live under `simulation_profiles*`.
- [x] Verified default dry-run `20260625T080749Z` resolves to `slam-direct-no-odom-prior`; explicit `ideal` dry-run `20260625T080803Z` remains available.


### Phase 55 [runtime-deadline]: make duration_sec a Go-owned task deadline

Status: completed.

目标：把 `duration_sec` 明确为 task runtime deadline，而不是固定 rosbag 录制时长。FSM/probe 正常 terminal 后只保留 5s rosbag grace；如果 deadline 到了仍没有 terminal evidence，Go runtime runner 必须 fail closed、停止 runtime，并写出可审计 timeout evidence。

Design:

- [x] `plan.DurationSec` 传入 Go runtime runner as `TaskDeadlineSec`。
- [x] live runner 使用 `RosbagPostTaskGraceSec=5s`：probe/FSM 完成后等待短尾 telemetry，然后 stop rosbag/services。
- [x] probe/FSM 未在 deadline 内完成时，runner 返回 `task_runtime_timeout` error。
- [x] timeout path emits runtime event `run.timeout` with deadline/stage payload。
- [x] timeout path stops rosbag and services instead of waiting for rosbag's own duration timeout。
- [x] 如果 `mission_summary.json` 缺失，Go 写最小 fail-closed summary with `reason=task_runtime_timeout`。
- [x] 如果 Python 已写 `duration_timeout` mission summary，Go 不覆盖；gate 保持 timeout failure。

Tests:

- [x] `TestExecuteRuntimeSpecsStopsRosbagAfterPostTaskGrace`: probe/FSM 完成早于 deadline -> grace stop，不 wait rosbag full duration。
- [x] `TestExecuteRuntimeSpecsTimesOutWhenProbeDoesNotFinishBeforeDeadline`: probe/FSM 一直不完成 -> deadline timeout error, `run.timeout`, cleanup, minimal mission summary。
- [x] `TestTaskRuntimeTimeoutSummaryDoesNotOverwritePythonDurationTimeout`: Python `duration_timeout` summary is preserved and gate blockers stay failed。

Acceptance:

- [x] 90s is an upper bound for task completion, not a fixed successful-run length。
- [x] successful hover can finish around FSM completion + 5s grace。
- [x] hung FSM/probe cannot make Go wait indefinitely or silently look green。
- [x] Go/Python boundary stays file/artifact based: Python writes mission summary if it reaches timeout; Go writes a minimal timeout summary only when missing。


## 已删除的旁路记录

以下旁路内容已从主线删除，不再作为后续执行入口：

- 新增的最小运动 task。
- exploration runtime 的运动合同分支。
- controller bootstrap / rearm / local target streaming 调试线。
- 与主线 hover artifact 不直接相关的长篇实验记录和分布阈值讨论。

保留原则：后续只围绕 hover 主线 artifact 的多源位移不一致做审计；任何新修改必须先证明它阻塞真实 ExternalNav/SLAM/FCU 安全链路。

## 验证计划

最小验证：

```bash
uv run pytest navlab/tests/companion/test_external_nav_source_selector.py -q
uv run pytest navlab/tests/companion/test_mission_hover_evidence.py navlab/tests/companion/test_hover_mission.py -q
```

扩展验证：

```bash
uv run pytest navlab/tests/companion -q
go test ./orchestration/sim/internal/tasks/...
just check-python
```

真实 usage pass：

```bash
just navlab-run hover
```

真实 run 验收：

- [ ] 至少连续 3-5 轮 hover。
- [ ] 每轮顶层没有 hard blocker；target exceed 可以是 yellow/warning，但不能超过 hard cap。
- [ ] 每轮 `mission_summary.ok=true`、landing PASS。
- [ ] 每轮 FCU local / SLAM corrected / external_nav drift 与 span 应记录 target/hard_cap tier；`<0.1m` 是 target，`>0.15m` 是 hard fail。
- [ ] Gazebo drift/span 在 Gazebo contract 闭环前只作为 review-only evidence，不单独 hard block。
- [ ] 每轮没有 hover-window `pose_or_yaw_jump`。
- [ ] 每轮没有把 Gazebo truth / known map / direct pose cheat 用作 runtime input。

## 预期中间状态

改完 fail-closed 后，系统可能先从：

```text
mission ok but top-level gate blocked
```

变成：

```text
selector rejected candidate
source_selector.ready=false
mission aborts safely to landing
summary names reject reason
```

这是可以接受的中间状态。只有当 Cartographer / scan-reference 后续 tuning 能连续不触发 reject，才应追求顶层 hover `TASK_STATUS_OK`。
