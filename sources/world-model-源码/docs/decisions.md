# Decisions

## 2026-06-27: Go sim runtime uses Docker SDK only

Decision: replace the Go sim Docker CLI runtime backend with a Docker SDK
backend behind the existing `runtime.Backend` interface. Runtime-execute now
uses SDK container create/start/wait/stop/logs/remove for services, probes, and
rosbag recording. The shell `docker` backend is not retained as a production
fallback.

Basis: WF1.x already moved preflight/prepare resource evidence to the Docker
SDK, and keeping a separate CLI runtime path would split service lifecycle,
rosbag finalize behavior, and failure evidence across two backends.

Reason: SDK-only runtime keeps Docker/Gazebo/SITL side effects inside the sim
runtime package while preserving the task/runtime spec schema. Rosbag is now a
runtime-owned lifecycle: start recorder, wait post-task grace, stop with SIGINT
through Docker SDK, wait for finalize evidence, then clean up the container.

Update: the Go sim image build path and official overlay source extraction also
use Docker SDK APIs. `navlab-sim build` now calls `ImageBuild` directly, and
prepare reads official baseline files through an SDK-started container probe.
The remaining Docker CLI mentions in Go sim are configuration/backend names,
docs, or tests that assert old CLI wrappers are absent.

## 2026-06-26: Real hover MAVLink runtime FSM stays behind tests

Decision: WF5B implements a Rust real hover MAVLink runtime FSM in
`runtime::mavlink`, with `RealHoverRuntimeRequest`,
`RealHoverRuntimeReport`, `run_real_hover_runtime`, and
`real_hover_runtime`. The `run hover` live CLI path still fails closed with
`real_hover_live_task_not_enabled` and does not call this runtime yet.

Basis: the command sequence and task FSM need unit coverage before any live
flight wiring. The current implementation can be tested against a fake MAVLink
adapter for GUIDED, arm, takeoff, hover-health hold, hover hold, landing, and
disarm without touching hardware.

Reason: this separates runtime behavior design from live-flight enablement.
WF5C/WF5D still need real SLAM, ExternalNav, rangefinder, landing evidence,
flight rosbag, and hover-health gates before the CLI can safely invoke the
hover runtime.

## 2026-06-26: Real hover safety uses props-installed, not no-props

Decision: real hover has its own final operator safety gate:
manual takeover, kill switch, safe area, and props installed. `motor-debug`
continues to require `no_props`, but `hover` ignores `no_props` and requires
`--confirm-props-installed` or `NAVLAB_CONFIRM_PROPS_INSTALLED=true`.

Basis: motor-debug is a no-props bench task. Real hover is a flight task, so
using a `no_props` confirmation would encode the wrong physical boundary and
could make a dry-run/no-props artifact look like a flight release gate.

Reason: the hover summary now records
`props_required_for_real_hover_no_no_props_shortcut`. Missing confirmations
block as `blocked_by_operator_safety` before runtime. Passing all confirmations
still does not enable live hover until the dedicated MAVLink hover runtime and
evidence gates are implemented.

## 2026-06-26: Real hover starts as dry-run design and fails closed live

Decision: register Rust real `hover` as a dry-run design task first. It writes
the same run artifact surface as `motor-debug` and a planned task FSM, but live
execution returns `real_hover_live_task_not_enabled` before any GUIDED, arm, or
takeoff command.

Basis: WF5 should extend the real workflow/FSM/artifact template after
`motor-debug`, but the live hover runtime still needs dedicated operator safety,
props-installed semantics, hover-health stable-window evidence, landing
evidence, and real flight rosbag handling.

Reason: this gives real hover a concrete artifact contract without creating a
false sense that live flight is implemented. The completion definition is
layered: MAVLink ExternalNav plus FCU local-position evidence is primary;
official DDS pose evidence can be a secondary crosscheck, not the sole gate.

## 2026-06-26: Common task FSM semantics stay pure and language-local

Decision: WF4 shares task FSM and policy semantics through pure data shapes,
not through cross-language runtime imports. Python common now exposes
`navlab.common.companion.mission.fsm` and `policy` helpers. Rust real uses
`workflows::fsm` with the same `navlab.fsm.v1` JSON shape, while
`motor-debug` keeps only task-specific evidence mapping.

Basis: `navlab.common` is a Python package used by companion/sim runtime code,
while `navlab-real` is a Rust binary. Directly importing Python common from the
Rust real runtime would add packaging and execution coupling before the schema
is stable.

Reason: the useful common layer here is pure FSM/evidence/policy vocabulary:
states, transitions, blockers, reason codes, operator confirmation semantics,
deadline semantics, and target/hard-cap checks. Docker/Gazebo/SITL, serial,
FCU, lidar, rangefinder, ROS topic sampling, and MAVLink IO remain in their
own sim or real runtime packages.

## 2026-06-26: Rust real motor-debug FSM uses coarse mission states

Decision: record `motor-debug` as a task FSM with coarse states:
`runtime_ready -> guided -> armed -> motor_spin_hold -> disarmed -> completed`.
MAVLink request, ACK, heartbeat, mode observation, and shutdown evidence stay
on transitions instead of becoming top-level FSM states.

Basis: WF3 needs motor-debug to be auditable and fail-closed without turning
the task body into a command log. The workflow DAG already owns
`preflight -> prepare -> common-doctor -> task-doctor -> runtime-execute`; the
task FSM should only describe where the mission body is.

Reason: a small stable state set makes blocked summaries actionable:
`failed_state=armed` means the task failed while entering the armed state, while
the transition evidence still preserves the exact arm request, ACK, heartbeat,
or blocker details needed for debugging.

## 2026-06-26: Rust real motor-debug owns run workflow DAG artifacts

Decision: make `navlab-real run motor-debug` write a run-level workflow DAG
summary beside the task request, task plan, runtime summary, and task result.
When `--with-doctor-chain` is enabled, the doctor chain writes into the run
artifact directory unless an explicit doctor artifact dir is provided. If the
doctor chain blocks, the CLI passes that summary to motor-debug instead of
returning early, so motor-debug writes a blocked run summary before failing.

Basis: WF2 requires motor-debug to become the real orchestration shape sample:
`preflight -> prepare -> common-doctor -> task-doctor -> runtime-execute`.
The prior CLI behavior could stop at doctor-chain error without a task run
summary, while dry-run wrote only `task_request.json`.

Reason: blocked and dry-run real tasks now expose the same operator-facing
artifact surface: `task_request.json`, `task_plan.json`,
`workflow_summary.json`, `summary.json`, and `task_result.json`. This keeps
doctor evidence attached to the task run and avoids treating motor-debug as a
special path before real hover is designed.

## 2026-06-16: SITL rangefinder must emulate the real Benewake serial boundary

Decision: `docker/profiles/navlab-sitl-external-nav.parm` is a
hardware-faithful SITL profile, not a Gazebo-specific compatibility profile.
Keep `RNGFND1_TYPE=20` and configure the FCU serial port with
`SERIAL7_PROTOCOL=9`, matching `docs/debug.param` and `docs/ori.param`. SITL
must adapt by emulating the Benewake TFmini serial peripheral, or the task must
fail closed with an explicit blocker. Do not rewrite this profile to
`RNGFND1_TYPE=10` just because the current simulator path can inject MAVLink
`DISTANCE_SENSOR`.

Update: this profile uses `EK3_SRC1_POSZ=2` so vertical position comes from the
down-facing rangefinder, matching the indoor low-altitude NavLab stack. It keeps
`EK3_SRC1_VELZ=6` so vertical velocity remains ExternalNav, matching the
ArduPilot Cartographer guidance. Do not set `VELZ` to `0` for the 2D SLAM path:
that disables a source the official ExternalNav setup expects. The difference
from the official example is only the vertical position source: official
Cartographer SITL uses barometer (`POSZ=1`), while NavLab's indoor profile uses
rangefinder (`POSZ=2`).

Basis: local ArduPilot sources define `RNGFND1_TYPE=10` as MAVLink and
`RNGFND1_TYPE=20` as `BenewakeTFmini-Serial`. `SERIAL*_PROTOCOL=9` is
Rangefinder. ArduPilot's own SITL Benewake TFmini example starts a serial
rangefinder backend with `--serial5=sim:benewake_tfmini`, then sets
`SERIAL5_PROTOCOL=9` and `RNGFND1_TYPE=20`.

Update: local hover live on 2026-06-16 showed the direct
`serial7:=sim:benewake_tfmini` backend can crash ArduPilot `arducopter` inside
the current official Gazebo/DDS bringup with a floating point exception. NavLab
therefore uses its own PTY-backed Benewake TFmini emulator and launches
ArduPilot with `serial7:=uart:/tmp/navlab_benewake_tfmini:115200`. The direct
`sim:benewake_tfmini` backend is retained only as source context and audit
evidence, not as the runtime path.

Reason: realistic simulation means the FCU sees the same peripheral boundary as
the real machine:

```text
Real: Benewake TFmini -> UART -> FCU
SITL: Gazebo range observation -> Benewake serial emulator -> SITL serial -> FCU
```

This is the same principle already used for X2 lidar: Gazebo may produce the
physical observation, but the downstream driver/FCU must consume the same
protocol class it consumes on hardware. Gazebo truth remains diagnostic-only;
missing serial rangefinder evidence must block the task instead of falling back
to MAVLink or truth odometry.

## 2026-06-16: SITL ExternalNav profile owns origin setup and fresh FCU feedback gates

Decision: `docker/profiles/navlab-sitl-external-nav.parm` is the active
realistic SITL ExternalNav profile. Its companion Lua origin script is also a
profile input at `docker/profiles/ahrs-set-origin.lua`, and Go sim copies it to
`sitl_work/scripts/ahrs-set-origin.lua` before launching ArduPilot so SITL can
load it with `SCR_ENABLE=1`.

Basis: ArduPilot SITL loads Lua scripts from the `scripts` directory under the
simulator start directory. The official baseline service starts from each run's
artifact `sitl_work`, so keeping the script only under `docs/` is not a runtime
configuration. The Lua profile also carries the same NavLab SITL origin defaults
as the parameter profile because SITL may process `.parm` files before a Lua
custom parameter table exists.

Reason: hover/exploration/scan-robustness must exercise the same
ExternalNav-only path as the real machine: no GPS truth fallback, no Gazebo
truth substitution, and no stale FCU position treated as healthy. A MAVLink
ExternalNav sender is ready only when it is actively sending `/external_nav/odom`
and the FCU is still publishing fresh `LOCAL_POSITION_NED`; historical
`local_position_count > 0` is not sufficient evidence.

## 2026-06-15: Go sim orchestrates Python runtime nodes during parity recovery

Decision: during sim parity recovery, Go owns task loading, registry,
execution planning, artifact generation, Docker/ROS process orchestration,
result gates, and summary writing. Python remains the runtime language for
NavLab sim companion nodes such as `hover_mission.py`, `obstacle_mission.py`,
and ROS probe/runtime scripts that embody the old mission behavior. Do not
rewrite these mission runtimes into Go as part of H0/H1.

Basis: the hover false pass came from replacing the old Python
`hover_mission.py` phase contract with a Go-generated generic FCU controller
readiness path. That changed semantics: `controller_ready` was treated like
`hover_hold`, and takeoff readiness was treated like hover completion.

Reason: the current migration target is Go orchestration with Python runtime,
not a full Go runtime rewrite. Preserving the Python runtime boundary lets Go
own the control plane while keeping the mature MAVLink mission state machines
traceable and comparable to the old orchestration baseline.

Update: `fcu-controller` is not part of the hover task during parity recovery.
It is a shared FCU/MAVLink setpoint adapter for workflow tasks such as
exploration and navigation, where another workflow publishes setpoint intent.
Hover is a mission-state-machine task, so only `hover_mission.py` may own the
MAVLink GUIDED/arm/takeoff/hold/landing sequence. Recombining hover with a
shared FCU adapter is deferred until the old Python hover/exploration/scan
semantics have been faithfully reproduced and accepted by live evidence.

Update: H2/H3 hover acceptance is now evidence-gated on the Python mission
summary. `hover_hold` requires `LOCAL_POSITION_NED`-based `current_z_ned`,
`altitude_error_m <= hover_altitude_tolerance_m`, positive local-position and
setpoint counts, sufficient hover-hold duration, drift `ok=true`, and landing
fields `land_command_accepted`, `touchdown_confirmed`, `disarmed`, and
`motors_safe`. ACKs, `GLOBAL_POSITION_INT`, or controller readiness are not
sufficient hover completion evidence.

## 2026-06-15: Evidence-first completion claims are mandatory

Decision: no orchestration task, migration slice, live run, replay artifact, or
Foxglove upload may be described as complete, passed, parity-equivalent, or
ready for the next stage unless the required runtime evidence exists and is
traceable. If evidence is missing, partial, contradictory, or generated by a
weaker path than the baseline, the status must be written as `blocked`,
`not_verified`, `not_equivalent`, or `false_pass_found`.

Basis: the Go sim migration exposed false-positive reporting in hover and
exploration. A controller readiness status, ACK, topic count, setpoint count,
short movement, static SLAM pose, generated script, or visible Foxglove layer
was treated as stronger evidence than it actually was. The hover artifact
`artifacts/sim/hover/20260615T115355Z/summary.json` was marked
`TASK_STATUS_OK` even though the observed takeoff height was only about
`0.19m` for a `0.5m` target. That artifact must be treated as invalid
acceptance evidence.

Reason: sim and real migration must fail closed. Reporting must follow code
and artifact evidence, not intent, apparent UI output, or inferred progress.
Visual replay artifacts are review aids only; they are never acceptance
evidence by themselves. Before continuing dependent work, especially Nav2/P13
or Python sim retirement, each prerequisite task must have a complete live
summary and must preserve the baseline task semantics documented in
`docs/general/sim_task_parity_differences_audit.md`.

Operational rule:

- Do not say "done", "completed", "passed", or "parity complete" without
  naming the summary/artifact/test that proves it.
- Do not use a weaker metric as a substitute for the original acceptance
  contract.
- Do not upload or cite Foxglove lite output as proof of task success unless
  the task summary already passed.
- If a previous claim is found false, mark the artifact and document as
  invalid/false-pass before doing more feature work.

## 2026-06-14: Go sim must preserve Python orchestration SLAM parity before Nav2 expansion

Decision: treat `cae4288` Python orchestration as the parity baseline for
SLAM/topic/frame/truth semantics while Go sim continues replacing the control
plane. Add `docs/general/orchestration_sim_python_parity_audit.md` as the
traceable migration record and align Go helper defaults with the old runtime
contract: `base_scan`, `rangefinder_down_frame`, `/rangefinder/down/*`,
`/ap/v1/*`, `/odometry` as diagnostic-only unless backed by a real-equivalent
sensor source, and `/slam/odom` + `/map` as SLAM-owned canonical outputs.

Basis: the P13 navigation debugging showed a migration regression risk: seed
maps and diagnostic odometry can make Foxglove look partially populated while
the actual Cartographer `/map` and `/slam/odom` ownership is broken. The old
Python P3/P6/P8 helpers explicitly blocked Gazebo truth as SLAM, ExternalNav,
planning, exploration, or control input and kept official maze overlay as a
visualization-only layer.

Reason: Nav2 work should build on the mature SLAM/FCU/rosbag/replay surface,
not replace it. Real migration later must use the same semantic audit: truth or
diagnostic signals may be recorded, but cannot become canonical SLAM or control
inputs.

Update: the 2026-06-14 Go sim live parity run exposed that the old
Python/Go-migrated stack could still leak official/Gazebo bridge odometry or
Gazebo pose TF into Cartographer/adapter paths. The accepted rule is stricter:
Gazebo may generate realistic sensor observations, but Gazebo `/odometry`,
Gazebo pose TF, seed maps, and official maze maps are diagnostic/review-only
unless a real-machine equivalent input is explicitly documented. `/slam/odom`
and `/map` must come from the SLAM backend, not from Gazebo truth or replay
overlays.

## 2026-06-13: Sim Docker images are split into infra and runtime layers

Decision: move simulation Dockerfiles into `docker/images/base/*.Dockerfile`,
`docker/images/infra/*.Dockerfile`, and `docker/images/runtime/*.Dockerfile`, import the
former `sim-infra` image definitions as base/infra images, and make
`navlab-sim build` resolve `base`, `infra`, `runtime`, or `all` as build
groups. A single image is selected with `--image` inside the `infra` or
`runtime` group.

Basis: Go sim now owns image build orchestration, while runtime images depend
on reusable base images such as ROS base, ArduPilot SITL, MAVLink Router, and
Gazebo headless. Keeping those base Dockerfiles in a separate repository makes
the sim build path harder to understand and harder to split later.

Reason: the sim repository boundary should own the full simulation image stack.
Image repositories use the `navlab/*` namespace, for example
`navlab/ros-base` and `navlab/gazebo-headless`. Tags carry the ROS distro
through the allowed policies `distro-git-commit`, `distro-datetime`, or
`distro-latest`, with `humble` as the default distro. Operators can select
`humble` or `jazzy` with `NAVLAB_SIM_DISTRO` or `navlab-sim build --distro`;
other distro values fail before Docker starts.

## 2026-06-13: Python contracts use generated navlab_contracts package

Decision: add `contracts/gen/python` as a generated `navlab_contracts` package,
generate Python protobuf classes with `protoc --python_out`, rewrite generated
imports under the `navlab_contracts.navlab` namespace, and validate golden JSON
examples with `google.protobuf.json_format.Parse`.

Basis: the repository already has a business/runtime `navlab` Python package.
Generating protobuf modules directly into top-level `navlab/...` would mix
contract code with runtime implementation code and make future repo splits
harder. The separate `navlab_contracts` package lets Python runtime code import
contract classes without reusing Go/Rust helpers or colliding with runtime
modules.

Reason: Python clients can now operate on generated protobuf classes while
still exchanging proto-compatible JSON artifacts when needed. The artifact
format remains language-neutral; only the reader/writer code moves from ad hoc
dict parsing to generated class parsing.

## 2026-06-13: Rust real depends on generated contract crate

Decision: add `contracts/gen/rust` as the `navlab-contracts` crate, generate
Rust protobuf structs with `prost-build`, validate the crate in
`scripts/quality/check-contracts.sh`, and make `orchestration/real` depend on it
through a local path dependency.

Basis: Rust real already emits proto-compatible JSON for task request, task
result, doctor result, source evidence, and MAVLink ACK artifacts. The generated
crate now proves the Rust client can compile against the same `contracts/proto`
schemas as Go sim, and real contract tests compare emitted JSON status/backend
strings against generated enum names.

Reason: sim and real should share schema/generated type contracts, not helper
code. `prost-build` keeps Rust generated code owned by the crate build while
still giving real-machine code a stable dependency boundary for a future repo
split. Python generated contracts are handled separately under
`contracts/gen/python`.

## 2026-06-13: Go contract codegen is checked in for sim readers

Decision: add checked-in Go protobuf generation under `contracts/gen/go` and
make Go sim TUI artifact replay read proto-compatible artifacts through the
generated `TaskRequest`, `RuntimePlan`, `TaskResult`, and `ArtifactManifest`
types with `protojson`.

Basis: the proto skeletons and golden JSON examples now parse through generated
Go types, and Go sim is the first consumer that benefits from stronger reader
types. `scripts/quality/check-contracts.sh` now validates proto syntax,
regenerates Go contracts through `scripts/contracts/generate-contracts-go.sh`,
runs the generated module tests, and fails only when
the generated output changes relative to the pre-check state.

Reason: this keeps the shared boundary in `contracts/proto` while avoiding a
new common helper package between sim and real. Go sim depends only on the
generated contract module through a local `replace`, so a future repo split can
keep the same generated module boundary. Rust and Python generated contracts
are handled by their own language-specific packages.

## 2026-06-13: Contract enforcement stays JSON-first before codegen

Superseded by: `2026-06-13: Go contract codegen is checked in for sim readers`.

Decision: add contract validation through checked-in proto syntax, golden JSON
examples, Go/Rust/Python compatibility tests, and a `scripts/quality`
contracts check instead of introducing generated protobuf code in this slice.

Basis: Go sim, Rust real, and Python runtime now emit or consume the contract
shapes, but the repo still has no stable generated-code ownership convention.

Reason: JSON-first enforcement catches boundary drift in CI while keeping sim
and real independently movable to future repositories. Generated code can be
added later once the schema surface stops changing.

## 2026-06-13: Contracts proto starts with semantic skeletons

Decision: split `contracts/proto/navlab` by semantic boundary
(`orchestration`, `runtime`, `safety`, `sensors`) and add minimal proto
skeletons plus golden JSON examples before wiring code generation.

Basis: Go sim, Rust real, and Python runtime now need cross-language contracts,
but the exact generated-code workflow is not yet a stable repo convention.

Reason: checked-in schemas and examples freeze the boundary without coupling the
current migration to a premature Buf/protoc, Go, Rust, or Python codegen stack.

## 2026-06-13: Root profiles only keep active cross-runtime inputs

