# jazzy 全栈重建 施工指引(新窗口接管此任务,2026-07-05)

> **为什么做这个(硬约束)**:作者 world-model 目标环境是 **jazzy**(铁证:上游原始 `config.toml` `distro="jazzy"`、所有镜像 `jazzy-latest`)。
> 我们之前在 **humble** 跑通,但 **PR 提给作者他用 jazzy 构建**——必须**在 jazzy 上真跑通** exploration + gbplanner_gain,否则 PR 作者无法跑=白干。
> **血泪教训(2026-07-05 实测)**:代码级"论证兼容"**不可靠**——我论证 `d8ff119` 通用兼容,真在 jazzy 构建**直接失败**(`COPY failed: root/.local/share/uv/python 不存在`)。**只信 jazzy 实跑,不信论证,不信退出码,只认 `docker images` 真镜像。**

## 一、目标与验收
1. 补齐 9/9 **jazzy** 镜像(`docker images | grep 'navlab.*jazzy'` 数到 9)。
2. `cd ~/ws/world-model/orchestration/sim && NAVLAB_SIM_DISTRO=jazzy go run ./cmd/navlab-sim run exploration --live-preflight` 端到端跑绿(或至少 FCU 起飞、frontier_lite 出指标)。
3. jazzy 上把 `strategy=gbplanner_gain` 真替换 frontier_lite 跑一遍(证明"模块直接替换")。

## 二、现状:jazzy 镜像 5/9(已成)+ 4 缺
- ✅ 已有(当初构建成功):`ros-base` `ardupilot-sitl` `mavlink-router` `companion` `slam-cartographer` 的 `:jazzy-latest`。
- ❌ 缺:`fast-lio` `gazebo-headless` `gazebo-sensor` `official-baseline`(重的那 4 个,当初卡编译坑退了 humble)。

## 三、构建命令(逐镜像)
```bash
# 前置:挂 keepalive(WSL 空闲关机杀 docker);cwd 必须是 orchestration/sim(go.mod 在这!)
cd /home/ai4s/ws/world-model/orchestration/sim
NAVLAB_SIM_DISTRO=jazzy go run ./cmd/navlab-sim build runtime --distro jazzy --image <fast-lio|gazebo-headless|gazebo-sensor|official-baseline>
# 验证真实产物(不信退出码):
docker images | grep 'navlab/<名>.*jazzy'
```

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
