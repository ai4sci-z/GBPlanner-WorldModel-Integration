# Orchestration Sim Remaining Migration Design

## 1. Purpose

This document defines the remaining migration from the legacy Python
`orchestration/src` simulation control plane into the Go package under
`orchestration/sim`.

The target is not to rewrite `navlab.sim.*` or `navlab.common.*` runtime nodes.
Those runtime nodes may remain Python. The target is to move orchestration
ownership into Go:

- task registry and task lifecycle
- project and task config normalization
- runtime service/probe/rosbag planning and execution
- Docker/Gazebo/SITL orchestration
- doctor and acceptance gate summaries
- artifact manifest/finalization
- image build control

Go sim must call Python runtime only across process, config, ROS topic, and
artifact boundaries. Go sim must not import Python helper implementation.

## 2. Current State

Already migrated into `orchestration/sim`:

- Go module and Cobra CLI.
- Viper project config loader.
- root `config.toml` aligned with legacy `config.simulation.toml`.
- task YAML configs in `configs/tasks`.
- registry for `hover`, `exploration`, and `scan-robustness`.
- helper inventory under `internal/tasks/helpers`.
- normalized simulation runtime config with task YAML overrides.
- dry-run `task_plan.json` and `manifest.json` artifacts.
- generated dry-run runtime artifacts, with manifest hash entries.
- runtime service/probe/rosbag specs and Docker CLI backend.
- generic runtime runner wired into `navlab-sim run <task>` live execution.
- live gate/blocker evaluation from runtime artifacts:
  - runtime execution errors
  - probe output files
  - rosbag metadata required-topic counts
  - task-specific config checks
  - landing acceptance
- final artifact files:
  - `summary.json`
  - `summary.md`
  - `run_config.toml`
  - manifest hash entries
- static task doctor commands:
  - `hover-doctor`
  - `exploration-doctor`
  - `scan-robustness-doctor`
- real ROS runtime/probe scripts for live sim tasks:
  - FCU pose relay publishes `/slam/odom`, controller status, hover status,
    setpoint output, landing status, rangefinder evidence, scan stabilization
    status, airframe disturbance status, and IMU/scan relay topics.
  - Probes sample live ROS topics through `ros2 topic echo` or `rclpy`
    `std_msgs/String` subscriptions instead of writing planned JSON.
  - Rosbag records use isolated output directories per record.
- metric-depth parity evidence:
  - hover drift and altitude error from the live pose stream
  - FCU owner uniqueness and FCU mode-window status
  - exploration accepted-goal and path-length metrics
  - SLAM odometry sample count, tracking state, and jump-quality metrics
  - scan stabilization retained/rejected/floor-risk metrics
  - airframe disturbance profile sweep and mode-window metrics
  - final aggregation under `summary.json.gate_evaluation.metrics`
- live Go sim parity smoke runs:
  - `hover`: `status=ok`
  - `exploration`: `status=ok`
  - `scan-robustness`: `status=ok`
- image build command parity for:
  - `companion`
  - `slam`
  - `gazebo-sensor`
  - `official-baseline`
  - `all`
- Python sim control-plane source retired from `orchestration/src/tasks`.
- Python sim image build entry retired from `orchestration/src`.
- Python real task-doctor specs for `hover`, `exploration`,
  `scan-robustness`, and `motor-debug` live in
  `orchestration/src/workflows/real/task_specs.py`.
- partial helper generation and command planning for:
  - artifacts
  - rosbag profiles
  - landing
  - scan integrity
  - navlab models
  - official stack
  - sensors
  - SLAM
  - FCU controller
  - frame contract
  - SLAM hover
  - scan stabilization
  - exploration workflow
  - scan robustness workflow
  - motion

No legacy Python sim orchestration entry remains in the supported control-plane
path. Python still present under `orchestration/src` is real-mode orchestration
or shared configuration/runtime framework that remains until Rust real replaces
it.

Metric-depth parity is implemented as structured ROS evidence rather than as
Python helper imports. Runtime scripts publish JSON on status topics, probes
sample and parse those topics, and the final gate evaluation aggregates the
important fields into `summary.json`.

## 3. Non-Goals

- Do not create `orchestration/common`.
- Do not keep Python orchestration as the long-term implementation.
- Do not migrate real preflight/prepare into Go sim.
- Do not make Go sim import Python modules.
- Do not enable accidental live Docker/ROS side effects from commands that are
  documented as dry-run.
- Do not rewrite Python navlab runtime nodes unless a task explicitly requires
  runtime behavior changes.

## 4. Target Package Shape

The Go sim package should grow in layers:

```text
orchestration/sim/
  cmd/navlab-sim/
  config.toml
  configs/tasks/*.yaml
  internal/
    artifacts/
    config/
    runtime/
      specs.go
      docker_backend.go
      paths.go
      mode_policy.go
    tasks/
      registry.go
      runner.go
      hover.go
      exploration.go
      scan_robustness.go
      helpers/
    ui/
```

`internal/tasks/helpers` remains one package until a helper grows large enough
to justify its own package. Runtime backend code should not live inside helpers,
because helpers describe task-specific behavior while runtime owns service
lifecycle mechanics.

