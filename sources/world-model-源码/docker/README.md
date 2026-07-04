# NavLab Docker Images

This directory owns the Docker assets used by the Go simulation
orchestrator. The image tree is intentionally grouped by runtime ownership so
future sim and real repositories can keep image definitions independent from
task code.

## Layout

```text
docker/
  images/
    base/
      ros-base.Dockerfile
    infra/
      ardupilot-sitl.Dockerfile
      fast-lio.Dockerfile
      gazebo-headless.Dockerfile
      mavlink-router.Dockerfile
    runtime/
      companion.Dockerfile
      gazebo-sensor.Dockerfile
      official-baseline.Dockerfile
      sim-python.Dockerfile
      slam.Dockerfile
  entrypoints/
  navlab_models/
  profiles/
  worlds/
```

- `images/base/` contains shared base images. `ros-base` is the current shared
  ROS base.
- `images/infra/` contains reusable simulation infrastructure images. These are
  not task-specific runtime containers.
- `images/runtime/` contains NavLab runtime images that run task services,
  probes, adapters, or compatibility entrypoints.
- `entrypoints/` contains container startup scripts mounted or copied into
  runtime containers.
- `profiles/` contains host-side runtime inputs such as SITL params, rosbag
  topic profiles, and sensor params. Containers mount this directory at
  `/workspace/profiles`.
- `worlds/` and `navlab_models/` contain Gazebo world/model assets mounted into
  the Gazebo container.

## Image Groups

The Go sim build command exposes three build groups plus `all`.

| Group | Image kind | Repository | Dockerfile |
| --- | --- | --- | --- |
| `base` | `ros-base` | `navlab/ros-base` | `images/base/ros-base.Dockerfile` |
| `infra` | `ardupilot-sitl` | `navlab/ardupilot-sitl` | `images/infra/ardupilot-sitl.Dockerfile` |
| `infra` | `mavlink-router` | `navlab/mavlink-router` | `images/infra/mavlink-router.Dockerfile` |
| `infra` | `gazebo-headless` | `navlab/gazebo-headless` | `images/infra/gazebo-headless.Dockerfile` |
| `infra` | `fast-lio` | `navlab/fast-lio` | `images/infra/fast-lio.Dockerfile` |
| `runtime` | `companion` | `navlab/companion` | `images/runtime/companion.Dockerfile` |
| `runtime` | `slam` | `navlab/slam-cartographer` | `images/runtime/slam.Dockerfile` |
| `runtime` | `gazebo-sensor` | `navlab/gazebo-sensor` | `images/runtime/gazebo-sensor.Dockerfile` |
| `runtime` | `official-baseline` | `navlab/official-baseline` | `images/runtime/official-baseline.Dockerfile` |

`sim-python.Dockerfile` is kept as a runtime compatibility image. It is not part
of the default `runtime` build group unless it is added to
`orchestration/sim/config.toml` and the Go image registry.

## Build Entrypoint

Use the Go sim CLI as the only supported image build entrypoint. Run it from
`orchestration/sim`:

```bash
cd orchestration/sim

go run ./cmd/navlab-sim build base
go run ./cmd/navlab-sim build infra
go run ./cmd/navlab-sim build runtime
go run ./cmd/navlab-sim build all
```

Use `--dry-run` to inspect the exact Docker commands without building:

```bash
go run ./cmd/navlab-sim build base --dry-run
go run ./cmd/navlab-sim build infra --dry-run
go run ./cmd/navlab-sim build runtime --dry-run
```

Build one image inside `infra` or `runtime` with `--image`:

```bash
go run ./cmd/navlab-sim build infra --image gazebo-headless
go run ./cmd/navlab-sim build infra --image fast-lio
go run ./cmd/navlab-sim build runtime --image companion
go run ./cmd/navlab-sim build runtime --image official-baseline
```

`--image` is only valid for `infra` and `runtime`. `base` is a separate group,
so build `ros-base` with:

```bash
go run ./cmd/navlab-sim build base
```

