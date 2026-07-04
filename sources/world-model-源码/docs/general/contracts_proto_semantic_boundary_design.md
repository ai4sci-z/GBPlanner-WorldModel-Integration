# Contracts Proto Semantic Boundary Design

## Goal

NavLab now has three active implementation lanes:

- `orchestration/sim`: Go simulation control plane.
- `orchestration/real`: Rust real-machine control plane.
- `navlab`: Python runtime nodes and domain runtime code.

These lanes must be able to split into separate repositories later without
losing task registry, runtime plan, doctor result, safety, sensor evidence, and
artifact summary compatibility.

The shared layer should therefore be `contracts/proto`, not shared Python,
shared Go, shared Rust, or a new `common` implementation package.

## Core Rule

Split proto by semantic boundary, not by language.

```text
contracts/proto/navlab/
  orchestration/v1/
    task_request.proto
    task_result.proto
    doctor_result.proto
    artifact_manifest.proto

  runtime/v1/
    runtime_plan.proto
    service_spec.proto
    probe_spec.proto
    process_event.proto

  safety/v1/
    command_policy.proto
    mavlink_ack.proto
    readiness_gate.proto

  sensors/v1/
    topic_contract.proto
    frame_contract.proto
    source_evidence.proto
```

Go sim, Rust real, and Python runtime may each generate code from these schemas,
but none of them owns the schema alone.

## Non-Goals

- Do not turn every human-authored TOML/YAML file into protobuf.
- Do not introduce shared helper implementations between sim and real.
- Do not replace ROS messages with NavLab protobuf messages.
- Do not require binary protobuf artifacts before JSON summaries are migrated.
- Do not block current Go/Rust work on full repo-wide code generation.

Human-authored config remains TOML/YAML because it is easier to inspect and edit:

```text
orchestration/sim/config.toml
orchestration/sim/configs/tasks/*.yaml
orchestration/real/config.toml
```

Proto constrains the stable structure after config is loaded:

```text
TOML/YAML
  -> Go/Rust loader
  -> normalized domain struct or proto-compatible struct
  -> runtime plan / task request
  -> result / summary / artifact manifest
```

## Boundary Ownership

### orchestration/v1

Owns task-level control-plane contracts.

Use this for:

- task registry metadata
- task request
- task result
- doctor result
- blockers / warnings / exit semantics
- artifact manifest
- final summary compatibility

Expected files:

```text
contracts/proto/navlab/orchestration/v1/task_request.proto
contracts/proto/navlab/orchestration/v1/task_result.proto
contracts/proto/navlab/orchestration/v1/doctor_result.proto
contracts/proto/navlab/orchestration/v1/artifact_manifest.proto
```

The existing `contracts/proto/navlab/runtime/v1/task_result.proto` should be
treated as the seed schema. During migration, either move it to
`orchestration/v1` or keep a compatibility wrapper until Go sim and Rust real
both write the orchestration-level result shape.

Important messages:

```proto
message TaskRequest {
  string schema_version = 1;
  string task_id = 2;
  string run_id = 3;
  RuntimeMode runtime_mode = 4;
  string artifact_dir = 5;
  repeated string capabilities = 6;
  google.protobuf.Struct parameters = 7;
  navlab.sensors.v1.SourceEvidence source_claims = 8;
}
```

```proto
message DoctorResult {
  string schema_version = 1;
  string task_id = 2;
  bool ok = 3;
  bool blocked = 4;
  repeated Blocker blockers = 5;
  repeated Check checks = 6;
}
```

```proto
message ArtifactManifest {
  string schema_version = 1;
  string run_id = 2;
  repeated Artifact artifacts = 3;
}
```

### runtime/v1

Owns runtime execution planning and process/probe event contracts.

This does not mean Docker/process/ROS launch implementation is shared. It means
Go sim and Rust real describe launch intent and results in the same shape.

Use this for:

- Docker service plan
- process service plan
- ROS probe plan
- rosbag record plan
- process start/exit event
- log file metadata
- service role and dependency order

