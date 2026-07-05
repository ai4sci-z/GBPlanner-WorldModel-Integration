# world-model 端到端 Bug 台账（给作者的 PR 清单）

> **用途**：①你（用户）随时查我到底找出并修了哪些真 bug；②提 PR 时的逐条依据。
> **原则**：只小修不大修、不动大框架；每条都有失败现场证据 + 源码根因 + 最小改动 + 提交号。
> **诚实标注**：✅已实测确认修好 / 🔵已提交但端到端尚未全绿（在验证链上推进了一个门）/ ⚠️需处理后再进 PR。
> 分支 `feat/gbplanner-gain-exploration-strategy`（基于上游 `09a5aa4`），最后更新 2026-07-05 深夜。

## 一句话现状（不粉饰）
end-to-end **仍未跑通**（最新 run `status=TASK_STATUS_ERROR`）。已从"机器人根本不存在"一路推进到"**takeoff 指令被接受（result 4→0）但飞机未爬升、EKF3 仍在收敛**"。当前前沿=EKF3 external-nav 收敛 / takeoff 后爬升。

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

## 下一步坑（当前前沿，尚未修）
**坑#17 候选**：takeoff 已被接受但飞机不爬升,`EKF3 still initialising`。方向:①EKF3 external-nav 收敛需要更长 warmup（bootstrap 时序/超时）②或 takeoff 后需要持续 setpoint 才爬升。取证中。

## 给作者的高价值观察（Issue 素材）
- B1/B14 说明作者**很可能从未端到端跑通过 exploration**（脚本编译不过、rangefinder 参数被固件无视）——任何人、任何 OS、Mac 或 Linux 跑到这步都会死,不是环境问题。
- B14 是**跨 4 文件的系统性参数名漂移**,固件升级(4.5)后旧名静默失效,最隐蔽。