Decision: remove obsolete gate-specific rosbag topic profiles from the root
`docker/profiles/` directory after Go sim started generating runtime rosbag topic
profiles under each run's artifact directory. Root `docker/profiles/` now keeps only
files with active non-historical consumers: X2 vendor params, SITL ExternalNav
params, Foxglove-lite topic profiles, and the remaining generic rosbag
fallbacks.

Basis: active Go sim tasks build rosbag record topic profiles from execution
plans at runtime instead of reading legacy `docker/profiles/navlab-*-rosbag-topics.txt`
files. Non-historical references now point only to the retained files.

Reason: leaving old P-stage rosbag profiles in the root made retired Python
orchestration paths look current and created a second apparent source of truth
beside Go sim's generated runtime plan artifacts.

## 2026-06-13: Python orchestration control plane is retired

Decision: delete the tracked Python orchestration project under
`orchestration/` after Go sim and Rust real became the active control-plane
implementations. This removes `orchestration/main.py`, `orchestration/src`,
`orchestration/tests`, the Python `pyproject.toml`/`uv.lock`, and the old
top-level Python real config files. The active entries are now
`orchestration/sim` for Go simulation orchestration and `orchestration/real`
for Rust real-machine orchestration.

Basis: Go sim owns build, doctor, task registry, task run planning/execution,
runtime artifact generation, and Docker/ROS script surfaces. Rust real owns
real config loading, registry, preflight, prepare, common-doctor, task-doctor,
doctor-chain, process runtime, and motor-debug MAVLink execution. Keeping the
old Python orchestration project would leave duplicate entrypoints and stale
CI/test surfaces.

Reason: this completes the repository split the project has been moving
toward: sim and real are independent packages with separate configs and quality
scripts. Python remains elsewhere in the repo only for runtime packages or
standalone command tooling, not for the `orchestration` control plane.

## 2026-06-13: Rust real motor-debug owns MAVLink transport loop

Decision: replace the motor-debug "runtime not migrated" live path with a
Rust MAVLink transport loop. The task now connects through the configured
MAVLink endpoint, waits for an FCU heartbeat, sends
`COMMAND_LONG MAV_CMD_DO_SET_MODE` for ArduCopter GUIDED mode, waits for both
mode ACK and GUIDED heartbeat, sends arm, holds in armed-idle only, sends
disarm, and writes heartbeat/ACK/runtime evidence back to `summary.json`.

Basis: Rust already owned the motor-debug task registry, safety confirmations,
plan contract, command policy model, and summary schema. The remaining Python
parity gap was transport/send/receive behavior: connection, heartbeat/ACK
waiting, and summary updates from real MAVLink responses.

Reason: this makes Rust real the owner of motor-debug execution semantics while
preserving fail-closed behavior. Without a heartbeat, Rust records
`motor_debug_heartbeat_timeout` and never sends arm. If any ACK rejects or
times out, Rust records the specific blocker; when arm succeeds it always
attempts disarm and records the shutdown claim.

## 2026-06-12: Rust real motor-debug owns MAVLink runtime policy model

Decision: migrate the real motor-debug MAVLink policy model into Rust before
opening the live MAVLink send path. Rust now owns the ArduCopter GUIDED mode
ID policy (`GUIDED` => `4` even when FCU mode mapping is missing or wrong),
the `MAV_CMD_COMPONENT_ARM_DISARM` arm/disarm command_long shape, MAV_RESULT
name mapping, ACK rejection blockers, and the command plan embedded in the
runtime `summary.json`.

Basis: the old Python tests encoded these semantics around
`ensure_guided_mode`, `send_arm_disarm`, `wait_command_ack`, and
`command_rejection_blockers`, while the Python runtime module itself has
already been retired from the repo. Recreating the behavior as a Rust model
keeps the safety and artifact contract testable without depending on Python.

Reason: this reduces the remaining live-runtime migration to transport and
message I/O only. The Rust live task still fails closed after operator
confirmations and summary writing, so no real motor command can be sent until
the MAVLink connection/send/receive loop is explicitly implemented and tested.

## 2026-06-12: Rust real motor-debug owns runtime summary contract

Decision: migrate the real motor-debug runtime artifact contract into Rust.
After operator confirmations pass, Rust now resolves the MAVLink router
endpoint, writes a `navlab.runtime.task_result.v1` `summary.json` with serial,
baud, endpoint, motor parameters, required GUIDED mode, no-takeoff/no-props
claims, arm/hold/disarm steps, and shutdown fields, then fails closed with
`motor_debug_rust_mavlink_runtime_not_migrated`.

Basis: Python motor-debug writes a runtime summary even when the subprocess
fails or cannot produce one. Rust previously stopped at a generic not-migrated
error after safety confirmation, leaving no task-result artifact for operators
or wrapper tests to inspect.

Reason: this fixes the artifact surface before adding real MAVLink actuation.
The endpoint conversion matches the Python policy (`host:port` becomes
`udpin:host:port`, already-prefixed endpoints pass through), and the actual
motor command path remains disabled until MAVLink send/ack behavior is ported
and tested.

## 2026-06-12: Rust real motor-debug owns operator safety gates

Decision: migrate real motor-debug operator confirmations into Rust. The
`navlab-real run motor-debug` command now accepts
`--confirm-manual-takeover`, `--confirm-kill-switch`, `--confirm-safe-area`,
and `--confirm-no-props`, plus compatible `NAVLAB_CONFIRM_*` environment
values. Live motor-debug evaluates these gates before any motor action and
fails closed with the same blocker names as Python when confirmations are
missing.

Basis: Rust real already owns motor-debug planning, doctor-chain gating, and
the run wrapper opt-in path, but live motor-debug still jumped directly to a
generic "not migrated" error. Python blocks missing operator confirmations
before invoking the runtime motor command, and that safety boundary must move
before MAVLink motor spin is ported.

Reason: this preserves the no-props and operator-readiness contract while
keeping the real MAVLink actuation path disabled. Once confirmations are all
present, Rust still fails closed at `live motor-debug execution is not migrated
to Rust yet`, so the next slice can focus only on the MAVLink/runtime command.

## 2026-06-12: Rust real run can opt into doctor-chain gating

Decision: wire `navlab-real run <task>` to optionally execute the Rust
doctor-chain before task execution via `--with-doctor-chain`. The default
`run --dry-run` path remains a fast task-plan command, while
`--with-doctor-chain` runs preflight, prepare, common-doctor, and task-doctor
first. Prepare stays dry-run unless `--allow-live-prepare` is explicitly set.

Basis: Python real run wrappers gate task execution through the doctor chain,
but Rust real initially exposed task execution and doctor-chain as separate
commands. Connecting them behind an explicit flag lets operators validate the
new Rust chain without changing the quick dry-run behavior or accidentally
starting real prepare services.

Reason: this closes the first wrapper parity gap while preserving safety.
Current hosts without ROS or serial hardware fail closed during preflight and
write chain artifacts; hosts with valid evidence can proceed to the existing
task dry-run or the still fail-closed live task path.

## 2026-06-12: Rust real owns the doctor-chain wrapper

Decision: add a Rust `doctor-chain` workflow and CLI command that runs the
real validation sequence as `preflight -> prepare -> common-doctor ->
task-doctor -> stop prepare`. The chain writes a single artifact directory with
`preflight.json`, `prepare.json`, `common-doctor.json`, `upstream.json`,
`task-doctor.json`, and `summary.json`. Prepare defaults to dry-run in the
chain unless `--allow-live-prepare` is explicitly passed.

Basis: Python real run wrappers already depend on this ordering, but Rust real
previously exposed only separate commands. With preflight, prepare,
common-doctor, task-doctor, and process backend now migrated, the missing piece
was the orchestration wrapper that preserves failure ordering and cleanup
semantics.

Reason: this moves the Python wrapper contract into Rust without requiring
flight execution yet. The chain is testable with injected environment/topic
probes, stops before prepare when preflight blocks, shares common-doctor
upstream evidence with task-doctor, and keeps real process startup opt-in.

## 2026-06-12: Rust real prepare live phase is explicit and stoppable

Decision: wire Rust real prepare service plans into the Rust process backend
through `start_prepare_phase` and `stop_prepare_phase`. The phase API starts
configured process services, records `started_services` in the prepare summary,
and stops handles in reverse order. The CLI keeps live execution behind
`--allow-live`; without `--dry-run` or `--allow-live`, prepare fails closed with
`prepare_live_execution_requires_explicit_allow_live_or_dry_run`.

Basis: the previous slice migrated the reusable process backend but prepare
still only produced plans. Python prepare returns handles so the higher-level
run wrapper can keep services alive through common/task doctor and then stop
them. Rust needs the same lifecycle boundary before replacing the Python
real-run chain.

Reason: this gives Rust real an end-to-end tested process lifecycle without
making accidental real hardware startup the default. Unit tests start harmless
local shell processes and verify summary output plus stop behavior; actual
ROS/MAVLink services remain opt-in and will be chained with readiness checks in
the next slice.

## 2026-06-12: Rust real process backend migrates before live prepare

Decision: add a Rust `runtime::process` backend with process `ServiceSpec`,
`ProbeSpec`, runtime handles, dry-run log generation, probe capture, service
start/wait/stop, log tailing, and Unix process-group termination. Prepare
service plans now map directly to process service specs, but
`navlab-real prepare` still keeps non-dry-run fail-closed until live readiness
and cleanup orchestration are migrated.

Basis: Python prepare depends on `ProcessBackend` to start MAVLink router,
NavLab bridge, lidar, SLAM, and rangefinder services. Starting these real
services is the hardware/process side-effect boundary, so the backend lifecycle
must be tested independently before prepare uses it for live execution.

Reason: this moves the reusable runtime substrate into Rust while preserving
the current safety policy. Dry-run, probe execution, exit-code handling, and
stop behavior are covered by Rust tests; the next slice can wire prepare live
start/stop and ROS readiness against the same specs.

## 2026-06-12: Rust real prepare owns service planning before live start

Decision: add `navlab-real prepare <task-id>` as a Rust real migration slice.
The command loads the project/task config, expands `navlab_mavlink` prepare
services, writes a prepare `summary.json`, validates serial provenance,
forbidden simulation tokens, required service commands, and motor-debug's
rangefinder exclusion. `--dry-run` produces an operator-inspectable service
plan; non-dry-run remains fail-closed with
`prepare_live_execution_not_migrated_to_rust_yet:pass_--dry-run`.

Basis: Python prepare mixes service selection, process startup, MAVLink router
probing, ROS topic readiness, and artifact reporting. Rust real already owns
preflight plus common/task doctor artifacts, but starting real processes is the
hardware side-effect boundary and should not be enabled before the process
backend lifecycle is migrated and tested.

Reason: this preserves the Python behavior that motor-debug omits rangefinder
prepare services while moving the project-level real process configuration into
the Rust package. The next slice can implement process start/stop behind the
same service plan without changing config shape or summary contracts.

## 2026-06-12: Rust real common-doctor produces task-doctor evidence

Decision: add `navlab-real common-doctor <task-id>` as the next Rust real
migration slice. The command can consume an explicit upstream evidence JSON, or
probe the live ROS graph with `ros2 topic list -t`, then writes both a
common-doctor summary and an optional upstream evidence JSON that
`navlab-real task-doctor` can consume unchanged. Missing ROS, missing required
topics, forbidden simulation topics, and SRC2 without external-nav readiness
all fail closed.

Basis: Python common-doctor is the shared bridge between prepare topic evidence
and task-specific doctor logic. Rust task-doctor already owns the downstream
artifact contract, so the clean boundary is to make common-doctor the producer
of the same upstream evidence structure rather than duplicating task checks.

Reason: this preserves the real task registry expansion model and keeps live
side effects bounded. The current Rust slice validates ROS topic presence/type
and FCU/external-nav metadata, while deeper prepare/runtime service ownership
and MAVLink execution can migrate later without changing the task-doctor input
contract.

## 2026-06-12: Rust real task-doctor consumes upstream evidence

Decision: migrate the next Rust real slice as `navlab-real task-doctor
<task-id>`. The command reads task config, consumes an optional upstream
evidence JSON file, writes a task-doctor `summary.json`, and currently ports the
motor-debug task-specific doctor contract. Without upstream evidence it fails
closed with `upstream_evidence_missing`; with FCU status metadata it reports the
observed mode while keeping GUIDED mode switching deferred to the run stage.

Basis: Python task-doctor combines upstream ROS topic evidence with
task-specific checks. Rust real does not yet own prepare/common ROS sampling, so
the safest migration boundary is an explicit artifact input rather than live ROS
side effects.

Reason: this lets prepare/common doctor later feed the same Rust task-doctor
contract without changing business logic. It also preserves the real task
registry model and keeps motor-debug from requiring current GUIDED mode during
doctor, matching the Python safety policy.

## 2026-06-12: Rust real migrates preflight as fail-closed probes

Decision: add `navlab-real preflight` as the next Rust real migration slice.
The command loads real project config, evaluates `process+real` runtime mode,
checks configured serial MAVLink endpoint shape, probes dependency command
groups, Python modules, ROS package prefixes, and process-service requirements,
then writes a `summary.json` artifact. It does not start prepare services,
connect to MAVLink, arm motors, or perform flight side effects.

Basis: Python real preflight is the safest real workflow to migrate after the
Rust CLI/logging/registry base because its useful behavior is environment
validation and artifact reporting. The current host may legitimately miss ROS,
Python runtime modules, or `/dev/ttyUSB1`; Rust should report those as
blockers rather than silently passing.

Reason: this gives Rust real a practical fail-closed operator check before
moving live prepare or motor-debug execution. Environment probing is behind a
trait and tested with `mockall`, so future MAVLink heartbeat and ROS probes can
be migrated without hardwiring hardware side effects into unit tests.

## 2026-06-12: Rust real tests use layered test tooling

Decision: use Rust's built-in test harness for simple unit tests, `rstest` for
parameterized task/config validation, `insta` for JSON/YAML output contracts,
`mockall` for future MAVLink/ROS boundary mocks, `criterion` for focused
performance benchmarks, and `tokio::test` for async runtime tests.

Basis: Rust real will migrate safety-critical preflight, prepare,
task-doctor, and MAVLink execution logic. Those paths need cheap unit tests,
stable artifact snapshots, and mockable hardware/process boundaries without
starting real flight side effects in normal CI.

Reason: this keeps ordinary `cargo test` fast and deterministic while still
making output contracts and future MAVLink abstractions testable. Benchmarks
compile in the full local check through `cargo bench --no-run`; CI/pre-commit
avoid running performance measurements by default.

## 2026-06-12: Rust real starts with CLI, registry, and tracing logging

Decision: start the Rust real orchestration package as an independent crate
under `orchestration/real`, with Clap CLI commands, a real task registry,
project/task config loading, dry-run `motor-debug`, and a reusable tracing
logging module. The logging module uses `tracing`, `tracing-subscriber`,
`tracing-appender`, `anyhow`, and `thiserror`, with human or JSON console
formatting and optional rolling file output. OpenTelemetry is intentionally not
implemented in this slice.

Basis: Python real remains the live side-effect implementation, but the
long-term split requires real orchestration to move to Rust without sharing
Python helpers with Go sim. The first Rust slice should establish the command,
config, logging, and registry contracts before MAVLink/ROS runtime side
effects move.

Reason: this preserves the task registry expansion path while keeping real
flight behavior fail-closed. `ratatui` was pinned to `0.29` after `0.30.1`
failed to compile in the current Rust 1.88 toolchain due an upstream
`ratatui-widgets` trait conflict. `crossterm`, `indicatif`, `mavlink`, and
`mcap` are present for the real terminal/runtime roadmap, but the initial
executable path only exposes dry-run behavior.

## 2026-06-12: Go sim owns simulation image builds

Decision: move simulation Docker image build orchestration into Go sim and
delete the legacy Python build surface. `navlab-sim build` owns image builds
from the Go `config.toml` image catalog, with `--tag` override and `--dry-run`
command inspection. The Python CLI `build` command and
`orchestration/src/images.py` were removed.

Basis: Go sim now owns the simulation control plane, including task registry,
runtime execution, ROS evidence probes, acceptance summaries, and artifact
generation. Leaving image build orchestration in Python would keep an obsolete
simulation entry point after the rest of sim moved to Go.

Reason: this closes the remaining Go sim command parity gap without deleting
Python real orchestration prematurely. Python image config dataclasses remain
only as part of the real/shared config reader until Rust real replaces that
surface; active sim image build behavior is Go-owned.

## 2026-06-12: Go sim metric-depth parity uses ROS status evidence

Decision: implement hover/exploration/scan-robustness metric-depth parity as
structured ROS status evidence. Runtime scripts publish drift, owner
uniqueness, FCU mode-window, exploration progress, SLAM odometry quality, scan
stabilization, and airframe disturbance profile-sweep fields on status topics.
Probe scripts parse `std_msgs/String.data` JSON into structured payloads, and
`summary.json.gate_evaluation.metrics` aggregates the key fields for final
inspection.

Basis: live task parity already passed at the service/probe/rosbag/landing
level, but the remaining gap was metric visibility. The old Python helper logic
mixed orchestration with metric extraction; Go sim should keep orchestration
ownership while treating Python runtime code and ROS topics as process
boundaries.

Reason: this keeps the sim/real split clean and preserves the task registry
extension path. Metrics are now artifact evidence, not imported helper state:
runtime status topics are the source, probe JSON is the sampled record, and the
final summary is the operator-facing aggregation.

## 2026-06-12: Go sim runtime/probe placeholders replaced by ROS evidence

Decision: replace generated Go sim placeholder runtime/probe scripts with ROS
topic behavior and validate the three built-in sim tasks live. The FCU runtime
script now subscribes to FCU pose and optional raw IMU/scan topics, then
publishes `/slam/odom`, controller/owner/hover/landing status, setpoint output,
rangefinder evidence, scan stabilization status, airframe disturbance status,
and IMU/scan relay topics. Probe scripts now sample ROS topics with `ros2 topic
echo` and use `rclpy` subscriptions for full `std_msgs/String` status payloads.
Rosbag outputs are isolated per record under `rosbag/<record-name>`.

Basis: live hover initially proved Docker/Gazebo/SITL orchestration worked but
blocked on missing ROS evidence. Exploration then exposed missing setpoint
output and shared rosbag output directories. Scan robustness exposed missing
IMU/stabilization/disturbance status topics and an outdated p12 FCU status
topic contract.

Reason: Go sim should fail or pass from ROS/artifact evidence, not planned JSON
markers. The current live checks passed for `hover`, `exploration`, and
`scan-robustness`; the follow-up metric-depth slice now extends this same
evidence path instead of reintroducing Python orchestration helpers.

## 2026-06-12: Go sim acceptance summaries block on missing runtime evidence

Decision: migrate Go sim live summaries from planned result gates to
artifact-based gate evaluation. `summary.json` now evaluates runtime errors,
required probe outputs, rosbag metadata required-topic counts, task-specific
config checks, and landing acceptance for hover, exploration, and
scan-robustness. Live finalization also writes `run_config.toml` and
`summary.md`, and records both files in the manifest.

Basis: the Go live runner can now start runtime specs, but acceptance parity
requires the final result to be driven by evidence artifacts rather than by the
existence of a plan. Python acceptance code blocked when probe summaries,
rosbag metadata, controller/landing evidence, or required task claims were
missing.

Reason: the Go implementation should fail closed. A runtime can finish without
proving task acceptance; in that case the summary must be `blocked` with
specific missing/evidence blockers. The later metric-depth slice reuses the same
summary contract by adding drift, owner, FCU mode-window, profile-sweep, and
SLAM quality fields under artifact-backed metrics.

## 2026-06-12: Go sim live run executes runtime specs before gate parity

Decision: enable `navlab-sim run <task>` without `--dry-run` for the Go sim
package by executing the generated `RuntimeSpecBundle` through the Docker
backend, writing `summary.json`, and recording it in the manifest. Add static
task doctor commands for `hover`, `exploration`, and `scan-robustness` that
reuse the same config, artifact generation, and runtime spec validation path
without starting Docker/ROS.

Basis: Go sim already owns task planning, config normalization, generated
runtime artifacts, runtime specs, Docker backend command construction, and a
generic runtime runner. The next parity step is to remove the CLI guard that
blocked live execution while preserving a truthful artifact contract.

Reason: live runtime orchestration can be tested and used before full
task-specific blocker parity is ported. The live summary therefore reports
runtime execution facts and keeps result gates marked as planned from the
execution plan, instead of claiming Python-equivalent acceptance results. This
lets Docker/ROS lifecycle bugs surface in Go now while keeping final gate parity
as an explicit remaining migration slice.

## 2026-06-12: Python orchestration deletion waits for whole-slice parity

Decision: delete generated Python caches immediately, but retire Python source
by ownership slice rather than file-by-file. Legacy sim source under
`orchestration/src/tasks/built_in`, `orchestration/src/tasks/workflows`, and
sim-only `orchestration/src/tasks/helpers` will be deleted after Go sim owns
live execution and gate summaries. Real orchestration Python will stay until
Rust real owns preflight, prepare, motor-debug, and process/runtime control.