## ROS Distro Selection

Supported distros are:

- `humble`
- `jazzy`

Selection precedence:

1. CLI `--distro`
2. `NAVLAB_SIM_DISTRO`
3. image-level `distro` in `orchestration/sim/config.toml`
4. global `[navlab.images].distro`
5. fallback `humble`

Examples:

```bash
NAVLAB_SIM_DISTRO=humble go run ./cmd/navlab-sim build infra
NAVLAB_SIM_DISTRO=jazzy go run ./cmd/navlab-sim build runtime
go run ./cmd/navlab-sim build runtime --distro jazzy
```

The selected distro is passed to Docker as `ROS_DISTRO=<distro>`.

## Tag Policy

Image repositories use the `navlab/*` namespace. Tags are resolved by the Go sim
builder from `[navlab.images].tag_policy` in `orchestration/sim/config.toml`.

Supported policies:

- `distro-git-commit`: `<distro>-<12-char git commit>`
- `distro-datetime`: `<distro>-<UTC timestamp>`
- `distro-latest`: `<distro>-latest`

The default policy is `distro-git-commit`.

Use `--tag` to override the configured policy for local builds:

```bash
go run ./cmd/navlab-sim build base --tag local
go run ./cmd/navlab-sim build infra --image mavlink-router --tag humble-dev
```

The resolved tag is also passed as `INFRA_TAG=<tag>`, so runtime Dockerfiles can
refer to infra images from the same build set.

## Build Context And Config

Image metadata lives in `orchestration/sim/config.toml` under
`[navlab.images.*]`. Each image entry owns:

- `group`: `base`, `infra`, or `runtime`
- `dockerfile`: path under `docker/images/...`
- `context`: build context, currently the workspace root
- `target`: optional Docker build target for multi-stage runtime images
- `repository`: final image repository

The default build context is the repository root because Dockerfiles copy code,
ROS packages, `docker/` assets, and selected `third_party/` sources.

Before building images that copy vendored source trees, make sure submodules are
available:

```bash
git submodule update --init --recursive
```

## Profiles

Host-side profile files live in `docker/profiles/`.

Current checked-in profiles:

- `navlab-sitl-external-nav.parm`: ArduPilot SITL params for external nav.
- `x2-vendor-sim.yaml`: X2 virtual sensor ROS params.
- `rosbag-topics.txt`: generic rosbag profile.
- `navlab-rosbag-topics.txt`: NavLab sim rosbag profile.
- `navlab-hover-foxglove-lite-topics.txt`: hover replay topic profile.
- `navlab-exploration-foxglove-lite-topics.txt`: exploration replay topic
  profile.

Containers should keep using `/workspace/profiles/...`. Host code and tests
should refer to `docker/profiles/...`.

## Compose Defaults

`compose/docker-compose.yaml` defaults to the `navlab/*:humble-latest` image set
for manual local runs. It mounts:

- `./docker/profiles` to `/workspace/profiles`
- `./docker/worlds` to `/workspace/worlds`
- `./docker/navlab_models` to `/workspace/models`
- `./docker/entrypoints/*.sh` to `/usr/local/bin/*.sh`

Use environment variables such as `SITL_IMAGE`, `ROUTER_IMAGE`,
`NAVLAB_GAZEBO_SENSOR_IMAGE`, and `FAST_LIO_IMAGE` to point compose at a custom
tag.

## Adding Or Changing Images

When adding a new simulation image:

1. Put the Dockerfile under the correct group in `docker/images/`.
2. Name it `<image-kind>.Dockerfile`.
3. Add or update the `[navlab.images.<key>]` entry in
   `orchestration/sim/config.toml`.
4. Add the image kind to the Go image registry if it should be buildable through
   `navlab-sim build`.
5. Add or update tests for build resolution and ownership checks.
6. Keep host profile inputs in `docker/profiles/` and container paths under
   `/workspace/profiles/`.

Do not put task configs in this directory. Simulation task configs live under
`orchestration/sim/configs/tasks/`.
