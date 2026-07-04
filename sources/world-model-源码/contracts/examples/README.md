# Contract Examples

Golden JSON examples map expected artifact shapes to their owning proto
messages. They are intentionally checked in before generated code so Go, Rust,
and Python readers can converge on the same boundary.

| Example | Proto message |
| --- | --- |
| `orchestration/sim_task_request.json` | `navlab.orchestration.v1.TaskRequest` |
| `orchestration/sim_navigation_summary.json` | Go sim task summary artifact |
| `orchestration/real_task_result.json` | `navlab.orchestration.v1.TaskResult` |
| `orchestration/doctor_result_blocked.json` | `navlab.orchestration.v1.DoctorResult` |
| `runtime/sim_runtime_plan.json` | `navlab.runtime.v1.RuntimePlan` |
| `runtime/real_process_event.json` | `navlab.runtime.v1.ProcessEvent` |
| `safety/motor_debug_ack_failed.json` | `navlab.safety.v1.MavlinkAck` |
| `sensors/real_source_evidence.json` | `navlab.sensors.v1.SourceEvidence` |
