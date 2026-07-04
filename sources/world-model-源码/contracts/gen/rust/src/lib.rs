pub mod navlab {
    pub mod orchestration {
        pub mod v1 {
            include!(concat!(env!("OUT_DIR"), "/navlab.orchestration.v1.rs"));
        }
    }

    pub mod runtime {
        pub mod v1 {
            include!(concat!(env!("OUT_DIR"), "/navlab.runtime.v1.rs"));
        }
    }

    pub mod safety {
        pub mod v1 {
            include!(concat!(env!("OUT_DIR"), "/navlab.safety.v1.rs"));
        }
    }

    pub mod sensors {
        pub mod v1 {
            include!(concat!(env!("OUT_DIR"), "/navlab.sensors.v1.rs"));
        }
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;

    use prost::Message;
    use serde_json::Value;

    use crate::navlab::orchestration::v1::{RuntimeMode, TaskRequest, TaskResult, TaskStatus};
    use crate::navlab::runtime::v1::{RuntimeBackend, RuntimePlan};
    use crate::navlab::safety::v1::MavlinkAck;
    use crate::navlab::sensors::v1::{RuntimeDomain, SourceEvidence};

    #[test]
    fn generated_types_can_encode_core_contracts() {
        let request = TaskRequest {
            schema_version: "navlab.orchestration.task_request.v1".to_string(),
            task_id: "hover".to_string(),
            run_id: "run".to_string(),
            runtime_mode: RuntimeMode::Sim as i32,
            artifact_dir: "artifacts/sim/hover/run".to_string(),
            capabilities: vec!["needs_gazebo".to_string()],
            parameters: None,
            source_claims: Some(SourceEvidence {
                runtime_domain: RuntimeDomain::Sim as i32,
                scan_source: "gazebo_x2_virtual_serial".to_string(),
                imu_source: "official_gazebo_imu_bridge".to_string(),
                rangefinder_source: "gazebo_down_rangefinder".to_string(),
                slam_source: "cartographer".to_string(),
                uses_truth_as_control_input: false,
                topics: vec![],
            }),
            created_at: None,
        };
        let mut bytes = Vec::new();
        request.encode(&mut bytes).expect("encode task request");
        let decoded = TaskRequest::decode(bytes.as_slice()).expect("decode task request");
        assert_eq!(decoded.task_id, "hover");
        assert_eq!(decoded.runtime_mode, RuntimeMode::Sim as i32);
    }

    #[test]
    fn golden_examples_match_generated_type_enums_and_fields() {
        let request = read_example("orchestration/sim_task_request.json");
        assert_eq!(request["runtimeMode"], RuntimeMode::Sim.as_str_name());
        assert_eq!(
            request["sourceClaims"]["runtimeDomain"],
            RuntimeDomain::Sim.as_str_name()
        );

        let result = read_example("orchestration/real_task_result.json");
        assert_eq!(result["status"], TaskStatus::Blocked.as_str_name());

        let plan = read_example("runtime/sim_runtime_plan.json");
        assert_eq!(
            plan["services"][0]["backend"],
            RuntimeBackend::Docker.as_str_name()
        );

        let ack = read_example("safety/motor_debug_ack_failed.json");
        assert_eq!(ack["command"], "ARM");

        let source = read_example("sensors/real_source_evidence.json");
        assert_eq!(source["runtimeDomain"], RuntimeDomain::Real.as_str_name());

        let _ = RuntimePlan::default();
        let _ = MavlinkAck::default();
        let _ = TaskResult::default();
    }

    fn read_example(relative: &str) -> Value {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("examples")
            .join(relative);
        let data = std::fs::read_to_string(&path)
            .unwrap_or_else(|err| panic!("read {}: {err}", path.display()));
        serde_json::from_str(&data).unwrap_or_else(|err| panic!("parse {}: {err}", path.display()))
    }
}
