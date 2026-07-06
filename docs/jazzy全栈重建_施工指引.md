> 📌 **状态戳(2026-07-06)**:本文含历史阶段内容。**当前权威状态**以 [RESUME_新窗口接管_2026-07-06.md](../RESUME_新窗口接管_2026-07-06.md) + [Bug 台账](../docs/world-model端到端Bug台账_给作者PR.md) 为准。要点:jazzy 镜像 **9/9 已完成并开箱验真**;无 hack 配置**物理起飞已复现**(run 20260706T110405:SIM+0.76m/电机1950/DAlt0.655m);**端到端 exploration 尚未全绿**(剩 frame_contract_probe:/tf_static=QoS、/ap/v1/pose/filtered=时序非QoS、accepted_goals 2<3);**未提交 PR**。

# jazzy 全栈重建 施工指引(新窗口接管此任务,2026-07-05)

> **为什么做这个(硬约束)**:作者 world-model 目标环境是 **jazzy**(铁证:上游原始 `config.toml` `distro="jazzy"`、所有镜像 `jazzy-latest`)。
> 我们之前在 **humble** 跑通,但 **PR 提给作者他用 jazzy 构建**——必须**在 jazzy 上真跑通** exploration + gbplanner_gain,否则 PR 作者无法跑=白干。
> **血泪教训(2026-07-05 实测)**:代码级"论证兼容"**不可靠**——我论证 `d8ff119` 通用兼容,真在 jazzy 构建**直接失败**(`COPY failed: root/.local/share/uv/python 不存在`)。**只信 jazzy 实跑,不信论证,不信退出码,只认 `docker images` 真镜像。**

## 一、目标与验收
1. 补齐 9/9 **jazzy** 镜像(`docker images | grep 'navlab.*jazzy'` 数到 9)。
2. `cd ~/ws/world-model/orchestration/sim && NAVLAB_SIM_DISTRO=jazzy go run ./cmd/navlab-sim run exploration --live-preflight` 端到端跑绿(或至少 FCU 起飞、frontier_lite 出指标)。
3. jazzy 上把 `strategy=gbplanner_gain` 真替换 frontier_lite 跑一遍(证明"模块直接替换")。

## 二、现状(2026-07-05 晚终版):✅✅ **9/9 全部建成+开箱验真,镜像阶段收官**
> official-baseline(17GB级):**原版 Dockerfile 零补丁一次过**(预研判断全中:ros-gz 天然配 Harmonic、--break-system-packages
> Py3.12 必需保留、MICRO_ROS_AGENT_REF=jazzy 默认即对——micro_ros_agent 58.4s 编过,humble 当初最狠的 Fast-CDR 坑 jazzy 天然不存在)。
> 开箱:/opt/ros/jazzy + ardupilot 全家桶 12 包 + BASELINE_OK。当前已转入 jazzy exploration 实跑阶段。
- ✅ 原有 5:`ros-base` `ardupilot-sitl` `mavlink-router` `companion` `slam-cartographer`。
  **已开箱验真**(`verify_jazzy_images.sh`,逐个进容器查 `/opt/ros`):ros-base/slam/companion 内部真 jazzy;
  ardupilot-sitl/mavlink-router 无 ROS(distro 无关,共用 ID 合理)。
  意外发现:**companion 的 humble tag 名不副实**(同 ID,内部其实是 jazzy/Py3.12)——难怪它从没报过 tomllib。
- ✅ 本轮新建 3(全部 `docker images` 实测 + 开箱验真):
  - `gazebo-headless:jazzy-latest`(5.21GB)——原版 Dockerfile 零补丁,BuildKit 直建。
  - `fast-lio:jazzy-latest`(1.85GB)——**坑:Livox-SDK2 GCC13 缺 `<cstdint>`**(std::uint8_t 不识),
    修法=cmake 加 `-DCMAKE_CXX_FLAGS="-include cstdint"`(改 in-repo Dockerfile,向后兼容,已提交 world-model 分支 `68c19bf`)。
    开箱:install 里 fast_lio+livox_ros_driver2、livox .so 实在。
  - `gazebo-sensor:jazzy-latest`(1.97GB)——**坑:ydlidar `declare_parameter("name")` 无默认值**(jazzy rclcpp 同 humble 已移除,
    原样构建实测失败打脸"jazzy 或许没这坑"),修法=humble 同款 26 处 sed(`gazebo-sensor-jazzy.Dockerfile` v2)。
    开箱:venv python 直接能跑(Py3.12.3 系统 python)→ **实锤 d8ff119 悬空软链坑 jazzy 不存在**,该 COPY 条件化依据坐实。
- 🔵 `official-baseline`:**预研结论=jazzy 用原版 Dockerfile 零补丁**(ros-gz 天然配 Harmonic、--break-system-packages Py3.12 必需、
  MICRO_ROS_AGENT_REF=jazzy 默认即对),只传 jazzy args+代理。构建已发车(最重,ArduPilot master 克隆+colcon 全家桶)。