Basis: Go sim now owns dry-run planning, config normalization, runtime artifact
generation, manifest entries, runtime specs, and a generic runner, but Python
sim live workflows still import helpers as a connected graph. Python real is
also still the active implementation for real prepare/task-doctor/motor-debug.

Reason: deleting individual helpers as soon as their pure logic is ported would
break the old Python entry point without removing that entry point. Whole-slice
retirement keeps the repository coherent while still preventing migrated Python
orchestration from lingering after Go or Rust parity exists. Python under
`navlab.*` remains runtime code, not orchestration control-plane code.

## 2026-06-12: Go sim adds a generic runtime runner behind dry-run

Decision: add a task-level runtime runner that executes a `RuntimeSpecBundle`
through the `runtime.Backend` interface by starting services, starting rosbags,
running probes, optionally waiting for rosbags, and cleaning up handles in
reverse order on success or failure. The public CLI still rejects non-dry-run
task execution.

Basis: hover, exploration, and scan-robustness live execution all need the same
service/probe/rosbag ordering and cleanup behavior. Implementing that lifecycle
behind the disabled live path lets Go tests validate orchestration semantics
without starting Docker, Gazebo, SITL, or ROS.

Reason: this keeps the next migration slice reusable and bounded. The backend
contract can now be tested with a fake runtime backend, while task-specific gate
evaluation and operator-facing live commands remain separate follow-up work.

## 2026-06-12: Go sim dry-run generates runtime artifacts

Decision: extend `navlab-sim run <task> --dry-run` so it generates the
task-specific runtime artifacts for hover, exploration, and scan-robustness
from the normalized `TaskRuntimeConfig`. The generated files include bridge and
vendor profiles, sensor/SLAM/FCU/frame/hover/exploration/stabilization runtime
TOML, runtime probe scripts, workflow probe scripts, and P12 bridge overrides.

Basis: the remaining sim migration needs the Go control plane to own the
parameterized artifact surface before live Docker/ROS execution is enabled.
Runtime spec validation alone proved commands could be shaped, but did not yet
prove the referenced probe/config files were produced by Go.

Reason: generating these files in dry-run keeps the migration side-effect
boundary clear: Go now owns deterministic task expansion and file artifacts,
while Docker containers, ROS graph sampling, and task execution remain disabled
until the live runner is introduced. This also preserves the task registry and
helper ownership model without reintroducing Python orchestration imports.

## 2026-06-12: Go sim normalizes full simulation runtime config before live runner

Decision: port the remaining Python simulation `RunConfig` surface into Go
typed config structs and normalize project defaults plus task YAML overrides
into `TaskRuntimeConfig`. Dry-run task plans now include this normalized runtime
config under `execution_plan.task_parameters.runtime_config`.

Basis: the remaining sim migration design requires full config schema before
hover/exploration/scan-robustness live runners can move. The legacy Python
runner relied on a large `RunConfig` object for topic contracts, runtime
thresholds, rosbag profiles, and safety/source claims.

Reason: live execution should consume a typed request instead of re-inferring
defaults inside every helper. Keeping this in dry-run first makes the normalized
runtime contract inspectable and testable while Docker/ROS side effects remain
disabled until a dedicated runner is introduced.

## 2026-06-12: Go sim remaining migration starts with runtime backend base

Decision: document the remaining simulation migration in
`docs/general/orchestration_sim_remaining_migration_design.md`, then migrate the
first missing base layer into Go: `internal/runtime` service/probe/rosbag specs,
a Docker CLI backend, and an adapter from task `ExecutionPlan` to executable
runtime specs. Dry-run now validates service/probe/rosbag specs and reports
their counts without starting Docker or ROS. The remaining pure `motion` helper
is also ported as P7 doctor summary and Foxglove notes logic, so no sim helper
remains in `planned` status.

Basis: user asked to first write a design document, then migrate the unfinished
simulation contents that were still outside `orchestration/sim`.

Reason: live hover/exploration/scan-robustness runners all need the same
backend contract before task-specific acceptance logic can move. Starting with
runtime specs avoids duplicating Docker/probe/rosbag mechanics inside each
helper and keeps dry-run behavior side-effect free while making future execution
plans mechanically valid. Porting `motion` closes the last non-runtime helper
gap before moving to full config schema and live task runners.

## 2026-06-12: Go sim owns deep runtime/probe/task execution planning

Decision: migrate the deeper simulation helper layer into Go as explicit
runtime execution planning. `sensors`, `fcu-controller`, `frame-contract`,
`slam-hover`, `scan-stabilization`, `exploration-workflow`, and
`scan-robustness-workflow` now have Go-owned runtime specs, generated artifact
plans, ROS probe/script plans, Docker service command plans, rosbag record
plans, and result gate plans. Their helper inventory status is
`ported_partial,runtime` instead of `planned,runtime`.

Basis: user asked to migrate the deeper ROS probe/runtime script/task execution
parts, including sensors, FCU controller, frame contract, SLAM hover, scan
stabilization, and workflow bodies.

Reason: the Go orchestration package should own task expansion, artifact
contracts, runtime service intent, and probe/gate topology before live execution
is enabled. The current CLI remains dry-run only, so Docker/ROS side effects are
still not started accidentally. Runtime probe scripts may still be Python inside
ROS containers because the navlab runtime remains Python, but the orchestration
helper logic that selects, parameterizes, and records those scripts is now in Go.

## 2026-06-12: Go sim runtime helpers migrate by side-effect boundary

Decision: runtime helpers with Docker/ROS side effects are migrated in partial,
testable slices. `navlab-models` now owns Go generation for P1 bridge/vendor
profiles plus Docker remove/log/gazebo-sensor command wrappers. `official-stack`
now owns Go Cartographer Lua parsing and Docker ROS shell command planning.
`slam` now owns Go P3 SLAM runtime TOML generation and SLAM backend Docker
command planning. Helpers that still require live ROS graph sampling or task
runtime execution remain marked `planned,runtime`.

Basis: user asked to continue migrating helpers that were still
`planned,runtime`, while preserving the task helper ownership under
`internal/tasks/helpers`.

Reason: splitting side-effect helpers into file generation, command planning,
and live execution lets Go tests cover deterministic behavior now, without
requiring Docker/Gazebo/ROS availability in every test run. The later runner can
reuse the same command/spec functions when real task execution is enabled.

## 2026-06-12: Go sim helper migration starts with inventory plus pure helpers

Decision: migrate Python non-real task helpers into Go sim in two layers. First,
`internal/tasks/helpers` records every non-real Python task helper/workflow used
by hover, exploration, and scan-robustness. Second, pure helpers that do not
need Docker, ROS, MCAP, or generated runtime scripts are ported directly to Go:
artifacts, rosbag profile parsing, landing gate logic, and scan-integrity motor
output candidate detection. These helpers live in one Go package with separate
files, not many one-function subpackages.

Basis: user asked to migrate all non-real Python task helpers, while preserving
task registry expansion. The helper set includes both small pure helpers and
large runtime helpers that start containers, generate Python ROS probes, inspect
ROS graphs, or write SDF/runtime overlays.

Reason: the inventory makes the full migration surface explicit in every
dry-run task plan. Porting pure helpers first gives testable Go behavior without
creating a half-migrated Gazebo/SITL execution path. Keeping them under
`internal/tasks/helpers` matches the old Python task-helper ownership while
avoiding a proliferation of tiny Go packages. Runtime helpers remain marked
`planned,runtime` until their Docker/ROS side effects are replaced in Go.

## 2026-06-12: Go sim dry-run writes task plan artifacts

Decision: `navlab-sim run <task> --dry-run` now writes a run-scoped
`task_plan.json` and `manifest.json` under the configured sim artifact root.
The manifest records contract version, implementation, runtime mode, backend,
task id, run id, and artifact hashes.

Basis: the Go task registry needs a stable artifact boundary before real
Gazebo/SITL/Docker execution is migrated. The user also wants proto/contract-like
constraints for task parameters and results across future Go/Rust/Python
boundaries.

Reason: dry-run artifacts make the task request/plan observable and testable
without pretending that runtime execution has already been ported. The same
artifact writer can later be extended to write proto-backed task request/result
files when real task runners are added.

## 2026-06-12: Go sim task registry starts with dry-run planning

Decision: implement the first Go simulation task layer as a registry-backed
planner. `navlab-sim doctor`, `list-tasks`, `show-task`, and `run <task>
--dry-run` use the Go registry plus YAML task configs, while real execution of
Gazebo/SITL/Docker services remains deferred.

Basis: user wants the task registry pattern preserved for fast task expansion,
but the current migration should not silently pretend that the old Python task
execution flow has already been ported.

Reason: a dry-run task plan establishes the extension point, task metadata,
capability declarations, config overrides, and CLI shape without creating a
half-migrated runtime path. Each task can later replace its plan steps with real
Go execution while keeping the same registry contract.

## 2026-06-12: Orchestration splits into sim and real packages

Decision: new orchestration work lives under only two package roots:
`orchestration/sim` for the Go simulation control plane and `orchestration/real`
for the Rust real-machine control plane. Each package owns its own project-level
`config.toml` at the package root, while task configs live under that package's
`configs/tasks/*.yaml`.

Basis: user clarified that the long-term shape is two independently adaptable
orchestration packages/repositories, not a shared Python orchestration tree or a
top-level shared `orchestration/configs` directory.

Reason: package-root `config.toml` makes each orchestration implementation
self-contained when it is split into its own repository. Keeping task configs in
`configs/tasks` preserves a clear distinction between project-level runtime
configuration and task-level parameters. Preflight and prepare are intentionally
not migrated in this slice.

## 2026-06-11: Real prepare and doctor phases have separate modules

Decision: keep real prepare startup/cleanup in `src.workflows.real.prepare`,
common FCU/ExternalNav checks in `src.workflows.real.common_doctor`, and task
doctor orchestration in `src.workflows.real.task_doctor`.

Basis: user clarified that `real_prepare` should not own common doctor or
task-specific doctor behavior.

Reason: prepare starts and stops services; common doctor evaluates shared FCU
and ExternalNav state after prepare; task doctor delegates task-specific checks
to the task object itself through `OrchestrationTask.build_real_task_doctor`.
Tasks that do not override that hook are skipped for task-specific doctor
checks instead of being hard-coded in a central branch.

Decision: real-runtime preflight/prepare/common-doctor/task-doctor modules live
under `src.workflows.real`, not `src.tasks`.

Basis: user clarified these modules are orchestration workflow phases rather
than user-facing tasks.

Reason: `src.tasks` should contain runnable task objects and task hooks.
Workflow phases coordinate runtime services, doctor gates, cleanup, and panels.
The hidden real-preflight registry entry may keep a small compatibility shim
under `src.tasks.built_in` only for registry compatibility.

## 2026-06-11: SITL companion nodes move under `navlab.sim`

Decision: move the remaining SITL mission, replay, marker, odom-relay, and scan
feature ROS entrypoints from the legacy companion node package into
`navlab.sim.companion.nodes`.

Basis: these nodes are used by simulation/acceptance flows, publish `/sim/*` or
Gazebo/replay artifacts, or run SITL-only mission controllers. They do not
belong in an unqualified top-level companion runtime namespace.

Reason: the target package boundary is safety-domain first. `navlab` should
converge on top-level `common`, `real`, and `sim` packages only; remaining
top-level packages are transitional migration surfaces.

## 2026-06-11: `navlab` top-level runtime packages converge to `common`, `real`, and `sim`

Decision: keep `navlab` top-level runtime ownership limited to `common`,
`real`, and `sim`. Move the former top-level `companion`, `gazebo_sensor`,
`slam`, and `interfaces` code under those domains instead of keeping
transitional top-level packages.

Basis: user clarified that code directly under `navlab` should be domain-neutral
only when it is truly common; otherwise it should live under the real or sim
safety-domain package.

Reason: a three-package top-level boundary makes it obvious whether code may
touch real hardware, simulation-only topics, or pure shared utilities.

Update: SLAM backend/config wrappers now live under `navlab.common.slam`,
Gazebo sensor runtime lives under `navlab.sim.gazebo_sensor`, simulation
companion launcher/config/acceptance code lives under
`navlab.sim.companion.runtime`, and ROS interface packages live under
`navlab.common.interfaces`.

## 2026-06-11: SLAM wrapper is shared common runtime

Decision: move the SLAM backend registry, runtime config, and CLI wrapper to
`navlab.common.slam`.

Basis: codebase research and user clarification.

Reason: the current SLAM wrapper does not own real hardware or Gazebo-specific
behavior. It defines a shared backend launch/config contract used by both real
and sim flows. Keeping it in `common` avoids duplicating launch arguments while
still allowing future `navlab.real.slam` or `navlab.sim.slam` packages if the
runtime behavior diverges.

## 2026-06-11: FCU MAVLink companion nodes are real runtime nodes

Decision: move the NavLab MAVLink bridge launcher, pose mirror, ExternalNav
sender, and IMU bridge under `navlab.real.companion.nodes`.

Basis: these entrypoints open MAVLink endpoints, request FCU streams, publish
FCU-derived status, or send MAVLink ODOMETRY. That is real FCU runtime behavior,
even when a SITL endpoint is used during development.

Reason: keeping these nodes under the top-level companion namespace blurred the
real/sim safety boundary. `orchestration` now keeps only the FCU bridge mode
registry and configured process command; the running MAVLink bridge code lives
inside the real runtime namespace.

## 2026-06-11: Gazebo truth nodes are simulation runtime nodes

Decision: move Gazebo truth odometry and Gazebo truth trajectory recording under
`navlab.sim.companion.nodes`.

Basis: these nodes consume Gazebo pose/odom topics and are SITL diagnostics, not
shared companion behavior for the real aircraft.

Reason: keeping Gazebo truth under the common companion node namespace made it
look available in real runtime. The sim namespace makes the diagnostic nature
explicit while preserving the same configured launch behavior.

## 2026-06-11: Runtime result contracts live in top-level `contracts/proto`

Decision: define language-neutral runtime artifact schemas under
`contracts/proto`, beside `navlab` and `orchestration`, instead of placing them
inside either package.

Basis: orchestration provides output file paths, runtime tasks write result
files, and orchestration reads those files for panels and CLI return codes. The
same artifact should remain readable by future Python, Rust, or other-language
tools.

Reason: `navlab` owns runtime behavior and `orchestration` owns process/control
flow. A sibling contract package avoids making either side the schema owner and
prevents future non-Python readers from importing Python runtime modules just to
parse task results.

## 2026-06-11: Real runtime code moves under `navlab.real`

Decision: move real hardware runtime code out of `orchestration/src/tasks` and into `navlab.real.*`; keep `orchestration` as the process/control plane.

Basis: package-boundary design in `docs/general/navlab_real_sim_package_boundary_design.md` and the current conflict where task wrappers also owned runtime nodes.

Reason: `navlab.real` is the safety boundary for code that may touch real serial devices, FCU links, or motor-affecting MAVLink commands. `orchestration` should provide config, paths, process lifecycle, doctor flow, and panels, but not directly own real runtime behavior.

## 2026-06-11: Motor-debug runtime writes summary to an orchestration-provided file

Decision: `orchestration` launches `navlab.real.companion.nodes.motor_debug` with `--summary-path`; the runtime writes the task summary file, and `orchestration` reads that file to add logs/task metadata and print panels.

Basis: user clarified that orchestration should provide file storage locations while runtime tasks emit their results to files.

Reason: a file contract keeps real MAVLink arm/hold/disarm behavior out of the orchestration process while preserving the existing artifact and panel workflow.

## 2026-06-10: FCU status fields are shared between bridge and common doctor

Decision: define FCU common-doctor fields once in `navlab.real.common.fcu_status`, and use that same list for both MAVLink bridge parameter publication and common-doctor parsing.

Basis: real `motor-debug` common doctor showed `Mode/GPS/VISO/EK3` as `unknown` even though those values are available from MAVLink, because the doctor expected fields that `/navlab/mavlink/status` was not publishing.

Reason: duplicating field names across the bridge and doctor creates silent drift. The bridge now requests the shared MAVLink parameters and publishes them under `/navlab/mavlink/status.parameters`; the doctor waits for that status to contain mode plus at least one shared parameter before summarizing.

Update: this module moved from the old top-level common FCU-status location to `navlab.real.common.fcu_status` because EKF source-set and ArduPilot FCU parameters are real-runtime semantics, not top-level shared utility code.

## 2026-06-10: Motor-debug GUIDED is a run-stage gate

Decision: `motor-debug` task doctor records the required mode and current FCU mode, but it does not block merely because the FCU is not already in `GUIDED`.

Basis: user clarified the task boundary: doctor checks FCU link / ExternalNav / task config, while `motor-debug run` owns switching to `GUIDED`, confirming it, then arm / hold / disarm.

Reason: requiring current `GUIDED` during task doctor turns a runtime state transition into a precondition and blocks the normal flow from `STABILIZE` to `GUIDED`. The hard gate belongs immediately before arm, where the MAVLink run path can send `set_mode(GUIDED)` and verify the heartbeat mode before `MAV_CMD_COMPONENT_ARM_DISARM`.

## 2026-06-10: Real common doctor uses a fixed metadata field list, not a new config surface

Decision: keep `real common doctor` field discovery as a small hard-coded `MetadataField` list that is iterated at runtime, instead of adding a separate config section for each EKF alias.

Basis: user feedback on the common-doctor boundary and local implementation shape.

Reason: the shared FCU / EKF / ExternalNav panel needs stable field names, but splitting those into dozens of config keys adds noise without buying flexibility. A field list keeps the structure explicit while still making the looped extraction easy to extend.

## 2026-06-10: No-props motor debug is a separate real task

Decision: add `run motor-debug` as a process+real-only task that uses MAVLink motor-test commands under explicit no-props and operator-safety confirmations.

Basis: current hardware debugging needs motor rotation without propellers, takeoff, hover, or landing.

Reason: motor-output checks should not reuse `hover` semantics. A separate task keeps no-props motor tests from being confused with autonomous flight readiness and lets dry-run print the debug plan without spinning motors.

## 2026-06-10: Real operator safety uses explicit wrapper flags

Decision: require non-dry-run real task execution to pass `--confirm-manual-takeover`, `--confirm-kill-switch`, and `--confirm-safe-area` before any future arm/takeoff path.

Basis: RTD.10 needs real operator safety confirmation without relying on simulation artifacts.

Reason: manual takeover, kill switch readiness, and safe-area checks are human/operator facts. They must be explicit at the real wrapper boundary and skipped only for dry-run because dry-run does not execute flight.

## 2026-06-10: Real pre-takeoff gates do not require Stage 1 artifacts

Decision: remove Stage 1 `ideal` and `mild_disturbance` artifacts as mandatory blockers for the real wrapper.

Basis: user hardware path and RTD.5A/RTD.5B real dry-run evidence already come from real lidar, FCU, SLAM, rangefinder, and task doctor summaries.

Reason: simulation artifacts are useful for regression and design comparison, but they do not prove the real aircraft's current sensors, FCU, operator safety, or flight environment. Real gates must depend on real evidence only.

## 2026-06-10: Real task doctor probes frame contracts directly

Decision: make RTD.7 validate `/scan` and `/slam/odom` frame IDs from sampled ROS message headers instead of relying only on topic presence and type.

Basis: codebase research on `check_real_task_upstream_topics` and the RTD.7 acceptance gap.

Reason: real SLAM/yaw readiness depends on frame correctness; a fresh topic with the wrong frame can make ExternalNav evidence unsafe even when topic list and type checks pass.

## 2026-06-10: Real RTD.5B height gate uses FCU DISTANCE_SENSOR plus altitude-hold contract

Decision: implement real height readiness as a NavLab rangefinder bridge from FCU MAVLink `DISTANCE_SENSOR` to `/rangefinder/down/range` and `/rangefinder/down/status`, then bind hover/landing task doctor to an explicit `altitude_hold_mode` gate.

Basis: RTD.5A real dry-run proved yaw through `/scan + /imu -> SLAM -> ExternalNav`; RTD.5B dry-run summary `artifacts/ros/navlab_real_prepare/20260610_081003/summary.json` shows the real FCU publishes down-facing `DISTANCE_SENSOR` with `orientation=25`, but current table placement reports `current_distance_m=0.0`.

Reason: horizontal 2D lidar/yaw readiness cannot prove vertical hover or landing safety. The real gate must reject invalid or stale height evidence and must not release autonomous hover only because SLAM yaw is ready.

## 2026-06-09: Landing acceptance gates precede real landing control

Decision: add the unified landing policy, summary schema, rosbag contract, and Stage 1/Stage 2 blocker before implementing the FCU LAND / return-home control path.

Basis: codebase research and the unified landing design.

Reason: hover, P8, and P12 currently finish at final hold/stop semantics. Marking landing as passed without a real LAND/disarm execution path would hide a safety gap. The first implementation slice makes incomplete landing visible in summaries and blocks full acceptance, while leaving actuator-level landing control as an explicit follow-up.

## 2026-06-09: Orchestration legacy helpers move to helpers/workflows

