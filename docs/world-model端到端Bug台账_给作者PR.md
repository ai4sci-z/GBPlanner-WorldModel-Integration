# world-model 端到端 Bug 台账（给作者的 PR 清单）

> **用途**：①你（用户）随时查我到底找出并修了哪些真 bug；②提 PR 时的逐条依据。
> **原则**：只小修不大修、不动大框架；每条都有失败现场证据 + 源码根因 + 最小改动 + 提交号。
> **诚实标注**：✅已实测确认修好 / 🔵已提交但端到端尚未全绿（在验证链上推进了一个门）/ ⚠️需处理后再进 PR。
> 分支 `feat/gbplanner-gain-exploration-strategy`（基于上游 `09a5aa4`）+ clean 分支 `fix/world-model-e2e-takeoff`（干净复现验证；提交链 `09a5aa4` → `79643b9` 真bug+死锁 → `77d951a` 撤hack → `dada2db` 探针修复），最后更新 **2026-07-06 晚（🏁 端到端全绿）**。

## 一句话现状（2026-07-06 晚 · 🏁 端到端全绿）
🏁 **world-model exploration 首次端到端全绿（无 hack，实测）**。run `20260706T130626`：`status=TASK_STATUS_OK`、`ok=True`、**blockers 空**、**4 探针全 ok**（frame_contract 8/8 话题含 /tf_static、/ap/v1/pose/filtered）、`accepted_goals=3/3`、`path_length=1.06m`、`takeoff.ok=True`、landing ok=True；BIN 物理铁证：**SIM 地面真值 +0.720m、电机 PWM 峰值 1950**。clean_repro.sh 首次 rc=0。
- 提交链（clean 分支 `fix/world-model-e2e-takeoff`）：`09a5aa4`(上游) → `79643b9`(5类真bug+B15死锁) → `77d951a`(撤3参数hack) → `dada2db`(B16 探针修复+测试断言遗留)。净 diff 286 行、零 hack：`integration/world-model-PR/CLEAN_REPRO_takeoff_fixes.diff`。
- **关键两刀**：B15 死锁修复（起飞完成前不转发探索 intent，相序互斥正解）+ B16 探针修复（见下）。
- **B16 探针双根因（都实测锤死，勿混）**：
  - `/tf_static`：latched（rosbag 实测 `transient_local`、count=3），探针硬编码 `qos_profile_sensor_data`(VOLATILE) 收不到锁存 → 改为**订阅按 publisher QoS 内省匹配**。
  - `/ap/v1/pose/filtered`：**不是 QoS、不是时序**（QoS 兼容且探针窗口内 17Hz 在发）。受控实验锤死真因：**后加入 participant 对 ArduPilot micro-ROS agent endpoints 的 DDS 发现需 28.97s**（graph 可见 type 但 publisher count=0 持续 28.9s，匹配后 40ms 即收到首条）；rosbag 因先于 agent 启动而秒配。探针旧逻辑每话题只等 ~2s、容器 30s 超时 → 永远采不到。修法=type 已发现(发布者存在)时等待上限提到 probe 预算(45s) + frame_contract 容器超时 30→90(对齐 exploration_probe 先例)。
  - 顺手清了 clean 分支两处**测试断言遗留**（slam_test 旧 `/imu`、runtime_artifacts_test 旧 RNGFND 参数名）+ 加回归守卫；`go build/vet/test ./...` 全绿。
- 诚实边界：`slam.ready=False` 仍存在（gate 靠 /slam/odom evidence 兜底,不挡全绿）；exploration 指标有 run 间波动(1.06~1.61m/2~3目标),本次 3/3 达标。
- 参数 hack 已撤销并提交(`77d951a`)：POSZ=2 测距仪、DISARM_DELAY 安全保护、readiness 45 均保持作者原样,**起飞与全绿都不依赖 hack**。
- 复现：`runbooks/world-model-jazzy/clean_repro.sh`(rc=0)；证据脚本：`summary_verdict.py`/`check_probes.py`/`decode_takeoff_bin.py`/`check_rosbag_qos.py`/`pose_first_ts.py`/`sub_latency_probe.py`(受控实验)。

