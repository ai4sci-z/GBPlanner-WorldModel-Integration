use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tracing::{info, instrument};

use crate::config::{ProjectConfig, TaskConfig};
use crate::contracts;

#[derive(Debug, Clone)]
pub struct TaskDoctorInput {
    pub upstream_json: Option<PathBuf>,
    pub summary_path: Option<PathBuf>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TopicEvidence {
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
    #[serde(default)]
    pub present: Option<bool>,
    #[serde(default)]
    pub fresh: Option<bool>,
    #[serde(default)]
    pub type_name: Option<String>,
    #[serde(default)]
    pub frame_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct UpstreamEvidence {
    #[serde(default)]
    pub ok: bool,
    #[serde(default)]
    pub blocked: bool,
    #[serde(default)]
    pub blockers: Vec<String>,
    #[serde(default)]
    pub required_topics: BTreeMap<String, TopicEvidence>,
}

impl Default for UpstreamEvidence {
    fn default() -> Self {
        Self {
            ok: false,
            blocked: true,
            blockers: vec!["upstream_evidence_missing".to_string()],
            required_topics: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct TaskDoctorSummary {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub task_name: String,
    pub task_doctor_claim: String,
    pub arm_claim: String,
    pub takeoff_claim: String,
    pub landing_claim: String,
    pub companion_claim: String,
    pub checked_at: String,
    pub fcu_bridge_mode: String,
    pub upstream: UpstreamEvidence,
    pub task_specific: Value,
}

#[instrument(skip(project, task_config, input))]
pub fn run_task_doctor(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    input: TaskDoctorInput,
) -> Result<TaskDoctorSummary> {
    let upstream = match input.upstream_json.as_deref() {
        Some(path) => load_upstream(path)?,
        None => UpstreamEvidence::default(),
    };
    let summary = build_task_doctor_summary(project, task_config, upstream);
    let path = input
        .summary_path
        .unwrap_or_else(|| default_summary_path(project, &task_config.id));
    write_summary(&path, &summary)?;
    write_doctor_result(&path, &summary)?;
    info!(
        ok = summary.ok,
        blocked = summary.blocked,
        task = summary.task_name,
        path = %path.display(),
        "wrote real task-doctor summary"
    );
    Ok(summary)
}

fn write_doctor_result(summary_path: &Path, summary: &TaskDoctorSummary) -> Result<()> {
    let result = contracts::doctor_result(
        &summary.task_name,
        summary.ok,
        &summary.blockers,
        vec![
            ("upstream_evidence_ok", summary.upstream.ok),
            ("task_specific_evaluated", true),
            ("guided_gate_deferred_to_run", true),
        ],
    );
    contracts::write_json(
        &summary_path.with_file_name("doctor_result.json"),
        &result,
        "real task-doctor result",
    )
}

pub fn build_task_doctor_summary(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    upstream: UpstreamEvidence,
) -> TaskDoctorSummary {
    let task_specific = build_task_specific(project, task_config, &upstream);
    let mut blockers = upstream.blockers.clone();
    if let Some(items) = task_specific.get("blockers").and_then(Value::as_array) {
        blockers.extend(items.iter().filter_map(Value::as_str).map(str::to_string));
    }
    blockers = dedupe(blockers);

    TaskDoctorSummary {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        blockers,
        task_name: task_config.id.clone(),
        task_doctor_claim: "evaluated".to_string(),
        arm_claim: "not_evaluated".to_string(),
        takeoff_claim: "not_evaluated".to_string(),
        landing_claim: "not_evaluated".to_string(),
        companion_claim: "not_started".to_string(),
        checked_at: utc_now(),
        fcu_bridge_mode: project.prepare.fcu_bridge_mode.clone(),
        upstream,
        task_specific,
    }
}

fn build_task_specific(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    upstream: &UpstreamEvidence,
) -> Value {
    match task_config.id.as_str() {
        "motor-debug" => build_motor_debug_task_doctor(project, upstream),
        "hover" => build_hover_task_doctor(project, upstream),
        task_name => json!({
            "ok": true,
            "blocked": false,
            "blockers": [],
            "skipped": true,
            "reason": format!("task_not_registered:unknown real task doctor spec '{task_name}'")
        }),
    }
}

fn build_motor_debug_task_doctor(project: &ProjectConfig, upstream: &UpstreamEvidence) -> Value {
    let metadata = task_fcu_status_metadata(project, upstream);
    let current_mode = metadata
        .get("mode")
        .or_else(|| metadata.get("mode_name"))
        .or_else(|| metadata.get("flight_mode"))
        .and_then(Value::as_str)
        .map(str::to_ascii_uppercase)
        .unwrap_or_else(|| "unknown".to_string());
    json!({
        "ok": true,
        "blocked": false,
        "blockers": [],
        "required_mode": "GUIDED",
        "guided_gate": "run_stage",
        "mode_switch_claim": "deferred_to_motor_debug_run",
        "current_fcu_mode": current_mode,
        "guided_mode": "deferred_to_run"
    })
}

fn build_hover_task_doctor(project: &ProjectConfig, upstream: &UpstreamEvidence) -> Value {
    let slam_odom = topic_ready(upstream, "/slam/odom");
    let external_nav = topic_ready(
        upstream,
        project.common_doctor.external_nav_status_topic.as_str(),
    );
    let mavlink_external_nav = topic_ready(
        upstream,
        project
            .common_doctor
            .mavlink_external_nav_status_topic
            .as_str(),
    );
    let rangefinder_range = topic_ready(upstream, "/rangefinder/down/range");
    let rangefinder_status = topic_ready(upstream, "/rangefinder/down/status");
    let fcu_status = topic_ready(upstream, project.task_doctor.fcu_status_topic.as_str())
        || topic_ready(
            upstream,
            project.task_doctor.fcu_bridge_state_topic.as_str(),
        );
    let mut blockers = Vec::new();
    if !slam_odom {
        blockers.push("real_hover_slam_odom_not_ready");
    }
    if !external_nav {
        blockers.push("real_hover_external_nav_not_ready");
    }
    if !mavlink_external_nav {
        blockers.push("real_hover_mavlink_external_nav_not_ready");
    }
    if !rangefinder_range || !rangefinder_status {
        blockers.push("real_hover_rangefinder_not_ready");
    }
    if !fcu_status {
        blockers.push("real_hover_fcu_status_not_ready");
    }
    json!({
        "ok": blockers.is_empty(),
        "blocked": !blockers.is_empty(),
        "blockers": blockers,
        "required_mode": "GUIDED",
        "guided_gate": "run_stage",
        "takeoff_gate": "run_stage",
        "landing_gate": "run_stage",
        "completion_definition": {
            "primary": "mavlink_external_nav_and_fcu_local_position",
            "secondary": "official_dds_pose_if_available",
            "gate_policy": "mavlink_external_nav_required_official_dds_crosscheck"
        },
        "required_evidence": {
            "slam_odom_ready": slam_odom,
            "external_nav_ready": external_nav,
            "mavlink_external_nav_ready": mavlink_external_nav,
            "rangefinder_ready": rangefinder_range && rangefinder_status,
            "fcu_status_ready": fcu_status
        },
        "sim_dependency_claim": "forbidden",
        "flight_claim": "not_started"
    })
}

fn topic_ready(upstream: &UpstreamEvidence, topic_name: &str) -> bool {
    upstream
        .required_topics
        .get(topic_name)
        .is_some_and(|topic| topic.present.unwrap_or(true) && topic.fresh.unwrap_or(true))
}

fn task_fcu_status_metadata(
    project: &ProjectConfig,
    upstream: &UpstreamEvidence,
) -> BTreeMap<String, Value> {
    if let Some(topic) = upstream
        .required_topics
        .get(project.task_doctor.fcu_status_topic.as_str())
    {
        if !topic.metadata.is_empty() {
            return topic.metadata.clone();
        }
    }
    upstream
        .required_topics
        .get(project.task_doctor.fcu_bridge_state_topic.as_str())
        .map(|topic| topic.metadata.clone())
        .unwrap_or_default()
}

fn load_upstream(path: &Path) -> Result<UpstreamEvidence> {
    let source = fs::read_to_string(path)
        .with_context(|| format!("read upstream evidence {}", path.display()))?;
    serde_json::from_str(&source)
        .with_context(|| format!("parse upstream evidence {}", path.display()))
}

fn write_summary(path: &Path, summary: &TaskDoctorSummary) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create task-doctor artifact dir {}", parent.display()))?;
    }
    fs::write(path, serde_json::to_string_pretty(summary)?)
        .with_context(|| format!("write real task-doctor summary {}", path.display()))
}

fn default_summary_path(project: &ProjectConfig, task_name: &str) -> PathBuf {
    project
        .paths
        .artifact_root
        .join("task-doctor")
        .join(run_id())
        .join(task_name)
        .join("summary.json")
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
    let mut seen = BTreeSet::new();
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
        CommonDoctorConfig, OrchestrationConfig, PathConfig, PreflightConfig, PrepareConfig,
        RuntimeConfig, SourceConfig, TaskDoctorConfig,
    };

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
            preflight: PreflightConfig::default(),
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

    fn hover_task_config() -> TaskConfig {
        TaskConfig {
            id: "hover".to_string(),
            family: "real".to_string(),
            description: "hover".to_string(),
            capabilities: vec![],
            task: BTreeMap::new(),
            safety: BTreeMap::new(),
        }
    }

    #[test]
    fn motor_debug_task_doctor_uses_fcu_status_metadata() {
        let upstream: UpstreamEvidence = serde_json::from_value(json!({
            "ok": true,
            "blocked": false,
            "blockers": [],
            "required_topics": {
                "/ap/v1/status": {
                    "metadata": {
                        "mode": "STABILIZE",
                        "armed": false
                    }
                }
            }
        }))
        .expect("upstream");

        let summary = build_task_doctor_summary(&project(), &task_config(), upstream);

        assert!(summary.ok);
        assert_eq!(summary.task_specific["current_fcu_mode"], "STABILIZE");
        assert_eq!(summary.task_specific["guided_gate"], "run_stage");
    }

    #[test]
    fn task_doctor_blocks_without_upstream_evidence() {
        let summary =
            build_task_doctor_summary(&project(), &task_config(), UpstreamEvidence::default());

        assert!(!summary.ok);
        assert_eq!(summary.blockers, vec!["upstream_evidence_missing"]);
        assert_eq!(summary.task_specific["current_fcu_mode"], "unknown");
    }

    #[test]
    fn hover_task_doctor_blocks_without_runtime_evidence() {
        let summary = build_task_doctor_summary(
            &project(),
            &hover_task_config(),
            UpstreamEvidence {
                ok: true,
                blocked: false,
                blockers: Vec::new(),
                required_topics: BTreeMap::new(),
            },
        );

        assert!(!summary.ok);
        assert_eq!(
            summary.task_specific["blockers"][0],
            "real_hover_slam_odom_not_ready"
        );
        assert_eq!(
            summary.task_specific["completion_definition"]["gate_policy"],
            "mavlink_external_nav_required_official_dds_crosscheck"
        );
    }

    #[test]
    fn hover_task_doctor_accepts_required_real_evidence_shape() {
        let upstream: UpstreamEvidence = serde_json::from_value(json!({
            "ok": true,
            "blocked": false,
            "blockers": [],
            "required_topics": {
                "/slam/odom": {"present": true, "fresh": true},
                "/external_nav/status": {"present": true, "fresh": true},
                "/mavlink_external_nav/status": {"present": true, "fresh": true},
                "/rangefinder/down/range": {"present": true, "fresh": true},
                "/rangefinder/down/status": {"present": true, "fresh": true},
                "/ap/v1/status": {"present": true, "fresh": true}
            }
        }))
        .expect("upstream");

        let summary = build_task_doctor_summary(&project(), &hover_task_config(), upstream);

        assert!(summary.ok);
        assert_eq!(summary.task_name, "hover");
        assert_eq!(
            summary.task_specific["required_evidence"]["mavlink_external_nav_ready"],
            true
        );
        assert_eq!(summary.task_specific["sim_dependency_claim"], "forbidden");
    }

    #[test]
    fn task_doctor_summary_json_contract_is_stable() {
        let upstream: UpstreamEvidence = serde_json::from_value(json!({
            "ok": true,
            "blocked": false,
            "blockers": [],
            "required_topics": {
                "/ap/v1/status": {
                    "metadata": {
                        "mode": "STABILIZE"
                    }
                }
            }
        }))
        .expect("upstream");
        let summary = build_task_doctor_summary(&project(), &task_config(), upstream);

        insta::assert_json_snapshot!(summary, {
            ".checked_at" => "[checked_at]"
        }, @r###"
        {
          "ok": true,
          "blocked": false,
          "blockers": [],
          "task_name": "motor-debug",
          "task_doctor_claim": "evaluated",
          "arm_claim": "not_evaluated",
          "takeoff_claim": "not_evaluated",
          "landing_claim": "not_evaluated",
          "companion_claim": "not_started",
          "checked_at": "[checked_at]",
          "fcu_bridge_mode": "navlab_mavlink",
          "upstream": {
            "ok": true,
            "blocked": false,
            "blockers": [],
            "required_topics": {
              "/ap/v1/status": {
                "metadata": {
                  "mode": "STABILIZE"
                },
                "present": null,
                "fresh": null,
                "type_name": null,
                "frame_id": null
              }
            }
          },
          "task_specific": {
            "blocked": false,
            "blockers": [],
            "current_fcu_mode": "STABILIZE",
            "guided_gate": "run_stage",
            "guided_mode": "deferred_to_run",
            "mode_switch_claim": "deferred_to_motor_debug_run",
            "ok": true,
            "required_mode": "GUIDED"
          }
        }
        "###);
    }
}
