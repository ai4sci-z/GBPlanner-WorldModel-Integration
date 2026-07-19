# WP304 E0 · OPEN-1 离线证据提取器、协议解码器与观测 schema 草案(不启动仿真)

> 本目录 = WP304 **E0 收口**交付:**离线证据提取器 + MAVLink 协议解码器(校验 CRC)+ 观测 schema 草案**
> + 环境无关 fixture。**运行时埋点尚未实现**(§4 缺口),**不得称"运行时埋点已完成"**。
> 未启动任何仿真/容器/负载工具。方案总纲见
> [../../../../governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md](../../../../governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md)。
> 状态权威 = [../../../../CURRENT_STATUS.md](../../../../CURRENT_STATUS.md)。

## 1. 纯观测证明(埋点不改被测系统)

`open1_tlog.py` / `open1_extract.py` 全**只读**:`open(path,"rb").read()` + `os.listdir/getsize`,
不写任何 run 产物、不发信号、不起进程、不碰控制/调度/ArduPilot 参数/仿真时序。
测试核心断言用**内存合成**数据;真实回放仅**读** world-model 历史产物(在盘则断言,不在则 SKIP/UNVERIFIED)。

## 2. 自包含 MAVLink 协议解码器(校验 CRC)

不用 pymavlink(OPEN-2 栽在该环境债)。手写最小 v1/v2 帧解析:
- **X25 CRC 校验**(STATUSTEXT crc_extra=83);真实 tlog 全量 STATUSTEXT `bad_crc=0` 自证(见 G1 回放段)。
- 帧长/签名帧(incompat&0x01,+13B)/结构检查;CRC 或结构失败 → 结构化 invalid 计数,不静默吞。
- STATUSTEXT 文本只取固定字段 `payload[1:51]`;v2 扩展 `id!=0`(分块长消息)→ **fail-closed 标 unsupported_chunk,不拼入文本**(不做重组)。
- 诚实边界:只对已知 crc_extra 的 msgid(此处 STATUSTEXT=253)做 CRC 校验;其它 msgid 按 len 前进并标 `frames_unchecked`(不冒充已校验)。

## 3. E0 提取结果(CRC 校验协议解析;已作 fixture 断言固化)

默认主线五 run,`Arm: Accels inconsistent`(CRC 校验后)与结局:

| run | 结局 | BIN | accel(CRC 校验) | STATUSTEXT 总数 | airborne(正证据) |
|---|---|---|---|---|---|
| 204428 | ✅ full-pass | Y | 20 | 170 | True |
| 211927 | ✅ full-pass | Y | 20 | 170 | True |
| 210849 | ❌ 未起飞 | Y | 20 | 134 | False |
| 205113 | ❌ 未起飞 | n | 0 | 108 | False |
| 210149 | ❌ 未起飞 | n | 0 | 108 | False |

允许保留的最强事实(逐条绑证据):
- accel 文本计数在成功与 BIN-present 失败间**均为 20**、两次 no-BIN 为 **0** → 该文本**不是成败判别器**。
- `airborne` 取自 `mission_summary.airborne_seen` **正证据**(True/False;缺失→UNKNOWN)。
- `ArduPilot Ready`/`EKF origin set` 只记 **marker 文本出现**,**不升级为"完整 boot 已完成"**。
- **UNKNOWN(不下结论)**:arm 请求/ack/拒绝时序、no-BIN 直接死因、两类是否同源 → `arm_status=UNKNOWN`。
- `canonical_config_hash`(解析 TOML→去易变字段→稳定序列化):五默认主线 run 折叠为 1(fixture 断言)。

## 4. per_attempt schema:已实现(离线可提取)vs 尚未实现(需运行时埋点)