---

## A. 主线交付物（PR 的真正目的）
| # | 提交 | 内容 | 状态 |
|---|---|---|---|
| A1 | `4a52df4` | **feat: 新增 `gbplanner_gain` 探索策略**——读 `/map`(OccupancyGrid) 做体积增益选向,替代脚本式 `frontier_lite`。加 `map_topic` 透传。 | 🔵 代码接进真实结构,go build/vet/test + py_compile 过;exploration 已全绿,**待 gbplanner_gain 替换实跑/或真 GBPlanner 桥接实跑;frontier_lite 基线已定档可作对照组** |

## B. 让 exploration 能跑起来的 bug 修复（都是作者代码真 bug，通用/向后兼容）

| # | 提交 | 症状（失败现场） | 根因 | 最小改动 | 状态 |
|---|---|---|---|---|---|
| B1 | `f0a7f6e` | 渲染出的 exploration 脚本 `python3 -m py_compile` **SyntaxError(line147)** | `text/template` 不做 Sprintf,`pattern[i %% len]` 的 `%%` 原样落盘 | 模板 `%%`→`%` | ✅ py_compile 复现→修后通过 |
| B2 | `0b85cea` | SLAM 后端 `ModuleNotFoundError: tomllib` 秒崩 | `tomllib` 是 Py3.11+ 标准库;栈为 jazzy 写,humble=Py3.10 无 | `try: tomllib / except: tomli` | ✅ jazzy 原生 tomllib 零影响 |
| B3 | `49d3551` | humble 拒绝空 `name:=` launch 参数 | 生成器对空值仍发参数 | 跳过空参数 | ✅ |
| B4 | `c8bc866` | official_baseline 容器 DDS participant 冲突 | 其他服务由 `baselineEnv()` 注入 `CYCLONEDDS_URI`,唯独 baseline 内联漏了 | 补该 env | ✅ Go 疏漏,通用 |
| B5 | `aa77fca` | 容器间 gz 话题互相看不见(gz 发现瘫痪) | `--user 1000:1000` 无 passwd 条目 → gz 默认分区(hostname:username)解析错乱 | 显式设 `GZ_PARTITION` | ✅ 编排真凶,通用 |
| B6 | `d3e73b7` | cartographer 时序崩(IMU 自吞回声) | IMU 净化桥 source 与 output 默认同为 `/imu` → 自己回灌自己 | 桥 output 改独立话题 | ✅ |
| B7 | `80c0fa8` | 同 B6 的 config 默认值那一针 | `SlamBackend.IMUTopic` 默认 `/imu` = 桥 source | 默认改 `/navlab/slam/imu` | ✅（B12 补测试）|
| B8 | `b13f268` | FCU bootstrap 请求 mode 15(AUTOTUNE) 而非 4(GUIDED),SITL "Mode change failed" | pymavlink `mode_mapping()` 按车型猜,把 Copter GUIDED=4 认成 Plane 表 15 | 优先信 config `guided_mode` | ✅ mode_switch mode_id=4 ok |
| B9 | `12ab9f0` | x2 emulator 收不到 scan,`/scan` 从不出现 | emulator 默认 reliable 订阅,projection 发布端 best-effort → RELIABILITY 不兼容被拒 | 订阅改 `qos_profile_sensor_data` | ✅（坑#8）|
| B10 | `68c19bf` | fast-lio 构建 `uint8_t is not a member of std` | Livox-SDK2 头文件用 `std::uint8_t` 未 `#include <cstdint>`,GCC13 不再传递包含 | cmake 加 `-include cstdint` | ✅ jazzy 镜像构建通过 |
| B11 | `f4d13b6` | `AHRS: EKF3 Yaw inconsistent 77 deg`,AHRS 停 DCM,takeoff result=4 | 位置源 `EK3_SRC1_POSXY=6`(ExtNav) 但 yaw 源 `EK3_SRC1_YAW=1`(Compass),坐标系打架 | yaw→ExtNav(`=6`) | 🔵 Yaw inconsistent 消失,yaw aligned;但未全绿 |
| B12 | `96dcf60` | `TestWriteSlamRuntimeConfig` 断言旧 `/imu` | B7 改了默认值但测试没跟 | 更新断言+加回归守卫 | ✅ go test 绿 |
| B13 | `5352d6b` | B11 后仍 `AHRS: DCM active`×19 | DCM 仍用磁罗盘 yaw,AHRS 一致性检查照挂 | 禁 compass(`COMPASS_USE/2/3=0`) | 🔵 DCM 消失,EKF3 origin set;未全绿 |
| B14 | `7c6a352` | EKF3 对齐完成却 `not started`;takeoff result=4 | **参数名漂移**:作者写 `RNGFND1_MIN_CM`(ArduPilot 4.5 前旧名),pinned 固件静默无视 → MIN 落默认 0.2m → TFmini 地面读数 0.095m 判无效 → `EK3_SRC1_POSZ=2` 高度源死 | 改新名 `RNGFND1_MIN/MAX/GNDCLR`(4 文件:profile+模板+Go 生成器+测试) | 🔵 **takeoff result 4→0(接受)**;但飞机未爬升,EKF3 still initialising |

