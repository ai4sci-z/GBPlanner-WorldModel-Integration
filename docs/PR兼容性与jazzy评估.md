# PR 兼容性评估:humble 上的修复能否在作者 jazzy 环境兼容跑(2026-07-05)

> **背景**:作者 world-model 的目标环境是 **jazzy**(Ubuntu 24.04 / Python 3.12),我们在 **humble**(Ubuntu 22.04 / Python 3.10)上跑通。
> 用户硬约束:**任务做完必须提交 PR,且 PR 里的代码必须保证作者 jazzy 环境能兼容跑;不能兼容就重建 jazzy。**
> 本文**逐条审查**给 world-model 分支(`feat/gbplanner-gain-exploration-strategy`,基于上游最新 `09a5aa4`)的每个提交,判断 jazzy 兼容性。
> **结论先行:10 个提交全部 jazzy 兼容,不需要重建 jazzy。** 依据如下。

## 一、逐条兼容性审查(git log 09a5aa4..HEAD)

| commit | 内容 | 性质 | jazzy 兼容性判断 |
|---|---|---|---|
| `f0a7f6e` | exploration 模板 `%%`→`%` | 纯 bug | ✅ **通用**:`text/template` 不处理 `%`,`%%` 在 jazzy 渲染也照样输出坏的 `%%`。这是与 ROS 版本无关的渲染 bug。 |
| `0b85cea` | `import tomllib` 加 `tomli` 兜底 | 向后兼容 | ✅ **零影响 jazzy**:写法是 `try: import tomllib / except ModuleNotFoundError: import tomli`。jazzy=Py3.12 **有** tomllib → 走原生,`import tomli` 那行**根本不执行**。(需在 pyproject 的 `<3.11` 条件依赖里声明 tomli,已注明。) |
| `4a52df4` | 新增 `gbplanner_gain` 策略 | 新功能 | ✅ **通用**:纯 ROS2 Python(rclpy/nav_msgs/std_msgs),不用任何 humble 专有 API;additive、默认策略不变。jazzy 直接可用。 |
| `49d3551` | 跳过空值 launch 参数 | 向后兼容 | ✅ **通用**:humble 拒绝空 `name:=`;空参数本来就无意义,跳过它在 humble/jazzy **都安全**(jazzy launch 只会更严或相同)。 |
| `d8ff119` | gazebo-sensor 镜像补拷 uv 托管 Python | 纯 bug | ✅ **通用**:上游 `COPY venv` 却不 COPY venv 的解释器(uv 托管 python)→ 悬空软链,服务秒退。无论 uv 装的是哪个 Python 版本,不拷都是 bug。jazzy 构建同样需要这 4 行 `COPY`。 |
| `c8bc866` | official_baseline 补 `CYCLONEDDS_URI` | 纯 bug | ✅ **通用**:其他服务都由 `baselineEnv()` 注入该 env,唯独 baseline 内联 Env 漏了——是 **Go 代码疏漏**,与 ROS 版本无关。jazzy 同样漏、同样该补。 |
| `aa77fca` | gz-transport 服务显式设 `GZ_PARTITION` | 通用改进 | ✅ **通用**:根因是容器以 `--user 1000:1000` 运行但无 passwd 条目 → gz 默认分区(hostname:username)解析错乱。这与 ROS 发行版无关,只与容器用户/gz-transport 有关;jazzy 同样受影响。显式设分区是稳健化。 |
| `d3e73b7` | IMU 净化桥不得回灌自己的 source topic | 纯 bug | ✅ **通用**:桥的 source 与 output 默认同为 `/imu` → 自吞回声 → cartographer 时序崩。逻辑 bug,与 ROS 版本无关。 |
| `80c0fa8` | SlamBackend.IMUTopic 默认值不得等于桥 source | 纯 bug | ✅ **通用**:同上问题的 config 默认值那一针(覆盖链)。通用。 |
| `b13f268` | FCU 优先信 config 的 GUIDED 号,不信 pymavlink 车型猜测 | 通用改进 | ✅ **通用**:`mode_mapping()` 依车型识别可能返回 Plane 表(GUIDED=15);优先用 config 明确值(Copter=4)在任何 ROS 版本、任何 SITL 握手时机都更稳。jazzy 同样受益。 |

## 二、humble 专用改动(**不进主 PR**,故不影响作者)

以下是"让它在我这台 humble 机器上构建/跑起来"的**本机环境适配**,**都在我们项目仓的独立目录**(不在 world-model 分支),**不会进 PR**:
- `runbooks/world-model-humble-fixes/gazebo-sensor-humble.Dockerfile`:把 venv 改用**系统 Python 3.10 + system-site-packages**(因 humble rclpy 是 Py3.10 C 扩展;jazzy 用 Py3.12,不需要此改)。
- ydlidar `declare_parameter` 26 处传默认值补丁(humble/jazzy 都移除了无默认值重载,但此补丁走独立 humble Dockerfile)。
- 薄层 robot.launch.py 补丁(sdformat_urdf gpu_lidar / SDF 版本)——humble libsdformat 特定。

> **要点**:主 PR 只含**上游代码文件**(Go/Python 模板/Dockerfile 的通用修复)。humble 专有的镜像重建脚本留在我们自己的 runbooks,作为"如何在 humble 复现"的附录,不塞给作者。

## 三、结论与行动

1. **不需要重建 jazzy**:给 world-model 的 10 个提交要么是通用 bug fix、要么向后兼容,jazzy 环境能兼容跑。
2. **PR 提交前的收尾动作**(任务达"做好"标准后执行):
   - 把 world-model 分支 rebase 到最新 `origin/main`(已确认 = `09a5aa4`,无更新)。
   - `pyproject.toml` 里 tomli 声明为 `python_version < "3.11"` 条件依赖(确保 jazzy 不多装)。
   - PR 描述里注明:"修复均为通用/向后兼容;humble 专用镜像适配见附录,不在本 PR。"
   - 用用户账号 `ai4sci-z` fork + 提交(照 `integration/world-model-PR/手动提交PR与Issue指南.md`)。
3. **诚实边界**:我**没有**在 jazzy 上实测过这些改动(当初 jazzy 构建就失败,没有可运行的 jazzy 环境)。上述兼容性是**代码级论证**(向后兼容写法 + 通用 bug 性质),不是 jazzy 实跑验证。**若作者/用户要求 100% 确证,唯一办法是重建 jazzy 实跑**——这点如实告知,不夸大。
