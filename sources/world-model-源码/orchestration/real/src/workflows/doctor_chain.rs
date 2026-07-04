use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::Serialize;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tracing::{info, instrument};

use crate::config::{ProjectConfig, TaskConfig};
use crate::workflows::common_doctor::{
    CommonDoctorInput, CommonDoctorSummary, TopicProbe, run_common_doctor,
};
use crate::workflows::preflight::{EnvironmentProbe, PreflightSummary, run_preflight};
use crate::workflows::prepare::{
    PrepareInput, PrepareSummary, start_prepare_phase, stop_prepare_phase,
};
use crate::workflows::task_doctor::{TaskDoctorInput, TaskDoctorSummary, run_task_doctor};

#[derive(Debug, Clone)]
pub struct DoctorChainInput {
    pub prepare_dry_run: bool,
    pub allow_live_prepare: bool,
    pub upstream_json: Option<PathBuf>,
    pub artifact_dir: Option<PathBuf>,
    pub summary_path: Option<PathBuf>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DoctorChainSummary {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub task_name: String,
    pub chain_claim: String,
    pub checked_at: String,
    pub artifact_dir: String,
    pub prepare_stopped: bool,
    pub preflight: PreflightSummary,
    pub prepare: Option<PrepareSummary>,
    pub common_doctor: Option<CommonDoctorSummary>,
    pub task_doctor: Option<TaskDoctorSummary>,
}

#[instrument(skip(project, task_config, environment, topic_probe, input))]
pub fn run_doctor_chain(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    environment: &dyn EnvironmentProbe,
    topic_probe: &dyn TopicProbe,
    input: DoctorChainInput,
) -> Result<DoctorChainSummary> {
    let artifact_dir = input
        .artifact_dir
        .clone()
        .unwrap_or_else(|| default_artifact_dir(project, &task_config.id));
    fs::create_dir_all(&artifact_dir).with_context(|| {
        format!(
            "create doctor-chain artifact dir {}",
            artifact_dir.display()
        )
    })?;

    let preflight = run_preflight(
        project,
        environment,
        Some(&artifact_dir.join("preflight.json")),
    )?;
    let mut summary = DoctorChainSummary {
        ok: false,
        blocked: true,
        blockers: preflight.blockers.clone(),
        task_name: task_config.id.clone(),
        chain_claim: "evaluated".to_string(),
        checked_at: utc_now(),
        artifact_dir: artifact_dir.display().to_string(),
        prepare_stopped: false,
        preflight,
        prepare: None,
        common_doctor: None,
        task_doctor: None,
    };

    if !summary.blockers.is_empty() {
        finalize_summary(&mut summary, input.summary_path.as_deref(), &artifact_dir)?;
        return Ok(summary);
    }

    let prepare_result = start_prepare_phase(
        project,
        task_config,
        PrepareInput {
            dry_run: Some(input.prepare_dry_run),
            allow_live: input.allow_live_prepare,
            summary_path: Some(artifact_dir.join("prepare.json")),
        },
    )?;
    summary.prepare = Some(prepare_result.summary.clone());
    summary
        .blockers
        .extend(prepare_result.summary.blockers.clone());
    if !summary.blockers.is_empty() {
        stop_prepare_phase(&prepare_result)?;
        summary.prepare_stopped = true;
        finalize_summary(&mut summary, input.summary_path.as_deref(), &artifact_dir)?;
        return Ok(summary);
    }

    let upstream_output = artifact_dir.join("upstream.json");
    let common = run_common_doctor(
        project,
        task_config,
        CommonDoctorInput {
            upstream_json: input.upstream_json,
            summary_path: Some(artifact_dir.join("common-doctor.json")),
            upstream_output: Some(upstream_output.clone()),
        },
        topic_probe,
    )?;
    summary.blockers.extend(common.blockers.clone());
    summary.common_doctor = Some(common);
    if !summary.blockers.is_empty() {
        stop_prepare_phase(&prepare_result)?;
        summary.prepare_stopped = true;
        finalize_summary(&mut summary, input.summary_path.as_deref(), &artifact_dir)?;
        return Ok(summary);
    }

    let task_doctor = run_task_doctor(
        project,
        task_config,
        TaskDoctorInput {
            upstream_json: Some(upstream_output),
            summary_path: Some(artifact_dir.join("task-doctor.json")),
        },
    )?;
    summary.blockers.extend(task_doctor.blockers.clone());
    summary.task_doctor = Some(task_doctor);

    stop_prepare_phase(&prepare_result)?;
    summary.prepare_stopped = true;
    finalize_summary(&mut summary, input.summary_path.as_deref(), &artifact_dir)?;
    info!(
        ok = summary.ok,
        blocked = summary.blocked,
        task = summary.task_name,
        artifact_dir = %artifact_dir.display(),
        "wrote real doctor-chain summary"
    );
    Ok(summary)
}

fn finalize_summary(
    summary: &mut DoctorChainSummary,
    summary_path: Option<&Path>,
    artifact_dir: &Path,
) -> Result<()> {
    summary.blockers = dedupe(std::mem::take(&mut summary.blockers));
    summary.ok = summary.blockers.is_empty();
    summary.blocked = !summary.blockers.is_empty();
    let path = summary_path
        .map(Path::to_path_buf)
        .unwrap_or_else(|| artifact_dir.join("summary.json"));
    write_json(&path, summary, "real doctor-chain summary")
}

fn write_json<T: Serialize>(path: &Path, value: &T, label: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create {label} dir {}", parent.display()))?;
    }
    fs::write(path, serde_json::to_string_pretty(value)?)
        .with_context(|| format!("write {label} {}", path.display()))
}

