# NavLab Real Orchestration Rust Review

日期：2026-06-23

这份文档记录对 `orchestration/real` Rust 部分的静态 review 结果。Review
只阅读代码和配置，没有运行 `cargo test`、没有连接真机、没有跑任何 real/sim 命令。

## Review 范围

本次 review 覆盖：

- Rust CLI 入口和命令分发：
  `orchestration/real/src/cli.rs`
- real project / task 配置加载：
  `orchestration/real/src/config.rs`
- `motor-debug` task 计划、operator confirmation、summary：
  `orchestration/real/src/tasks/motor_debug.rs`
- MAVLink runtime：
  `orchestration/real/src/runtime/mavlink.rs`
- Process backend 和 prepare 启停：
  `orchestration/real/src/runtime/process.rs`
  `orchestration/real/src/workflows/prepare.rs`
- Preflight、common doctor、task doctor、doctor chain：
  `orchestration/real/src/workflows/preflight.rs`
  `orchestration/real/src/workflows/common_doctor.rs`
  `orchestration/real/src/workflows/task_doctor.rs`
  `orchestration/real/src/workflows/doctor_chain.rs`
- 当前 real 配置：
  `orchestration/real/config.toml`
  `orchestration/real/configs/tasks/motor-debug.yaml`

## 总结

当前 Rust real orchestration 已经有比较清楚的安全边界：real/sim mode 分离、
process backend、operator confirmation、doctor chain、MAVLink GUIDED/arm/disarm
路径、artifact summary 都已经有结构。

但如果目标是真机安全执行，当前还有几个必须先处理的问题：

- `motor-debug` arm 后遇到 ACK 丢失时不一定 disarm。
- preflight 对 MAVLink 链路的验证过弱，只检查串口路径存在。
- live run 可以不经过 doctor chain。
- common doctor 只看 topic 名存在，不验证 sample freshness 和关键 metadata。
- live prepare 启动服务后马上停止，并没有真正等待 readiness。
- MAVLink target system/component 固定为 `1/0`。
- `motor_percent` / `motor_count` 当前没有真正驱动 motor test。

## 发现的问题

### 1. High: `motor-debug` 发出 arm 后不一定 disarm

证据：

- `orchestration/real/src/runtime/mavlink.rs:185` 发送 arm command。
- `orchestration/real/src/runtime/mavlink.rs:187` 等待 arm ACK。
- `orchestration/real/src/runtime/mavlink.rs:207` 只有 `arm_ack.accepted == true`
  才发送 disarm。

风险：

如果 arm command 实际被飞控执行，但 `COMMAND_ACK` 丢失、延迟、被 router 丢弃或
被代码错过，`arm_ack` 会是 `None`。这种情况下代码会记录
`motor_debug_arm_ack_timeout`，但不会发送 disarm。真机可能留在 armed 状态。

建议：

- 引入 `arm_command_sent` 标志。
- 只要 arm command 发出，就在退出 runtime 前 best-effort disarm。
- disarm 后继续监听 heartbeat，确认 `base_mode` 不再 armed。
- 如果 disarm ACK 超时但 heartbeat 已显示 disarmed，可记录为安全降级成功。
- 如果既没有 disarm ACK，也没有 disarmed heartbeat，summary 必须 hard block。

### 2. High: preflight MAVLink 检查太弱

证据：

- `orchestration/real/src/workflows/preflight.rs:238` 到
  `orchestration/real/src/workflows/preflight.rs:252` 只检查：
  - `settings.enabled`
  - `settings.port` 不是 network endpoint
  - `Path::new(&settings.port).exists()`
- `orchestration/real/config.toml` 中配置了：
  - `heartbeat_timeout_sec`
  - `required_messages = ["HEARTBEAT", "SYS_STATUS", "ATTITUDE"]`
  但 Rust preflight 没有真正验证这些 MAVLink message。

风险：

只要 `/dev/ttyUSB1` 存在，preflight 就可能把 serial MAVLink 标成可用。接错设备、
baud 错、飞控没上电、权限不足、mavlink-router 独占串口等情况都可能漏过。

建议：

- preflight 至少执行一次非破坏性 MAVLink probe：
  - 打开串口或连接配置 endpoint。
  - 在 `heartbeat_timeout_sec` 内收到 `HEARTBEAT`。
  - 在窗口内收到 required messages 或给出明确 blocker。