Expected files:

```text
contracts/proto/navlab/runtime/v1/runtime_plan.proto
contracts/proto/navlab/runtime/v1/service_spec.proto
contracts/proto/navlab/runtime/v1/probe_spec.proto
contracts/proto/navlab/runtime/v1/process_event.proto
```

Important messages:

```proto
message RuntimePlan {
  string schema_version = 1;
  string task_id = 2;
  string run_id = 3;
  repeated ServiceSpec services = 4;
  repeated ProbeSpec probes = 5;
  repeated RosbagSpec rosbags = 6;
}
```

```proto
message ServiceSpec {
  string name = 1;
  string role = 2;
  RuntimeBackend backend = 3;
  string image = 4;
  repeated string command = 5;
  map<string, string> env = 6;
  string cwd = 7;
  repeated VolumeMount volumes = 8;
  repeated string networks = 9;
  bool required = 10;
  string log_path = 11;
}
```

### safety/v1

Owns safety and hardware-affecting command evidence.

Most safety messages are real-specific today, but they should still be schema
controlled because sim and real summaries need comparable safety claims.

Use this for:

- command policy
- operator confirmation
- arm/disarm/hold command intent
- MAVLink ACK result
- GUIDED/mode evidence
- fails-closed reason
- readiness gate result

Expected files:

```text
contracts/proto/navlab/safety/v1/command_policy.proto
contracts/proto/navlab/safety/v1/mavlink_ack.proto
contracts/proto/navlab/safety/v1/readiness_gate.proto
```

Important messages:

```proto
message CommandPolicy {
  string schema_version = 1;
  string task_id = 2;
  bool require_operator_confirmation = 3;
  bool require_no_props = 4;
  repeated string allowed_commands = 5;
  repeated string denied_commands = 6;
}
```

```proto
message MavlinkAck {
  string command = 1;
  string result = 2;
  int32 result_code = 3;
  bool accepted = 4;
  string mode_before = 5;
  string mode_after = 6;
  string statustext = 7;
}
```

### sensors/v1

Owns stable sensor/source evidence, not raw ROS message schemas.

Use this for:

- topic readiness
- topic owner uniqueness
- frame contract
- scan source evidence
- IMU source evidence
- rangefinder source evidence
- SLAM odom quality evidence
- ExternalNav readiness evidence

Expected files:

```text
contracts/proto/navlab/sensors/v1/topic_contract.proto
contracts/proto/navlab/sensors/v1/frame_contract.proto
contracts/proto/navlab/sensors/v1/source_evidence.proto
```

Important messages:

```proto
message TopicContract {
  string topic = 1;
  string message_type = 2;
  double min_rate_hz = 3;
  double max_latest_age_sec = 4;
  bool require_unique_owner = 5;
  repeated string allowed_publishers = 6;
}
```

```proto
message SourceEvidence {
  RuntimeDomain runtime_domain = 1;
  string scan_source = 2;
  string imu_source = 3;
  string rangefinder_source = 4;
  string slam_source = 5;
  bool uses_truth_as_control_input = 6;
  repeated TopicEvidence topics = 7;
}
```

## Versioning Rules

Use both versioned paths and explicit schema fields.

```text
contracts/proto/navlab/orchestration/v1/task_result.proto
schema_version = "navlab.orchestration.task_result.v1"
```

Rules:

- `v1` paths are append-only after initial adoption.
- New fields must be optional-compatible in proto3.
- Do not reuse field numbers.
- Do not rename meaning in place; add a new field.
- JSON summaries must include `schema_version`.
- Artifact manifests must record producer and schema version.

## Artifact Strategy

Each task run should eventually write these standard artifacts:

```text
task_request.json
runtime_plan.json
doctor_result.json
task_result.json
manifest.json
```

Binary `.pb` files can be added later:

```text
task_request.pb
runtime_plan.pb
task_result.pb
manifest.pb
```

JSON is the first migration target because it is easy to inspect during Go/Rust
parity work.

