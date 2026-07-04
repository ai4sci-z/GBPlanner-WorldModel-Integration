# NavLab Contracts

This package owns language-neutral contracts shared by `navlab` runtimes and
Go/Rust orchestration implementations.

`orchestration` chooses artifact paths and starts processes. Runtime tasks write
their result artifacts to those paths. The contract here defines the stable
shape those artifacts must follow so future readers can be implemented in
Python, Rust, or another language without importing runtime code.

Design scope:

- `proto/navlab/orchestration/v1`: task request/result, doctor result, and
  artifact manifest contracts.
- `proto/navlab/runtime/v1`: runtime plan, service spec, probe spec, and process
  event contracts.
- `proto/navlab/safety/v1`: command policy, MAVLink ACK, and readiness gate
  contracts.
- `proto/navlab/sensors/v1`: topic, frame, and source evidence contracts.

See `docs/general/contracts_proto_semantic_boundary_design.md` for the detailed
boundary design and migration plan.

Current implementation scope:

- Minimal proto skeletons now exist under:
  - `proto/navlab/orchestration/v1`
  - `proto/navlab/runtime/v1`
  - `proto/navlab/safety/v1`
  - `proto/navlab/sensors/v1`
- Golden JSON examples live under `examples/`.

Current implementation note:

- Existing tasks may still write implementation-specific `summary.json`.
- New or migrated cross-language artifacts should write proto-compatible JSON
  such as `task_request.json`, `runtime_plan.json`, `doctor_result.json`,
  `task_result.json`, and `manifest.json`.
- Go protobuf code generation is wired under `contracts/gen/go` and validated by
  `scripts/quality/check-contracts.sh`. Regenerate it with
  `scripts/contracts/generate-contracts-go.sh`.
- Rust protobuf code generation is wired under `contracts/gen/rust` as the
  `navlab-contracts` crate. It uses `prost-build` at Cargo build time and is
  validated by `scripts/quality/check-contracts.sh`.
- Python protobuf code generation is wired under `contracts/gen/python` as the
  `navlab_contracts` package and validated by
  `scripts/quality/check-contracts.sh`. Regenerate it with
  `scripts/contracts/generate-contracts-python.sh`.