- 📌 同日在 world-model 分支补 2 提交:`68c19bf`(fast-lio cstdint)+`12ab9f0`(坑#8 emulator sensor-data QoS,还清"本地 M 未提交"欠账)。

## 三、构建命令(逐镜像)

> 🔴🔴 **2026-07-05 实测重大更正**:`go run ./cmd/navlab-sim build` **不能用**!编排器内置 builder 走 Docker **经典 builder(无 BuildKit)**,而这些 Dockerfile 用了 `RUN --mount=type=cache`(gazebo-headless/official-baseline 都有),经典 builder 在 Step 8 直接报 `the --mount option requires BuildKit` 失败——**但 harness 吞掉错误,仍打印 `OK NavLab image build completed` 且 rc=0**(典型假成功,`docker images` 里根本没镜像)。humble 当初也是因此绕过 Go builder。
>
> **正解:直接用 `DOCKER_BUILDKIT=1 docker build`**。已封装成 `runbooks/world-model-jazzy/build_jazzy.sh <infra|runtime> <image>`:自动定位 Dockerfile、传 `INFRA_TAG=jazzy-latest ROS_DISTRO=jazzy`、official-baseline 加 host 网+7897 代理、**构建后 grep `docker images` 核验真产物**(NO 则 rc=1)。
>
> 镜像分组(build.go 实锤):**infra**=ardupilot-sitl/mavlink-router/**gazebo-headless**/**fast-lio**;**runtime**=companion/slam-cartographer/**gazebo-sensor**/**official-baseline**。

```bash
# 前置:挂 keepalive(WSL 空闲关机杀 docker)
wsl bash -lc 'nohup sleep infinity >/dev/null 2>&1 &'
# 逐镜像(直用 BuildKit,自带真产物核验):
bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/build_jazzy.sh infra   gazebo-headless
bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/build_jazzy.sh infra   fast-lio
bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/build_jazzy.sh runtime gazebo-sensor  runbooks/world-model-jazzy/gazebo-sensor-jazzy.Dockerfile
bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-jazzy/build_jazzy.sh runtime official-baseline
# 验证真实产物(不信退出码):
docker images | grep 'navlab/.*jazzy'
```

**gazebo-sensor jazzy 特办**:in-repo Dockerfile 含我 `d8ff119` 的 `COPY .../uv/python`(jazzy 无此路径→COPY failed)。jazzy 版=d8ff119 父提交 `c2cc690` 的原版(已导出 `runbooks/world-model-jazzy/gazebo-sensor-jazzy.Dockerfile`,无 COPY)。若 ydlidar `declare_parameter` 在 jazzy GCC13 也编不过,再套用 `gazebo-sensor-humble.Dockerfile` 的 26 处 sed 补丁。

## 四、已知 jazzy 坑 + 修法(用 humble 经验)
| 镜像 | jazzy 坑 | 修法(我已在 humble 会修) |
|---|---|---|
| gazebo-sensor | **①`d8ff119` 我加的 COPY uv python 在 jazzy 失败**(jazzy Py3.12 uv 用系统 python,无托管 python 路径) | **把该 COPY 条件化/移除**(仅 humble 需要)。改 `docker/images/runtime/gazebo-sensor.Dockerfile` |
| gazebo-sensor | ②ydlidar `declare_parameter("name")` 无默认值形式,GCC/rclcpp 编不过 | 传默认值(humble 已补 26 处,见 `runbooks/world-model-humble-fixes/gazebo-sensor-humble.Dockerfile` 的 sed 补丁,搬到 jazzy) |
| gazebo-sensor | ③YDLidar-SDK 的 `%X` 格式 warning(**只是 warning 不致命**) | 忽略 |
| fast-lio | Livox SDK 在 GCC13(jazzy)编不过(`uint8_t` 缺 `#include <cstdint>`) | 补 `#include <cstdint>` / patch Livox |
| official-baseline | 当初 humble 补的 ros-gzharmonic/pip 等是 **humble-ism**;jazzy 用**原始** Dockerfile(可能本来就对) | 先原样构建看坑,jazzy 可能不需要 humble 补丁 |
| (通用) | gpu_lidar / sdformat / RSP 崩(坑#9)——**humble 特有(humble sdformat_urdf 不认 gpu_lidar)**,**jazzy 可能没这个坑** | jazzy 先不打 robot.launch.py 薄层补丁,看是否本来就能 spawn |

> **重要推断**:humble 那 13 个运行时坑里,很多是 **humble 特有**(tomllib/venv Py版本/sdformat gpu_lidar/空 launch 参数),**jazzy 上大概率不存在**。所以 jazzy 全栈可能比想象顺——当初是卡在**构建编译坑**(uint8_t/declare_parameter),那些我现在都会修。

## 五、脚本铁律(我 2026-07-05 栽过跟头)
- **改文件→构建→恢复** 的脚本:①用**绝对路径**(别 `cd` 来 `cd` 去后用相对路径)②恢复用 `git checkout <file>` 而非 `cp`(cwd 变了 cp 会失败还破坏文件)③每步 `pwd` 确认。
- 我连栽 3 次 cwd bug(go module 找不到、恢复路径失效、Dockerfile 被删没恢复)——务必绝对路径。
- 变量在 `wsl bash -c "$VAR"` 里常被吞 → **写脚本文件执行**。

## 六、jazzy 已验证的(语言层,别重复)
真 `ros:jazzy-ros-base`(Py3.12)实测过:tomllib 原生零影响、gbplanner_gain/frontier_lite 脚本 py_compile、rclpy+nav_msgs+std_msgs 可 import(脚本 `runbooks/diagnostics/jazzy兼容实测_Py312.sh`)。**语言层 OK,缺的是全栈构建+运行。**

## 七、给 world-model 分支的 10 提交里,PR 前要处理的
- `d8ff119`(COPY uv python):**jazzy 有害,要条件化或移出 PR**。
- 坑#7 QoS 修复(`navlab/sim/gazebo_sensor/cli.py`)**本地 M 未提交**(不在 10 提交里)——通用修复,PR 前补提交。
- 其余 9 项:jazzy 语言层已验/通用 bug,但**未全栈实跑**——jazzy 全栈跑通后才算真兼容。
- 详见 `docs/PR兼容性与jazzy评估.md`、`integration/world-model-PR/PR物料清单.md`。
