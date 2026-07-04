# NavLab FSM Artifact Schema

Status: draft v1

This document defines the public FSM artifact contract used by NavLab sim,
real, task-level runtimes, and runtime sub-FSMs.

The schema is intentionally independent from language-local FSM libraries. Go
may use `qmuntal/stateless` and Rust may use `statig`, but artifacts must expose
only the NavLab fields below.

## Schema Version

Every FSM artifact uses:

```json
{
  "schema_version": "navlab.fsm.v1"
}
```

## Required Identity Fields

- `schema_version`: fixed string, `navlab.fsm.v1`.
- `fsm_name`: stable FSM name, for example `rosbag_recorder` or
  `motor_debug_task`.
- `scope`: one of `task`, `runtime`, `service`, `probe`, `rosbag`, `mavlink`, or
  another stable project scope.
- `task_id`: task id that owns the FSM.
- `run_id`: run id that owns the FSM.
- `state`: current state.
- `mode`: `planned`, `actual`, `blocked_before_runtime`, or another explicit
  mode.
- `ok`: true when the FSM reached an acceptable terminal state.
- `blocked`: true when the FSM ended in a failed or blocked state.

## Optional Hierarchy Fields

Runtime sub-FSMs do not get embedded into the workflow DAG. They are linked by
artifact reference.

- `parent_fsm`: optional parent FSM reference.
- `sub_fsms`: optional list of child FSM artifact references.
- `artifact_path`: optional path to this FSM artifact, usually relative to the
  run artifact root.

`parent_fsm` fields:

- `fsm_name`
- `scope`
- `artifact_path`

`sub_fsms[]` fields:

- `fsm_name`
- `scope`
- `artifact_path`
- `state`
- `ok`
- `blocked`
- `failure_reason_code`

## State Model Fields

- `states[]`: declared states, each with `state`, optional `terminal`,
  optional `failure`, and optional `description`.
- `triggers[]`: declared triggers, each with `trigger` and optional
  `description`.
- `transitions[]`: observed or planned transitions.
- `guards[]`: side-effect-free guard checks used by transitions.
- `evidence`: run-level evidence map for the FSM.
- `reason_codes[]`: stable reason codes used by this FSM.
- `blockers[]`: stable blockers with `code`, `message`, and optional `source`.

Transition fields:

- `from_state`
- `to_state`
- `trigger`
- `at`
- `ok`
- `reason_code`
- `evidence`
- `guard_results`

Guard fields:

- `name`
- `ok`
- `required`
- `reason_code`
- `evidence`

## Failure Fields

Failed or blocked FSMs should set:

- `failed_state`: destination or current state where failure was detected.
- `failed_trigger`: trigger that exposed the failure.
- `failure_reason_code`: stable reason code.
- `recoverable`: whether retry/recovery is allowed by policy.

Failure states are regular states with `failure=true`; examples:

- `start_failed`
- `stop_failed`
- `finalize_timeout`
- `evidence_missing`
- `required_topics_missing`
- `cleanup_failed`

## Debug Artifacts

Debug graph artifacts are optional review artifacts, not gate inputs.

- `debug_artifacts[]`: artifact references such as DOT graphs.
- DOT graph output should be treated as derived documentation. The JSON artifact
  is authoritative.

## Example: Rosbag Recorder Runtime Sub-FSM

```json
{
  "schema_version": "navlab.fsm.v1",
  "fsm_name": "rosbag_recorder",
  "scope": "rosbag",
  "task_id": "hover",
  "run_id": "20260627T020802.064314492Z",
  "state": "completed",
  "mode": "actual",
  "ok": true,
  "blocked": false,
  "parent_fsm": {
    "fsm_name": "hover_runtime",
    "scope": "runtime"
  },
  "transitions": [
    {
      "from_state": "idle",
      "to_state": "starting",
      "trigger": "start",
      "ok": true
    },
    {
      "from_state": "finalizing",
      "to_state": "evidence_verified",
      "trigger": "verify_evidence",
      "ok": true,
      "reason_code": "rosbag_metadata_ready"
    }
  ],
  "reason_codes": [
    "rosbag_metadata_ready"
  ]
}
```

## Boundary

The FSM schema may mention evidence paths and reason codes. It must not contain
Docker SDK types, Gazebo/SITL handles, serial-port handles, MAVLink crate types,
or third-party FSM library serialization.