## C. 不进主 PR（humble 专用，需条件化）
| # | 提交 | 说明 |
|---|---|---|
| C1 | `d8ff119` | gazebo-sensor 补拷 uv 托管 python——**jazzy 有害**(该路径不存在,COPY failed)。仅 humble 需要。PR 前条件化或移出。详见 [PR兼容性与jazzy评估.md](PR兼容性与jazzy评估.md) |

---

## B15（关键）· 死锁修复：takeoff 被接受但不爬升的真根因 —— 2026-07-06 已解
**症状**：GUIDED takeoff ack=0(接受) 但 CTUN.DAlt(期望高度)全程摁在 0、电机不到悬停、无人机不爬。
**逐层实锤(BIN 的 CTUN/RCOU/SIM 解码)**：DAlt=0 → 控制器被命令"保持当前高度"而非爬升。
**真根因(读 fcu_controller_runtime.py.tmpl 源码)**：`on_setpoint_intent` **无条件**把探索工作流的 setpoint/intent 转成 cmd_vel + 本地位置设定点灌给飞控。起飞前 intent 是"静止 hold"，在 GUIDED 下覆盖 takeoff 的爬升目标(DAlt=当前高度) → 永不离地 → takeoff never ok → controller never ready → 工作流一直发 hold intent → **死锁**（cmd_vel 排除法：`controller_ready` 需 `takeoff.ok`，故 hold cmd_vel 不是它发的；真凶是 on_setpoint_intent 无门转发）。
**最小改动**：`on_setpoint_intent` 加 `if bootstrap_ready(state):` 门——起飞完成前不转发探索 intent。相序互斥正解，不动大框架。
**验证(实测)**：无 hack 配置 run `20260706T110405`，BIN 解码 SIM 地面真值 +0.760m、四电机 PWM 峰值 1950、CTUN DAlt 0.655m、`takeoff.ok=True`。（注：物理起飞=真；但该 run accepted_goals=2<3、两个 probe rc=20，**端到端未全绿**，见文末"下一步坑"。）
**诚实修正**：曾额外堆 3 个参数 hack（EK3_SRC1_POSZ 改气压计/DISARM_DELAY=0/readiness 拉长），不符合物理实际。去掉后照样飞，证明只需 B15 逻辑修复。**撤销已作为 commit `77d951a` 正式提交**（此前只改工作树未提交、diff 未重导，被 Codex 查出不自洽，现已修复）。

