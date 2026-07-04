# NavLab Real Orchestration

`orchestration/real` is the Rust control plane for real-machine workflows. It
owns real task registration, preflight checks, prepare workflow execution,
doctor chains, MAVLink transport for motor-debug, structured logging, and real
task artifacts.

## Scope

This package owns:

- Rust CLI entrypoint `navlab-real`.
- Project config loading from `config.toml`.
- Real task config loading from `configs/tasks/*.yaml`.
- Real task registry, currently focused on `motor-debug`.
- Preflight, prepare, common doctor, task doctor, and doctor-chain workflows.
- MAVLink connection, heartbeat/ACK handling, GUIDED/arm/hold/disarm command
  flow for supported real tasks.
- Structured console/file logging through `tracing`.
- Generated contract usage through the `navlab-contracts` Rust crate.

This package does not own:

- Python runtime node implementations. See [`../../navlab/README.md`](../../navlab/README.md).
- Simulation orchestration. See [`../sim/README.md`](../sim/README.md).
- Docker image build orchestration. See [`../../docker/README.md`](../../docker/README.md).
- Protobuf schema definitions. See [`../../contracts/README.md`](../../contracts/README.md).

## Layout

```text
orchestration/real/
  benches/
  configs/tasks/
  src/
    logging/
    runtime/
    tasks/
    workflows/
    cli.rs
    config.rs
    contracts.rs
    main.rs
  Cargo.toml
  config.toml
```

- `src/cli.rs` defines the Clap command surface.
- `src/config.rs` loads project and task configuration.
- `src/tasks/` owns task types, registry, and `motor-debug` behavior.
- `src/runtime/` owns process and MAVLink runtime integration.
- `src/workflows/` owns preflight, prepare, task doctor, common doctor, and
  doctor-chain behavior.
- `src/logging/` owns tracing subscriber setup, JSON/human formatting, file
  logging, and rotation.

## Commands

Run from `orchestration/real`.

```bash
cargo run -- doctor
cargo run -- list-tasks
cargo run -- show-task motor-debug
```

Run preflight and doctor workflows:

```bash
cargo run -- preflight
cargo run -- prepare motor-debug --dry-run
cargo run -- common-doctor motor-debug
cargo run -- task-doctor motor-debug
cargo run -- doctor-chain motor-debug --prepare-dry-run
```

Run `motor-debug` only with explicit operator confirmations and the correct lab
safety state:

```bash
cargo run -- run motor-debug \
  --with-doctor-chain \
  --confirm-manual-takeover \
  --confirm-kill-switch \
  --confirm-safe-area \
  --confirm-no-props
```

## Logging

The CLI uses `tracing`, `tracing-subscriber`, and `tracing-appender`.

Console output defaults to human-readable logs:

```bash
cargo run -- --log-level info doctor
```

JSON output is available for production-style collection:

```bash
cargo run -- --log-format json doctor
```

File logging is opt-in:

```bash
cargo run -- --log-file --log-dir logs/real doctor
```

Use structured fields in Rust code:

```rust
tracing::info!(task_id = %task_id, "task started");
```

## Configuration

Project-level configuration lives in `config.toml`.

Important sections:

- `[orchestration]`: must identify `family = "real"` and
  `implementation = "rust"`.
- `[runtime]`: must use `mode = "real"` and process backend.
- `[paths]`: workspace root, artifact root, and task config directory.
- `[sources]`: required real topic/source claims and forbidden simulation
  inputs.
- `[preflight]`: host environment, serial MAVLink, dependency, and ROS package
  requirements.
- `[prepare]`: process commands, topic probes, startup windows, and runtime
  summaries.

Task configs live under `configs/tasks/*.yaml`. The current built-in task is:

- `motor-debug`

## Safety Boundary

Real orchestration must fail closed. Commands that can touch hardware require
explicit operator confirmations and should write structured summaries that
include observed MAVLink ACKs, command outcomes, and blocker reasons.

Real workflows must reject simulation-only evidence such as Gazebo truth,
ideal scans, and simulation sensor status topics. The configured forbidden
topics are part of the real readiness contract.

## Contracts And Artifacts

Real artifacts are written under the configured real artifact root, currently
`../../artifacts/real`. Cross-language outputs should use the generated Rust
`navlab-contracts` crate from `../../contracts/gen/rust`.

Schema ownership and regeneration are documented in
[`../../contracts/README.md`](../../contracts/README.md).

## Development Commands

Format Rust code:

```bash
../../scripts/quality/format-rust.sh
```

Run Rust tests:

```bash
cargo test
```

Run the real orchestration benchmark:

```bash
cargo bench --bench motor_debug_plan
```

Run the Rust quality profile from the repository root:

```bash
./scripts/quality/check-rust.sh
```

## Maintenance Rules

- Keep real safety and hardware-specific behavior in this package.
- Keep task registration explicit in the Rust task registry.
- Keep task configs in YAML under `configs/tasks`.
- Keep project-level config in `config.toml`.
- Use generated contract types for shared outputs where possible.
- Add tests when changing safety confirmations, MAVLink command flow,
  preflight/prepare readiness, doctor summaries, artifact schema, or logging.