**已实现(`open1_extract.py` 输出)**:`freeze_ref{simulation_profile, control_mode, canonical_config_hash, created_at}`、
`input_hashes{run_config/summary/mission_summary/tlog sha256}`、
**`evidence_quality`(九输入独立质量:PRESENT_VALID/MISSING/EMPTY/MALFORMED/READ_ERROR/UNSUPPORTED/
UNSUPPORTED_SCHEMA/PRESENT_NO_MATCH;tlog 质量经协议解析判定,垃圾文件≠PRESENT_VALID;
**逐输入 schema 契约**:manifest 需 run_id/created_at/artifacts、summary 需已知 status+ok+blockers、
mission `airborne_seen` 若在必须 bool、probes `ok` 若在必须 bool、run_config 需 inputs.simulation_profile/control_mode——
合法 JSON 但 schema 不符 → UNSUPPORTED_SCHEMA,计入 CORRUPT 类,acceptance_eligible=False)**、
**`evidence_errors` + `evidence_gate{required_inputs, failed_inputs, optional_gaps, reasons, status∈COMPLETE/INCOMPLETE/CORRUPT}`**、
`outcome{bin_present, tlog_bytes, reported_task_status, reported_task_ok, evidence_complete,
**acceptance_eligible(=业务主张∧证据门,R003 验收唯一依据)**, airborne(controller 侧结构化), mission_blockers, abort_reason}`、
`fcu_statustext{…}`、`arm_status=UNKNOWN`、`ros2_sampled{仅采样点}`。
⚠️ **兼容字段 `full_pass` 只表示历史 summary 主张(=reported_task_ok),不代表证据完整,不得作为 R003 gate**。

**尚未实现(需 world-model 运行时埋点,登记为 `evidence_gaps`,E1 前须申请扩权,不静默改)**:
宿主负载时序;SITL stdout/stderr + 退出码/生命周期(no-BIN 死因关键);heartbeat/dataflash 时刻;
连续 external-nav/readiness 序列;arm request/ack/reject 时序 + EKF/INS 连续残差;companion digest。

## 4b. 独立标注工具(open1_annotate.py):冻结验收门 + 溯源实绑

- `verify` = **冻结验收门(fail-closed)**:行集必须恰等于冻结五 run,且
  RAN=5 / PASS=5 / FAIL=0 / SKIP=0 才 rc=0;全 SKIP、部分 SKIP、行缺/行多均非零。
- `replay` = 观测性回放(非验收门),SKIP 不判失败,rc 只随 FAIL。
- **provenance 实绑**(每行核):claimed commit 必须 40-hex 且在 wm 仓 `git cat-file -t` 可解析为 commit;
  registry 源必须解析为 `EXTERNAL_REGISTRY:<仓内文件>#<节锚>`,文件存在、节存在,且 **节区域内**
  (锚到下一同级标题)同时含该 run_id、该 commit 前缀、该 profile(防前缀在他章出现的假绑定);
  run_dir 基名必须==run_id。tool/data commit 由 git 派生,脏树/不可派生 → fail-closed。

## 5. 运行

```
python3 test_open1_tlog.py       # G1 协议门:合成帧(真实 CRC)+ 真实 tlog CRC 自证
python3 test_open1_extract.py    # G2 提取语义门(合成)+ A-06 schema 反例 + G3 历史回放(5 run,绑 run_id/路径/hash)
python3 test_open1_annotate.py   # B 反例门:TSV schema 失败关闭 + 冻结门/溯源反例(全SKIP/deadbeef/伪registry 必非零)
python3 open1_annotate.py verify     # 冻结验收门(见 §4b)
python3 open1_extract.py <run_dir>   # 只读打印单 run 提取 JSON
```

## 6. 下一步(申请)

E0 已收口(离线提取器 + 协议解码器 + schema 草案 + E0-CORRECT 补正)。
E1 sidecar 实现停点已于 2026-07-19 获负责人放行并达成(见 §7):
**E1 sidecar 已编码并通过 fixture/dry-run;未执行真实仿真、A/A、pilot 或行为验收。**
下一步 = **E1 A/A 实验停点,须负责人另行放行;OFF×2 + ON×2,任何控制语义差异立即停止。**
未放行不跑 A/A/pilot/E2、不启动仿真、不改 world-model。

## 7. E1 sidecar(2026-07-19;状态词:已编码并通过 fixture/dry-run,未执行真实仿真/A/A/pilot/行为验收)