## B16（收官）· frame_contract 探针双根因 —— 2026-07-06 晚已修，端到端全绿
**症状**：frame_contract_probe 采不到 `/tf_static` 与 `/ap/v1/pose/filtered`（两话题实际都健康发布）。
**根因A·/tf_static（QoS）**：latched 话题（rosbag 实测 `reliable+transient_local`、count=3），探针硬编码 `qos_profile_sensor_data`（VOLATILE+BEST_EFFORT），后加入的订阅收不到锁存样本。
**根因B·/ap/v1/pose/filtered（DDS 慢发现，非 QoS 非时序）**：受控实验（同镜像/env/host 网络容器、40s 长等待订阅）锤死：**订阅创建后 28.97s publisher 才匹配（graph 早可见 type、count_publishers 持续 0），匹配后 40ms 首条即达**——cyclone 后加入 participant 对 ArduPilot micro-ROS agent（FastDDS）endpoints 的 SEDP 发现极慢；rosbag 先于 agent 启动故秒配（不对称）。探针旧逻辑每话题 ~2s 窗口 + 容器 30s 超时 → 必死。
**最小改动**（commit `dada2db`,5 文件 +48/-9）：
1. `ros_probe.py.tmpl`：订阅 QoS 改 publisher 内省匹配（`get_publishers_info_by_topic` → 按其 reliability+durability 订阅）。
2. `ros_probe.py.tmpl`：type 已发现（=发布者存在）时订阅等待上限从 ~2s 提到 `PROBE_TIMEOUT_SEC`；type 未发现仍快速失败。
3. `FrameContractSpec` 加 `ProbeTimeoutSec=45`（模板本就认此 key,exploration_probe 已有 45 先例）；`probeTimeoutSec()` frame_contract 容器 30→90（对齐 exploration_probe）。
4. 顺手修 clean 分支测试断言遗留：`slam_test.go`（旧 `/imu`→`/navlab/slam/imu`+自吞回声守卫）、`runtime_artifacts_test.go`（RNGFND 旧参数名→4.5 新名+裸旧名守卫）。
**验证（实测,run `20260706T130626`）**：`TASK_STATUS_OK`、blockers 空、4 探针全 ok（frame_contract 8/8 话题）、accepted_goals=3/3、path 1.06m、SIM+0.720m、电机 1950;`go build/vet/test ./...` 全绿;clean_repro.sh 首次 rc=0。

## 下一步（端到端全绿后）—— 2026-07-06 晚
1. **frontier_lite 基线定档**：多跑几次 clean_repro 记录指标波动区间（accepted_goals 2~3、path 1.06~1.61m 已观测),作为 GBPlanner 对比的对照组。
2. **ros1_bridge 接真 GBPlanner**（预研B 已能飞）：按 `integration/ros1_bridge/` 设计稿分阶段（先 ROS1 侧单独出 trajectory → 桥标准消息 → trajectory_to_intent dry-run → 低速短程接 FCU → 补 gate 话题）。**先跑通再接,不盲接**。
3. **三个一键 GUI 演示 + 源码级讲解**：①原始 GBPlanner(预研B) ②world-model 原版 frontier_lite(现已全绿) ③gbplanner 接入后。
4. **PR/Issue 定稿提交**（前置已达成:全绿✅ + 净diff✅;剩 PR_BODY/ISSUE_BODY 从 DRAFT 定稿,经用户同意后提交）。

- 诊断脚本：`runbooks/world-model-jazzy/` 下 `check_probes.py`、`summary_verdict.py`（终审）、`verify_codex.py`、`decode_takeoff_bin.py`（SIM/RCOU/CTUN）、`check_rosbag_qos.py`、`pose_first_ts.py`（mcap 话题时间戳）、`sub_latency_probe.py`+`run_sub_experiment.sh`（DDS 慢发现受控实验）、`decode_ctun.py`。

## 给作者的高价值观察（Issue 素材）
- B1/B14/B15 说明作者**很可能从未端到端跑通过 exploration**（脚本编译不过、rangefinder 参数被固件无视、起飞被自身探索指令死锁）——任何人、任何 OS 跑到这步都会死,不是环境问题。
- B15 死锁最有价值：起飞与导航指令的相序竞争，属经典临界区问题，作者代码缺相序门。
- B14 是**跨 4 文件的系统性参数名漂移**,固件升级(4.5)后旧名静默失效,最隐蔽。
