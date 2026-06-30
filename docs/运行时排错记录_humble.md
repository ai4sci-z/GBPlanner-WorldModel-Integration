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

## 坑 #3(下一个,待办):cartographer 收不到 `/scan`

- **证据**:run `20260630T075417Z` SLAM 日志反复 `Queue waiting for data: (0, scan)`。
- **现象**:cartographer 已运行,但没收到激光 `/scan` → 不出 `/slam/odom`/`map`。
- **方向(待查)**:gazebo-sensor / x2 虚拟串口扫描链是否把 `/scan` 发出来(humble 下传感器桥)。**今晚不追,记录待续。**

## 当前进度(用于汇报)

| 坑 | 状态 | 实测证据 |
|---|---|---|
| #1 tomllib(SLAM 头号崩溃) | ✅ 已修+验证 | run2 日志 tomllib 出现 0 次,SLAM 越过 |
| #2 空 launch 参数 | ✅ 已修+验证 | run2 `malformed` 0 次,cartographer_node 真启动 |
| #3 `/scan` 未到 cartographer | ⬜ 待办 | run2 日志 `waiting for data: scan` |

**一句话**:连修两个 humble 真 bug,把 SLAM 从"一启动就崩"推进到"cartographer 节点真正运行、只差激光数据"。
后续(`/scan` 链路 → SLAM healthy → frontier_lite 真指标 → 阶段4 端到端)留作下一步。

> 说明:这些 humble 兼容修复(tomllib、空 launch 参数,加上模板 `%%` 编译 bug)都是给 world-model 作者的真实、可提交贡献,
> 已固化在 world-model 分支 `feat/gbplanner-gain-exploration-strategy`,物料见 `integration/world-model-PR/`。