- `telemetry_contract.py` 契约层:schema/身份/D4 字段表/evidence gate/五层分母/airborne 语义。
- `telemetry_sidecar.py` 采集层:原子写(tmp→fsync→rename→dirfsync)/不可变 JSONL 段+原子 index
  (sha256/双时戳/truncated/dropped)/单 writer 互斥/崩溃恢复(不猜修)/宿主 /proc 采集
  (cpu_freq 不可读=UNAVAILABLE)/Docker 只读(容器退出码≠SITL 进程退出码=UNAVAILABLE)
  /ROS 只订不发(同 ROS_DOMAIN_ID)/容量与 CPU3%/64MB 预算(超→telemetry_overrun,不碰 producer)。
- `open1_arm_timeline.py`:tlog→telemetry/arm_timeline.json(arm request/ACK/reject/statustext;
  crc_extra 50/152/143 经真 tlog 自证+判别性反证;无可靠时戳→UNKNOWN)。
- 入口:`batch_lifecycle.py` `WP303_TELEMETRY=on|off`(默认 off=零变化;on 由 launcher 启停,
  batch_id/run 根贯通,run_id 读 producer run 记录;telemetry_status 与 producer rc 分录)。

```
python3 test_telemetry_contract.py    # 契约反例门(红案1-10/24/25+gate+五层)
python3 test_telemetry_sidecar.py     # 存储/采集/只读适配/容量反例门(红案11-19/22/23)
python3 test_open1_arm_timeline.py    # 合成固定向量 + 五 run 真 tlog 自证回放
python3 test_telemetry_entry.py       # WP303 正式入口 20 案 dry-run(红案20/21)
```

## 7b. E1-CORRECT(2026-07-19):可执行 sidecar 闭合

状态词:E1 sidecar 具备项目内可执行 CLI,并通过 fixture backend 的真实主循环、run-id 握手、
进程级互斥/恢复和正式证据门 dry-run;真实 Docker/ROS、A/A 和行为验收未执行。

- `telemetry_sidecar.py` = 正式 CLI(`--backend real|fixture`,real 本轮禁用);
- `run_registry.py` = run 身份注册表 + `aggregate` 五层分母正式聚合入口;
- writer 互斥 = 内核 flock;恢复 = 死后显式 recover(CORRUPT 拒写);
- WP303 on 默认命令 = 版本库内 sidecar(task record 存全量 argv;覆盖=fixture/test only);
- monitor 三态:process_state / evidence_state(来自产物)/ finalization_state。

```
python3 test_run_registry.py     # 12 案:唯一新增/零/双/mtime/symlink/半写/重复
python3 test_writer_mutex.py     # 9 案进程级:并发拒/TERM/SIGKILL 恢复/损坏 index 拒写
python3 test_telemetry_cli.py    # CLI 反例 + fixture 真主循环 + required 闭包 + 五层聚合
python3 test_telemetry_entry.py  # 入口 20 案:默认 CLI/三态/三身份全等/off 零变化
```

## 7c. E1L(2026-07-19):运行期旁路链闭合

状态词:E1 sidecar 已形成运行期状态机:在 fixture 子进程仍存活时完成真实 run-id 握手、
连续采集、周期封存和正式 evidence/five-layer dry-run;real Docker/ROS 仅编码及 recording
fixture,A/A 和真实行为验收未执行。

- `run_registry.py watch` = 并发 watcher(producer 存活期 resolve;8 终态);
- `--once` = 完整处理一个 attempt;多 run = `--expected-runs N`(WP303 默认命令);
- 状态机 WAIT_IDENTITY→ACTIVE(连续+周期封存)→FINISHING;采集器独立线程互不阻塞;
- concrete ROS adapter 已编码并过 recording-node fixture(真实 ROS 图未验);
- 事后派生一律标 `post_run_derived`。

```
python3 test_telemetry_runtime.py   # R1-R15+watcher 终态+SIGKILL 恢复+全时序 dry-run(58P)
python3 test_ros_adapter.py         # concrete 只订不发结构门(12P)
```
