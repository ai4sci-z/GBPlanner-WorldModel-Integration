# Orchestration Legacy Helper 深拆 TODO

## 背景

当前 orchestration 的 task 表面已经收窄到少数 built-in 入口：

- `build`
- `doctor`
- `hover`
- `exploration`
- `exploration-doctor`
- `real-preflight-doctor`
- `scan-robustness`
- `scan-robustness-doctor`

旧 P-stage task class 已经不再作为 runnable task 暴露；legacy helper 深拆已执行为 `orchestration/src/tasks/helpers/` 和 `orchestration/src/tasks/workflows/` 两层。

这个 TODO 记录本次迁移的完成标准：built-in task 不再 import `src.tasks.legacy`，legacy 包被删除，后续只在 helper/workflow 包内继续做函数级小重排。

## 目标

- built-in task 只表达任务流程，不依赖 legacy 模块名。
- P8 exploration 和 P12 scan robustness 继续作为核心 built-in 验收入口。
- P9/P10/P11 的可复用能力沉淀为 helper，不再保留独立旧 task 语义。
- helper 按职责拆分到稳定模块，例如 artifact、profile、runtime service、sensor、scan、SLAM、FCU、frame、motion。
- 最终删除 `orchestration/src/tasks/legacy/`，不保留兼容包。

## 不做什么

- [x] 不在这一步改变 P8/P12 gate 判断语义。
- [x] 不重新引入 P-stage CLI task。
- [x] 不把 helper 深拆和 runtime real/sim 分流混成一个大改。
- [x] 不为了删文件放宽 Gazebo truth、`set_pose`、FCU owner、SLAM feedback 等验收约束。
- [x] 不在 helper 尚未迁移完成时删除仍被 built-in 使用的 legacy 模块。

## 当前状态

legacy 包已删除；`TaskRegistry`、`TASK_NAME`、`OrchestrationTask` 只出现在真正的 task 入口里。

当前结构：

- `tasks/workflows/exploration.py`: P8 exploration 主流程。
- `tasks/workflows/scan_robustness.py`: P12 scan robustness 主流程和扰动 profile 处理。
- `tasks/helpers/artifacts.py`: JSON/text artifact 写入和文件 hash。
- `tasks/helpers/rosbag_profiles.py`: rosbag profile topic、metadata counts、profile validation。
- `tasks/helpers/official_stack.py`: 官方 baseline/runtime stack helper。
- `tasks/helpers/navlab_models.py`: 官方 maze + X2 overlay/profile helper。
- `tasks/helpers/sensors.py`: rangefinder/IMU/X2 model overlay helper。
- `tasks/helpers/slam.py`: SLAM backend 配置、probe、summary helper。
- `tasks/helpers/fcu.py`: FCU controller、owner、状态机相关 helper。
- `tasks/helpers/frame_contract.py`: frame contract probe/runtime config helper。
- `tasks/helpers/motion.py`: bounded motion helper。
- `tasks/helpers/slam_hover.py`: SLAM hover、baseline env、setup source、summary helper。
- `tasks/helpers/scan_integrity.py`: P10 scan integrity summary/metric helper。
- `tasks/helpers/scan_stabilization.py`: P11 scan stabilization/replay helper。

当前 built-in 直接依赖：

- `built_in/exploration.py` -> `workflows/exploration.py`
- `built_in/scan_robustness.py` -> `workflows/scan_robustness.py`

## P0：冻结深拆前基线

目标：先确认“没有隐藏旧 task”这个状态是可验证的。

### 任务

- [x] 保留并升级回归测试：源码和测试不得 import legacy。
- [x] 固化 `TaskRegistry.names()` 期望，只包含当前 built-in task。
- [x] 生成 legacy helper import graph，标记从 P8/P12 roots 可达的模块。
- [x] 列出 tests 中直接 import legacy helper 的位置，并随迁移改到 helper/workflow import。

### 验收

- [x] legacy 包已删除，不再需要检查其中是否有 task class。
- [x] CLI task list 只出现当前 built-in task。
- [x] 依赖图已收敛到 helper/workflow 包，没有立即可删但未删的 legacy helper。

## P1：抽 artifact/profile 基础 helper

目标：先拆最底层、最无业务语义的通用函数，降低后续模块互相 import 的复杂度。

### 任务

- [x] 抽出 JSON/text 写入 helper。
- [x] 抽出文件 hash helper。
- [x] 抽出 rosbag profile topic 解析和校验 helper。
- [x] 抽出 rosbag metadata counts/load helper。
- [x] 把相关测试从 legacy import 改到新 helper 模块。

### 候选位置

- `orchestration/src/tasks/helpers/artifacts.py`
- `orchestration/src/tasks/helpers/rosbag_profiles.py`

### 验收

- [x] `official_stack.py`、`navlab_models.py` 不再定义纯 artifact/profile 通用函数。
- [x] built-in 行为不变。
- [x] 相关单测通过。

## P2：抽 official stack 和环境 bringup helper

目标：把官方 baseline、maze、X2 overlay、setup source 这些“运行环境准备”能力从旧 P-stage 文件名里移出来。

### 任务

