# NavLab Simulation Orchestration

`orchestration/sim` is the Go control plane for simulation tasks. It owns the
simulation task registry, YAML task config loading, Docker runtime planning,
artifact writing, generated contract emission, image build orchestration, and
terminal replay UI.

## Scope

This package owns:

- Go CLI entrypoint `navlab-sim`.
- Project config loading from `config.toml` with Viper-compatible TOML shape.
- Task config loading from `configs/tasks/*.yaml`.
- Built-in simulation task registry for `hover`, `exploration`, `navigation`,
  and `scan-robustness`.
- Docker runtime service/probe plans.
- Runtime artifact generation and task result summaries.
- TUI replay for simulation artifact directories.
- Docker image build command parity for base, infra, and runtime images.

This package does not own:

- Python runtime node implementations. See [`../../navlab/README.md`](../../navlab/README.md).
- Dockerfile content and profile assets. See [`../../docker/README.md`](../../docker/README.md).
- Real-machine task execution. See [`../real/README.md`](../real/README.md).
- Protobuf schema definitions. See [`../../contracts/README.md`](../../contracts/README.md).

## Layout

```text
orchestration/sim/
  cmd/navlab-sim/
  configs/tasks/
  internal/
    artifacts/
    config/
    images/
    runtime/
    tasks/
    tui/
    ui/
  config.toml
  go.mod
```

- `cmd/navlab-sim/` contains Cobra CLI wiring.
- `internal/config/` loads project TOML and task YAML.
- `internal/tasks/` owns task registry, planning, runtime specs, blocker
  evaluation, and summary generation.
- `internal/runtime/` owns Docker runtime command construction.
- `internal/images/` owns Docker image build resolution.
- `internal/artifacts/` writes dry-run and runtime artifacts.
- `internal/tui/` owns replay UI and live event presentation.

## Commands

Run from `orchestration/sim`.

```bash
go run ./cmd/navlab-sim doctor
go run ./cmd/navlab-sim list-tasks
go run ./cmd/navlab-sim show-task hover
```

Plan a task without starting Docker services:

```bash
go run ./cmd/navlab-sim run hover --dry-run
go run ./cmd/navlab-sim run exploration --dry-run
go run ./cmd/navlab-sim run navigation --dry-run
go run ./cmd/navlab-sim run scan-robustness --dry-run
```

Open a replay TUI for a generated artifact directory:

```bash
go run ./cmd/navlab-sim tui ../../artifacts/sim/RUN_ID
```

Build and upload a Foxglove-lite replay:

```bash
go run ./cmd/navlab-sim foxglove build-replay 20260615T082821Z --task hover
go run ./cmd/navlab-sim foxglove upload 20260615T082821Z --task hover --dry-run
go run ./cmd/navlab-sim foxglove upload 20260615T082821Z --task hover --force
```

`build-replay` reads the task raw MCAP, applies
`docker/profiles/navlab-*-foxglove-lite-topics.txt`, writes
`rosbag_foxglove/rosbag_foxglove_0.mcap`, and validates the visualization-only
`/navlab/official_maze/map` overlay that was live-published into the raw rosbag.
Compressed raw inputs such as `hover_rosbag_0.mcap.zstd` are stream-read without
writing a decompressed raw copy. `upload` is lite-only: it refuses raw task MCAPs and fails if
`foxglove_replay_summary.json` does not prove every `overlay` and `required`
topic is present.

Build simulation images through the Go entrypoint:

```bash
go run ./cmd/navlab-sim build base
go run ./cmd/navlab-sim build infra
go run ./cmd/navlab-sim build runtime
go run ./cmd/navlab-sim build all
```

See [`../../docker/README.md`](../../docker/README.md) for Docker image layout,
tag policy, distro selection, and single-image build examples.

## Configuration

Project-level configuration lives in `config.toml`.

Important sections:

- `[orchestration]`: must identify `family = "sim"` and
  `implementation = "go"`.
- `[orchestration.runtime]`: must use simulation mode and Docker backend.
- `[paths]`: workspace root, artifact root, and task config directory.
- `[navlab.images]`: image tag policy and image definitions.
- task-specific runtime sections such as `[landing]`, `[sitl]`, `[slam]`,
  `[nav2]`, `[navigation_adapter]`, `[navigation_mission]`, and
  `[official_baseline]`.

Task configs live under `configs/tasks/*.yaml`. Each task config declares:

- `id`
- `family`
- `description`
- `capabilities`
- `task` defaults
- task-specific parameter blocks

Current built-in tasks:

- `hover`
- `exploration`
- `navigation`
- `scan-robustness`

### Navigation Task

`navigation` is the P13 Nav2-backed indoor navigation gate. Its runtime chain is:

```text
NavigateToPose
  -> /cmd_vel_nav
  -> /navlab/fcu/setpoint/intent
  -> navlab-fcu-controller
  -> /ap/v1/cmd_vel
```

The task waits for controller, SLAM, map and costmap readiness before sending
goals. Its timeout is a failure deadline, not a required runtime. A successful
run finishes after the navigation gate, landing gate and artifact flush pass.

The current accepted live reference is:

```text
artifacts/sim/navigation/20260614T062658Z/summary.json
```

That run passed with `TASK_STATUS_OK`, empty blockers, final landing acceptance,
and valid rosbag profiles.

## Contracts And Artifacts

The sim orchestrator writes artifacts under the configured sim artifact root,
currently `../../artifacts/sim`. Generated files include runtime plans, task
requests/results, summaries, and replay inputs.

Cross-language outputs should use generated Go protobuf types from
`navlab/contracts/gen/go` where possible. Contract definitions and regeneration
commands are documented in [`../../contracts/README.md`](../../contracts/README.md).

## Development Commands

Format and lint affected Go files:

```bash
../../scripts/quality/format-go.sh --scope modified
```

Run Go tests:

```bash
go test ./...
```

Run the Go quality profile from the repository root:

```bash
./scripts/quality/check-go.sh
```

Verify a Docker image build command without building:

```bash
go run ./cmd/navlab-sim build infra --image gazebo-headless --distro jazzy --tag local --dry-run
```

## Maintenance Rules

- Keep task registration explicit in the Go task registry.
- Keep task configs in YAML under `configs/tasks`.
- Keep project-level config in `config.toml`.
- Keep Dockerfile ownership in `docker/images`, not under this package.
- Do not add real-machine behavior or hardware safety policy here.
- Add tests when changing config loading, task registry behavior, image build
  resolution, runtime specs, artifact schema, or TUI event parsing.
