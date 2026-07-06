# world-model 端到端 Bug 台账（给作者的 PR 清单）

> **用途**：①你（用户）随时查我到底找出并修了哪些真 bug；②提 PR 时的逐条依据。
> **原则**：只小修不大修、不动大框架；每条都有失败现场证据 + 源码根因 + 最小改动 + 提交号。
> **诚实标注**：✅已实测确认修好 / 🔵已提交但端到端尚未全绿（在验证链上推进了一个门）/ ⚠️需处理后再进 PR。
> 分支 `feat/gbplanner-gain-exploration-strategy`（基于上游 `09a5aa4`）+ clean 分支 `fix/world-model-e2e-takeoff`（干净复现验证；提交链 `09a5aa4` → `79643b9` 真bug+死锁修复 → `77d951a` 撤 3 参数 hack），最后更新 **2026-07-06（起飞突破 + 参数hack撤销已提交 + Codex查证纠偏）**。

## 一句话现状（2026-07-06 更新 · 起飞突破 + Codex 查证纠偏）
🎯 **无 hack 配置下无人机物理起飞已实测复现**。从全新克隆的作者源码(09a5aa4)干净复现，连修 5 类作者真 bug + 1 处死锁逻辑，起飞**不依赖任何参数 hack**。实测证据 run `20260706T110405`（BIN 解码）：**SIM 地面真值高度 +0.760 m**（584.190→584.950）、**四电机 PWM 峰值 1950**、CTUN DAlt 0.655 m、`bootstrap/takeoff.ok=True`。
- ⚠️ **诚实边界(重要)**：**端到端 exploration 尚未全绿**。同一 run：`accepted_goals=2`（<min 3，触发 `accepted_goals_below_min`）、`slam ready=False`、`frame_contract_probe` 与 `exploration_probe` 均 rc=20。此前文档"exploration_probe ok=True / 接受 3 目标"是**过度声称**（那是另一次 run 的结果，存在 run 间波动），现按实测更正。**物理起飞=真;端到端全绿=尚未达到。**
- **关键那一刀=死锁逻辑修复**（B15）：起飞完成前不把探索 intent 转发给飞控，否则"保持当前位置"指令覆盖 GUIDED takeoff 爬升（CTUN.DAlt 被摁在 0）→永不离地→死锁。这是相序互斥正解，非强改 DAlt。
- **参数 hack 已撤销并提交**（Codex 查出的不自洽已修复）：原栽过 3 个不符合物理实际的 hack（EK3_SRC1_POSZ 改气压计 / DISARM_DELAY=0 / readiness 拉长）。之前**只改了工作树、从未提交、diff 也未重导**，导致 `CLEAN_REPRO_takeoff_fixes.diff` 与"已撤销"文字矛盾；现已作为 commit `77d951a` 提交到 clean 分支，diff 重新导出为**净无 hack 变更集**（153 行、零 hack 字符串）。测距仪高度源 POSZ=2、安全保护均保持作者原样。
- ◉ **剩余 gate（按根因区分，勿混为一谈）**：
  - `/tf_static`：latched（rosbag 实测 `dur=transient_local`、count=3），探针用 `qos_profile_sensor_data`（VOLATILE）收不到锁存样本 → **需 QoS 修复**（订阅按 publisher 内省匹配 reliable+transient_local）。
  - `/ap/v1/pose/filtered`：rosbag 实测 `dur=volatile`、`rel=best_effort`、count=512 → **与探针 QoS 本就兼容，不是 durability 问题**；疑时序（探针在 EKF pose 产出前、SLAM 仍 `waiting_for_scan_and_imu` 时就跑）或 DDS type-hash，**待深查，QoS 补丁修不了它**。
  - `exploration_probe`：**不是采样 bug**，是探索工作流自报 `ok=False`（accepted_goals 2<3），属探索质量/波动。
