# L1/L1.5 诊断臂 bring-up 证据(2026-07-15)

> **[后续状态指针 · 2026-07-16]** 本文是 07-15 原始实验记录(只读,数值不改)。其"下一步/补跑中/根因域"
> 表述已被后续证据推进:根因定位 = B21(东轴镜像,已验证)+ B22(IMU 倒装,候选),修复与全分母统计见
> `l15_frame_audit_evidence_2026-07-16.md` §4b;当前状态见仓库根 CURRENT_STATUS.md。

> 版本:wm `9852e46`(两次 bring-up 跑)/ 正式批 = wm `57924c0`;
> companion 按各 HEAD retag(依赖未变,retag 合法);判决权威 = BIN 全窗口重放,
> 任务退出码/gate blockers 只是表象(诊断跑 gate 必然报 truth/SLAM blockers,属设计)。

## 1. 实装与放行(全部已 commit)

- 三诊断 profile:`gps-ekf-services`(L1)/`truth-external-nav`(L1.5)/`imu-flu-correction`(L2-fix)
  (wm `ff919fb`);放行门 wm `13a3979`(doctor `hover_profile_runnable` + 审计 acknowledged,
  诊断跑带 purpose 烙印,gate-evaluate 不放水 → 不可能冒充验收绿)。
- bring-up 修的两个真接线坑:
  1. **任务 FSM 卡 S1**:`waiting_for_fcu_external_nav`——L1 设计上 FCU 不融合 external-nav
     (VISO_TYPE=0),该等待永不满足 → 35s preflight_timeout,一次解锁都不发生。
     修 = gps-baseline profile 下 `require_external_nav=false`(wm `9852e46`)。
  2. **RTF 崩塌 × 90s 默认时长**:全服务栈下实测 RTF≈0.08(L0 零服务时 0.33);90s 墙钟 ≈ 7 仿真秒,
     GPS EKF 解锁点在 ~13 仿真秒(prearm:Accels inconsistent 至 ~12.5s + GPS 配置至 ~9.3s)——
     必然砍死在解锁前。修 = 批预算 `--duration-sec 1500`。
- 坑(留档):900s 跑被 SIGKILL 时 `mission_summary.json` 不落盘;`l0_bin_verdict.py` 对多次
  解锁窗口只计首窗(163311 报 armed 9.97s 实为第三窗 35.4s)——L1 批判决用全窗口重放,勿直接套 L0 脚本。

## 2. bring-up 两跑(L1 = 全服务栈 + 官方 GPS EKF)

| run | 解锁 | armed 连续时长(仿真 s) | 起飞 | roll/pitch 峰(°) | crash |
|---|---|---|---|---|---|
| 20260715T163311(600s 墙钟) | 3 次(前两窗无起飞,10s DISARM_DELAY 自动上锁) | 第三窗 **35.4+**(至日志尾) | EV15@34.4/EV28@37.1 | **0.3 / 0.0** | 无 |
| 20260715T164553(900s 墙钟) | 1 次@13.2s,零上锁循环 | **55.8+**(至日志尾,airborne ~53s,alt 0.45m) | EV15@13.7/EV28@16.4 | **0.3 / 0.0** | 无 |

对照:L2(同服务栈,唯一差异 = EKF 吃 external-nav)armed 14-18 仿真秒即翻(roll 122-142°)。

## 3. 状态词(纪律)

- **OBSERVED(强信号,尚非结论)**:全服务在场 + GPS EKF,两跑均稳定飞穿 L2 翻机窗
  (35.4s / 55.8s armed vs L2 的 14-18s),姿态与 L0 同量级(≤0.4°)。
- **受伤假设**:"服务在场负载/DDS 导致失稳"——服务全在,机稳如 L0。
- **仍 OPEN**:链内根因二选一(喂入内容/时序 ∣ EK3 融合参数);待正式批
  (L1×3 + L1.5×3,`l1_bisect_batch.sh`,DURATION_SEC=1500)反事实 ≥3 次后才准升级状态词。