- 如果串口被 mavlink-router 占用，应配置一个只读 network endpoint 作为 probe。
- summary 区分 `serial_path_exists`、`serial_open_ok`、`heartbeat_ok`、
  `required_messages_seen`。

### 3. High: live `run motor-debug` 可以不经过 doctor chain

证据：

- `orchestration/real/src/cli.rs:419` 只有传入 `--with-doctor-chain` 才跑
  doctor chain。
- `orchestration/real/src/cli.rs:441` 无论是否跑 doctor chain，都会进入
  `task.run(...)`。

风险：

真机 live run 只要带齐 operator confirmations，就可以绕过 preflight、prepare、
common doctor、task doctor。operator confirmations 是人工承诺，不等价于链路健康
和 source boundary 检查。

建议：

- 对非 dry-run 的 real task，默认强制 doctor chain。
- 如果确实要允许绕过，使用高摩擦参数，例如
  `--skip-doctor-chain-i-understand-risk`。
- summary 记录 doctor chain artifact path 和是否通过。
- live run 中如果没有 doctor chain evidence，应 fail closed。

### 4. High: common doctor 只看 topic 存在，不看 freshness / metadata

证据：

- `orchestration/real/src/workflows/common_doctor.rs:101` 使用
  `ros2 topic list -t`。
- `orchestration/real/src/workflows/common_doctor.rs:221` 遍历 required topics。
- `orchestration/real/src/workflows/common_doctor.rs:227` 对存在的 topic 写入空
  metadata。
- `orchestration/real/src/workflows/common_doctor.rs:229` 直接把 `fresh` 设为
  `true`。
- `orchestration/real/src/workflows/common_doctor.rs:285` 在 metadata 缺失时
  `configured_external_nav_source_set` 变成 `unknown`。
- `orchestration/real/src/workflows/common_doctor.rs:310` 只在
  `configured_external_nav_source_set == "SRC2"` 且 external nav 不 ready 时 block。

风险：

topic 名存在但没有 sample、sample stale、metadata 不包含 FCU mode/source-set/local
position/external nav readiness 时，common doctor 仍可能通过。这对真机准备阶段太松。

建议：

- 不只用 `ros2 topic list -t`，需要对关键 topic 做 bounded sample read。
- 至少验证：
  - `/navlab/mavlink/status` 有 fresh sample。
  - FCU mode / armed / local_position_valid 可解析。
  - ExternalNav source set 和 yaw readiness 可解析。
  - `/scan`、`/imu/data`、`/slam/odom` 有 freshness。
- 对 `unknown` source set 不应默认通过；真机应 fail closed。

### 5. Medium: live prepare 启动后马上停止，且不等待健康

证据：

- `orchestration/real/src/workflows/prepare.rs:151` 判断允许 live prepare。
- `orchestration/real/src/workflows/prepare.rs:152` 调用 `start_prepare_phase(...)`。
- `orchestration/real/src/workflows/prepare.rs:154` 立即 `stop_prepare_phase(...)`。
- `start_prepare_phase` 只启动 process 并记录 started services，没有按
  `startup_timeout_sec` / `health_topics` 等待 readiness。

风险：

`prepare --allow-live` 更像是“服务能 spawn”，不是“真机 runtime ready”。随后如果
doctor chain 继续运行，服务可能已被停止，topic probe 看到的是外部残留进程或空图。

建议：

- 将 prepare phase 设计成显式生命周期：
  - `prepare start`
  - health wait
  - doctor / task doctor
  - `prepare stop`
- doctor chain 内部可以 start 后保持服务，直到 common/task doctor 完成再 stop。
- standalone `prepare --allow-live` 如果只是 smoke，应在命令名或 summary 中说明
  `started_then_stopped_smoke`。

### 6. Medium: MAVLink target system/component 固定

证据：

- `orchestration/real/src/runtime/mavlink.rs:254` 到
  `orchestration/real/src/runtime/mavlink.rs:262` 固定：
  - `target_system = 1`
  - `target_component = 0`

风险：

如果 `SYSID_THISMAV` 不是 1，或者 router 上存在多个 MAVLink system，command 可能发给
错误对象或收不到 ACK。component 固定为 0 对 broadcast command 有时能工作，但 real
runtime 的 evidence 会变弱。

建议：