- diff（已纠正）：`integration/world-model-PR/CLEAN_REPRO_takeoff_fixes.diff`；干净复现：`runbooks/world-model-jazzy/clean_repro.sh`；查证脚本：`verify_codex.py` / `decode_takeoff_bin.py` / `check_rosbag_qos.py`。

---

## A. 主线交付物（PR 的真正目的）
| # | 提交 | 内容 | 状态 |
|---|---|---|---|
| A1 | `4a52df4` | **feat: 新增 `gbplanner_gain` 探索策略**——读 `/map`(OccupancyGrid) 做体积增益选向,替代脚本式 `frontier_lite`。加 `map_topic` 透传。 | 🔵 代码接进真实结构,go build/vet/test + py_compile 过;**端到端替换演示待 exploration 跑通** |

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

## 下一步坑（当前前沿，尚未修）—— 2026-07-06（Codex 查证后按根因重写）
**物理起飞已复现，但端到端 exploration 尚未全绿。剩余 3 类 gate，根因各不相同，勿混为一谈：**

1. **`frame_contract_probe` → `/tf_static`（真·QoS 问题）**
   - rosbag 实测：`/tf_static` count=3、`dur=transient_local`、`rel=reliable`（latched）。探针用 `qos_profile_sensor_data`（VOLATILE+BEST_EFFORT）→ 加入订阅时锁存样本已发完，收不到。
   - **最小修方向**：探针模板 `templates/python/ros_probe.py.tmpl`（`sample_message_topic`，约 L169 `create_subscription(..., qos_profile_sensor_data)`）→ 订阅前用 `get_publishers_info_by_topic` 内省 publisher QoS，按其 reliability+durability 建订阅（对 /tf_static 即 reliable+transient_local）。草稿脚本 `runbooks/world-model-jazzy/patch_probe_qos.py`（**尚未应用/验证**）。

2. **`frame_contract_probe` → `/ap/v1/pose/filtered`（不是 QoS 问题）**
   - rosbag 实测：count=512、`dur=volatile`、`rel=best_effort` → **与探针 `qos_profile_sensor_data` 本就兼容**。所以 QoS 补丁**修不了它**。
   - 疑因：探针在 EKF 位姿产出前就跑（同 run frame_contract_probe 采到的 `/navlab/slam/status` 仍 `waiting_for_scan_and_imu`、slam ready=False），或 ArduPilot DDS type-hash。**待深查**（对比 rosbag 中该话题首条时间戳 vs 探针窗口）。

3. **`exploration_probe`（不是采样 bug）**
   - 该 run `/navlab/exploration/status` 采到了数据，但 payload 自报 `ok=False`：`accepted_goals=2`（min 3）、`path_length_m=1.6095`（ok）。blocker 名义叫 `topic_sample_missing` 但真因是 `accepted_goals_below_min`（探针把 payload.ok=False 也归到该 blocker 名下）。`/navlab/landing/status` 是级联（等 task 完成）。
   - 属探索质量/run 间波动（另一次曾达 3 目标），需稳定化，非探针 bug。

- 诊断脚本：`runbooks/world-model-jazzy/` 下 `check_probes.py <run_dir>`、`verify_codex.py`（git+run 综合）、`decode_takeoff_bin.py`（SIM/RCOU/CTUN 起飞物理）、`check_rosbag_qos.py`（话题 QoS/durability）、`decode_ctun.py`（DAlt/ThO 控制回路）。

## 给作者的高价值观察（Issue 素材）
- B1/B14/B15 说明作者**很可能从未端到端跑通过 exploration**（脚本编译不过、rangefinder 参数被固件无视、起飞被自身探索指令死锁）——任何人、任何 OS 跑到这步都会死,不是环境问题。
- B15 死锁最有价值：起飞与导航指令的相序竞争，属经典临界区问题，作者代码缺相序门。
- B14 是**跨 4 文件的系统性参数名漂移**,固件升级(4.5)后旧名静默失效,最隐蔽。