- **[07-16 更新]** 正式批 L1×3 已完成并判决(见 §4.2):L1 臂 CONFIRMED 稳,
  "服务在场负载/DDS"假设正式击毙;L1.5×3 由 `l15_batch.sh` 补跑中,结果见 §4.4。
- 注意:两跑因墙钟截断未完成降落相,不构成 GATE-4b 语义的"60s 悬停 PASS";
  它们只回答"翻/不翻"这个二分问题。

## 4. 正式批

- 启动:2026-07-15,`DURATION_SEC=1500 bash l1_bisect_batch.sh`(L1×3 → L1.5×3,串行)。
- 判决方法:对每 run `sitl/logs/*.BIN` 全窗口重放(ARM/EV/ATT/MSG),工具
  `l1_bin_full_window.py`(全窗口,修掉 l0_bin_verdict.py 只计首窗的坑);
  指标 = armed 连续时长 / roll/pitch 峰 / crash;与 L0(6/6 稳)和 L2(5/5 翻)同尺对照。

### 4.1 批次沿革(三次启动,UTC)

1. `l1_bisect_batch_20260715T155249Z`(wm `ff919fb`):6 跑全被 doctor/audit 挡在
   runtime 前(放行门尚未实装)——无 BIN,不计入。
2. `l1_bisect_batch_20260715T160342Z`(wm `13a3979`):`--duration-sec` 尚未加,
   90s 默认预算在解锁前砍跑(`task_runtime_timeout during probes`)——不计入。
3. `l1_bisect_batch_20260715T185138Z`(wm `57924c0`,DURATION_SEC=1500)= **正式批**。
   L1 三跑全启动;**批进程死于 run3 期间**(推断随启动它的终端一起被杀,SIGHUP/进程组),
   run3 容器成孤儿继续飞了 ~30 min(BIN 持续落盘,已快照存证),**L1.5×3 从未启动**
   → 由 `l15_batch.sh` 于 2026-07-15T19:16Z 补跑(setsid 脱离会话,同锁防重入)。

### 4.2 L1 臂正式批判决(BIN 全窗口重放,3/3 稳)

| run(artifacts/sim/hover/) | 解锁窗 | armed 连续(仿真 s) | roll/pitch 峰(°) | crash |
|---|---|---|---|---|
| 20260715T185138 | 窗1 9.9s 未起飞自动上锁;窗2 起飞(EV15@30.8/EV28@31.6) | **45.6+**(截断) | 0.4 / 0.0 | 无 |
| 20260715T185547 | 1 窗,EV15@13.7/EV28@16.5 | **56.0+**(截断) | 0.3 / 0.0 | 无 |
| 20260715T185957 | 1 窗,EV15@13.7/EV28@16.5 | **269.0+**(孤儿跑加长观测) | 0.4 / 0.1 | 无 |

- run3 判决用定稿 BIN(手动 docker stop 后,log_end 282.3 仿真 s,BIN 在该 run
  `sitl/logs/00000001.BIN` 持久保存);该 run 无 summary.json(批进程死亡,gate 从未评估)。
- 所有"截断"= 截断于 log 尾(见 §4.3 的 runner 收尾机制),非翻机、非 disarm。
- **结论(CONFIRMED,反事实 3 次正式批 + 2 次 bring-up = 5/5 稳)**:全服务栈在场 +
  官方 GPS EKF,armed 45.6~269.0 仿真 s 无一翻机,姿态峰值与 L0 同量级(≤0.4°),
  干净飞穿 L2 的 14-18s 翻机窗 15 倍余量。**"服务在场负载/DDS 导致失稳"假设正式击毙。**
  链内根因收窄到 external-nav 喂入路径二选一:喂入内容(SLAM 质量)∣ 喂入机制/时序/EK3 融合参数。
  判决臂 = L1.5(truth-external-nav):稳 → SLAM 内容;翻 → 机制/时序/参数。

### 4.3 正式批暴露的平台问题(记台账,GATE-4b 本体的真 blocker)