- 从 initial heartbeat 读取 `system_id` / `component_id`。
- command target 默认使用 heartbeat 观测到的 system/component。
- 后续 ACK / heartbeat 过滤同一个 target system。
- summary 记录 target 来源：`configured` 或 `heartbeat_observed`。

### 7. Medium: `motor_percent` / `motor_count` 当前没有实际 motor test 行为

证据：

- `orchestration/real/src/tasks/motor_debug.rs:199` 将 `plan.motor_percent` 和
  `plan.motor_sec` 放入 `MotorDebugRuntimeRequest`。
- `orchestration/real/src/runtime/mavlink.rs:202` 到
  `orchestration/real/src/runtime/mavlink.rs:204` 只设置
  `throttle_command_claim = "not_sent_armed_idle_only"` 并 sleep。
- `motor_count` 没有进入 runtime request。

风险：

CLI 和配置叫 `motor_percent` / `motor_count`，用户可能以为会按百分比转电机。但当前
行为只是 `GUIDED -> arm -> idle hold -> disarm`。这对安全是保守的，但命名容易误导。

建议：

- 如果当前任务只允许 armed idle，改名或 summary 明确写：
  `motor_test_command_claim = not_sent_armed_idle_only`。
- CLI 可以拒绝非默认 `motor_percent` / `motor_count`，避免误解。
- 如果后续要真实 motor test，应单独设计 `MAV_CMD_DO_MOTOR_TEST` 路径，并增加更强
  operator confirmation。

## 次要观察

### task doctor 对 motor-debug 的检查偏弱

证据：

- `orchestration/real/src/workflows/task_doctor.rs:164` 构造 motor-debug task doctor。
- `orchestration/real/src/workflows/task_doctor.rs:173` 到
  `orchestration/real/src/workflows/task_doctor.rs:182` 总是返回
  `ok=true`，只把 GUIDED gate 标记为 `run_stage`。

风险：

这符合“GUIDED 切换属于 run 阶段”的设计，但 task doctor 几乎没有验证 motor-debug
特有约束，例如 no-props confirmation 是否仅 run 时检查、FCU 是否 currently armed、
是否存在 RC manual takeover evidence。

建议：

- task doctor 至少 block 当前已 armed 的状态。
- 如果未来接入 RC takeover/kill switch topic，应在 task doctor 中验证它们可观测。

### dry-run tests 没有覆盖真实 cwd 假设

证据：

- `orchestration/real/src/config.rs:614` 到 `orchestration/real/src/config.rs:621`
  有配置加载测试。
- prepare command 中多处使用相对路径和 shell 环境：
  `orchestration/real/src/config.rs:384` 到
  `orchestration/real/src/config.rs:468`。

风险：

如果从 repo root 而不是 `orchestration/real` 运行，部分 command 的相对路径可能不对。

建议：

- 在 service plan 中明确 `cwd`。
- 对 `uv --project orchestration`、`source install/setup.bash` 等路径加 config-level
  normalization 或 doctor 检查。

## 建议修复顺序

1. 先修 `motor-debug` arm 后 best-effort disarm。
2. 强制 live run 默认经过 doctor chain。
3. 增强 preflight MAVLink heartbeat / required message 检查。
4. 增强 common doctor topic sample freshness 和 metadata 检查。
5. 调整 live prepare 生命周期和 readiness wait。
6. 从 heartbeat 学习 MAVLink target system/component。
7. 澄清 `motor-debug` 是 armed idle 还是实际 motor test。

## 验收建议

修复后建议至少增加这些测试：

- arm ACK timeout 但 arm command 已发送时，runtime 仍发送 disarm。
- disarm ACK timeout 但 heartbeat 显示 disarmed 时，summary 标记 safe shutdown。
- 非 dry-run `run motor-debug` 不带 doctor chain 时默认 blocked。
- preflight 在 serial path 存在但无 heartbeat 时 blocked。
- common doctor 在 required topic 存在但无 fresh sample / metadata unknown 时 blocked。
- prepare live phase 会等待 health topic 或明确报告 readiness timeout。

## 本次未验证

本次没有运行：

- `cargo test`
- `cargo run -- doctor`
- `cargo run -- doctor-chain motor-debug`
- 任何 MAVLink、ROS2、串口或真机命令

原因：本次任务目标是保存静态 review 结果，用户明确要求“不用跑”。