Decision: delete `orchestration/src/tasks/legacy` by moving reusable gate code into `src.tasks.helpers` and built-in task workflows into `src.tasks.workflows`.

Basis: codebase research and current task-surface cleanup.

Reason: the runnable task surface is already reduced to built-in tasks, but P8/P12 still depended on legacy module names. A package-level split removes the legacy import boundary now while preserving gate function bodies and test behavior. Smaller function-level cleanup can continue inside the helper package without keeping a legacy compatibility layer alive.

## 2026-06-03: NavLab Gazebo uses IQ-style quad with ArduPilot Gazebo plugin

Decision: use `iq_sim` as the Iris quad + lidar model reference, but build the runtime plugin from official `ardupilot_gazebo`.

Basis: codebase research and upstream docs.

Reason: `iq_sim` demonstrates the quad layout, rotor channel mapping, and mounted lidar structure the lab wants, but it targets Gazebo Classic / ROS 1. The current runtime is ROS Jazzy / Gazebo Harmonic, so the actual SITL-Gazebo JSON bridge should come from official `ardupilot_gazebo`. Model files stay in `world-model` and are mounted into the Gazebo container; plugin code and base image construction stay in `sim-infra`.

## 2026-06-03: NavLab service images use separate Dockerfiles

Decision: keep `navlab-companion`, `navlab-slam-cartographer`, and `navlab-gazebo-sensor` in separate Dockerfiles.

Basis: codebase research and service ownership.

Reason: companion, SLAM, and Gazebo/sensor runtimes have different dependency owners. The sensor image owns YDLidar SDK and the vendor driver, the SLAM image owns Cartographer and NavLab ROS localization packages, and the companion image owns mission/MAVLink/runtime Python plus shared ROS message compatibility. Separate Dockerfiles make manual builds, cache behavior, and future algorithm swaps easier to reason about.

## 2026-06-04: NavLab replay publishes self-contained quadrotor markers

Decision: publish the moving `navlab_iq_quad` replay model on `/sim/markers` as self-contained primitive geometry: body, heading arrow, arms, rotor discs, motors, and X2 lidar marker.

Basis: codebase research and Foxglove replay constraints.

Reason: the Gazebo world already flies `model://navlab_iq_quad`, but ROS MCAP replay cannot directly render Gazebo's nested model tree. File-path mesh resources such as `file:///workspace/...` only work on machines with that exact path, so they fail for Foxglove Cloud and for other developers' local replay. MCAP attachments are not automatically resolved by `visualization_msgs/Marker` mesh resources, and large Collada payloads are not a good fit for repeated ROS Marker messages. Primitive markers are portable and visible anywhere the MCAP is opened. Exact mesh replay should be added later as a Foxglove `SceneUpdate` channel using `ModelPrimitive.data`, not as ROS Marker `file://` resources.

## 2026-06-07: NavLab P6 records a portable vehicle shell layer

Decision: record `/navlab/vehicle/markers` in the P6 SLAM hover MCAP and generate it from the FCU pose with primitive `MarkerArray` geometry.

Basis: current replay gap and Foxglove portability.

Reason: P6 already proves the SLAM -> ExternalNav -> EKF -> hover loop, but Foxglove replay still needs a vehicle shell layer to make the motion readable. The shell must not depend on local mesh paths because the same MCAP should open on another laptop or in Foxglove Cloud. A primitive `MarkerArray` following `/ap/v1/pose/filtered` is self-contained, portable, and easy to keep in acceptance as a required topic.

## 2026-06-07: NavLab P7 doctor stays a fast config gate

Decision: make `motion-gate-doctor` validate P7 configuration, rosbag profile, topic contracts, and truth-control boundaries without re-running the full P0-P6 dependency doctor chain by default.

Basis: local P7 implementation and doctor runtime behavior.

Reason: P7 acceptance already launches and validates the full official stack, sensors, SLAM, frame contract, FCU bootstrap, and motion gate. Nesting all prior doctor dependency probes inside P7 doctor makes the lightweight prerequisite check slow enough to obscure config failures. The fast doctor keeps P7 iteration usable while preserving full-stack proof in `motion-gate-acceptance`.

## 2026-06-04: NavLab hover gate requires SLAM-derived ExternalNav

Decision: current completion gate must feed `external_nav_bridge` from SLAM `/odom`, not from `/gazebo/truth/odom`.

Basis: current phase goal and real-machine migration requirement.

Reason: Gazebo truth is useful for diagnosing ArduPilot Gazebo plugin, SITL parameters, coordinate transforms, and FCU ExternalNav acceptance, but it does not exist on the real machine. If the acceptance gate passes while ExternalNav comes from Gazebo truth, the result only proves a diagnostic FCU path, not a real no-GPS SLAM feedback loop. The current phase is complete only when `/scan + /imu/data -> SLAM -> /odom -> /external_nav/odom -> MAVLink ODOMETRY -> SITL EKF -> LOCAL_POSITION_NED` holds during takeoff and hover.

Implementation note: `/gazebo/truth/odom` should still be recorded in rosbag and summary for error analysis. It must be labeled as diagnostic truth, and acceptance should mark the run blocked or not complete if it is used as the ExternalNav source.

## 2026-06-04: NavLab figure-eight world uses narrow corridors

Decision: use a horizontal figure-eight indoor world with about `0.60 m` side corridors, about `0.725 m` north/south corridors, and a wider `1.55 m` shared waist around the origin.

Basis: current phase goal and local Gazebo validation.

Reason: the current phase needs a world that is tight enough to expose lidar orientation, TF, marker frame, and SLAM map issues before adding exploration. The side and top/bottom corridors are deliberately much narrower than the earlier wide room, while the center waist remains wider so the quad can take off and hover at the origin without immediately colliding. Gazebo truth remains diagnostic, but `/scan_ideal` now publishes real ray data against the narrowed walls.

## 2026-06-04: NavLab down rangefinder is a gazebo-sensor FCU peripheral

Decision: superseded for SITL FCU input by the 2026-06-16 Benewake serial
boundary decision. `gazebo-sensor` still publishes ROS review/height topics
from the Gazebo down range observation, but it must not inject FCU rangefinder
data with MAVLink `DISTANCE_SENSOR` in sim.

Basis: current phase goal and real-machine mechanism.

Reason: on the real drone, altitude hold can be handled by the FCU using its
own rangefinder input; the companion computer should not be required just to
hold height. The accepted SITL equivalent is now `Gazebo range observation ->
ArduPilot Benewake serial simulator -> SITL Serial7 -> FCU`, while
`/rangefinder/down/range` is a ROS observation topic for height estimator,
review, summary, and rosbag. Companion may observe `/rangefinder/down/status`,
FCU telemetry, and Gazebo truth for summary and rosbag, but it must not send
rangefinder data or directly control throttle/pose for hover.

## 2026-06-04: NavLab replay TF closes through navlab_world-map-odom-base_link

Decision: publish replay/display transforms as `navlab_world -> map -> odom -> base_link -> laser_frame/imu_link`.

Basis: P3 TF validation and Foxglove replay requirements.

Reason: Foxglove needs every displayed sensor frame to resolve into the fixed frame. `navlab_world` is the stable Gazebo/replay frame, while `map`, `odom`, `base_link`, `laser_frame`, and `imu_link` are the frames expected by SLAM and ROS tooling. The bridge is diagnostic/display infrastructure; it does not command Gazebo and does not replace the real SLAM feedback gate. When a SLAM backend later owns `map -> odom`, the replay bridge can be configured or disabled without changing the sensor and FCU topic contracts.

## 2026-06-04: NavLab X2 simulation keeps ROS 0 degrees as vehicle front

Decision: map Gazebo `/scan_ideal` ROS angle `0` directly into the virtual X2 protocol path and keep the vendor driver profile `reversion=false`, `inverted=false`.

Basis: local container smoke against the figure-eight world and YDLidar X2 profile defaults.

Reason: the previous 180-degree remapping plus driver reversion/inversion made `/scan` appear opposite the vehicle heading in Foxglove. The P3 contract is that `/scan_ideal` and `/scan` use the same geometric convention: `0 deg` is the vehicle front, `+90 deg` is left, `-90 deg` is right, and rear is `+/-180 deg`. Mission and scan feature code should consume that convention directly instead of compensating for a reversed scan.

## 2026-06-04: NavLab SLAM runtime uses a backend registry wrapper

Decision: start SLAM through `navlab.common.slam.cli` and a backend registry instead of assembling Cartographer launch arguments in orchestration.

Basis: codebase research and future backend replacement requirement.

Reason: orchestration should know which container/backend to start, not how a specific SLAM backend launches internally. The stable contract is `/scan + /imu/data -> /odom + SLAM health`; Cartographer is only the current backend. A registry wrapper lets future backends keep the same input/output topics while owning their own launch command, status topic, and internal parameters. It also prevents the host layer from accidentally feeding `external_nav_bridge` with `/gazebo/truth/odom`.

## 2026-06-05: NavLab SLAM ROS packages use NavLab-scoped names

Decision: replace the old Stage 1 ROS package names with NavLab-scoped packages: `navlab_slam_bringup`, `navlab_cartographer_adapter`, `navlab_external_nav_bridge`, `navlab_slam_imu_bridge`, and `navlab_fake_odom`.

Basis: codebase research and SLAM backend replacement requirement.

Reason: names such as `indoor_bringup`, `cartographer_indoor`, and `fake_external_nav` made the current runtime look like the old synthetic Stage 1 path. The SLAM container now exposes a generic contract, `/scan + /imu/data -> /odom + /navlab/slam/status`, while Cartographer remains only the selected backend implementation. This keeps future SLAM backends from inheriting Cartographer-specific or fake-ExternalNav naming.

## 2026-06-05: Cartographer config is part of the completion gate

Decision: treat `navlab_cartographer_2d.lua` and its runtime launch arguments as first-class acceptance inputs, not incidental files behind the adapter.

Basis: codebase research and hover-SLAM diagnostic failures showing `/odom` can be healthy at the transport level while still drifting against Gazebo truth.

Reason: P4 is not complete just because a node publishes `/odom`. The completion gate must prove that `cartographer_ros` is running with an explicit configuration, that the adapter only converts backend TF into odometry, and that real-machine tuning items are documented separately from simulation defaults. The stable contract stays backend-agnostic, but the current backend must still be configured and audited like real SLAM.

## 2026-06-05: Cartographer dependency uses ROS Jazzy binary package first

Decision: use the distro-matched `ros-${ROS_DISTRO}-cartographer-ros` package
in `docker/images/runtime/slam.Dockerfile` as the default Cartographer dependency
source.

Basis: local Docker build and current need to configure Cartographer rather than patch its source.

Reason: the SLAM image already builds successfully with the ROS Jazzy binary package, and the project-owned surface is the NavLab launch/config/adapter contract. Downloading upstream Cartographer source into this repo is only needed if the binary package is unavailable, a specific upstream commit must be locked, or the algorithm source must be patched. Keeping the default route binary-based reduces build complexity while still allowing a future source-build stage with pinned commits.

## 2026-06-04: NavLab orchestration uses a task registry

Decision: dispatch orchestration workflows through `src.tasks.registry` instead of hardcoding workflow bodies in `host.py`.

Basis: codebase research and P5 workflow separation.

Reason: `host.py` should stay focused on Docker, compose, container, and runtime-command primitives. Workflows such as image build, doctor, full acceptance, hover acceptance, and future exploration acceptance have different completion gates and artifact semantics. A task registry keeps the CLI stable while allowing each workflow to own its own run logic, output checks, and future companion command. This prevents P5 hover acceptance from being mixed with the older obstacle demonstration gate.

## 2026-06-04: NavLab hover gate is split into FCU diagnostic and SLAM feedback gates

Decision: add a smaller `hover-diagnostic` gate that starts no SLAM container, does not require ExternalNav readiness, and does not send horizontal local-position setpoints.

Basis: codebase research and failing hover acceptance artifacts.

Reason: the previous hover gate mixed two separate failure classes: FCU altitude/rangefinder/GUIDED/takeoff stability and SLAM-derived horizontal ExternalNav drift. The diagnostic gate proves `GUIDED -> arm -> takeoff -> hover` with rangefinder altitude input and observation-only replay topics first. The full `hover` gate remains the completion gate for `/scan + /imu/data -> SLAM /odom -> /external_nav/odom -> MAVLink ODOMETRY -> SITL EKF -> LOCAL_POSITION_NED` feedback.

## 2026-06-05: NavLab must converge to official ArduPilot ROS2 first

Decision: treat the official ArduPilot ROS2, Gazebo, and Cartographer tutorials plus `ArduPilot/ardupilot_ros` as the baseline for NavLab indoor no-GPS SLAM work.

Basis: external research against `ardupilot.org/dev/docs/ros2.html`, `ros2-sitl.html`, `ros2-gazebo.html`, `ros2-cartographer-slam.html`, and the `ardupilot_cartographer` package.

Reason: the current custom `/odom -> /external_nav/odom -> MAVLink ODOMETRY` path is useful for diagnostics, but it is not the official ROS2/DDS route. To avoid proving a synthetic bridge instead of the real mechanism, the next convergence target is `/ap` DDS visibility, official `ardupilot_gz_bringup` structure, official Cartographer Lua/EKF baseline, and eventually ExternalNav feedback through the official ROS2 interface. The MAVLink sender can remain as a fallback or transition tool, not the completion definition.

## 2026-06-05: P0 official baseline has a separate failing gate

Decision: implement P0 as `official-baseline-doctor` plus `official-baseline-acceptance`, separate from the NavLab hover and obstacle acceptance tasks.

Basis: codebase research and P0 execution.

Reason: Cartographer dependencies can be present while the runtime is still using NavLab's custom SITL/Gazebo/MAVLink fallback route. The P0 gate must therefore report `ok=false` when `/ap` DDS nodes/topics are absent, `external_nav_route` is not `official_dds`, or the Gazebo bringup mode is not the official equivalent. This makes the current failure useful: it proves the project has not accidentally relabeled diagnostic MAVLink feedback as the official ArduPilot ROS2 baseline.

## 2026-06-06: P0 needs an official baseline runtime image

Decision: keep `navlab/companion`, `navlab/slam-cartographer`, and `navlab/ardupilot-sitl` as their current service images, but do not treat any of them as the official ROS2/DDS baseline runtime.

Basis: codebase research, official ArduPilot package inspection, and P0 doctor execution.

Reason: the current SITL image contains `arducopter` but no ROS2 CLI; companion and SLAM images contain ROS2, but lack `ardupilot_sitl`, `ardupilot_msgs`, `ardupilot_dds_tests`, `micro_ros_agent`, `ardupilot_gz_bringup`, `ardupilot_gz_application`, `ardupilot_gazebo`, `ardupilot_gz_gazebo`, `ardupilot_sitl_models`, and `ardupilot_cartographer`. Official bringup requires `ardupilot_sitl sitl_dds_udp.launch.py`, which includes the micro-ROS agent, SITL, and MAVProxy, while `ardupilot_gz_bringup` includes that DDS launch when `use_dds_agent=true`. The next P0 implementation step should therefore create or select a dedicated official baseline image/layer that installs these packages from ArduPilot source repos, rather than weakening P0 to pass through the existing MAVLink fallback route.

## 2026-06-06: P0 pins ardupilot_ros Cartographer source to humble

Decision: keep the official baseline image on ROS Jazzy, but clone `ArduPilot/ardupilot_ros` from the `humble` branch for the `ardupilot_cartographer` package.

Basis: codebase research plus official-source inspection.

Reason: the current `main` and `jazzy` branches of `ArduPilot/ardupilot_ros` only expose the `ardupilot_ros` metapackage, while the official Cartographer launch/config package still exists on the `humble` branch as `ardupilot_cartographer`. P0 is a baseline conformance check for the official DDS/SITL/Gazebo/Cartographer route, so the image must include that package explicitly instead of silently replacing it with NavLab's custom SLAM wrapper. This pin should be revisited when the official repository restores or renames the Cartographer package on a Jazzy-native branch.

## 2026-06-06: P0 uses the Jazzy micro-ROS Agent source

Decision: build `micro-ROS/micro-ROS-Agent` from its `jazzy` branch in the official baseline image.

Basis: Docker build failure and source branch inspection.

Reason: the Humble micro-ROS Agent source fetches an XRCE-DDS Agent that requires `fastcdr` v1, while the ROS Jazzy base provides `fastcdr` v2.2.7. P0 still keeps `ardupilot_cartographer` on the ArduPilot `humble` branch because that package is missing from the current ArduPilot `jazzy` branch, but Micro-ROS Agent must match the ROS distribution ABI so the official DDS bridge can build.

Follow-up: install `ros-jazzy-micro-ros-msgs` from the ROS Jazzy binary repository rather than cloning `micro_ros_msgs` source. The Jazzy Agent source depends on this message package, and using the distro binary keeps message generation and middleware ABI aligned with the base ROS installation.

## 2026-06-06: P0 Dockerfile keeps apt dependencies independent from source refs

Decision: declare ArduPilot and micro-ROS source `ARG`s after the official baseline image's apt dependency layer.

Basis: Docker build behavior during P0 image iteration.

Reason: changing a source branch such as `MICRO_ROS_AGENT_REF` should invalidate only the source clone/build layers. If source refs are in scope before the apt `RUN`, Docker can rerun the expensive and network-sensitive system dependency layer even though the package list did not change. Keeping the dependency layer independent makes repeated official-baseline convergence practical.

## 2026-06-06: P0 installs Micro-XRCE-DDS-Gen explicitly

Decision: clone `ardupilot/Micro-XRCE-DDS-Gen` at `v4.7.0`, build it with Gradle, and put its `scripts` directory on `PATH` inside the official baseline image.

Basis: Docker build failure while compiling `ardupilot_sitl`.

Reason: the official ArduPilot DDS SITL package invokes `microxrceddsgen` during configure. Building only `micro_ros_agent` is not enough: the agent is the runtime DDS bridge, while `Micro-XRCE-DDS-Gen` is the code generator needed by ArduPilot's ROS2 package build. The image should fail early if `microxrceddsgen -help` is unavailable, because later DDS launch checks cannot be meaningful without generated message support.

## 2026-06-06: P0 builds Micro-XRCE-DDS-Gen with Java 17

Decision: install `openjdk-17-jdk-headless` and set `JAVA_HOME` for the official baseline image instead of using the distro `default-jdk`.

Basis: Docker build failure in `Micro-XRCE-DDS-Gen` Gradle configure.

Reason: Ubuntu noble's `default-jdk` can resolve to Java 21, while the `Micro-XRCE-DDS-Gen` Gradle wrapper currently uses Gradle 7.6 and fails with `Unsupported class file major version 65`. Java 17 is supported by that Gradle generation and is sufficient for building the XRCE-DDS code generator, so pinning Java 17 keeps the P0 image reproducible without patching upstream Gradle files.

## 2026-06-06: P0 official DDS probe uses Cyclone DDS on Jazzy

Decision: set the P0 official baseline runtime to `rmw_cyclonedds_cpp` and keep the official baseline ROS/DDS domain at `0`.

Basis: P0 manual probes and `uv run --project orchestration python orchestration/main.py official-baseline-acceptance 30`.

Reason: in the current ROS Jazzy environment, Fast DDS can discover ArduPilot bare DDS endpoints, but `/ap/v1/time` does not deliver samples to `ros2 topic echo` during the P0 probe. Cyclone DDS receives `/ap/v1/time` samples and records them into MCAP, although it may print type-hash warnings for bare DDS endpoints. ArduPilot's DDS launch defaults to domain `0`, so P0 aligns `ROS_DOMAIN_ID=0` with `DDS_DOMAIN_ID=0` for the official baseline while NavLab's normal custom runtime can keep its separate domain.

## 2026-06-06: P1 keeps the official maze and swaps only the lidar path

Decision: after P0, keep the official `ardupilot_gz_bringup iris_maze.launch.py` world and Iris lidar model for P1, and introduce only the NavLab X2 virtual-serial plus vendor-driver scan path.

Basis: local comparison against `/home/nn/workspace/3588/ardupilot_ros` and current P0 baseline artifacts.

Reason: replacing the world, vehicle model, lidar mechanism, and SLAM input at the same time makes failures hard to attribute. The official maze/Iris baseline already exercises ArduPilot Gazebo bringup, DDS, and Cartographer; P1 should isolate the next variable to the X2 mechanism: Gazebo scan source -> X2 protocol emulator -> `ydlidar_ros2_driver` -> `/scan`. P7/P8 should still stay in the official maze for motion and exploration because that scene is already richer than the current NavLab figure-eight world. NavLab's 8 字形 world and custom vehicle model move to a later optional migration phase after the official maze path has proven scan, rangefinder/IMU, SLAM quality, hover, motion, and exploration.

## 2026-06-06: P1 overrides only the official scan bridge output

Decision: keep launching `ardupilot_gz_bringup iris_maze.launch.py`, but bind-mount a P1 bridge YAML over the official `iris_3Dlidar_bridge.yaml` so the official `ros_gz_bridge` no longer publishes ROS `/scan`.

Basis: official launch inspection inside `navlab/official-baseline:latest` and P1 acceptance runs.

