# world-model exploration 运行时排错记录(jazzy→humble 迁移坑,逐个剥)

> 背景:world-model 这套栈原为 jazzy(Ubuntu 24.04 / Python 3.12)写,本机搬到 humble(Ubuntu 22.04 / Python 3.10)。
> 9 个镜像已全部构建成功(预研A),但**运行时**还有一连串版本坑。本文按"只信真实产物"的铁律,逐个记录:
> 每个坑都给【真实证据(日志原文)】+【根因】+【修复】+【验证】。证据来自 `artifacts/sim/exploration/<run_id>/`。
> 最后更新 2026-06-30。

## 坑 #1(头号):SLAM 崩于 `ModuleNotFoundError: No module named 'tomllib'`

- **证据**:`artifacts_sample/exploration_summary.json` L404 `slam_runtime_log.last_problem_lines`;
  run `20260630T004434Z` 的 `slam_backend.runtime.log`。
- **根因**:`tomllib` 是 Python **3.11+** 标准库;humble=Py3.10 没有。
  `navlab/common/toml_values.py` 与 `navlab/sim/companion/runtime/config.py` 顶层 `import tomllib` →
  `navlab.common.slam.config` 导入 `toml_values` → SLAM 节点启动即崩 → 无 `/slam/odom`、`/tf`、`/scan` →
  飞控永远 `waiting_for_pose`、所有探针 rc=20。**这是 exploration 在 humble 上起不来的头号原因。**
- **修复**(world-model 分支 commit `0b85cea`):两个文件 `import tomllib` 改为
  `try: import tomllib / except ModuleNotFoundError: import tomli as tomllib`(API 一致,drop-in);
  humble 环境装 `tomli`。本机为让挂载运行时取到 tomli,把 `tomli` vendor 到 `/workspace` 根(PYTHONPATH)。
- **验证(实测)**:① SLAM 容器内挂载改后代码 + 装 tomli → `import navlab.common.toml_values` / `navlab.common.slam.config` 均 OK;
  ② 重跑 run `20260630T075024Z`,其 `slam_backend.runtime.log` 中 `tomllib` 出现 **0 次** → 已越过此坑。✅

## 坑 #2:SLAM launch 报 `malformed launch argument 'cartographer_configuration_directory:='`

- **证据**:run `20260630T075024Z` 的 `slam_backend.runtime.log` 尾:
  `malformed launch argument 'cartographer_configuration_directory:=', expected format '<name>:=<value>'`。
- **根因**:`navlab/common/slam/backends.py` 的 `CartographerBackend.command` 把**所有** launch 参数
  (含空串值,如未设置的 `cartographer_configuration_directory`)都拼成 `key:=value`;
  ROS2 humble 的 launch **拒绝空值** `name:=`。
- **修复**(world-model 分支 commit `49d3551`):构造参数时**跳过渲染为空串的参数**,让 launch 文件用自身默认值。
  (`launch_value`:bool→true/false 非空,故只有值为 `""` 才被跳过,安全。)
- **验证(实测)**:重跑 run `20260630T075417Z`,`malformed launch argument` 出现 **0 次**,
  且 `slam_backend.runtime.log` 显示 **`cartographer_node` 真正启动并运行**(日志停在
  `Queue waiting for data: (0, scan)` = 等激光数据)。✅ SLAM 节点已能起来。

## 坑 #3:cartographer 收不到 `/scan` → 根因已锁定:gazebo-sensor 镜像 venv 悬空软链

- **证据链**(2026-07-01 实测):
  1. run `20260630T075417Z` SLAM 日志反复 `Queue waiting for data: (0, scan)`;
  2. 该 run **没有任何 gazebo_sensor 日志** = 发 `/scan` 的服务根本没起来;
  3. 进容器直接跑服务用的解释器:`/opt/gazebo-sensor-venv/bin/python` → **"No such file or directory"**;
  4. `ls -l` 实锤:venv 的 python 是软链 → `/root/.local/share/uv/python/cpython-3.14-.../python3.14`,
     **而 uv 托管的这个 Python 没被拷进最终镜像**(builder 阶段只 `COPY` 了 venv 目录)→ 悬空软链。
- **因果**:gazebo_sensor 服务启动即"解释器不存在"→ 崩、无日志 → `/scan`/`/sim/x2/*` 全无 → cartographer 干等。
- **修复**(已写入 `runbooks/world-model-humble-fixes/gazebo-sensor-humble.Dockerfile`):
  最终阶段补 `COPY --from=builder /root/.local/share/uv/python /root/.local/share/uv/python`。
- **验证**:重建脚本 `build_gazebo_sensor2.sh`(含真实产物自检)——✅ **重建成功(2026-07-02 实测)**:
  新镜像 `navlab/gazebo-sensor:humble-latest` 生成,`VENV_PYTHON=OK`(镜像内 `/opt/gazebo-sensor-venv/bin/python --version` 真能执行,输出 Python 3.14.5)。**镜像级修复完成;端到端重跑 exploration 验证 `/scan` 待做**(需等 GBPlanner 演示容器空出资源)。

## 坑 #4:venv 修好后 gazebo_sensor 仍秒退 → 同一命令里的第二死点

- **证据**(2026-07-03 run `20260703T004145Z`):镜像 venv 已修(`VENV_PYTHON=OK`),但该 run 仍无
  gazebo_sensor 日志、`/scan` 仍缺、blockers 与上次相同 → 服务还是没起来。
- **根因**:启动命令为 `source /opt/navlab_sensor_ws/install/setup.bash && exec venv/python -m ...`;
  `install/` 目录由 **ydlidar 的 colcon 构建**生成——而 humble 版镜像**故意跳过了**该构建(humble 编不过)
  → `source` 失败 → `&&` 链中断 → 容器秒退无日志。**与坑#3(venv)是同一命令里两个独立死点,修掉第一个才暴露第二个。**
- **修复**:Dockerfile 补一个 no-op `install/setup.bash` 占位(仿真走 gz gpu_lidar→ros-gz-bridge,不需要 ydlidar 驱动)。
- **验证(实测)**:重建后**逐段冒烟测试 4/4 全通**(source ros → source 占位 → venv import cli → cli --help),
  启动链首次完全打通。端到端 run#4 验证中。
- **方法教训**:修"启动即死"类 bug,应**先在容器里逐段模拟完整启动命令**再烧整轮 e2e——本次已按此法执行。

## 当前进度(用于汇报)

| 坑 | 状态 | 实测证据 |
|---|---|---|
| #1 tomllib(SLAM 头号崩溃) | ✅ 已修+验证 | run2 日志 tomllib 出现 0 次,SLAM 越过 |
| #2 空 launch 参数 | ✅ 已修+验证 | run2 `malformed` 0 次,cartographer_node 真启动 |
| #3 `/scan` 无发布者 | 🔵 根因锁定+修复已写,镜像重建中 | venv python 悬空软链实锤(见上);重建后需重跑 exploration 验证 |

**一句话**:三个 humble 真坑逐个实锤——SLAM 从"一启动就崩"推进到"cartographer 真运行",`/scan` 断点也已定位到
镜像构建 bug 并写好修复;重建镜像 → 重跑 exploration → 看 SLAM healthy 是下一步(注:重跑需等 GBPlanner 演示容器空出来,避免抢资源)。

> 说明:这些 humble 兼容修复(tomllib、空 launch 参数,加上模板 `%%` 编译 bug)都是给 world-model 作者的真实、可提交贡献,
> 已固化在 world-model 分支 `feat/gbplanner-gain-exploration-strategy`,物料见 `integration/world-model-PR/`。