## 5. Runtime Backend Contract

The first missing base layer is a Go runtime backend equivalent to the active
Python contract:

- `ServiceSpec`: long-running service/container.
- `ProbeSpec`: one-shot command/probe.
- `RosbagSpec`: `ros2 bag record` task.
- `RuntimeHandle`: started process/container identity.
- `ProbeResult`: stdout/stderr/return code/log path.
- `RuntimeBackend`: `StartService`, `RunProbe`, `StartRosbag`, `Wait`,
  `Stop`, `Logs`.

The first Go backend is Docker CLI based, not a new SDK dependency. This keeps
the Go module small and makes shell-visible command parity easy to inspect.

Docker backend behavior:

- explicit image required for Docker service/probe
- explicit command required
- no hidden fallback to host process
- service logs and probe output can be written to artifact files
- container names stay task-specific and deterministic
- network defaults only when specified by spec or task plan

Process backend is not required for Go sim now. It belongs primarily to Rust
real, unless a future sim host-process runner is explicitly needed.

## 6. Config Schema Migration

`orchestration/sim/config.toml` already mirrors legacy project-level simulation
config. The next step is complete typed normalization:

- project-level:
  - router
  - SITL
  - sensor container
  - SLAM container
  - official baseline
  - landing
  - runtime backend
  - navlab image catalog
- sim runtime sections:
  - official maze X2
  - rangefinder/IMU
  - SLAM backend quality
  - FCU controller
  - frame contract
  - SLAM hover
  - motion gate
  - exploration gate
  - scan integrity gate
  - scan stabilization
  - airframe disturbance

Task YAML remains task-level override/config. Root `config.toml` remains
project-level config. The Go loader should normalize config precedence into a
typed request before any runner starts runtime side effects.

## 7. Task Lifecycle

Every sim task should support the same lifecycle:

```text
load project config
load task YAML
normalize task request
build runtime plan
write plan artifacts
if dry-run: stop here
generate runtime artifacts
start services/probes/rosbag through RuntimeBackend
wait/collect logs
evaluate gates/blockers
write summary + manifest
return task exit code
```

Doctor commands are task lifecycle subsets:

```text
hover-doctor
exploration-doctor
scan-robustness-doctor
```

They should use the same config, backend, artifact, and gate code as live runs.
They should not be separate ad hoc runners.

## 8. Python Retirement Boundary

Python under `navlab.sim.*`, `navlab.common.*`, and `navlab.real.*` is runtime
code, not orchestration control-plane code. It stays until a separate runtime
rewrite is explicitly requested.

Python under `orchestration/src` is legacy control-plane code and should leave
the repository when its responsibility is covered by Go sim or Rust real.

Delete order:

1. Remove generated caches immediately:
   - `orchestration/**/__pycache__`
   - `orchestration/.pytest_cache`
2. Removed in the Python sim retirement slice:
   - `orchestration/src/tasks/built_in/hover.py`
   - `orchestration/src/tasks/built_in/exploration.py`
   - `orchestration/src/tasks/built_in/scan_robustness.py`
   - `orchestration/src/tasks/workflows/exploration.py`
   - `orchestration/src/tasks/workflows/scan_robustness.py`
   - sim-only helpers under `orchestration/src/tasks/helpers`
3. Removed in the Python sim retirement slice:
   - `orchestration/config.simulation.toml`
   - `orchestration/configs/{hover,exploration,scan_robustness}.toml`
   - Python tests that import deleted sim modules
4. Audit remaining wrappers/docs that mention the retired Python sim entry:
   - `justfile` sim command wrappers that still call `orchestration/main.py`
   - historical config precedence docs that describe the pre-Go TOML split
5. Remove Python real orchestration only after Rust real is implemented:
   - `orchestration/src/workflows/real/*`
   - `orchestration/src/tasks/built_in/motor_debug.py`
   - `orchestration/src/tasks/fcu_bridge/*`
   - `orchestration/config.real.toml`
   - `orchestration/configs/{real_preflight,real_prepare,motor_debug}.toml`
6. Remove shared Python orchestration framework last:
   - `orchestration/main.py`
   - `orchestration/src/cli.py`
   - `orchestration/src/runtime/*`
   - `orchestration/src/configs/*`
   - `orchestration/src/tasks/base.py`
   - `orchestration/src/tasks/registry.py`
   - `orchestration/pyproject.toml`
   - `orchestration/uv.lock`

Important: do not delete individual Python helper files just because their pure
logic has a Go equivalent. The old Python sim workflows import helpers as a
connected graph, so individual deletion creates broken legacy imports without
removing the legacy entry point. Delete them in one sim-source retirement slice
after Go live execution and gate summaries pass.

## 9. Migration Order

### P0: Design and runtime base

- Write this design document.
- Add Go `internal/runtime` specs and Docker backend.
- Cover command construction and fake-runner behavior in tests.
- Keep CLI live execution disabled until task runner is explicit.

### P1: Config schema completion