fn default_artifact_dir(project: &ProjectConfig, task_name: &str) -> PathBuf {
    project
        .paths
        .artifact_root
        .join("doctor-chain")
        .join(run_id())
        .join(task_name)
}

fn run_id() -> String {
    let now = OffsetDateTime::now_utc();
    format!(
        "{:04}{:02}{:02}T{:02}{:02}{:02}Z",
        now.year(),
        u8::from(now.month()),
        now.day(),
        now.hour(),
        now.minute(),
        now.second()
    )
}

fn utc_now() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "unknown".to_string())
}

fn dedupe(values: Vec<String>) -> Vec<String> {
    let mut seen = std::collections::BTreeSet::new();
    let mut result = Vec::new();
    for value in values {
        if seen.insert(value.clone()) {
            result.push(value);
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{
        CommonDoctorConfig, OrchestrationConfig, PathConfig, PreflightConfig,
        PreflightDependencyConfig, PrepareConfig, RuntimeConfig, SerialMavlinkConfig, SourceConfig,
        TaskDoctorConfig,
    };
    use crate::workflows::preflight::{CommandGroupEvidence, RosPackageEvidence};
    use crate::workflows::task_doctor::UpstreamEvidence;
    use serde_json::json;
    use std::collections::BTreeMap;

    #[derive(Debug)]
    struct HealthyEnvironment;

    impl EnvironmentProbe for HealthyEnvironment {
        fn command_path(&self, command: &str, _ros_distro: &str) -> Option<String> {
            Some(format!("/usr/bin/{command}"))
        }

        fn python_module_present(&self, _module: &str) -> bool {
            true
        }

        fn ros_package_prefix(&self, package: &str, _ros_distro: &str) -> RosPackageEvidence {
            RosPackageEvidence {
                present: true,
                prefix: format!("/opt/ros/humble/share/{package}"),
                error: String::new(),
            }
        }

        fn process_services(&self) -> Vec<String> {
            Vec::new()
        }
    }

    #[derive(Debug)]
    struct StaticTopicProbe {
        upstream: UpstreamEvidence,
    }

    impl TopicProbe for StaticTopicProbe {
        fn collect(&self, _project: &ProjectConfig, _task_id: &str) -> Result<UpstreamEvidence> {
            Ok(self.upstream.clone())
        }
    }

    fn project() -> ProjectConfig {
        ProjectConfig {
            orchestration: OrchestrationConfig {
                family: "real".to_string(),
                implementation: "rust".to_string(),
                contract_version: "navlab.orchestration.v1".to_string(),
            },
            runtime: RuntimeConfig {
                mode: "real".to_string(),
                backend: "process".to_string(),
            },
            paths: PathConfig {
                workspace_root: "../..".into(),
                artifact_root: "artifacts/real".into(),
                task_config_dir: "configs/tasks".into(),
            },
            sources: SourceConfig {
                scan_source_claim: "real_lidar_driver".to_string(),
                scan_source_topic: "/scan".to_string(),
                fcu_source_claim: "real_serial_mavlink_or_ardupilot_dds_bridge".to_string(),
                imu_source_claim: "real_fcu_or_sensor".to_string(),
                rangefinder_source_claim: "real_or_not_required".to_string(),
                slam_source_claim: "real_slam".to_string(),
                required_real_topics: vec![],
                forbidden_simulation_input_topics: vec![],
            },
            preflight: PreflightConfig {
                serial_mavlink: SerialMavlinkConfig {
                    enabled: false,
                    ..SerialMavlinkConfig::default()
                },
                dependencies: PreflightDependencyConfig {
                    required_command_groups: Vec::new(),
                    required_ros_packages: Vec::new(),
                    required_python_modules: Vec::new(),
                    required_process_services: Vec::new(),
                },
                ..PreflightConfig::default()
            },
            prepare: PrepareConfig::default(),
            common_doctor: CommonDoctorConfig::default(),
            task_doctor: TaskDoctorConfig::default(),
        }
    }

    fn task_config() -> TaskConfig {
        TaskConfig {
            id: "motor-debug".to_string(),
            family: "real".to_string(),
            description: "test".to_string(),
            capabilities: vec![],
            task: BTreeMap::new(),
            safety: BTreeMap::new(),
        }
    }

    fn upstream() -> UpstreamEvidence {
        serde_json::from_value(json!({
            "ok": true,
            "blocked": false,
            "blockers": [],
            "required_topics": {
                "/ap/v1/status": {
                    "metadata": {
                        "mode": "STABILIZE",
                        "armed": false,
                        "configured_external_nav_source_set": "SRC1"
                    }
                },
                "/external_nav/status": {
                    "metadata": {
                        "ready": true
                    }
                },
                "/mavlink_external_nav/status": {
                    "metadata": {
                        "ready": true
                    }
                }
            }
        }))
        .expect("upstream")
    }

    #[test]
    fn doctor_chain_runs_preflight_prepare_common_and_task_doctor() {
        let temp = tempfile::tempdir().expect("tempdir");
        let summary = run_doctor_chain(
            &project(),
            &task_config(),
            &HealthyEnvironment,
            &StaticTopicProbe {
                upstream: upstream(),
            },
            DoctorChainInput {
                prepare_dry_run: true,
                allow_live_prepare: false,
                upstream_json: None,
                artifact_dir: Some(temp.path().to_path_buf()),
                summary_path: None,
            },
        )
        .expect("summary");

        assert!(summary.ok);
        assert!(summary.prepare_stopped);
        assert!(summary.prepare.as_ref().expect("prepare").dry_run);
        assert!(summary.common_doctor.is_some());
        assert!(summary.task_doctor.is_some());
        assert!(temp.path().join("preflight.json").is_file());
        assert!(temp.path().join("prepare.json").is_file());
        assert!(temp.path().join("common-doctor.json").is_file());
        assert!(temp.path().join("task-doctor.json").is_file());
        assert!(temp.path().join("summary.json").is_file());
    }

    #[test]
    fn doctor_chain_stops_before_prepare_when_preflight_blocks() {
        let mut project = project();
        project.runtime.backend = "docker".to_string();
        let temp = tempfile::tempdir().expect("tempdir");
        let summary = run_doctor_chain(
            &project,
            &task_config(),
            &HealthyEnvironment,
            &StaticTopicProbe {
                upstream: upstream(),
            },
            DoctorChainInput {
                prepare_dry_run: true,
                allow_live_prepare: false,
                upstream_json: None,
                artifact_dir: Some(temp.path().to_path_buf()),
                summary_path: None,
            },
        )
        .expect("summary");

        assert!(!summary.ok);
        assert!(summary.prepare.is_none());
        assert_eq!(
            summary.blockers,
            vec!["runtime_backend_must_be_process:docker"]
        );
    }

    #[test]
    fn doctor_chain_summary_json_contract_is_stable() {
        let temp = tempfile::tempdir().expect("tempdir");
        let summary = run_doctor_chain(
            &project(),
            &task_config(),
            &HealthyEnvironment,
            &StaticTopicProbe {
                upstream: upstream(),
            },
            DoctorChainInput {
                prepare_dry_run: true,
                allow_live_prepare: false,
                upstream_json: None,
                artifact_dir: Some(temp.path().to_path_buf()),
                summary_path: None,
            },
        )
        .expect("summary");

        insta::assert_json_snapshot!(json!({
            "ok": summary.ok,
            "blocked": summary.blocked,
            "blockers": summary.blockers,
            "task_name": summary.task_name,
            "prepare_stopped": summary.prepare_stopped,
            "preflight_ok": summary.preflight.ok,
            "prepare_claim": summary.prepare.as_ref().expect("prepare").prepare_claim,
            "prepare_dry_run": summary.prepare.as_ref().expect("prepare").dry_run,
            "prepare_service_count": summary.prepare.as_ref().expect("prepare").service_count,
            "common_mode": summary.common_doctor.as_ref().expect("common").common_state.mode,
            "task_required_mode": summary.task_doctor.as_ref().expect("task").task_specific["required_mode"],
        }), @r###"
        {
          "blocked": false,
          "blockers": [],
          "common_mode": "STABILIZE",
          "ok": true,
          "preflight_ok": true,
          "prepare_claim": "planned",
          "prepare_dry_run": true,
          "prepare_service_count": 4,
          "prepare_stopped": true,
          "task_name": "motor-debug",
          "task_required_mode": "GUIDED"
        }
        "###);
    }

    #[test]
    fn healthy_environment_smoke() {
        let evidence = CommandGroupEvidence {
            candidates: vec!["ros2".to_string()],
            found: true,
            selected: "ros2".to_string(),
            path: "/usr/bin/ros2".to_string(),
        };
        assert!(evidence.found);
    }
}