- [x] 抽 official baseline runtime config/helper 到 `helpers/official_stack.py`。
- [x] 抽 maze/X2 overlay 写入 helper 到 `helpers/navlab_models.py` / `helpers/sensors.py`。
- [x] 抽 bridge override helper 到 `helpers/navlab_models.py`。
- [x] 抽 official setup source 和 baseline env helper 到 `helpers/slam_hover.py` 相关 helper。
- [x] 明确这些 helper 继续消费显式 runtime config，不引入 real/sim 隐式 fallback。

### 候选位置

- `orchestration/src/tasks/helpers/official_stack.py`
- `orchestration/src/tasks/helpers/navlab_models.py`

### 验收

- [x] `workflows/exploration.py` 和 `workflows/scan_robustness.py` 不再从 legacy 模块 import 通用环境 helper。
- [x] real/sim mode 分流仍由 runtime 配置决定，不藏在 helper 默认值里。

## P3：抽 sensor/scan helper

目标：让 P10/P11/P12 的 scan 能力成为可复用 helper，而不是通过旧 gate 模块互相调用。

### 任务

- [x] 抽 scan integrity metric 和 summary builder 到 `helpers/scan_integrity.py`。
- [x] 抽 scan stabilization replay/profile helper 到 `helpers/scan_stabilization.py`。
- [x] 抽 airframe disturbance profile sweep helper 到 `workflows/scan_robustness.py`。
- [x] 抽 motor output、tilt、scan 水平复原相关 summary helper 到 scan helper/workflow。
- [x] 把 P12 对 P11/P10 旧模块的 import 改成新 helper import。

### 候选位置

- `orchestration/src/tasks/helpers/scan_integrity.py`
- `orchestration/src/tasks/helpers/scan_stabilization.py`
- `orchestration/src/tasks/helpers/airframe_profiles.py`

### 验收

- [x] `workflows/scan_robustness.py` 不再 import legacy `scan_stabilization_gate.py`。
- [x] `helpers/scan_stabilization.py` 不再 import legacy `scan_integrity_gate.py`。
- [x] P12 scan robustness doctor/acceptance 测试仍覆盖倾斜扰动场景。

## P4：抽 FCU/SLAM/frame/motion helper

目标：把 P4-P7 的 prerequisites 和 probe 能力拆为稳定 helper，供 P8/P12 组合使用。

### 任务

- [x] 抽 FCU owner、arming/mode、setpoint owner、状态机 summary helper 到 `helpers/fcu.py`。
- [x] 抽 SLAM backend probe 和 quality summary helper 到 `helpers/slam.py` / `helpers/slam_hover.py`。
- [x] 抽 frame contract runtime config/probe helper 到 `helpers/frame_contract.py`。
- [x] 抽 bounded motion probe/helper 到 `helpers/motion.py`。
- [x] 把 exploration 主流程改为组合这些 helper，而不是 import 旧 P4-P7 文件。

### 候选位置

- `orchestration/src/tasks/helpers/fcu.py`
- `orchestration/src/tasks/helpers/slam.py`
- `orchestration/src/tasks/helpers/frame_contract.py`
- `orchestration/src/tasks/helpers/motion.py`

### 验收

- [x] `workflows/exploration.py` 不再 import legacy P4-P7 文件。
- [x] P8 exploration doctor/acceptance 行为不变。

## P5：重写 built-in 入口依赖

目标：built-in task 入口只依赖新 helper，不再依赖 legacy root module。

### 任务

- [x] 把 `built_in/exploration.py` 的实现目标从 `legacy.exploration_gate` 改到新 exploration workflow helper。
- [x] 把 `built_in/scan_robustness.py` 的实现目标从 `legacy.airframe_disturbance_gate` 改到新 scan robustness workflow helper。
- [x] 新 workflow helper 保持使用 runtime backend 和 runtime mode 显式参数。
- [x] 更新 CLI smoke test 和 task registry 测试。

### 验收

- [x] `rg "src.tasks.legacy" orchestration/src/tasks/built_in` 无结果。
- [x] `exploration`、`exploration-doctor`、`scan-robustness`、`scan-robustness-doctor` 仍可运行。
- [x] task registry surface 不变。

## P6：删除 legacy helper 文件

目标：只有当依赖图确认不可达时才删除文件。

### 任务

- [x] 删除已无 import 的 legacy helper 文件。
- [x] 删除 tests 中对 legacy helper 的 import。
- [x] 删除 `orchestration/src/tasks/legacy/__init__.py`。
- [x] 增加回归测试：源码中不得再 import `src.tasks.legacy`。
- [x] 更新 docs/README 和相关 TODO 状态。

### 验收

- [x] `rg "src.tasks.legacy" orchestration/src orchestration/tests` 无结果。
- [x] `find orchestration/src/tasks/legacy -type f` 无业务 helper 文件，或 legacy 目录已删除。
- [x] orchestration 单测通过。
- [x] CLI/just smoke 通过。

## 最终验收

- [x] `TaskRegistry.names()` 只包含当前 built-in task。
- [x] P8 exploration 和 P12 scan robustness 是主线验收入口。
- [x] P9/P10/P11 能力已经沉淀为 helper，不再体现为 runnable task。
- [x] built-in task 不 import legacy。
- [x] legacy helper 目录不存在。
- [x] full orchestration tests 通过。