Reason: the official Iris lidar bridge maps Gazebo `/lidar` directly to ROS `/scan`. P1 needs `/scan` to mean “X2 virtual serial -> `ydlidar_ros2_driver` output”, otherwise Cartographer would receive a mixed topic from both `ros_gz_bridge` and the vendor driver. The bridge override preserves the official maze, Iris model, SITL, DDS, odometry, IMU, TF, and point cloud bridges, while freeing `/scan` for the vendor driver. The P1 acceptance blocks if `/scan` has a `ros_gz_bridge` publisher or if Cartographer is not subscribed to the vendor `/scan`.

## 2026-06-07: P7 FCU local-position rate gate allows DDS jitter

Decision: set the P7 `min_fcu_local_position_rate_hz` threshold to 1.5 Hz while keeping the latest-age gate at 1.5 seconds.

Basis: P7 acceptance artifact `artifacts/ros/navlab_companion_sitl_gazebo/20260607_114343/summary.json`.

Reason: the ArduPilot DDS filtered local-position stream is nominally about 2 Hz, but a full P7 run measured 1.93 Hz across the motion-probe window while latest samples stayed fresh and all motion, SLAM, ExternalNav, rangefinder, and rosbag gates passed. A 1.5 Hz floor preserves a real liveness/rate check without failing on scheduler jitter around the nominal 2 Hz publisher.

## 2026-06-07: P7 separates motion coordination from FCU setpoint ownership

Decision: run P7 as a motion coordinator plus the existing `navlab_fcu_controller` owner instead of letting the P7 probe publish `/ap/v1/cmd_vel` directly.

Basis: P7 design/TODO audit after the first green acceptance artifact.

Reason: the P7 design requires the mission/coordinator layer to publish motion intent while the unique FCU controller converts that intent into the movement setpoint output. The first accepted run proved motion but used the probe as the setpoint publisher, which made the owner boundary weaker than the written contract. The P7 controller runtime now subscribes to `/navlab/fcu/setpoint/intent`, publishes `/navlab/fcu/setpoint/output`, `/navlab/fcu/controller/status`, `/navlab/fcu/owner/status`, `/navlab/hover/status`, and owns `/ap/v1/cmd_vel`; the P7 coordinator publishes `/navlab/motion/status` and intent only. The verified artifact is `artifacts/ros/navlab_companion_sitl_gazebo/20260607_121115/summary.json`.

## 2026-06-07: P7 yaw scan window is four seconds

Decision: set the default P7 `yaw_window_sec` to 4.0 seconds while keeping `yaw_rate_radps=0.20` and `min_yaw_delta_rad=0.25`.

Basis: split coordinator/controller P7 acceptance run `artifacts/ros/navlab_companion_sitl_gazebo/20260607_120406/summary.json`.

Reason: after routing motion through the FCU controller intent path, the yaw command includes an extra intent-to-output hop and startup/settle latency. A 3 second yaw window produced about 0.243 rad, just below the gate, while the same controller path with a 4 second window produced 0.450 rad in `artifacts/ros/navlab_companion_sitl_gazebo/20260607_121115/summary.json`. Extending the action window preserves the stricter yaw delta gate instead of lowering the minimum accepted motion.

## 2026-06-07: P8 starts with bounded frontier-lite exploration

Decision: implement P8 as a bounded `frontier_lite` exploration gate that publishes exploration goals and FCU setpoint intents, while the existing `navlab_fcu_controller` remains the only `/ap/v1/cmd_vel` owner.

Basis: P8 design/TODO and the verified P7 coordinator/controller split.

Reason: P8 needs to prove an exploration claim without prematurely requiring a full production Nav2 stack. The bounded strategy uses SLAM map growth, scan clearance, TF/FCU readiness, and task state to choose forward probes or yaw scans, records coverage/progress metrics, and blocks on safety/stuck/owner/truth-input violations. This preserves the P6 hover and P7 motion boundaries while adding a real exploration acceptance artifact: `artifacts/ros/navlab_companion_sitl_gazebo/20260607_144800/summary.json`.

## 2026-06-07: P8 records the official Iris lidar TF as static

Decision: publish `base_link -> base_scan` from the SLAM bringup static TF path with the official Iris lidar offset `z=0.075077`, and make generated official-maze SLAM runtime files pass `laser_frame=base_scan` instead of only `laser_frame_id`.

Basis: Foxglove inspection of `artifacts/ros/navlab_companion_sitl_gazebo/20260607_153832/rosbag/rosbag_0.mcap` and comparison with `/home/nn/workspace/3588/ardupilot_gz/ardupilot_gz_description/models/iris_with_lidar/model.sdf`.

Reason: the original bag used `/scan.header.frame_id=base_scan`, but `/tf_static` contained `base_link -> laser_frame` while `base_link -> base_scan` appeared only on dynamic `/tf`. Foxglove can then report `Missing transform from frame <base_scan> to frame <map>` when visualizing scans/maps. The official model fixes the lidar at `base_link -> base_scan` with `z=0.075077`, so future P3-P8 runs should record that relationship on `/tf_static` directly instead of relying on a post-process MCAP patch.

## 2026-06-07: P9 uses representative replay runs

Decision: keep P8 acceptance conservative, but define a separate P9 representative replay profile that moves farther and moderately faster before building the official-maze Foxglove overlay.

Basis: P8 artifacts and P9 overlay design review.

Reason: the minimum P8 gate proves the exploration control loop, but its default speed and action windows can produce less than a meter of travel, which is not enough to make the official maze overlay useful. P9 should prefer a longer replay run, for example 0.18 m/s with at least 2.5 m path length and five accepted goals, while keeping the same no-truth-input, unique-owner, clearance, stop-drift, SLAM, ExternalNav, and FCU health gates. This preserves P8 as a safety gate and makes P9 a publishable replay artifact instead of an over-aggressive flight gate.

## 2026-06-07: P9 suppresses post-run ROS graph noise for transient topics

Decision: filter CycloneDDS type-hash discovery warnings from ROS shell capture and skip post-run `ros2 topic info` for transient P8 exploration status topics.

Basis: P9 display replay `artifacts/ros/navlab_companion_sitl_gazebo/20260607_223132/summary.json` passed with recorded `/navlab/exploration/*` messages, but terminal output still printed CycloneDDS type-hash warnings and `Unknown topic` lines after the exploration coordinator exited.

Reason: `Failed to parse type hash ... USER_DATA '(null)'` comes from DDS discovery metadata for ArduPilot/micro-ROS participants and does not imply message loss. `/navlab/exploration/status`, `/navlab/exploration/goal`, `/navlab/exploration/coverage`, and `/navlab/motion/status` are transient runtime publishers; after the run exits, `ros2 topic info` can report them as unknown even though rosbag and summary counts prove data was recorded. The acceptance evidence should come from rosbag/profile counts and runtime summaries, not from a late ROS graph query for transient publishers.

## 2026-06-08: P10 prioritizes body-fixed lidar scan integrity before real flight

Decision: make P10 the body-fixed lidar attitude compensation and scan integrity gate, and move the earlier true-lidar exploration strategy optimization out of P10.

Basis: P9 official-maze overlay replay validation and the real-drone risk that motor/ESC/prop mismatch can tilt a non-gimbaled 2D lidar scan plane.

Reason: P8/P9 prove exploration and replay in simulation, but they still assume the 2D lidar scan is close enough to a horizontal slice. On a real drone, small roll/pitch from actuator mismatch can make the scan hit the floor, ceiling, or wrong wall height and silently contaminate SLAM. P10 should therefore make `/scan` an attitude-validated topic, preserve raw scan for diagnostics, reject or clip unsafe tilted scans, and require normal plus fault-injection gates before pushing exploration farther or attempting real-machine flight.

## 2026-06-08: P10 owns `/scan` through a scan integrity filter

Decision: split the X2 chain into `/navlab/x2/scan_raw -> /navlab/x2/scan_normalized -> navlab_scan_integrity_filter -> /scan` for P10.

Basis: P10 implementation and green artifact `artifacts/ros/navlab_companion_sitl_gazebo/20260608_095523/summary.json`.

Reason: keeping the vendor driver directly on `/scan` makes it impossible to prove that SLAM only consumes attitude-validated scans. The raw topic is now diagnostic, the normalizer owns timestamp/frame normalization, and `navlab_scan_integrity_filter` is the unique `/scan` publisher. P10 also exposes a runtime fault-injection topic so mild and hard roll/pitch bias can prove that unsafe tilted scans are warned/dropped instead of silently reaching SLAM.

## 2026-06-08: P10.1 records attitude observability before compensation

Decision: add P10.1 flight attitude metrics, scan attitude quality schema, and best-effort motor-output observability before attempting any richer scan compensation.

Basis: P10 green artifact `artifacts/ros/navlab_companion_sitl_gazebo/20260608_103819/summary.json` and the real-drone concern that non-synchronized motor/ESC outputs can tilt a body-fixed 2D lidar.

Reason: before correcting tilted scans, the gate should first quantify how much the vehicle actually rolled/pitched during flight and whether actuator output is observable at all. The summary now records max/RMS roll and pitch, yaw and attitude-rate metrics, scan tilt/filter/warn counts, and motor-output fields. If no motor/servo/actuator/ESC output topic is exposed in the ROS graph, the summary explicitly reports `motor_output_claim=not_available` with null PWM/RPM/bias fields rather than inventing actuator evidence.

## 2026-06-08: P11 uses P9 replay for bounded 2D scan stabilization

Decision: define P11 as a bounded 2D lidar scan stabilization gate based on the P9 representative replay profile, rather than as a P8 slow-exploration check or a 3D lidar migration.

Basis: P10 proved that hard tilted scans can be dropped safely, but higher-speed representative replay can reduce SLAM scan availability if P10 remains purely drop-only.

Reason: the next risk is medium roll/pitch during faster motion, not a new exploration strategy. P11 should compare a P10 drop-only baseline against a bounded 2D projection candidate under the P9 replay motion profile, keep all pass/compensate/drop thresholds configurable, and preserve the P10 rule that hard tilt and floor-hit risk are rejected instead of being projected into fake walls. Broader exploration strategy optimization moves after P12 airframe disturbance robustness, once the scan input contract is stable under realistic motor/ESC/vibration profiles.

## 2026-06-08: P11 keeps live replay conservative when tilt stays below passthrough

Decision: accept the P11 live P9 representative replay when the vehicle remains in the passthrough tilt zone, while proving bounded projection behavior through the P11 fault profile and recording `compensation_not_triggered_reason` in the summary.

Basis: P11 acceptance artifact `artifacts/ros/navlab_companion_sitl_gazebo/20260608_122544/summary.json` passed with `ok=true`, `blockers=[]`, and `compensation_not_triggered_reason=tilt_never_exceeded_passthrough_tilt_deg`.

Reason: the acceptance run is still the correct P9 representative replay profile, but the simulated FCU held roll/pitch below the configured `passthrough_tilt_deg`, so forcing live compensation would require injecting artificial attitude into the flight loop and would weaken the real replay evidence. P11 therefore records a same-run P10 drop-only baseline estimate, keeps `/scan` uniquely owned by `navlab_scan_stabilization_filter`, and uses the fault profile to prove medium safe tilt, floor-hit risk, hard tilt, stale attitude, and invalid config behavior without projecting unsafe beams into SLAM.

## 2026-06-08: P11 waits longer for replay readiness than P8 slow gates

Decision: give P11 representative replay an explicit `replay_readiness_timeout_sec=90.0` and collect the FCU controller runtime summary after rosbag recording finishes, with `controller_summary_timeout_sec=45.0`.

Basis: failed P11 artifact `artifacts/ros/navlab_companion_sitl_gazebo/20260608_135843/summary.json` had healthy scan stabilization topics but failed because the P8 replay probe timed out before map/controller readiness fully settled, while `controller_runtime_summary.json` appeared later in the same artifact.

Reason: P11 is testing bounded scan stabilization under the P9 representative replay profile, not the minimum P8 slow exploration profile. The scan chain can be healthy while the replay layer needs a longer readiness window for Cartographer map publication and FCU hold-ready completion. Making these waits explicit config fields avoids hiding the timing dependency in code and prevents a late controller summary from being misreported as missing.

## 2026-06-08: P12 focuses on airframe disturbance scan robustness

Decision: define P12 as the motor bias / ESC lag / thrust multiplier / vibration robustness gate for body-fixed 2D lidar scan stabilization, not as an active frontier exploration phase.

Basis: P10/P11 proved scan integrity and bounded 2D stabilization under the current simulated attitude envelope, but the simulated airframe is still too ideal compared with a real drone whose motors, props and ESCs are not perfectly matched.

Reason: before making exploration more aggressive, the system must prove that P11 horizontal recovery remains safe when realistic disturbance sources create sustained roll/pitch bias, response lag, dynamic overshoot and IMU vibration/noise. P12 should run clean and disturbed P9 representative replay profiles, keep all disturbance parameters configurable, compare scan/SLAM/ExternalNav/FCU/map health against clean baseline, and make hard disturbance fail clearly instead of silently polluting SLAM. Active frontier exploration moves after this robustness envelope is known.

## 2026-06-08: P12 uses plugin-level ESC first-order lag

Decision: implement P12 ESC lag as an ArduPilot Gazebo plugin extension instead of the earlier PID/frequency proxy. The official-baseline image now applies `patches/ardupilot_gazebo_esc_lag.patch`, each `<control>` may declare `<escTimeConstantMs>`, and P12 SDF overlays write per-motor ESC time constants directly.

Basis: the proxy approach was useful for the first deterministic profile sweep, but it did not actually model command response delay. The user explicitly required real plugin-level first-order lag before treating P12 as complete.

Reason: P12 is the last scan/airframe robustness gate before real-drone trials. A real first-order command filter keeps the disturbance at the motor-control boundary, preserves per-motor thrust multiplier semantics, avoids pretending `p_gain` is ESC physics, and lets `mild_bias`, `esc_lag`, and `vibration` live P9 replays exercise the same stabilized `/scan` contract under more realistic attitude dynamics.

## 2026-06-08: P10/P11/P12 review follow-up tightens scan robustness contracts

Decision: add explicit attitude-source age gates for P10/P11, document P11 live compensation limits, and make P12 ESC patch reproducibility and map-risk scope explicit.

Basis: review found that scan-attitude timestamp offset is not enough to detect a silent attitude source, P11 same-run baseline is not a true A/B flight, and P12's `escTimeConstantMs` plugin patch is an external dependency.

Reason: stale attitude, biased baseline estimates, and patch drift are all failure modes that can look like healthy topic flow. P10/P11 now expose `max_attitude_source_age_ms=250.0`; P11 docs state current P9 live replay may not trigger compensation unless P12 disturbance profiles push tilt above passthrough; P12 docs record `ardupilot_gazebo` baseline commit `cc0290d964dfa373531963a8fc39093a0836af0a` and downgrade `map_artifact_score` to optional/future rather than a soft hard-gate placeholder.

## 2026-06-08: P12 gates FCU mode during disturbed replay

Decision: require each P12 live disturbed replay to prove FCU mode stays `GUIDED` throughout the configured disturbance window by reading `/ap/v1/status.mode` from the raw MCAP and comparing it to `required_fcu_mode_number=4`.

Basis: P12 can otherwise pass scan/SLAM health even if a disturbance profile pushes ArduPilot into RTL/LAND/failsafe and the replay keeps publishing stale or degraded data.

Reason: the mode gate uses `/navlab/exploration/status` first-to-last samples as the conservative P9 replay disturbance window, so pre-replay bootstrap is excluded but the active exploration/motion period is covered. `/ap/v1/status` and the window topic are required in the P12 raw rosbag profile; missing status data, invalid `mode_number`, or any non-GUIDED sample now produces an explicit blocker instead of being hidden inside generic FCU health.

## 2026-06-08: Orchestration gets a backend abstraction before any language rewrite

Decision: keep `orchestration` in Python for now and introduce a `RuntimeBackend` abstraction with Docker and process implementations instead of rewriting the orchestration layer in Go or Rust.

Basis: current P8/P9/P10/P11/P12 gates are already Python-based and their risk is not Python syntax or runtime speed; the real coupling is that service start/stop, rosbag recording, probe execution, logs, and path mapping are scattered across `python_on_whales` calls.

Reason: Docker remains the reproducible default for development and CI, while a process backend is the right shape for the compute box where ROS services may run under host process management or systemd. The backend boundary lets gate logic stay unchanged, makes missing process config fail explicitly, and avoids silent Docker/process fallback that would hide field failures.

## 2026-06-08: Runtime backend and runtime mode are explicit two-lane contracts

Decision: support only `docker + simulation` and `process + real` as valid orchestration runtime combinations.

Basis: codebase research and real-machine migration requirement.

Reason: `backend` describes lifecycle management, while `mode` describes the data/source boundary. The Docker path remains the P8-P12 Gazebo/SITL acceptance mainline, and the process path is reserved for the compute-box / real-drone mainline. `process + simulation` and `docker + real` are rejected for now so host-process debugging cannot be mistaken for real flight, and containerized real hardware cannot silently bypass device, udev, network, and FCU boundary design.

## 2026-06-08: Orchestration task surface moves to built-in runtime tasks

Decision: expose only built-in orchestration tasks for hover, P8 movement/exploration, real preflight, and scan robustness, while keeping old P-stage modules as legacy helper implementation details for now.

Basis: codebase research showed `orchestration/src/tasks` had grown to many phase-specific CLI entries and about 13k lines, with P9/P10/P11/P12 now converging on one tilted-scan robustness concern under explicit runtime mode.

Reason: real/sim is now a runtime mode concern, so individual historical phase commands should not be the operator-facing API. The stable task surface is `build`, `doctor`, and `run <task>` for `hover`, `exploration`, and `scan-robustness`; P9 replay, P10 integrity, P11 stabilization, and P12 disturbance behavior are folded under scan robustness. The old modules remain importable during this transition because P8 and P12 still share helper functions, but `TaskRegistry` and the CLI no longer expose historical P-stage tasks or per-task doctor entries as public runnable tasks.

## 2026-06-08: Legacy P-stage task helpers move out of the task root

Decision: move retained P-stage helper modules under `src.tasks.legacy`, remove their `TaskRegistry` decorators, and delete obsolete `acceptance`, `hover-diagnostic`, and `hover-slam-diagnostic` orchestration task files.

Basis: the built-in task surface now provides the operator API, while code reference checks showed P8 exploration and scan robustness still depend on helper functions from older phase modules.

Reason: deleting all P-stage modules in one step would break the current P8/P12 helper graph, but leaving them in `src.tasks` root made them look like runnable first-class tasks. The legacy subpackage keeps shared helpers available for the transition, makes imports explicit, and lets truly unreferenced old task files leave the tree.

## 2026-06-08: Legacy helpers no longer define runnable task classes

Decision: convert the remaining legacy `*Task` classes into module-level `run_*` helper functions and add a regression test that forbids `TASK_NAME`, `OrchestrationTask`, and `TaskRegistry` usage inside `src.tasks.legacy`.

Basis: the built-in task wrappers still need P8 exploration and P12 scan-robustness implementations, and the P12 live path still needs P11 replay logic, but these are implementation helpers rather than operator-facing tasks.

Reason: keeping old `*Task` classes in legacy made the code look like hidden runnable tasks even though registry and CLI no longer exposed them. Removing the class shells makes the boundary explicit. A dependency graph from `exploration` and `scan-robustness` still reaches all remaining legacy modules, so no additional legacy file is currently safe to delete without deeper helper extraction.

## 2026-06-09: Stage 1 SLAM IMU input uses companion FCU IMU

Decision: route Gazebo/SITL SLAM IMU input from `/navlab/fcu_imu/data` instead of `/ap/imu/experimental/data`.

Basis: hover acceptance artifact `artifacts/ros/navlab_companion_sitl_gazebo/20260609_095754` showed `/imu/status` waiting for an absent ArduPilot DDS experimental IMU topic while the companion pose mirror is the configured FCU MAVLink/simulation IMU producer.

Reason: hover should still require standardized `/imu/status` readiness before takeoff, but Stage 1 must feed that readiness from the actual companion FCU IMU path. The SLAM IMU bridge uses steady-clock input timing for readiness because ROS simulation time can be paused or repeated during startup. This preserves the safety gate and removes the topic mismatch that blocked Gazebo hover from reaching takeoff and landing evaluation.

## 2026-06-09: P12 runtime contract is the standard for earlier built-in flight tasks

Decision: keep the later P12-proven runtime contract as the standard and migrate hover/P8 forward to it instead of weakening hover-specific readiness.

Basis: user clarification that P12 has already run as a complete hover-capable and motion-capable path, plus hover acceptance artifacts showing failures in bootstrap contract alignment before landing evaluation.

Reason: hover is only the smallest task body, not a separate lower-standard runtime. If hover cannot take off while P12 can hover and move, the useful conclusion is that hover is missing pieces of the P12/P8 bootstrap, SLAM, ExternalNav, or FCU controller contract. Lowering Cartographer, ExternalNav, local-position, or FCU readiness for hover would create a second flight standard and make Stage 1 landing acceptance less representative of the later real-drone path.

