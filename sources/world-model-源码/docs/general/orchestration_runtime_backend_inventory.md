# Orchestration Runtime Backend Inventory

## 2026-06-08 baseline

这个清单是 `docs/general/orchestration_runtime_backend_refactor_todo.md` 的 P0 迁移基线，用来避免 RuntimeBackend 重构时把已经验证过的 Docker 主线改坏。

## Direct Docker dependency files

当前直接触达 `python_on_whales` / `DockerClient` / `DockerException` 的主线文件：

```text
orchestration/src/host.py
orchestration/src/tasks/acceptance.py
orchestration/src/tasks/airframe_disturbance_gate.py
orchestration/src/tasks/build.py
orchestration/src/tasks/exploration_gate.py
orchestration/src/tasks/fcu_controller.py
orchestration/src/tasks/frame_contract.py
orchestration/src/tasks/hover.py
orchestration/src/tasks/hover_diagnostic.py
orchestration/src/tasks/hover_slam_diagnostic.py
orchestration/src/tasks/motion_gate.py
orchestration/src/tasks/official_baseline.py
orchestration/src/tasks/official_maze_x2.py
orchestration/src/tasks/rangefinder_imu.py
orchestration/src/tasks/scan_integrity_gate.py
orchestration/src/tasks/scan_stabilization_gate.py
orchestration/src/tasks/slam_backend.py
orchestration/src/tasks/slam_hover.py
```

新增兼容层：

```text
orchestration/src/runtime/docker_backend.py
```

## High-value migration targets

优先迁移活跃 P10/P11/P12 链路，不回头维护已经验证过但不再主线使用的旧 just 快捷入口。

```text
P10 scan_integrity_gate
  rosbag container: navlab-p10-rosbag
  migrated sample: rosbag start/wait/log goes through DockerBackend
  shared needs: rosbag recorder, container log capture, runtime probe output

P11 scan_stabilization_gate
  rosbag container: navlab-p11-rosbag
  migrated sample: rosbag start/wait/log goes through DockerBackend
  shared needs: container log capture, replay probe output

P12 airframe_disturbance_gate
  waits P11 rosbag container from delegated P11 path
  direct calls: DockerClient().wait / logs
  shared needs: delegated rosbag handle, replay analysis probe, backend summary fields
```

## Shared Docker patterns to extract

```text
compose lifecycle
  host._compose_client
  host._compose_up
  host._compose_stop
  host._compose_logs
  host._compose_ps_status

long-running service containers
  host._start_official_baseline_container
  host._start_slam_container
  host._start_companion_container
  official_maze_x2 / rangefinder_imu / slam_backend service starts

one-shot runtime/probe commands
  host._docker_run_runtime_command
  host._docker_run_ros_shell_capture
  host._docker_exec_runtime_command

log capture
  host._capture_stack_logs
  host._capture_compose_service_log
  host._capture_official_baseline_log
  task-level _capture_container_log helpers

rosbag recorder containers
  P3/P5/P6/P7/P8/P10/P11 recorder helpers share the same start/wait/log/remove shape
```

## Backend-independent contracts

这些逻辑不应该知道 Docker 或 process backend：

- topic profile 选择和 required topic 判断
- TF/static TF completeness 判断
- scan attitude integrity/stabilization 判断
- FCU owner、GUIDED mode window、setpoint ownership 判断
- `uses_gazebo_truth_as_input=false` 和 `set_pose_count=0` 判断
- summary schema 和 blocker 语义
- Foxglove full/lite artifact 生成后的上传逻辑

## First implemented slice

已落地的样板：

```text
orchestration/src/runtime/specs.py
  ServiceSpec / RosbagSpec / ProbeSpec / RuntimeHandle / ProbeResult

orchestration/src/runtime/backend.py
  RuntimeBackend protocol

orchestration/src/runtime/docker_backend.py
  DockerBackend start_service / start_rosbag / run_probe / wait / stop / logs

orchestration/src/runtime/process_manager.py
  host-side ManagedProcess / ProcessManager for cwd/env/log/process-group lifecycle

orchestration/src/runtime/process_backend.py
  ProcessBackend start_service / start_rosbag / run_probe / wait / stop / logs / dry-run, delegated to ProcessManager

orchestration/src/runtime/paths.py
  WorkspacePathMapper for docker / process path mapping

orchestration/src/project_config.py
  [orchestration.runtime] backend config parser with NAVLAB_RUNTIME_BACKEND override

orchestration/src/host.py
  _capture_compose_service_log now uses DockerBackend.logs as a low-risk migration sample

orchestration/src/tasks/scan_integrity_gate.py
  P10 rosbag recorder start/wait/log now uses DockerBackend + RuntimeHandle as the first active-gate migration sample

orchestration/src/tasks/scan_stabilization_gate.py
  P11 rosbag recorder start/wait/log now uses DockerBackend + RuntimeHandle

orchestration/src/host.py
  _docker_run_ros_shell_capture now builds a ProbeSpec and delegates to DockerBackend.run_probe

P10/P11/P12 summaries
  top-level summary now records runtime_backend and runtime_backend_summary
```
