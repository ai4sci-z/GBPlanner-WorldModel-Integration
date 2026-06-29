# 预研A 构建排错记录(jazzy → humble)

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