- Port the remaining simulation `RunConfig` sections into Go structs.
- Preserve task YAML overrides.
- Add loader tests that compare required legacy defaults.
- Expose normalized runtime source claims in dry-run plan.

Status: complete for current hover/exploration/scan-robustness sim scope.

### P2: Runtime plan to spec conversion

- Convert `ExecutionPlan` service/probe/rosbag plans into runtime specs.
- Add artifact-relative path mapping.
- Add validation that plans missing image/command/profile fail before execution.

### P3: Artifact generation

- Generate runtime TOML/scripts/bridge/vendor/profile artifacts into run-scoped
  artifact directories.
- Keep SDF/param overlays behind explicit inputs because official baseline
  source still lives in a Docker image.
- Write manifest entries for generated artifacts and logs.

Status: dry-run artifact generation and manifest entries are complete; live log
entries remain part of P4/P5/P6.

### P4: Hover live runner

- Implement hover first because it exercises:
  - Gazebo/SITL official baseline
  - sensors
  - SLAM
  - FCU controller
  - frame contract
  - SLAM hover
  - landing
- Start with Docker service/probe orchestration and artifact collection.
- Port blocker evaluation after artifacts are available.

Status: runtime service/probe/rosbag orchestration, artifact-based blocker
evaluation, landing blocking, final artifact generation, and hover metric-depth
evidence are wired into the CLI. Hover metrics include drift, altitude error,
owner uniqueness, FCU mode-window evidence, and SLAM odometry quality fields.

### P5: Exploration live runner

- Reuse hover runtime stack.
- Add P8 exploration probe, motion/exploration gate evaluation, and optional
  mild disturbance profile.
- Port `motion` helper to at least doctor summary parity.

Status: runtime orchestration, generated P8 probe/script artifacts,
artifact-based blockers, landing blocking, final artifact generation, and P8
metric-depth evidence are wired. Exploration metrics include accepted goals,
minimum-goal contract, path length, minimum path-length contract, motion speed,
controller mode-window evidence, and SLAM odometry quality fields.

### P6: Scan robustness live runner

- Reuse hover/P8 runtime stack.
- Add P11/P12 runtime configs, disturbance profile sweep, live replay, FCU mode
  gate, and landing summary.

Status: runtime orchestration, generated P11/P12 artifacts, artifact-based
blockers, landing blocking, final artifact generation, and scan robustness
metric-depth evidence are wired. P11/P12 metrics include retained/rejected scan
ratios, floor-risk metrics, profile sweep status, airframe disturbance profile,
and FCU mode-window evidence.

### P7: Image build and final artifact behavior

- Build command parity for companion/slam/gazebo-sensor/official-baseline.
- Port final summary markdown and optional upload boundary if still required.

Status: image build command parity is complete in Go sim. `navlab-sim build`
supports `infra`, `runtime`, and `all` build groups, uses `--image` to select a
single image inside `infra` or `runtime`, reads the project-level image catalog
from `config.toml`, supports configured tag policy or `--tag` override, and
provides `--dry-run` command inspection. The Python `build` CLI command and
`orchestration/src/images.py` were removed.
Final summary markdown is already generated by live task finalization; upload
integration remains out of scope unless a future artifact transport is added.

## 10. Status Labels

Helper migration status should be precise:

- `planned`: no Go behavior yet.
- `ported_basic`: pure or low-side-effect behavior is ported.
- `ported_partial`: specs/plans/generators exist, but live parity is incomplete.
- `ported_live`: live runtime behavior exists and is testable through backend.
- `ported_full`: live behavior plus doctor/gate/artifact parity is complete.

Runtime side-effect helpers should keep `runtime_action=true`.

## 11. Acceptance Checks

Every migration slice must run:

```bash
cd orchestration/sim
go test ./...
go build ./cmd/navlab-sim
go run ./cmd/navlab-sim doctor
go run ./cmd/navlab-sim --artifact-root "$(mktemp -d)" run hover --dry-run
go run ./cmd/navlab-sim --artifact-root "$(mktemp -d)" run exploration --dry-run
go run ./cmd/navlab-sim --artifact-root "$(mktemp -d)" run scan-robustness --dry-run
```

Live parity checks are stricter and must not be replaced by dry-run:

```bash
cd orchestration/sim
go build ./cmd/navlab-sim
./navlab-sim run hover
./navlab-sim run exploration
./navlab-sim run scan-robustness
```

As of 2026-06-12, `hover`, `exploration`, and `scan-robustness` have passed live
Go sim runs with Docker/Gazebo/SITL/ROS services, probes, rosbags, landing
evidence, and artifact-based gate evaluation. Metric-depth parity is checked by
the structured status samples and the aggregated
`summary.json.gate_evaluation.metrics` section.

## 12. Risks

- The legacy Python task logic embeds large probe scripts. Go should not become
  a dumping ground for huge opaque Python strings unless that script is the
  runtime boundary itself.
- Docker/Gazebo/SITL startup failures must be reported as service contract
  failures, not generic command failures.
- Task YAML must stay readable and stable because it is the fast extension path.
- Full parity should be measured by generated summaries and blockers, not by
  matching internal implementation line-for-line.