## 2026-06-09: Hover Stage 1 uses the P12-aligned FCU/SLAM bootstrap

Decision: run the built-in `hover` acceptance through the same official baseline, Gazebo sensor, SLAM backend, P4 FCU controller, and P6 hover probe contract used by later P8/P12 paths, then finish with a `land_in_place` landing intent and controller landing summary.

Basis: `artifacts/ros/navlab_companion_sitl_gazebo/20260609_110400/summary.json` passed with `ok=true`, `acceptance_stage=simulation`, `simulation_landing_claim=evaluated`, `real_landing_claim=not_evaluated`, `/slam/odom` ExternalNav input, `/navlab/landing/status` recorded, `landing.state=landing_complete`, `disarmed=true`, and `motors_safe=true`.

Reason: the earlier legacy hover mission failed before takeoff because it did not satisfy the P12/P6 runtime contract (`/tf`, SLAM odom, official DDS pose/status, and P4 controller ownership). The hover task now validates the same contract and treats MAVLink disarm as a final-state gate: a denied disarm ACK is acceptable only if the subsequent heartbeat confirms the vehicle is already disarmed, which preserves the required `disarmed && motors_safe` landing condition without overfitting to ACK behavior.

## 2026-06-09: Hover Stage 1 now requires both ideal and mild disturbance profiles

Decision: extend built-in hover Stage 1 to run both `ideal` and `mild_disturbance` Gazebo/SITL profiles, expose the chosen `simulation_profile` in summary, and treat landing completion as `LAND -> touchdown -> disarm`, not as a single ACK round-trip.

Basis: hover accepted with `simulation_profile=ideal` in `artifacts/ros/navlab_companion_sitl_gazebo/20260609_120302/summary.json` and `simulation_profile=mild_disturbance` in `artifacts/ros/navlab_companion_sitl_gazebo/20260609_115602/summary.json`; both reported `acceptance_stage=simulation`, `simulation_landing_claim=evaluated`, `real_landing_claim=not_evaluated`, `landing.ok=true`, and `disarmed=true`.

Reason: the mild-disturbance run proved the old single-shot LAND ACK rule was too brittle for Stage 1. The controller now retries LAND, keeps monitoring descent, and only finalizes acceptance after touchdown and disarm are confirmed. This keeps the simulation gate aligned with the later real flight contract instead of making hover depend on perfect ACK timing.

## 2026-06-09: P8 Stage 1 follows the P12 profile contract before real Stage 2

Decision: extend built-in P8 exploration with the same `ideal` / `mild_disturbance` Stage 1 profile contract as hover and P12, and require the mild profile to keep the Gazebo lidar -> X2 virtual serial -> vendor scan chain on `gazebo_ideal` rather than accepting static fallback.

Basis: P8 `ideal` passed in `artifacts/ros/navlab_companion_sitl_gazebo/20260609_122759/summary.json`; P8 `mild_disturbance` passed in `artifacts/ros/navlab_companion_sitl_gazebo/20260609_125158/summary.json` with `/lidar=1433`, `/scan=1677`, `/sim/x2/status=479`, `/navlab/airframe_disturbance/status=479`, `landing.policy=return_home_then_land`, `landing.state=landing_complete`, `simulation_landing_claim=evaluated`, and `real_landing_claim=not_evaluated`.

Reason: P8 is the movement/exploration bridge between hover and P12, so it cannot pass Stage 1 only under ideal motors or by using X2 static fallback. The new P8 lidar/X2 preflight catches missing Gazebo ideal scan before the long acceptance window, and Stage 2 remains blocked until process+real preflight, manual takeover/kill-switch readiness, and a real-machine return-home landing run are performed.

## 2026-06-09: Orchestration config is split by runtime mode and task

Decision: derive the default orchestration config from `NAVLAB_RUNTIME_MODE` (`config.simulation.toml` or `config.real.toml`), keep runtime backend/mode controlled only by `NAVLAB_RUNTIME_BACKEND` and `NAVLAB_RUNTIME_MODE`, and move built-in task defaults into `orchestration/configs/<task>.toml`.

Basis: the real/simulation boundary must be visible at command time, while hover/P8/P12 task parameters need to evolve independently without turning one root `config.toml` into an unreadable mixed system/task file.

Reason: TOML should not silently turn a run into real flight or switch the backend. Runtime backend/mode are therefore environment-or-default only, with valid combinations still limited to `docker+simulation` and `process+real`. Built-in task invocation now resolves `CLI option > task config > hard-code default`, and task config overlays internal sections such as FCU, landing, exploration, and disturbance thresholds. The legacy root `orchestration/config.toml` has been deleted; default execution no longer uses `NAVLAB_ORCHESTRATION_CONFIG` or any legacy root config.

## 2026-06-09: Real preflight uses serial MAVLink as FCU primary evidence

Decision: make `process+real` preflight check the configured FCU serial MAVLink port with `pyserial` and `pymavlink`, while the console prints a Rich panel/table operator summary and the full JSON summary remains the audit artifact.

Basis: the real vehicle reads FCU data from a physical MAVLink serial link, not SITL TCP/UDP or simulated serial, and the operator needs key readiness facts visible in the terminal before any real flight entry.

Reason: ROS `/ap/*` topics can prove the graph surface exists, but they are not sufficient evidence that the real FCU serial boundary is healthy and they belong to later prepare/task-doctor phases. The preflight doctor now records only runtime boundary, dependency checks, serial open state, heartbeat, system/component ids, autopilot, mode, armed state, required MAVLink message counts, and non-flight claims. TCP/UDP MAVLink endpoints are rejected as serial evidence, and blocked runs show the important facts in the console instead of forcing the operator to inspect JSON first.

## 2026-06-09: Operator CLI uses build, doctor, and one run wrapper

Decision: remove public per-task subcommands from `orchestration/src/cli.py` and expose only `build`, `doctor`, and `run <task>`.

Basis: codebase research and operator-entry cleanup for real/simulation runtime mode.

Reason: the former per-task doctor subcommands made the real path ambiguous because the operator could confuse task-specific internal checks with the real preflight/prepare/run wrapper. The unified wrapper now reads `NAVLAB_RUNTIME_BACKEND` and `NAVLAB_RUNTIME_MODE`; in `docker+simulation` it dispatches the built-in simulation task, while in `process+real` it first runs the runtime doctor and then blocks until real prepare/task doctor/flight phases are implemented. The public task registry mirrors that surface by hiding per-task doctor entries.

## 2026-06-09: Real prepare starts helpers before task doctor but owns cleanup

Decision: implement real Stage 2 wrapper phases as `preflight -> prepare -> task doctor -> flight boundary`, where prepare starts only non-companion helper processes and returns process handles to the wrapper for cleanup.

Basis: `docs/scenarios/indoor/todos/real_prepare_and_task_doctor_todo.md` requires prepare to own side effects, task doctor to remain non-flight, and companion/arm/takeoff to start only after both phases pass.

Reason: MAVLink router, MAVROS, lidar, and SLAM must be live before task doctor can verify the ROS surface that companion will consume. At the same time, the current implementation still stops at the flight boundary, so losing helper process handles after a successful prepare would leave orphan host processes if task doctor fails or the wrapper blocks before companion startup. The wrapper therefore keeps prepare handles and stops them on exit until the real flight runner owns the full process lifecycle.

## 2026-06-09: Indoor real-flight yaw evidence must come from ExternalNav

Decision: require `external_nav_yaw_ready=true` in real task doctor for indoor SLAM tasks; compass calibration and manual override are recorded only as context and cannot satisfy the yaw gate.

Basis: the real hover/P8/P12 path is an indoor SLAM flight path, so the relevant yaw source is the SLAM/ExternalNav pipeline consumed by the FCU, not GPS-era compass readiness.

Reason: treating compass calibration or manual override as equivalent yaw evidence would let a real autonomous task proceed without proving that the ExternalNav yaw used by the controller is ready. Uncalibrated compass is not a standalone blocker, but it also does not remove the requirement for ExternalNav yaw readiness.

## 2026-06-09: Real Stage 2 uses fcu_bridge_mode registry

Decision: start real Stage 2 with `fcu_bridge_mode = "navlab_mavlink"` in an orchestration `fcu_bridge` registry, and derive preflight dependencies plus prepare/task-doctor required topics from the selected mode.

Basis: the working simulation FCU chain uses NavLab MAVLink router/bridge topics (`/navlab/mavlink/status`, `/navlab/fcu/local_position_pose`, `/mavlink_external_nav/status`, `/external_nav/status`) instead of MAVROS.

Reason: requiring MAVROS, GeographicLib geoid data, or `/ap/v1/*` topics for every real prepare path blocks a valid NavLab MAVLink bridge mode. A registry keeps the current mode simple while making future `mavros` or `ardupilot_dds` modes additive rather than hard-coded into preflight and prepare.

## 2026-06-09: Real Stage 2 keeps rangefinder height separate from 2D lidar SLAM

Decision: define the real Stage 2 sensor contract as three separate chains: FCU MAVLink/bridge, 2D lidar -> SLAM/ExternalNav yaw, and height/rangefinder evidence.

Basis: simulation already has a rangefinder/altitude evidence path in addition to the 2D lidar `/scan` path, while the real drone's 2D lidar is only a horizontal scan source.

Reason: `/scan` can prove horizontal geometry, SLAM odometry, and yaw readiness, but it cannot prove hover altitude or landing height. If a real ROS rangefinder bridge exists, it must publish the same contract as simulation, `/rangefinder/down/range` and `/rangefinder/down/status`; otherwise prepare/task doctor must explicitly record FCU telemetry evidence such as MAVLink `RANGEFINDER` / `DISTANCE_SENSOR`, baro, or EKF height instead of silently treating 2D lidar as a height source.

## 2026-06-10: Real height bridge prefers FCU DISTANCE_SENSOR over RANGEFINDER

Decision: use ArduPilot MAVLink `DISTANCE_SENSOR` with down-facing orientation as the primary real height evidence for hover/landing gates and for the future `/rangefinder/down/range` bridge.

Basis: a tabletop lift test on `/dev/ttyUSB1 @ 115200` showed `DISTANCE_SENSOR.current_distance` changing from 0 to about 45 cm as the vehicle was lifted, with `orientation=25` (`MAV_SENSOR_ROTATION_PITCH_270`). `RANGEFINDER.distance` changed consistently most of the time but showed an isolated 6.53 m spike while `DISTANCE_SENSOR` remained near 42 cm.

Reason: real Stage 2 needs the same ROS topic contract as simulation, but not the same source. Simulation generates `/rangefinder/down/range` from Gazebo scan data; real should generate it from FCU telemetry. `DISTANCE_SENSOR` carries min/max distance and orientation fields, making it safer for validity filtering. `RANGEFINDER`, baro, and EKF height remain useful diagnostics or secondary evidence, but they should not by themselves unlock hover or landing readiness.

## 2026-06-10: Real SLAM yaw uses the simulation contract with real hardware sources

Decision: make RTD.5A real prepare run the same `scan + IMU + Cartographer TF/odom + ExternalNav` yaw contract as simulation, with `/dev/ttyUSB0` publishing real `/scan`, `/dev/ttyUSB1` MAVLink IMU publishing `/imu/data` -> `/imu`, Cartographer publishing TF-backed `/slam/odom`, and `/external_nav/status.ready=true` as the accepted yaw gate.

Basis: `just navlab-doctor` passed with `Status OK`; `NAVLAB_RUNTIME_BACKEND=process NAVLAB_RUNTIME_MODE=real uv run --project orchestration python orchestration/main.py run hover --dry-run` passed preflight, prepare, and task doctor on 2026-06-10. The latest prepare summary `artifacts/ros/navlab_real_prepare/20260610_023033/summary.json` records real scan and IMU samples, `/navlab/slam/status.ready=true`, `/external_nav/status.ready=true`, `accepted_topic=/external_nav/status`, and no prepare blockers.

Reason: the yaw gate must prove the real SLAM/ExternalNav chain rather than accept placeholder odom, fake odom, FCU pose TF, or simulation topics. The real Cartographer config disables the missing odometry input while keeping backend TF output, the pose mirror no longer injects replay TF into the real TF tree, and prepare probes actual samples/status JSON instead of only topic names.

## 2026-06-10: Real motor-debug reuses prepare and ExternalNav before arm

Decision: define `run motor-debug` as a process+real, no-props, GUIDED-only arm/hold/disarm debug task that first runs real prepare and connects through mavlink-router instead of opening the FCU serial directly.

Basis: a real motor-debug run reached GUIDED but arm was rejected with `MAV_RESULT_FAILED` and ArduPilot `STATUSTEXT` values `Arm: RC not found` and `Arm: GPS 1: Bad fix`. The simulation profile already follows the ArduPilot Cartographer SLAM ExternalNav contract with GPS disabled and EKF source set to ExternalNav, while the failing real path had not yet proven the same FCU parameter and ExternalNav readiness before arm.

Reason: `GPS 1: Bad fix` is not a motor command formatting problem; it indicates the FCU still has GPS/pre-arm assumptions or EKF source mismatch. `motor-debug` must therefore share the real prepare chain that brings up router, FCU bridge, real scan, Cartographer, and ExternalNav, then send only `MAV_CMD_COMPONENT_ARM_DISARM` arm/hold/disarm commands in GUIDED. `RC not found` remains a separate pre-arm issue and should not be hidden by force arm unless a future bench-only override is explicitly designed.

## 2026-06-10: VIO and GPS/Non-GPS docs constrain the same ExternalNav contract

Decision: use the ArduPilot VIO tracking camera and GPS/Non-GPS transition docs as supporting references for NavLab lidar SLAM ExternalNav checks, without changing NavLab's primary sensor route from lidar + IMU + Cartographer.

Basis: VIO and Cartographer differ in upstream sensor source, but both feed external pose into ArduPilot EKF. The GPS/Non-GPS transition doc also clarifies that EKF source sets can switch between GPS and non-GPS sources, which is relevant to interpreting `GPS 1: Bad fix` during an indoor arm attempt.

Reason: NavLab should not treat ROS `/external_nav/status.ready=true` alone as proof that the FCU is ready to arm. Ground checks must also prove the FCU receives ExternalNav, local position changes consistently when the vehicle is moved, EKF origin/home are handled, and the active EKF source no longer depends on GPS for the indoor path. Future GPS/non-GPS transitions should use EKF source sets rather than ad hoc motor-debug overrides.

## 2026-06-11: Orchestration config code lives under src.configs

Decision: move orchestration configuration code into `orchestration/src/configs/`: `project_config.py` owns root project config, `run_config.py` owns `OrchestrationConfig` and `RunConfig`, and `task_config.py` owns shared task TOML helpers.

Basis: the old top-level `config.py`, `project_config.py`, and `task_config.py` names made it unclear which config object should be read first.

Reason: `ProjectConfig` is the root process-level config and must be initialized explicitly with `init_project_config()`. `load_project_config()` only returns the initialized singleton and raises if called before initialization. `RunConfig` remains a per-run/per-task object and now lives in `run_config.py`. Task-specific dataclasses stay in their task modules, while generic task config helpers live in `configs/task_config.py`.

## 2026-06-11: Project paths are not RunConfig

Decision: replace the former root `RuntimeConfig` name with `ProjectPaths` inside `ProjectConfig`.

Basis: `RuntimeConfig` was easy to confuse with `RunConfig`, but it only represented project paths such as lab root, ArduPilot root, mavlink-router root, venv path, and the selected config file.

Reason: `ProjectConfig.paths` is now clearly project/environment-level state. `RunConfig` is the single-run task execution state with run id, artifact dir, duration, and merged orchestration config.

## 2026-06-11: Real prepare failures must distinguish runtime process errors from FCU readiness

Decision: keep the real prepare ROS graph probe on the configured timeout and fix process launch failures at their source: `rangefinder_bridge` runs under system Python with the orchestration venv on `PYTHONPATH`, and moved ROS packages must be rebuilt so `install/` symlinks point at `navlab/common/slam/...`.

Basis: `just navlab-doctor` initially failed with a 2 s `ros2 topic list` timeout, then with missing rangefinder/SLAM topics. The real logs showed `rangefinder_bridge` could import `rclpy` but not `pymavlink`, and `navlab_slam_bringup` / `navlab_cartographer_adapter` install symlinks still pointed at the deleted `navlab/slam/...` tree. After using the configured 5 s topic probe, adding the venv site-packages to the rangefinder command, and rebuilding the moved ROS packages, `just navlab-doctor` passed with prepare rc=0 and common doctor rc=0.

Reason: these are not new FCU blockers or task-doctor policy questions. They are local runtime packaging issues caused by the real/sim package move and mixed ROS/system Python execution. Fixing them preserves the existing ExternalNav readiness contract instead of weakening the doctor checks.

## 2026-06-12: Python sim orchestration is retired

Decision: delete the Python simulation task champions, workflows, helper package, `config.simulation.toml`, and old TOML task configs after Go sim gained live execution, gate blocker evaluation, and final artifact summaries.

Basis: `orchestration/sim` now owns `hover`, `exploration`, and `scan-robustness` through the Go registry, Cobra CLI, Viper config loading, YAML task configs, Docker runtime specs, dry-run artifacts, live runtime runner, blocker evaluation, and summary/manifest writers.

Reason: keeping Python sim entrypoints after Go sim parity creates two orchestration surfaces for the same tasks. Python remains only for runtime nodes and transitional real orchestration. Real task-doctor checks that were embedded in Python sim built-ins now live under `orchestration/src/workflows/real/task_specs.py`, and `TaskRegistry` only exposes the Python real `motor-debug` task until Rust real replaces it.

## 2026-06-12: Go sim live smoke shows control-plane completion before task parity

Superseded by: `2026-06-12: Go sim runtime/probe placeholders replaced by ROS
evidence`.

Decision: treat Go sim control-plane migration as complete, but keep hover,
exploration, and scan-robustness live parity open until generated runtime/probe
scripts perform real ROS task behavior instead of placeholder reporting.

Basis: `./navlab-sim run hover` was executed on 2026-06-12. The first run
exposed two Go runtime bugs: the official baseline service was missing from the
runtime bundle, and rosbag `timeout --signal=INT` return code `124` was treated
as a failure. After fixing those, hover live started `official_baseline`,
`gazebo_sensor`, `slam_backend`, `p4_controller`, probes, and `p6_hover_rosbag`;
the bag recorded `/ap/v1/pose/filtered`. The final summary still blocked on
missing `/slam/odom`, `/navlab/fcu/controller/status`, `/navlab/hover/status`,
and landing evidence because several generated scripts still emit
`planned_runtime_script` / `planned_probe_script`.

Reason: deleting Python sim entrypoints was still valid because the Go package
now owns the orchestration surface and fails closed with truthful blockers. But
live task acceptance is not complete until the Go-generated runtime layer starts
real SLAM/controller/hover/exploration/scan behavior and produces the evidence
that the final summary gates require.

## 2026-06-13: Go sim TUI starts with artifact replay

Decision: implement the first Go sim TUI slice as replay-only plus dry-run replay:
`navlab-sim tui <artifact-dir>` reads existing artifacts, and
`navlab-sim run <task> --dry-run --tui` generates dry-run artifacts before
opening the same view. Live Docker/ROS monitoring remains a later event-sink
slice.

Basis: `orchestration/sim` already writes `manifest.json`, `task_request.json`,
`runtime_plan.json`, `summary.json`, and `doctor_summary.json`; these are enough
to render task identity, runtime component counts, blockers, artifact status,
and log paths without starting runtime services.

Reason: replay-only TUI gives operators a faster artifact inspection surface
without introducing Docker/ROS side effects or changing task execution
semantics. Bubble Tea is pinned to `v1.2.4` so the sim module keeps its Go 1.24
toolchain boundary while still using the Charm terminal stack selected for Go
sim.

## 2026-06-13: Go sim live TUI consumes runtime events

Decision: add `RuntimeEventSink` to the Go sim runtime runner and make
`navlab-sim run <task> --tui` execute the existing live runner behind a Bubble
Tea monitor. The TUI updates service/probe/rosbag state from events, tails the
selected component log file, focuses the blocker panel on failures, and refreshes
from `summary.json` after the run writes final artifacts.

Basis: the runner already has deterministic service, rosbag, probe, wait, and
cleanup boundaries. Emitting events at those points avoids changing Docker CLI
execution or task semantics while giving the TUI enough state for live
monitoring.

Reason: live TUI should be a monitor over the same runner and artifacts, not a
second execution path. Keeping JSON artifacts canonical preserves CI/replay
behavior, while the event sink can later map cleanly to
`runtime.v1.ProcessEvent` when generated contract types are adopted.

## 2026-06-13: P13 starts with a truthful Nav2 dry-run contract

Decision: implement the first P13 Nav2 indoor navigation slice as Go sim
configuration, task registry, execution plan, generated runtime artifacts, and
static gate checks. Live Nav2 lifecycle, NavigateToPose action handling, and
adapter node behavior remain explicit TODO items instead of being reported as
complete.

