> 📌 **状态戳(2026-07-06)**:本文含历史阶段内容。**当前权威状态**以 [RESUME_新窗口接管_2026-07-06.md](../RESUME_新窗口接管_2026-07-06.md) + [Bug 台账](../docs/world-model端到端Bug台账_给作者PR.md) 为准。要点:jazzy 镜像 **9/9 已完成并开箱验真**;无 hack 配置**物理起飞已复现**(run 20260706T110405:SIM+0.76m/电机1950/DAlt0.655m);**端到端 exploration 尚未全绿**(剩 frame_contract_probe:/tf_static=QoS、/ap/v1/pose/filtered=时序非QoS、accepted_goals 2<3);**未提交 PR**。

# 预研A 构建排错记录(jazzy → humble)

> 📌 **2026-07-03 校核**:本文覆盖**构建阶段**(已完成,9/9 镜像)。**运行时**排坑(9 坑,含总根因)见 [运行时排错记录_humble.md](运行时排错记录_humble.md)。

> 这段"发现假成功 → 定位根因 → 对症修复"的过程,组会讲故事很有用(体现工程严谨)。最后更新 2026-06-29。

## 1. 现象:报"成功"但其实没成功
`navlab-sim build all` 跑完报 `rc=0 / BUILD_OK`,但**自检发现不对**:
```bash
$ docker images | grep navlab    # 只看到 5 个,应有 9 个
navlab/ros-base / ardupilot-sitl / mavlink-router / companion / slam-cartographer  ✅
# 缺:gazebo-headless、fast-lio、gazebo-sensor、official-baseline  ❌
```
日志里这 4 个只有 `Building NavLab X`、没有 `Successfully tagged` → **它们失败了,但命令仍报 OK(假成功)**。

> 教训:**绝不能只看"命令退出码=0"就当成功,必须自检真实产物**(docker images 数量)。

## 2. 排查:不是内存(OOM),是编译不兼容
- 先怀疑 OOM(WSL 仅 ~15GB / 24 核,24 并行编译可能爆内存)。
- **查证排除**:`free -h` 有 13GB 空闲、日志无 `killed/out of memory/OOM` 痕迹 → **不是 OOM**。
- 看真实编译错误(去重统计):
  ```
  26×  error: no matching function ... rclcpp::Node::declare_parameter(...)   # ROS2 API 变了
   6×  error: 'uint8_t' is not a member of 'std'                             # GCC13+ 要 #include <cstdint>
  ```
- **根因**:`config.toml` 里 `distro = "jazzy"`(Ubuntu 24.04 + ROS2 Jazzy)**太新**;Livox SDK / ydlidar / ardupilot_gz 这些上游代码是为 **humble(Ubuntu 22.04)** 写的,在 jazzy 的新编译器/新 rclcpp 下编不过。
- 排除"项目自带补丁能修":`patches/` 只有一个无关的 `ardupilot_gazebo_esc_lag.patch`,**没有修这些编译错误的补丁**。

## 3. 修复:切到 humble 重建
```bash
# config.toml: distro = "jazzy"  ->  "humble"
# 重新 navlab-sim build all(humble),jazzy 日志已备份为 navlab_build_jazzy.log
```
humble = Ubuntu 22.04,正是这些机器人上游代码的目标平台,预期可编过。**重建进行中(后台)。**

## 4. 自检清单(本次)
- [x] 用 `docker images` 核对真实产物数量(发现 5≠9)
- [x] 区分 OOM vs 编译错误(查 free/日志,排除 OOM)
- [x] 定位具体编译错误并归因到 distro
- [x] 检查项目补丁是否覆盖(否)
- [x] 备份失败日志(navlab_build_jazzy.log)做证据
- [ ] humble 重建结果(待完成后再次 `docker images` 核对 9 个全绿)

## 5. 状态
- 当前:humble 全套重建后台进行中(任务 bf7d69x5m)。
- 完成后:再次自检 `docker images`(必须 9 个全绿),再 `--live-preflight` 确认 exploration 可跑,然后真跑 exploration + 截图。

## 6. humble 重建结果:6/9,深挖 3 个失败的真因(2026-06-29 晚)
humble 修好了 fast-lio(Livox 在 jazzy 编不过、humble 过了),但**自检 `docker images` 发现仍 6/9**。逐个查真因(**三个各不相同**):

