# NavLab Runtime Package

`navlab` contains the Python runtime modules, ROS-facing helpers, sensor
simulation components, and runtime tests used by both simulation and real
orchestration. It is not the orchestration control plane. Go sim and Rust real
own task planning and execution policy.

## Scope

`navlab` owns:

- Runtime Python modules started inside containers or host processes.
- ROS helper code for SLAM, perception, MAVLink bridge nodes, and sensor
  adapters.
- Simulation sensor runtime components such as Gazebo X2, rangefinder, scan
  integrity, scan stabilization, and airframe disturbance helpers.
- Real companion nodes that publish normalized runtime evidence for real
  workflows.
- Runtime tests under `navlab/tests`.

`navlab` does not own:

- Simulation task registry or task YAML loading. See
  [`../orchestration/sim/README.md`](../orchestration/sim/README.md).
- Real task registry or safety workflow execution. See
  [`../orchestration/real/README.md`](../orchestration/real/README.md).
- Docker image build orchestration. See [`../docker/README.md`](../docker/README.md).
- Shared protobuf schema design. See
  [`../contracts/README.md`](../contracts/README.md).

## Layout

```text
navlab/
  common/
    perception/
    slam/
    contracts.py
    logging.py
    process_manager.py
    rosbag.py
  real/
    common/
    companion/
  sim/
    common/
    companion/
    gazebo_sensor/
  tests/
  config.toml
  pyproject.toml
```

- `common/` contains runtime helpers that are valid across sim and real, such as
  perception utilities, process helpers, rosbag topic handling, and SLAM runtime
  adapters.
- `sim/` contains simulation-specific runtime components.
- `real/` contains real-machine runtime components and companion nodes.
- `tests/` contains unit and ownership tests for runtime modules.
- `config.toml` is runtime package configuration used by launched runtime
  processes. It is distinct from `orchestration/sim/config.toml` and
  `orchestration/real/config.toml`.

## Configuration Boundary

Human-authored runtime configuration remains TOML/YAML. Runtime code may emit or
consume generated contract-compatible JSON where cross-language readers need a
stable schema.

Use these rules:

- Use `/workspace/...` paths for files referenced from inside containers.
- Use repository-relative paths such as `docker/profiles/...` for host tests and
  host utilities.
- Keep simulation sensor params under `docker/profiles` when they are mounted
  into containers.
- Keep task-level parameters in the owning orchestration package's
  `configs/tasks` directory.

## Runtime Contracts

Runtime modules should prefer stable evidence over implementation-specific
strings. Examples include:

- topic counts and topic freshness
- SLAM status and odometry quality
- FCU status and MAVLink evidence
- sensor source evidence
- artifact paths and summaries

Cross-language artifacts should align with [`../contracts/README.md`](../contracts/README.md).

## Development Commands

Run the runtime Python tests:

```bash
uv run pytest navlab/tests
```

Run a focused test while editing a runtime component:

```bash
uv run pytest navlab/tests/gazebo_sensor
uv run pytest navlab/tests/slam
uv run pytest navlab/tests/common
```

Run Python quality checks from the repository root:

```bash
./scripts/quality/format-python.sh
./scripts/quality/check-python.sh
```

## Maintenance Rules

- Keep sim-only behavior under `navlab/sim`.
- Keep real-only behavior under `navlab/real`.
- Put truly shared runtime utilities under `navlab/common` only when both sim
  and real can use them without pulling in mode-specific assumptions.
- Do not add orchestration task registry logic here.
- Do not make runtime modules depend on Go or Rust implementation details.
- Add or update ownership tests when moving ROS packages, Dockerfiles, profiles,
  or runtime modules.