Basis: P13 depends on existing P10/P11/P12 scan, SLAM, FCU owner, and landing
contracts, but it adds new Nav2/costmap/adapter boundaries. The first slice now
loads `[nav2]`, `[nav2.costmap]`, `[navigation_adapter]`, and
`[navigation_mission]`, registers the `navigation` task, generates
`nav2_params.yaml`, `navigation_adapter_runtime.toml`, Nav2/costmap/navigation
probe scripts, and a navigation rosbag profile.

Reason: Nav2 should not be treated as accepted until lifecycle/action/costmap
evidence is real. A dry-run contract lets CI and reviewers validate the
configuration and artifact boundary now while preserving fail-closed blockers
for the future live runtime implementation.

## 2026-06-13: P13 required sections use explicit TOML section detection

Decision: detect required P13 sections by scanning exact TOML section headers
instead of using `viper.IsSet("nav2")`.

Basis: `viper.IsSet("nav2")` is true when only nested keys such as
`[nav2.costmap]` exist, so it cannot distinguish an explicitly configured
`[nav2]` contract from nested defaults. P13 needs fail-closed behavior when the
top-level Nav2 contract is omitted.

Reason: exact section detection preserves the no-hardcode contract: defaults
may fill individual values, but they must not silently create a missing P13
configuration boundary.

## 2026-06-13: P13 mission runtime is gated by Nav2 action readiness

Decision: generate a `navigation_mission_runtime.py` script that checks
NavigateToPose action availability before publishing any bounded goal. If the
action server is unavailable, the script writes `nav2_action_unavailable` to the
navigation status and exits without sending a goal.

Basis: P13 requires Nav2 lifecycle/action readiness to be decoupled from FCU
readiness, and the adapter must not receive navigation intent from a mission
planner that has not proven Nav2 is ready.

Reason: this keeps the first mission runtime slice fail-closed. It lets dry-run
and CI validate the mission/action contract now, while real goal success remains
a separate live acceptance item.

## 2026-06-13: Go sim live runs may override runtime image tags explicitly

Decision: keep `distro-git-commit` as the default image tag policy, but allow
runtime execution to override the resolved tag with
`NAVLAB_SIM_RUNTIME_IMAGE_TAG` or `NAVLAB_SIM_IMAGE_TAG`.

Basis: P13 live validation found locally available `humble-latest` runtime
images while the current working tree resolved to a new git-commit tag that had
not been built yet.

Reason: release and CI paths should remain reproducible by default, but local
live acceptance needs a deliberate way to use already-built images without
rebuilding every runtime image for each intermediate commit.

## 2026-06-13: Go sim runtime sources ROS through `ROS_DISTRO`

Decision: runtime service commands and Docker entrypoints source ROS from
`/opt/ros/${ROS_DISTRO:-humble}/setup.bash` instead of a fixed Jazzy path.

Basis: the sim image catalog supports Humble and Jazzy, and local live P13
images are tagged as Humble. Hard-coded Jazzy setup paths break valid Humble
runtime images.

Reason: distro selection belongs to `config.toml` and `NAVLAB_SIM_DISTRO`, not
individual service command strings. This preserves the two-distro contract while
keeping Humble as the documented fallback.

## 2026-06-13: P13 sim live keeps `/map` owned by SLAM

Decision: keep `/map` as the mature SLAM/Cartographer map topic and prevent the
generated P13 navigation adapter from publishing a synthetic seed occupancy
grid on that topic. If Nav2 needs a bounded static-layer seed, publish it on
`/navlab/navigation/seed_map` and point the Nav2 static layer at that internal
topic. The adapter may still publish the identity `map -> odom` transform as a
startup bridge and derives costmap health from Nav2 global/local costmap topics.

Basis: P13 must extend the existing world/SLAM review surface instead of
replacing it. Publishing a synthetic seed grid on `/map` pollutes Foxglove
replay and hides the SLAM map that P9/P12 already used successfully.

Reason: Nav2 still needs a map frame and global costmap input, but the canonical
review artifact must show the same `/map`, `/scan`, `/slam/odom`, TF, and FCU
topics that the mature sim tasks used. Bounded navigation goals and costmap
health are P13 additions; they must not overwrite the baseline SLAM evidence.

## 2026-06-14: P13 frontier-lite evidence is emitted by sim runtime

Decision: keep P13 active exploration as a bounded frontier-lite contract in
Go-generated sim runtime scripts. The mission node emits frontier candidates,
accepted/rejected frontier records, unreachable-goal blacklist entries, coverage
growth, and a no-truth flag on `/navlab/navigation/status`; probes and summary
parsing only validate and surface that evidence.

Basis: P13 should not consume Gazebo truth or official maze overlays as planning
input, but it still needs auditable active-exploration evidence for CI and
artifact review.

Reason: putting the evidence at runtime keeps live runs, golden examples, and
future split repos on the same summary contract, while avoiding a shared helper
library between sim and real.

## 2026-06-14: P13 `/cmd_vel_nav` live chain is accepted by evidence, not by action success alone

Decision: treat P13 live navigation success as the combined evidence of
NavigateToPose goal acceptance, `/cmd_vel_nav` adapter activity, FCU command
publication, odom path length, coverage growth, final landing status, and
rosbag profile health. Nav2 action result success remains recorded, but a
timeout or non-success result for one bounded goal is not by itself a task
failure if the configured navigation gate passes.

Basis: live run `artifacts/sim/navigation/20260614T062658Z/summary.json` passed
with `TASK_STATUS_OK`, empty blockers, `accepted_goals=3`,
`path_length_m=4.2269`, `coverage_growth=0.75`, adapter `intent_count=2928`,
controller `ready=true`, landing `ok=true`, and all required rosbag profiles
`ok=true`.

Reason: the debugging question was whether `/cmd_vel_nav` was missing because
the mission goal was not sent, Nav2 goal handling was blocked, or TF/costmap
prevented controller output. The accepted artifact proves the mission sends
goals, Nav2 accepts bounded goals, `/cmd_vel_nav` drives the adapter, the FCU
controller publishes `/ap/v1/cmd_vel`, and the vehicle moves. Summary evaluation
therefore must not let early hover-probe landing blockers override the final
navigation landing sample; landing acceptance owns landing blockers, while
navigation probes own navigation/adapter/controller readiness.

## 2026-06-14: P13 official maze overlay is live-published for review only

Decision: publish `/navlab/official_maze/map` during sim runtime with a
dedicated ROS2 node and record it in the raw rosbag as a standard
`nav_msgs/OccupancyGrid`. P13 navigation uses the Go sim raw MCAP at
`rosbag/navigation_rosbag/navigation_rosbag_0.mcap`, then the replay builder
creates `rosbag_foxglove/rosbag_foxglove_0.mcap` by filtering/downsampling
existing MCAP messages with Foxglove's Go MCAP library.

Basis: live navigation must not use the official maze as planning input, but
Foxglove review needs a stable visual reference layer. The raw MCAP must now
contain `/navlab/official_maze/map`; if it is missing, `navlab-sim foxglove
build-replay` fails instead of inventing the topic later.

Reason: this separates acceptance evidence from review presentation without
hand-written ROS2 serialization in Go. Raw artifacts stay faithful to live
runtime topics, while `--lite` uploads carry the official maze overlay plus a
smaller P13 topic set for inspection.

Update: do not scale the official maze overlay to the observed `/map` bbox. The
P9 replay path already rasterized official SDF wall coordinates directly and
then overlaid the mature SLAM `/map`, `/scan`, and `/slam/odom` topics. P13
must preserve that identity overlay behavior first, then add Nav2 visual layers
after the baseline SLAM/scan/maze alignment is stable. The navigation adapter
also no longer publishes a synthetic seed occupancy grid on `/map`; its seed
map is isolated on `/navlab/navigation/seed_map`, while `/map` belongs to SLAM.

## 2026-06-15: Go Foxglove upload is lite-only

Decision: move the Foxglove-lite replay contract into Go sim and make upload
lite-only. `navlab-sim foxglove build-replay` generates
`rosbag_foxglove/rosbag_foxglove_0.mcap` and `foxglove_replay_summary.json`.
`navlab-sim foxglove upload` refuses raw MCAPs and validates
`docker/profiles/navlab-*-foxglove-lite-topics.txt` before upload.

Basis: the old Python path did more than upload: it built the lite MCAP,
filtered/downsampled topics, validated `/navlab/official_maze/map`, and wrote a
summary. Migrating only the upload shell allowed raw MCAPs to bypass the topic
contract.

Reason: Foxglove artifacts are review artifacts, not runtime acceptance inputs.
Missing `/navlab/official_maze/map` or any profile `required` topic must fail
closed instead of uploading a misleading recording. Raw task MCAPs remain local
acceptance evidence and are not uploaded by the Go Foxglove uploader.

Update: raw rosbag files may stay compressed as `*.mcap.zstd`. The Go replay
builder must stream-decompress compressed raw MCAPs through Foxglove's Go MCAP
reader and write only `rosbag_foxglove/rosbag_foxglove_0.mcap`. It must not
persist a large decompressed raw copy, and upload must still target only the
lite MCAP plus summary attachments.

## 2026-06-14: Hover and exploration block Nav2 until SLAM parity is stable

Decision: stop P13/Nav2 feature work until Go sim hover and exploration pass
with Cartographer-owned `/map` and `/slam/odom`. Gazebo/official `/odometry`,
Gazebo `/gazebo/tf`, seed maps, and `/navlab/official_maze/map` remain diagnostic or
review-only and must not become hover/exploration success inputs.

Basis: hover live run `artifacts/sim/hover/20260614T211212Z/summary.json`
passed with SLAM-owned `/map`, `/slam/odom`, controller output, hover status,
and landing status. Exploration live run
`artifacts/sim/exploration/20260614T223900Z/summary.json` reached the workflow
and accepted goals, but `/slam/odom` stayed static with `path_length_m=0`.

Reason: Nav2 depends on the same SLAM pose chain. If hover/exploration do not
move on SLAM-owned odometry, Nav2 debugging will mask the wrong layer.

## 2026-06-14: Cartographer dynamic TF is isolated on `/navlab/slam/tf`

Decision: remap Cartographer's dynamic `/tf` output to `/navlab/slam/tf`, and
configure `navlab_cartographer_adapter` to read that topic when generating
`/slam/odom`. Keep Gazebo diagnostic pose TF isolated from global `/tf`.

Basis: exploration runs showed `base_link` TF conflicts and stale TF warnings
when Cartographer `map -> base_link` and bridge `odom -> base_link` shared
global `/tf`.

Reason: `/slam/odom` must be SLAM-owned while preserving diagnostic TF for
review. Isolating Cartographer TF avoids mixing Gazebo/bridge pose into SLAM
acceptance and gives real migration a clear contract.

## 2026-06-15: FCU takeoff readiness is configurable MAVLink evidence

Decision: make FCU controller bootstrap use task-configured MAVLink takeoff
readiness thresholds instead of a hard-coded runtime-script expression. The
default threshold is `max(takeoff_min_height_m=0.15,
takeoff_alt_m*takeoff_min_height_ratio=0.35)` and is satisfied only by
`LOCAL_POSITION_NED` or `GLOBAL_POSITION_INT` evidence.

Basis: hover live run `artifacts/sim/hover/20260615T005618Z/summary.json`
passed with `pose_source=slam_odom`, `bootstrap_ready=true`, and landing
`ok=true`. Exploration live run
`artifacts/sim/exploration/20260615T010250Z/summary.json` had SLAM movement
(`path_length_m=0.737`) and no Gazebo truth input, but FCU bootstrap stayed
blocked because `takeoff.ok=false`.

Reason: this keeps the Gazebo truth boundary intact while avoiding a brittle
magic number in the generated Python controller. The takeoff readiness gate
only permits controller operation; hover/exploration success still requires the
task-specific SLAM/path/goal/landing evidence.

## 2026-06-15: Go sim FCU motion uses MAVLink local-position setpoints

Decision: keep `/ap/v1/cmd_vel` as the FCU controller output/recording surface,
but drive SITL motion through MAVLink `SET_POSITION_TARGET_LOCAL_NED` lookahead
setpoints derived from `/navlab/fcu/setpoint/intent` and current
`LOCAL_POSITION_NED`. Do not use Gazebo `/odometry`, Gazebo TF, seed maps, or
official maze overlay as control inputs.

Basis: Go exploration initially reached controller ready and published hundreds
of DDS cmd_vel messages, but `path_length_m` stayed near zero. The old Python
P8 mission moved SITL by sending MAVLink local-position targets ahead of the
current FCU local position. After porting that semantic route, exploration live
passed in `artifacts/sim/exploration/20260615T024623Z/summary.json` with
`accepted_goals=3`, `path_length_m=0.8409`,
`mavlink_setpoint_count=443`, `mavlink_local_position_count=40`, and
`usesTruthAsControlInput=false`. Hover smoke also passed in
`artifacts/sim/hover/20260615T024140Z/summary.json`.

Reason: ArduPilot/SITL is the FCU boundary in simulation just as MAVLink is the
FCU boundary in real. DDS cmd_vel alone is a useful ROS trace surface but is not
sufficient evidence that ArduPilot executed horizontal movement. The lookahead
MAVLink setpoint path preserves the no-Gazebo-truth rule while restoring the
old Python movement behavior.

Follow-up: Cartographer remains the stability risk. The run
`artifacts/sim/exploration/20260615T023414Z/summary.json` satisfied exploration
and landing gates but showed late Cartographer rejected TF / dropped point
warnings and a `std::length_error`; adapter rejection kept this from becoming
accepted `/slam/odom`, but future SLAM metrics should expose reject counts and
max odom step directly in summary.

## 2026-06-15: `/odometry` is diagnostic truth, not Cartographer input

Decision: remove `/odometry` from all default Cartographer odometry-input
settings. The explicit Cartographer odometry input placeholder is now
`/cartographer/odometry_input`, and FCU controller generated runtime defaults
leave the Cartographer odometry relay disabled. The old
`navlab_cartographer_2d.lua` profile was renamed to
`navlab_cartographer_2d_diagnostic_odom.lua` so `use_odometry=true` cannot be
selected by the old default-looking filename.

Basis: code review found that `/odometry` had two identities: Gazebo/bridge
truth for diagnostics and Cartographer odometry input when a `use_odometry=true`
Lua profile is selected. The current `_real.lua` profile disables odometry, but
one future filename or config change could silently reconnect Cartographer to
Gazebo truth.

Reason: `/odometry` remains useful in review rosbags for drift comparison, but
it must not be a SLAM, ExternalNav, Nav2, or controller input. Requiring a
non-truth topic name for odometry input makes any real odometry source an
explicit operator/config decision instead of an accidental fallback.

## 2026-06-15: Gazebo truth TF is isolated from global `/tf`

Decision: remap Gazebo pose bridge TF to `/gazebo/tf` and `/gazebo/tf_static`.
`gazebo_truth_odom` may subscribe to `/gazebo/tf` to derive diagnostic
`/gazebo/truth/odom`, but Gazebo truth TF must not be published into global
`/tf`.

Basis: Gazebo physics can publish an `odom -> base_link` pose bridge that looks
like a normal runtime transform in Foxglove or rosbag replay. Even when the
algorithm chain does not consume it, mixing it with Cartographer/runtime TF in
the same namespace makes review ambiguous and can hide accidental truth usage.

Reason: `/tf` remains the runtime transform surface for real-equivalent robot
state. Gazebo pose is diagnostic ground truth, so its topic name must advertise
that boundary just like `/gazebo/truth/odom`.

## 2026-06-15: Gazebo model odometry uses an explicit diagnostic namespace

Decision: publish Gazebo model bridge odometry as `/gazebo/model/odometry`
instead of bare `/odometry`. Navigation rosbags may record both `/odometry` and
`/gazebo/model/odometry` as review topics, but neither can be required for task
acceptance.

Basis: `/odometry` had already been demoted to diagnostic-only, but the bridge
override still used `ros_topic_name: "odometry"`. That name looks like a
generic robot odometry source and is easy to confuse with a real-equivalent
SLAM/Nav2 input.

Reason: Gazebo model odometry is a dead-end diagnostic signal. Its topic name
must make that provenance obvious and must not become a Cartographer,
ExternalNav, Nav2, or controller dependency.

## 2026-06-15: SLAM stability metrics are summary evidence before blockers

Decision: surface Cartographer/adapter stability in live summaries without
immediately turning every warning into a task blocker. `/navlab/slam/status`
now carries TF rejection ratio and max accepted/rejected/observed jump metrics,
and Go summary parsing records `slam_backend.runtime.log` counts for dropped
points, rejected odom TF log lines, `std::length_error`, fatal, error, and
warning lines.

Basis: hover/exploration can satisfy task and landing gates while Cartographer
later reports rejected TF, dropped points, or process instability. Treating that
as missing Go task migration would hide the real issue: SLAM backend stability.

Reason: metrics must be visible and comparable across runs before choosing
thresholds. Once the distribution is known, a later gate can promote severe
signals such as `std::length_error` or excessive rejection ratio into blockers.

## 2026-06-15: Sim tasks fail closed instead of using Gazebo truth fallback

Decision: when SLAM, Nav2, ExternalNav, FCU controller, landing, or workflow
evidence is missing or unstable, the task records blockers and artifacts and
fails/blocks. It must not substitute Gazebo truth, Gazebo model odometry,
Gazebo TF, seed maps, official overlays, or SDF geometry for canonical runtime
outputs such as `/slam/odom`, `/map`, navigation success, landing success, or
controller inputs.

Basis: the sim migration is intended to exercise the same sensor-processing and
control path as real hardware. Gazebo truth is useful for diagnosing drift and
runtime defects, but using it as fallback would make the sim result easier than
real operation and would hide the failure that needs fixing.

Reason: a blocked run with clear evidence is more valuable than a false pass.
Diagnostic-only topics can explain failures; they cannot repair acceptance.

## 2026-06-15: Go sim MAVLink bootstrap listens to MAVProxy output (superseded)

Decision: superseded. Earlier H5 work set the Go sim FCU bootstrap endpoint default to
`udpin:0.0.0.0:14550`. ArduPilot's official MAVProxy launch emits FCU traffic
with `--out 127.0.0.1:14550`; the controller must listen on that port instead
of opening a peer-style `udp:127.0.0.1:14550` connection.

Basis: `scan-robustness` live run
`artifacts/sim/scan-robustness/20260615T062053Z/summary.json` blocked with
`heartbeat_timeout`, `bootstrap_ready=false`, and zero `/ap/v1/cmd_vel`
messages even though SITL and SLAM were running. After switching to
`udpin:0.0.0.0:14550`, live run
`artifacts/sim/scan-robustness/20260615T063115Z/summary.json` passed with
`mavlink_bootstrap.ok=true`, target system `1`, GUIDED mode, arm/takeoff ACKs,
153 MAVLink setpoints, hover evaluation, and landing completion.

Reason: MAVLink bootstrap is real-equivalent FCU evidence. A timeout must block
the task rather than falling back to Gazebo truth, but the listener endpoint
must match the official MAVProxy output contract so the controller can observe
real FCU heartbeat and ACKs.

Superseding note: this fixed a single-listener scan-robustness path but is not
the correct shared runtime topology for hover parity. Hover runs both a mission
MAVLink controller and a down-rangefinder MAVLink sender. Letting both bind the
same UDP listener recreates a hidden single-port race.

## 2026-06-15: Sim rangefinder uses the same MAVProxy UDP surface as Python parity (superseded)

Decision: superseded. Earlier H5 work set the Go sim down-rangefinder MAVLink endpoint default to
`udpin:0.0.0.0:14550`, matching the old Python orchestration's now-retired
rangefinder MAVLink endpoint key. That superseded runtime listened to the
official MAVProxy/ArduPilot UDP stream, observed heartbeat, and sent
`DISTANCE_SENSOR` back on that channel.

Basis: H5 hover live run
`artifacts/sim/hover/20260615T144150Z/summary.json` blocked before takeoff:
`mission_summary.json` showed `arm_ack_ok=false`, `takeoff_ack_ok=false`, and
STATUSTEXT `Arm: Rangefinder 1: No Data`. The rangefinder ROS topic existed,
but `/rangefinder/down/status` reported `mavlink_peer_observed=false` and
`sent_count=0` because the Go default had drifted to `tcp:127.0.0.1:5760`.
Old Python `orchestration/config.toml` used `udpin:0.0.0.0:14550`.

Reason: rangefinder acceptance is FCU evidence, not a ROS topic-count check.
If the MAVLink peer is absent, the task must block; the endpoint default must
match the official FCU stream used by the previous working Python path.

Superseding note: the old Python runtime also had a `mavlink-router` service in
the base compose stack. The correct parity point is the router topology, not the
single retired rangefinder MAVLink endpoint string in isolation. This whole
decision is further superseded by P14: down rangefinder FCU input is now
Benewake serial over Serial7, configured by `rangefinder_virtual_serial_link`
and `rangefinder_serial_baud`, not by a MAVLink sender endpoint.

## 2026-06-15: Go sim hover restores the Python MAVLink router topology (superseded)