## Code Generation Strategy

Do not wire full codegen until schemas stabilize.

Recommended first steps:

1. Add `.proto` files and checked-in JSON examples.
2. Add Buf or protoc validation only for contracts.
3. Add Go encode/decode tests against JSON examples.
4. Add Rust encode/decode tests against the same examples.
5. Add Python read/write compatibility tests for runtime summaries.

Suggested layout:

```text
contracts/
  proto/
    navlab/...
  examples/
    orchestration/
      sim_task_request.json
      real_task_result.json
      doctor_result_blocked.json
    runtime/
      sim_runtime_plan.json
      real_process_event.json
    safety/
      motor_debug_ack_failed.json
    sensors/
      real_source_evidence.json
  README.md
```

## Migration Todo

### Phase 1: Freeze design and examples

- [x] Add this design document.
- [x] Update `contracts/README.md` to describe semantic boundaries.
- [x] Add minimal proto files with package names and boundary messages.
- [x] Add golden JSON examples for one sim task and one real task.
- [x] Add golden examples for doctor, runtime, safety, and sensors contracts.
- [x] Add a schema index that maps each example to its owning proto message.

### Phase 2: Go sim writes proto-compatible JSON

- [x] Map Go sim `Plan` to `orchestration.v1.TaskRequest`.
- [x] Map Go sim runtime specs to `runtime.v1.RuntimePlan`.
- [x] Map Go sim summary/manifest to `TaskResult` and `ArtifactManifest`.
- [x] Keep current task YAML and `config.toml` unchanged.
- [x] Add Go tests that validate emitted JSON against golden examples.

### Phase 3: Rust real writes proto-compatible JSON

- [x] Map Rust real task registry output to `TaskRequest`.
- [x] Map preflight/prepare/task-doctor output to `DoctorResult`.
- [x] Map motor-debug MAVLink evidence to `safety.v1.MavlinkAck`.
- [x] Map real source checks to `sensors.v1.SourceEvidence`.
- [x] Add Rust tests that validate emitted JSON against golden examples.

### Phase 4: Python runtime reads/writes stable result shapes

- [x] Runtime nodes keep writing task-specific details in JSON fields.
- [x] Common metadata moves into contract-compatible fields.
- [x] Python runtime code does not import Go or Rust implementation code.
- [x] Add Python compatibility tests for runtime summary read/write.

### Phase 5: Enforce contracts in CI

- [x] Validate `.proto` syntax.
- [x] Validate golden examples against Go/Rust/Python readers.
- [x] Fail CI when `schemaVersion` is missing from contract artifacts that require it.
- [x] Add checked-in Go generated contracts under `contracts/gen/go` once Go sim
  starts consuming contract readers directly.
- [x] Add Rust generated contract crate under `contracts/gen/rust` once Rust real
  starts validating outputs against generated types.
- [x] Add Python generated contract package under `contracts/gen/python` once
  Python runtime clients need class-based contract access.

## Current Repository Mapping

Current state:

- Go sim already owns runtime plans and generated artifact manifests.
- Rust real owns real workflows, task registry, and MAVLink runtime evidence.
- Python remains runtime node code under `navlab`, not orchestration control
  plane code.
- `contracts/proto/navlab/runtime/v1/task_result.proto` exists as the first
  seed schema.

Near-term refactor:

- Treat existing runtime `TaskResult` as transitional.
- Add orchestration-level `TaskResult` when both Go sim and Rust real need the
  same final summary contract.
- Keep the old schema readable until migrated summaries are emitted by both
  lanes.

## Review Checklist

Before adding a new proto message, verify:

- Is this data crossing language or repository boundaries?
- Is it stable enough to version?
- Is it machine-read by more than one implementation?
- Would TOML/YAML be better because a human edits it directly?
- Can task-specific fields live under `google.protobuf.Struct` until stable?
- Does this belong to orchestration, runtime, safety, or sensors?

If the answer is only "this removes local duplication", do not add proto. Use a
local type in the owning implementation instead.
