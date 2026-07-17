# WP304 E0 · OPEN-1 埋点实现与只读提取(不启动仿真)

> 本目录 = WP304 **E0 阶段**交付:埋点 schema + 解析器 + 对既有 tlog/BIN/JSON 的**只读**提取器
> + 环境无关 fixture 测试。**未启动任何仿真/容器/负载工具**。方案总纲见
> [../../../../governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md](../../../../governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md)。
> 状态权威 = [../../../../CURRENT_STATUS.md](../../../../CURRENT_STATUS.md)。

## 1. 纯观测证明(埋点不改被测系统)

本目录三个 py 全部**只读**:

- `open1_tlog.py`:`open(path,"rb").read()` 解析字节,不写盘、不发信号、不起进程。
- `open1_extract.py`:对 run 目录只 `os.listdir/os.path.getsize/open(...,read)`,**不写任何 run 产物**,
  不碰控制/调度/ArduPilot 参数/仿真时序。
- 测试:核心断言用**内存合成**数据;真实回放仅**读** world-model 历史产物(在盘则断言,不在则跳过)。

→ 满足 E0 契约"证明埋点不改控制/调度/ArduPilot 参数/仿真时序"。**运行时**才能取的字段(§4)
一律不在此实现,登记为缺口,E1 前须单独申请扩权(改 world-model)。

## 2. 自包含 tlog STATUSTEXT 解码器(为何不用 pymavlink)

OPEN-2 候选实现栽在 pymavlink 环境依赖(节点级测试 mavlink=None 炸)。E0 手写最小
MAVLink v1/v2 帧解析(stdlib only),确定性、可复现,替代上一轮 `strings` 启发式。
限制(诚实边界):不校验 CRC(失配 i+=1 重同步)、不解析 STATUSTEXT 分块扩展。

## 3. E0 确定性结论(替换上一版启发式;已作 fixture 断言固化)

`open1_tlog` 精确解码 STATUSTEXT(msgid 253),默认主线:

| run | 结局 | BIN | `Arm: Accels inconsistent` | STATUSTEXT 总数 | boot ready |
|---|---|---|---|---|---|
| 204428 | ✅ full-pass | Y | **20** | 170 | True |
| 211927 | ✅ full-pass | Y | **20** | 170 | True |
| 210849 | ❌ 未起飞 | Y | **20** | 134 | True |
| 205113 | ❌ 未起飞 | **n** | **0** | 108 | True |
| 210149 | ❌ 未起飞 | **n** | **0** | 108 | True |

- **`Accels inconsistent` 计数在成功与 BIN-失败间恒等于 20 → 定量证伪"accel=失因"**(不是判别器,是启动瞬态)。
- **no-BIN 两次:accel=0,但 `ArduPilot Ready`/`EKF3 origin set` 均在** → 已完成 boot,却**从未进入 arm 循环**
  (成功/BIN-失败都有 ~20 次 arm 尝试触发 accel 提示;no-BIN 一次都没有)。no-BIN 根因仍 **UNKNOWN**,
  但已收窄为"**boot 完成后、arm 循环前失速**",与 BIN-失败(accel 循环未消解)是**不同签名**。
- `canonical_config_hash`:默认主线 6 run 折叠为 1、诊断臂 4 run 折叠为 1、两组不同 → 配置身份埋点成立。

## 4. per_attempt schema:已实现(事后可提取)vs 需运行时埋点(缺口)

**已实现(本目录 `open1_extract.py` 输出)**:
`freeze_ref{simulation_profile, control_mode, canonical_config_hash, created_at}`、
`outcome{bin_present, tlog_bytes, status, full_pass, airborne, mission_blockers, abort_reason}`、
`fcu_statustext{total, window_sec, accels_inconsistent_count, boot_markers, distinct_texts}`、
`ros2_sampled{startup_readiness_ok, imu_probe_ok}(仅采样点)`。

**需 world-model 运行时埋点(E0 只登记为 `evidence_gaps`,E1 前须申请扩权,不得静默改)**:
- `host{loadavg/cpu/freq/mem/io}` 时序(H1 负载相关性的唯一证据来源);
- SITL 控制台/进程退出码(**no-BIN 死因关键**);
- `fcu.ekf_status_report[]` / `ins_accel_residual[]` 时序(accel "消解 vs 未消解"分界);
- `fcu.arm_request[]` / `arm_reject_reason[]` 时刻(H3 时序竞态);
- `freeze_ref.companion_digest`(历史未捕获)。

## 5. 运行

```
python3 test_open1_tlog.py       # 解码器环境无关单测(合成帧)
python3 test_open1_extract.py    # 提取器合成断言 + 可选真实回放
python3 open1_extract.py <run_dir>   # 只读打印单 run 提取 JSON
```

## 6. 下一步(申请)

E0 已交付(埋点 schema + 解析器 + fixture)。**唯一申请动作 = 放行 E1 静默 pilot(≤3)**,
且 E1 需先决定运行时缺口(§4)如何捕获:若必须改 world-model,**先申请扩大范围**。
未经放行不跑 E1/E2、不启动仿真、不改 world-model。
