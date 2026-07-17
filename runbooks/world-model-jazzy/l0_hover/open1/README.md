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
**`evidence_quality`(九输入独立质量:PRESENT_VALID/MISSING/EMPTY/MALFORMED/READ_ERROR/UNSUPPORTED/PRESENT_NO_MATCH;
tlog 质量经协议解析判定,垃圾文件≠PRESENT_VALID)**、
**`evidence_errors` + `evidence_gate{required_inputs, failed_inputs, optional_gaps, reasons, status∈COMPLETE/INCOMPLETE/CORRUPT}`**、
`outcome{bin_present, tlog_bytes, reported_task_status, reported_task_ok, evidence_complete,
**acceptance_eligible(=业务主张∧证据门,R003 验收唯一依据)**, airborne(controller 侧结构化), mission_blockers, abort_reason}`、
`fcu_statustext{…}`、`arm_status=UNKNOWN`、`ros2_sampled{仅采样点}`。
⚠️ **兼容字段 `full_pass` 只表示历史 summary 主张(=reported_task_ok),不代表证据完整,不得作为 R003 gate**。

**尚未实现(需 world-model 运行时埋点,登记为 `evidence_gaps`,E1 前须申请扩权,不静默改)**:
宿主负载时序;SITL stdout/stderr + 退出码/生命周期(no-BIN 死因关键);heartbeat/dataflash 时刻;
连续 external-nav/readiness 序列;arm request/ack/reject 时序 + EKF/INS 连续残差;companion digest。

## 5. 运行

```
python3 test_open1_tlog.py       # G1 协议门:合成帧(真实 CRC)+ 真实 tlog CRC 自证
python3 test_open1_extract.py    # G2 提取语义门(合成)+ G3 历史回放(5 run,绑 run_id/路径/hash)
python3 open1_extract.py <run_dir>   # 只读打印单 run 提取 JSON
```

## 6. 下一步(申请)

E0 已收口(离线提取器 + 协议解码器 + schema 草案)。**唯一申请动作 =
进入 R003-WP304-E1 最小旁路观测补丁方案停点**(只写方案,不编码、不跑仿真;
须先裁决 `eab0cc6` 独立 worktree 复现 ∣ 或 `288b486` 立新基线不合并历史统计)。
未放行不跑 E1/E2、不启动仿真、不改 world-model。