Decision: superseded. Earlier H5 work tried to start `mavlink_router` before
the official baseline whenever the task needed the SITL/Gazebo stack.
Hover/exploration/navigation/scan runtime clients would use router endpoints
instead of competing for the same `udpin:0.0.0.0:14550` listener. The default
FCU bootstrap endpoint was `tcp:127.0.0.1:5760`; the simulated down rangefinder
sent `DISTANCE_SENSOR` via `udpout:127.0.0.1:14550`.

Basis: baseline commit `a3e0f7a` used `NAVLAB_SERVICES=("gazebo",
"gazebo-sensor", "mavlink-router", "sitl")`. Its `navlab/config.toml`
configured companion MAVLink readers through router TCP endpoints and the down
rangefinder through `udpout:mavlink-router:14550`. H5 Go hover runs that used
two direct `udpin:0.0.0.0:14550` consumers showed `/rangefinder/down/range`
ROS samples but no FCU `DISTANCE_SENSOR`, and ArduPilot blocked arming with
`Arm: Rangefinder 1: No Data`.

Reason: the rangefinder, mission controller, ExternalNav sender, and telemetry
mirrors are separate clients of the same FCU stream. A router is the stable
boundary that lets simulation mirror real multi-client MAVLink wiring. If the
router or a client endpoint fails, the task must block with evidence; it must
not force-arm or substitute Gazebo truth.

Superseding note: this copied the old compose topology into the new official
baseline incorrectly. The official Gazebo bringup already owns SITL master
`tcp:127.0.0.1:5760` and MAVProxy output `127.0.0.1:14550`. Adding a separate
router that also listened on `5760` stole the official master surface and made
hover runs receive rangefinder traffic but no FCU heartbeat or DDS pose.

## 2026-06-15: Go official-baseline MAVLink router is UDP fan-out only

Decision: Go sim may start `mavlink_router` for official-baseline tasks, but
only as a UDP fan-out for the official MAVProxy output. The router listens on
`0.0.0.0:14550`, disables TCP listening with `ROUTER_TCP_PORT=0`, and forwards
FCU traffic to internal clients on `127.0.0.1:14551` and `127.0.0.1:14552`.
Hover mission/runtime listens on `udpin:0.0.0.0:14551`. The down rangefinder
listens on `udpin:0.0.0.0:14552`, observes FCU heartbeat through the router,
and sends `DISTANCE_SENSOR` back over the learned peer. It must fail closed if
that MAVLink peer is absent.

Basis: the official launch in
`ardupilot_gz/ardupilot_gz_bringup/launch/robots/robot.launch.py` derives
`master_port = 5760 + offset` and `mavlink_out = 14550 + offset`. H5 Go runs
`artifacts/sim/hover/20260615T153951Z`,
`artifacts/sim/hover/20260615T154958Z`, and
`artifacts/sim/hover/20260615T155940Z` started a router that opened the
conflicting TCP `5760` server and then blocked in `wait_ready`: no FCU
heartbeat/local-position evidence reached the hover mission and
`/ap/v1/pose/filtered` was missing. A later no-router test
`artifacts/sim/hover/20260615T162735Z` restored mission heartbeat/local-position
but left the down rangefinder with `mavlink_peer_observed=false`, proving that
the missing piece is multi-client UDP fan-out, not a TCP master replacement.

Reason: the old Python compose stack and the new official baseline are
different runtime topologies. The invariant is not "always run a TCP router on
5760"; the invariant is that every control input must come through
real-equivalent MAVLink or ROS algorithm outputs, and any missing
FCU/rangefinder evidence blocks the task instead of using Gazebo truth,
force-arm, or topic-count substitutes.

## 2026-06-15: Hover airborne evidence outranks NAV_TAKEOFF ACK

Decision: Go sim hover must not require a successful `MAV_CMD_NAV_TAKEOFF` ACK
after the vehicle is already proven airborne by MAVLink position evidence.
`takeoff_ack_ok` remains in the mission summary as diagnostic evidence, but the
state machine may enter hover-settle/hold when `LOCAL_POSITION_NED` or
`GLOBAL_POSITION_INT` confirms the configured airborne threshold.

Basis: H5 live run `artifacts/sim/hover/20260615T164659Z` had
`rangefinder_count=2651`, `armed_seen=true`, `airborne_seen=true`, and
`current_z_ned=-0.69`, but `NAV_TAKEOFF` returned FAILED and the migrated hover
state machine stayed in `takeoff` with zero setpoints. The baseline Python
obstacle mission gates on `airborne_seen`, not `takeoff_ack_ok`.

Reason: acceptance must prove real motion, not a particular ACK path. A failed
takeoff ACK with no airborne evidence still blocks; a failed ACK with clear
airborne evidence is recorded for diagnostics while hover/landing continue.

## 2026-06-15: Hover landing accepts touchdown/disarm evidence over LAND ACK

Decision: Go sim hover landing acceptance is based on real MAVLink state
evidence: touchdown confirmed, disarm confirmed when required, and motors safe.
`MAV_CMD_NAV_LAND` ACK remains in the summary as diagnostic evidence but is not
required when the vehicle has already landed and disarmed.

Basis: H5 live run `artifacts/sim/hover/20260615T170341Z` completed the hover
body with `hover_body_ok=true`, `target_z_ned=-0.69`, `altitude_error_m=0.01`,
and `hover_hold_duration_sec=17.95`. Landing then reached
`touchdown_confirmed=true`, `disarmed=true`, and `motors_safe=true`, but
`land_command_accepted=false`; requiring the ACK alone incorrectly blocked a
physically completed landing.

Reason: the sim acceptance target is real-equivalent behavior, not a specific
ACK bookkeeping path. Missing touchdown/disarm/motor-safe evidence still
blocks; a missing LAND ACK with those signals present is recorded, not used to
override the observed landing.

## 2026-06-15: Hover rosbag required topics follow lite replay evidence

Decision: Go sim hover rosbag required topics are limited to the replay and
task-state evidence that must be present in the lite artifact: `/tf`,
`/tf_static`, `/map`, `/scan`, `/slam/odom`, `/navlab/hover/status`,
`/navlab/landing/status`, and `/rangefinder/down/range`. IMU samples, FCU
status, and rangefinder status remain required runtime evidence through probes
or `mission_summary.json`, but they are not required to be recorded in the
hover replay MCAP.

Basis: H5 live run `artifacts/sim/hover/20260615T171440Z` completed the
mission with `mission_summary.ok=true`, `airborne_seen=true`,
`hover_body_ok=true`, `landing_ok=true`, `disarmed=true`, `motors_safe=true`,
and `altitude_error_m=0`. The only remaining blocker was
`rosbag_profile_failed:hover_rosbag` because the Go rosbag required set still
expected `/ap/v1/status`, `/imu`, and `/rangefinder/down/status`, while the
lite profile intentionally drops or makes those topics optional to keep replay
artifacts small.

Reason: task acceptance must fail closed on missing behavior evidence, not on
whether high-frequency or diagnostic topics were retained in a review artifact.
This keeps hover from passing on topic counts alone while also preventing a
successful flight/landing from being marked failed only because lite replay
filtering omitted nonessential diagnostics.

## 2026-06-16: Hover altitude evidence requires source cross-check

Decision: Go sim hover acceptance must fail closed unless the hover hold window
contains consistent altitude evidence from FCU local position, merged
ExternalNav height, and rangefinder-derived height. `takeoff_ack_ok=false` can
only be tolerated when the same cross-check proves the vehicle is airborne and
at the configured target height. The summary must record FCU local `z`,
ExternalNav `z`, rangefinder height, pairwise differences, tolerance status, and
drift quality.

Basis: Earlier hover runs could pass the task body with `takeoff_ack_ok=false`
or with only FCU local-position altitude evidence. That was too loose for the
ExternalNav chain because `/slam/odom` supplies horizontal pose while
rangefinder/height estimation must supply the vertical component. A stale or
missing height path must block instead of being hidden by local-position count
or a broad drift pass.

Reason: hover is the base task for exploration and navigation. If hover does
not prove that FCU local altitude, `/external_nav/odom` height, and
`/rangefinder/down/range` agree during the hold phase, later tasks can inherit a
bad estimator while still looking superficially healthy. Drift is therefore
graded as `tight`, `nominal`, `marginal`, or failing quality, and a pass with
centimeter-level drift is not automatically labeled GPS-like.

## 2026-06-16: Hover loses navigation evidence fail closed after takeoff

Decision: once hover has observed the vehicle airborne, loss of GUIDED mode,
ExternalNav, MAVLink ExternalNav sender readiness, or fresh FCU local-position
feedback is a terminal abort that starts landing. The state machine must not
fall back to a preflight `wait_ready` or mode-setting phase while armed and
airborne, and hold setpoints may only be sent in `hover_settle` or
`hover_hold`. A task duration timeout after arming/airborne must also start
landing before writing the final failed summary.

Basis: live run `artifacts/sim/hover/20260616T155015Z` showed the migrated
hover task entering hover phases and then ending with `phase=wait_ready`,
`setpoints_sent_count=262`, stale ExternalNav/height evidence, unstable drift,
and no landing evaluation. That path let a post-takeoff estimator loss keep
driving position setpoints instead of treating it as a flight-safety failure.

Reason: fail-closed behavior must be explicit. Before takeoff, missing
navigation evidence means wait; after takeoff, missing navigation evidence
means stop the task body, record the reason, and hand control to landing. This
keeps hover from masking estimator dropouts as a timeout or a generic unstable
hold.

## 2026-06-24: Trim unreachable Go sim helper surface after hover audit split

Decision: remove Go sim helpers that are unreachable even when tests are included,
and also remove older helper APIs that were only kept alive by tests while the
runtime now uses generated runtime specs, artifacts, probes, and thin CLI
wrappers.

Basis: `go run golang.org/x/tools/cmd/deadcode@latest -test ./...` is clean
after the cleanup. The removed surfaces were direct Docker helper wrappers,
motion doctor summary helpers, convenience wrappers around newer option-based
APIs, and legacy official-stack / scan-integrity helpers that were no longer
referenced by production paths.

Reason: the sim orchestrator should expose one active path per responsibility:
runtime specs for execution, artifact/probe files for Go/Python boundaries, and
`internal/audits/hover` for hover audit analysis. Keeping test-only legacy
surfaces makes future hover/runtime reviews harder and increases the chance of
fixing the wrong path.

## 2026-06-24: Consolidate hover audit CLIs under navlab-sim

Decision: remove the standalone Go hover audit command packages and expose the
same artifact audits through `navlab-sim audit hover ...` subcommands.

Basis: after moving audit logic to `internal/audits/hover`, the old
`cmd/hover-*-audit` packages were only thin JSON wrappers. Keeping many small
entrypoints made future audit additions likely to duplicate flags, output
handling, and error handling.

Reason: `navlab-sim` should be the single simulation control-plane CLI. A
breaking CLI cleanup is acceptable here because it prevents another compatibility
layer while preserving the audit JSON schemas and default output artifacts.

## 2026-06-25: Hover span SLO policy is Go-owned and tiered

Decision: hover XY span is no longer a single binary `0.1m` hard gate. Go owns
and records the resolved policy (`hover_span_target_m`,
`hover_span_hard_cap_m`), passes it to Python through generated runtime files
and CLI args, and Python classifies span/drift as green, yellow, or red. Target
exceed below hard cap is warning/statistical evidence, while hard-cap exceed and
real safety events remain hard blockers. Gazebo-only drift remains review-only
until its observation contract is promoted.

Basis: Phase 41/42 runs showed runtime health green and no ExternalNav/SLAM
loss, but mission body blocked only because `horizontal_span_m` slightly
exceeded `0.1m` (`0.103m`, `0.118m`). A fresh Phase 47 usage pass
`20260625T023143Z` completed `TASK_STATUS_OK` with the Go-provided policy
recorded in artifacts.

Reason: hover is a stochastic closed-loop sim/real experiment, not a pure
function. Treating the SLO target as the hard cap turns normal tail behavior
into false failures. Separating target, hard cap, and cohort percentiles keeps
real safety fail-closed while allowing distribution-based review.

## 2026-06-25: Phase 49 hover cohort is case-study evidence, not a P99 claim

Decision: treat the fresh five-run `slam-direct-no-odom-prior` hover cohort as
evidence that the basic hover body is operationally usable under the current
Go-owned SLO policy, while explicitly limiting the claim to `case_study_only`.
The remaining yellow health band is observation-contract debt, not a runtime
hover-body blocker.

Basis: five consecutive Phase 49 runs (`20260625T030617Z`,
`20260625T030852Z`, `20260625T031110Z`, `20260625T031325Z`,
`20260625T031541Z`) completed `TASK_STATUS_OK` with
`runtime_hover_health_final.band=green` and `sim_auto_continue`. The cohort
artifact `artifacts/sim/hover/phase49_5run_hover_health_cohort.json` reports
mission hover span max `0.067324m`, target exceed count `0`, hard-cap exceed
count `0`, and `sample_size_rule=case_study_only`.

Reason: the valid samples are all below both the `0.1m` target and `0.15m`
hard cap, so the main hover loop is usable for the current sim profile. Because
five samples cannot support a strong tail claim, P95/P99 values are descriptive
case-study statistics only. Gazebo contract findings remain review-only and
belong to the observation-contract phases.

## 2026-06-25: Hover artifacts use a breaking readable directory layout

Decision: new sim hover artifacts use a deliberately breaking layout: reviewer
entry files stay at the run root, while runtime scripts/configs/logs, probes,
audits, rosbag profiles, rosbags, and SITL state live in dedicated
subdirectories. SQLite is not part of the single-run runtime chain.

Basis: Phase 50 usage artifact `artifacts/sim/hover/20260625T035409Z`
completed `TASK_STATUS_OK` with `gate_evaluation.ok=true`. Its root contains
only entry files and directories, while `runtime/scripts`,
`runtime/config`, `runtime/logs`, `probes`, `audits`, `profiles`, `rosbag`, and
`sitl` hold the detailed evidence. The post-run hover health artifact moved to
`audits/hover_health_summary.json`, and `navlab-sim audit hover health`,
`contract`, and `gate-replay` default to `audits/`.

Reason: keeping one flat artifact directory made debugging and review too
expensive as hover evidence grew. A compatibility layer for old flat paths would
preserve the confusion, so the new Go path model owns the layout going forward.
SQLite remains a future rebuildable cohort index/cache only, not the source of
truth for a single run.

## 2026-06-25: Gazebo hover evidence stays review-only until contract promotion

Decision: Phase 48 makes Gazebo comparability and FCU/controller evidence explicit
in hover audits without changing runtime control. `navlab-sim audit hover
contract` reports Gazebo frame origin, time basis, sign convention,
model/link-name resolution, and a promotion rule; `navlab-sim audit hover
trajectory` reports peak-time direction agreement/disagreement across SLAM,
ExternalNav, FCU local pose, Gazebo model odometry, and scan-reference odometry.

Basis: the latest successful hover artifact `artifacts/sim/hover/20260625T035409Z`
shows SLAM and ExternalNav peak motion agreeing, while Gazebo model odometry can
still point in the opposite relative-X direction under the unpromoted contract.
The same artifact has no FCU controller/setpoint status samples, so the audit
must label that as explicit review evidence debt instead of silently treating it
as pass or fail.

Reason: Gazebo is useful as a simulation review source, but it is not a real
flight safety truth source until frame origin, model/link resolution, timestamp,
and sign convention are promoted by a separate tested decision. Missing FCU
control evidence should be obvious to reviewers, but in hover it remains
optional/review-only until a later phase turns it into a hard runtime gate.

## 2026-06-25: Startup readiness is separate from hover-body SLO

Decision: classify hover artifacts that never reach airborne/`hover_hold` as
startup/readiness failures rather than hover span SLO samples. The gate metrics
now emit `startup_readiness` evidence covering mission state, rangefinder input,
height readiness, Benewake serial byte/frame counts, probe sample semantics, and selected rosbag counts.

Basis: preflight artifact `artifacts/sim/hover/20260625T022810Z` stopped at
`S1 wait_nav_ready` with rangefinder input count `0`, Benewake serial `byte_count=0` / `frame_count=0`, no `/rangefinder/down/range`
samples, missing height estimate, and ExternalNav waiting for height. A fresh
post-change run `artifacts/sim/hover/20260625T051820Z` completed
`TASK_STATUS_OK` and replays as a valid hover-body sample.

Reason: rangefinder/height startup failures are operational readiness problems,
not evidence that the hover span policy or controller body is unstable. Keeping
the classifier in Go gate metrics preserves fail-closed behavior while making
cohort filtering and debugging explicit.

## 2026-06-25: Startup readiness runtime action policy is Go-owned

Decision: Phase 52 treats startup readiness as a Go-owned runtime action policy
with three separate strategy layers: `wait_longer_policy`, `fail_fast_policy`,
and `prearm_restart_policy`. Python mission/FSM code consumes resolved policy
through generated runtime files/CLI/env and writes evidence back; it does not own
policy defaults or silently choose wait/restart behavior.

Basis: Phase 51 made `startup_readiness_failure` classification explicit, but it
only diagnosed stuck rangefinder/height startup after the fact. The next runtime
slice needs a policy boundary before adding any active restart behavior, because
restart is only safe before armed/airborne/`hover_hold` and must be bounded and
artifacted.

Reason: keeping the strategy in Go lets sim/real profiles, CLI overrides,
artifacts, gate metrics, and cohort reports agree on the same policy. It also
prevents Python mission code from accumulating hidden, task-specific wait and
restart heuristics.

## 2026-06-25: Task duration is a runtime timeout, not fixed rosbag time

Decision: live sim runs stop rosbag recording shortly after task completion
instead of waiting for the configured task duration to elapse. The default
post-task rosbag grace is 5 seconds; `duration_sec` remains the upper-bound
timeout used by mission/runtime components, Go runtime watchdog, and rosbag's
own safety timeout.

Basis: hover missions can complete their FSM in roughly 50 seconds, while the
task YAML uses `duration_sec=90` as the maximum allowed runtime. The previous
runtime runner waited for rosbag containers to hit their 90-second timeout after
probes completed, making successful runs appear to hang for the unused timeout
budget.

Reason: task completion should be event-driven by the FSM/probe result, with a
small grace period to capture trailing telemetry. Keeping the 90-second value as
a safety cap preserves fail-closed timeout behavior without wasting every green
run's tail. If the FSM/probe path does not complete before the deadline, Go
emits `run.timeout`, stops runtime, and writes a minimal timeout mission summary
only when Python did not already write one.

## 2026-06-25: Default hover runs the Phase 41/42 no-odom-prior profile

Decision: `just navlab-run hover` now uses the `slam-direct-no-odom-prior`
simulation profile by default. The older `ideal` profile remains available only
as an explicit override for debugging or legacy comparison.

Basis: Phase 41/42 established the current hover mainline as direct
`/slam/odom` ExternalNav with the no-odom-prior Cartographer config. Later
Phase 47/49/52 usage passes and cohorts used that command path, while the task
YAML still defaulted to `ideal`, creating artifacts that looked like mainline
hover runs but were not testing the active route.

Reason: the default command should produce evidence for the route we actually
trust and discuss. Keeping thresholds (`target=0.1m`, `hard_cap=0.15m`) in Go
runtime config/CLI overrides preserves policy ownership while removing the
accidental old-profile footgun.

## 2026-06-25: Hover simulation profiles are a Go registry

Decision: hover route profiles are now defined by a Go registry instead of raw
string branches in `ApplySimulationProfile`. The registry and profile
resolution both live in `simulation_profiles.go`; each hover profile records
its purpose, allowed tasks, ExternalNav input mode, and Cartographer config
effect. Unknown hover profiles fail fast with the allowed names.

Basis: after making `slam-direct-no-odom-prior` the default hover profile, the
profile name still behaved like a magic string. The same route semantics were
spread across YAML, helper constants, tests, and an if/else block. Phase 54
centralizes those semantics in `simulation_profiles.go` and echoes the resolved
profile metadata into `runtime_plan.json`.

Reason: adding or reviewing a hover profile should be a registry-entry change,
not another scattered control-plane branch. Keeping resolution in Go preserves
the Go/Python boundary: Python receives generated runtime files and artifacts,
but does not own profile policy.

## 2026-06-27: WF-DAG breaks to the new workflow artifact contract

Decision: Go sim and Rust real workflow artifacts use the new WF0/WF-DAG node
contract directly: `id/kind/deps/required/mode/domain/side_effect_policy` plus
node result fields such as `skipped`, `skip_reason`, `artifacts`, and
`started_at`/`finished_at`. Legacy `node_id`/`stage` JSON fields and Rust real
root `workflow_summary.json` compatibility output are not preserved.

Basis: sim and real are being aligned around `dag/workflow_summary.json` as the
single workflow DAG artifact. Keeping old field names or root mirrors would
create two active contracts and make later proto/schema promotion ambiguous.

Reason: this is still an internal orchestration artifact. Breaking now keeps
review, gate, cohort, and future shared readers pointed at one shape while the
surface area is small. Runtime side effects and evidence adapters remain
domain-specific; only the workflow artifact contract is shared.