- **runner 不等 mission**(`runtime_runner.go`:起服务→跑 probes→probes 完即 rosbag
  grace→finalize→cleanup SIGKILL 全部服务):RTF 崩塌下 probes ~130s 墙钟就完,
  mission 才飞到 hover_settle(仿真 ~36s)即被杀 → `mission_summary` 永不落盘、
  `/navlab/landing/status` 零消息 → `hover_mission_summary_missing`/`landing_not_evaluated`/
  `rosbag_required_topics_missing` 三 blocker 全是这一刀的下游表象。`--duration-sec`
  只是 deadline 上限,不决定运行时长。**对二分判决无伤(窗口远超翻机窗),
  但 GATE-4b 本体(60s 悬停+降落+summary 5/5)必须先修**:runner 需等 mission 退出
  (或 landing/status 出现)再收尾。
- 孤儿 run3 顺带观测:mission 在 armed 269 仿真 s 时仍未进入降落(容器活、无人杀)——
  RTF 崩塌下 mission 自身的相位推进也可能有墙钟/仿真钟混用问题,待 GATE-4b 修 runner 时一并核。

### 4.4 L1.5 臂正式批判决(`l15_batch.sh`,2026-07-15T19:16-19:28Z,wm `57924c0`,3/3 翻)

| run(artifacts/sim/hover/) | armed 连续(仿真 s) | roll/pitch 峰(°) | crash |
|---|---|---|---|
| 20260715T191629 | **29.9**(43.0s CrashCheck 上锁) | **179.5** / 82.9 | `AngErr=149>30` |
| 20260715T192023 | **29.7**(42.7s CrashCheck 上锁) | **180.0** / 63.0 | `AngErr=152>30` |
| 20260715T192423 | **21.9**(35.4s CrashCheck 上锁) | 38.9 / **83.0** | `AngErr=50>30` |

- 三跑均正常解锁(~13s)+ 起飞完成(EV28),起飞后 ~15-20 仿真 s 内姿态发散到 CrashCheck
  强制上锁;run1/run2 逐秒级复刻(armed 29.9 vs 29.7,crash 43.0 vs 42.7)——**确定性失稳,非随机**。
- 任务退出码均 rc=1 status=blocked(诊断跑设计内表象,判决只认 BIN)。

### 4.5 二分矩阵终局(GATE-4b 链内根因,CONFIRMED)

| 臂 | 配置 | 结果 |
|---|---|---|
| L0 | GPS 定位,零 SLAM 服务 | 6/6 稳 |
| L1 | 全服务在场 + 官方 GPS EKF | **5/5 稳**(正式批 3 + bring-up 2) |
| L1.5 | 全服务在场 + **origin 归一化 Gazebo 真值**喂 external-nav | **3/3 翻** |
| L2 | 全服务在场 + SLAM 喂 external-nav | 5/5 翻 |

**CONFIRMED(每臂反事实 ≥3 次)**:翻机严格跟随"external-nav 进 EK3 的喂入路径"这个
单一开关走。已排除:①服务在场负载/DDS(L1 稳);②SLAM 估计内容质量(L1.5 用完美真值照样翻,
且翻法与 L2 同族:起飞后姿态发散 → AngErr CrashCheck)。
**根因域收窄为:external-nav 喂入机制本身——嫌疑集中在 mavlink_external_nav 喂入器
(odom→VISION_POSITION_ESTIMATE 的帧约定 FLU/FRD、ENU/NED 转换与时间戳/时序)与
EK3 融合侧(EK3_SRC 组合、EK3 delay、噪声参数)。**
注意:`imu-flu-correction` 臂(修 SLAM 的 IMU 输入帧向)被本判决**降级**——L1.5 不经 SLAM
照样翻,SLAM 输入侧修正不可能是充分解;它只在"帧向错误同时存在于喂入器"的复合假设下仍有价值。
下一步(按既定矩阵):在 L1.5(最小翻机臂,真值可控)上做 EK3_SRC/delay/帧向单变量。
每假设仍须反事实 3-5 次才准写 ROOT_CAUSE。