| 镜像 | 真因(实证) | 修法 |
|---|---|---|
| gazebo-headless | Dockerfile 用 `RUN --mount=type=cache`(需 BuildKit),但编排器 `navlab-sim build` 的 docker SDK 用**旧版构建器**,报 `the --mount option requires BuildKit` | 改用 `DOCKER_BUILDKIT=1 docker build` CLI 直接重建 |
| official-baseline | 同样 `# syntax=dockerfile:1.7`+`--mount` 需 BuildKit;且它 `FROM gazebo-headless` → gazebo-headless 挂导致它**级联失败** | gazebo-headless 好后用 CLI BuildKit 重建 |
| gazebo-sensor | `ydlidar_ros2_driver` 的 `declare_parameter`(无默认值形式)在 humble rclcpp **模板推导失败** | 仿真用 gz 雷达经 ros-gz-bridge,**不需要 ydlidar 硬件驱动** → 补丁版 Dockerfile 跳过它,保留 YDLidar-SDK + ros-gz-bridge |

**关键洞察(防后续再踩)**:编排器的 SDK 构建用的是**经典构建器**,凡 Dockerfile 用 `--mount` 的都会挂;**改用 `DOCKER_BUILDKIT=1 docker build` CLI 直建**即可。这不是代码问题,是构建器配置问题。

**当前**:gazebo-headless、gazebo-sensor(补丁版)正用 CLI BuildKit 后台重建;完成后建 official-baseline,再自检 9/9。

## 7. 进展更新(2026-06-29 深夜)
- ✅ **gazebo-sensor**:补丁版(跳过仿真用不到的 ydlidar 硬件驱动)**构建成功**。
- 🔧 **gazebo-headless**:第一次 CLI BuildKit 重建仍失败 —— `gz sim` 报 exit 127(命令找不到)。**真因**:humble 默认 `ros-gz` 装的是 **Fortress**(用 `ign gazebo`),没有 Harmonic 的 `gz sim`。**修法**:patch 最后阶段从 OSRF 仓库显式装 `gz-harmonic`(提供 `gz sim`)+ 尽力装 `ros-gzharmonic` 桥。**正在重建并自动验证 `gz sim`**(未验证完不算成功)。
- ⏳ **official-baseline**:自动接力链(`chain2`:等 gazebo-headless 好 → BuildKit CLI 建 → 自检 9/9)。
- **铁律重申**:后台任务报"exit 0"≠成功——脚本外层 echo 会掩盖真实失败;必须看真正的 `BUILD_EXIT` + `gz sim` 验证 + `docker images` 核对真实产物。这一条已让我连续抓出多次假成功。

## 8. official-baseline 的 Gazebo 版本冲突(最后一关)
gazebo-headless 修好后到 **8/9**,official-baseline 仍失败(apt exit 100)。精确原因(实证):base(gazebo-headless)装了 **Harmonic 版 `ros-gzharmonic-*`**,而 official-baseline 的 apt 列表又要装 **Fortress 版 `ros-gz-*`** → 两者 **Conflicts**(`ros-gzharmonic-bridge` Conflicts `ros-gz-bridge`,等 5 个)。**修法**:把 official-baseline 的 `ros-${ROS_DISTRO}-ros-gz` 也改成 `ros-gzharmonic`(全栈统一 Harmonic)。**正在重建**(ardupilot 递归克隆+编译较久)。
> 教训:humble 上用 Gazebo Harmonic,**所有镜像的 ros_gz 必须统一 Harmonic 版**,混入任何 Fortress 版都会冲突。这是"为 jazzy 设计的栈搬到 humble"的核心代价。

## 9. 完整修复清单(humble 跑通 9 镜像所需的全部改动)
| 镜像 | 问题 | 修法 |
|---|---|---|
| 全部 | 编排器 SDK 用经典构建器,不支持 `--mount` | 改用 `DOCKER_BUILDKIT=1 docker build` CLI |
| fast-lio | jazzy GCC13 编不过 Livox | 换 humble 自动解决 |
| gazebo-sensor | ydlidar 驱动 declare_parameter 不兼容 | 补丁:跳过 ydlidar(仿真用 ros-gz-bridge) |
| gazebo-headless | humble 缺 Harmonic `gz sim` | 补丁:装 `gz-harmonic`+`ros-gzharmonic` |
| official-baseline | ① `ros-gz`(Fortress)与 base 的 Harmonic 冲突;② `pip install --break-system-packages` 在 humble 旧 pip 上**无此选项**(jazzy/24.04 才有) | ① `ros-gz`→`ros-gzharmonic`;② 去掉 `--break-system-packages` |

> ⏳ **official-baseline 状态(如实)**:已应用上面两处补丁,正在重建;apt 已过,接下来 ardupilot 递归克隆 + colcon 编译(较久)**尚未验证完**——`docker images` 真出现该镜像前,不算成功。可能还会在 colcon 阶段遇到新问题,遇到我继续修+如实报。
>
> **规律总结**:这套栈是为 **jazzy(Ubuntu24.04)** 写死的,搬到 humble(22.04)需逐个补 jazzy-ism(新 pip 选项、新 Gazebo 默认版本、新编译器宽容度…)。每个都实测真因、对症修,已 5 处。
