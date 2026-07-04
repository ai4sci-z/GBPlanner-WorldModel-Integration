# World Model

World Model is the NavLab autonomy and orchestration workspace for indoor,
GPS-denied drone simulation and real-machine validation. The repository is
split into runtime code, simulation orchestration, real-machine orchestration,
shared contracts, Docker assets, scripts, and design documentation.

This README is the project-level entrypoint. Detailed ownership, commands, and
maintenance rules live in the README for each subsystem.

## System Boundaries

| Area | Owner | Purpose |
| --- | --- | --- |
| [`navlab/`](navlab/README.md) | Python runtime package | Container-side and host-side runtime nodes, ROS helpers, SLAM adapters, sensor simulation, and runtime tests. |
| [`orchestration/sim/`](orchestration/sim/README.md) | Go sim orchestration | Simulation task registry, YAML task loading, Docker runtime planning, image build orchestration, artifacts, and TUI replay. |
| [`orchestration/real/`](orchestration/real/README.md) | Rust real orchestration | Real-machine task registry, preflight/prepare/doctor workflows, MAVLink motor-debug execution, structured logging, and real artifacts. |
| [`contracts/`](contracts/README.md) | Shared protobuf contracts | Language-neutral request/result/runtime/safety/sensor contracts for Go, Rust, and Python clients. |
| [`docker/`](docker/README.md) | Simulation image assets | Base, infra, and runtime Dockerfiles plus Gazebo worlds, models, entrypoints, and runtime profiles. |
| [`scripts/`](scripts/README.md) | Developer automation | Quality checks, formatters, contract codegen, operations helpers, and standalone command tools. |
| [`docs/`](docs/README.md) | Design record | Roadmaps, design docs, TODOs, decisions, and migration notes. |

## Architecture

The repository intentionally separates orchestration from runtime behavior.

- `orchestration/sim` is the Go control plane for simulation.
- `orchestration/real` is the Rust control plane for real hardware.
- `navlab` contains runtime modules and ROS-facing code that those control
  planes start, inspect, or validate.
- `contracts/proto` defines shared schema boundaries. Generated code is checked
  in under `contracts/gen` for Go, Rust, and Python users.
- Docker image definitions live under `docker/images`, while sim task configs
  live under `orchestration/sim/configs/tasks`.

The long-term direction is that sim and real can move into separate
repositories while continuing to depend on shared contracts and compatible
artifact formats.

## Quick Start

Install or initialize the repository toolchain first, then run the narrow check
for the subsystem you are changing.

```bash
git submodule update --init --recursive
```

Simulation orchestration:

```bash
cd orchestration/sim
go test ./...
go run ./cmd/navlab-sim doctor
go run ./cmd/navlab-sim list-tasks
```

Real orchestration:

```bash
cd orchestration/real
cargo test
cargo run -- doctor
cargo run -- list-tasks
```

Runtime Python package:

```bash
uv run pytest navlab/tests
```

Project-level quality checks:

```bash
./scripts/quality/check-contracts.sh
./scripts/quality/check-go.sh
./scripts/quality/check-rust.sh
./scripts/quality/check-python.sh
```

## Documentation Map

Start with these documents for implementation work:

- Simulation task and Docker runtime work:
  [`orchestration/sim/README.md`](orchestration/sim/README.md) and
  [`docker/README.md`](docker/README.md)
- Real-machine workflow work:
  [`orchestration/real/README.md`](orchestration/real/README.md)
- Runtime Python or ROS node work:
  [`navlab/README.md`](navlab/README.md)
- Cross-language schema work:
  [`contracts/README.md`](contracts/README.md)
- Design rationale and roadmap:
  [`docs/README.md`](docs/README.md) and [`docs/decisions.md`](docs/decisions.md)

## Repository Rules

- Keep sim-only orchestration behavior in `orchestration/sim`.
- Keep real-only orchestration behavior in `orchestration/real`.
- Keep shared runtime code in `navlab/common`; avoid adding orchestration
  helpers there.
- Keep task configs under each orchestration package's `configs/tasks`.
- Keep human-authored config in TOML/YAML and normalize it into domain structs
  or generated contracts at runtime boundaries.
- Keep Dockerfiles under `docker/images/{base,infra,runtime}` and profile
  inputs under `docker/profiles`.
- Update the nearest README when changing ownership boundaries, commands,
  configuration layout, or artifact contracts.

## Artifacts

Runtime outputs are written under `artifacts/`, with sim and real using separate
artifact roots from their project configs. Generated artifacts should be treated
as evidence, not source. Cross-language artifacts should prefer the protobuf
contract shapes documented in [`contracts/README.md`](contracts/README.md).
