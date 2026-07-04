use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tracing::{info, instrument};

use crate::config::{ProjectConfig, TaskConfig};
use crate::contracts;
use crate::workflows::task_doctor::{TopicEvidence, UpstreamEvidence};

#[derive(Debug, Clone)]
pub struct CommonDoctorInput {
    pub upstream_json: Option<PathBuf>,
    pub summary_path: Option<PathBuf>,
    pub upstream_output: Option<PathBuf>,
}

#[cfg_attr(test, mockall::automock)]
pub trait TopicProbe {
    fn collect(&self, project: &ProjectConfig, task_id: &str) -> Result<UpstreamEvidence>;
}

#[derive(Debug, Clone, Copy)]
pub struct HostTopicProbe;

#[derive(Debug, Clone, Serialize)]
pub struct CommonDoctorSummary {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub task_name: String,
    pub common_doctor_claim: String,
    pub arm_claim: String,
    pub takeoff_claim: String,
    pub landing_claim: String,
    pub companion_claim: String,
    pub checked_at: String,
    pub fcu_bridge_mode: String,
    pub upstream: UpstreamEvidence,
    pub common_state: CommonState,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct CommonState {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub gps_type: String,
    pub gps1_type: String,
    pub viso_type: String,
    pub ek3_src1: SourceSetState,
    pub ek3_src2: SourceSetState,
    pub gps_source_sets: Vec<String>,
    pub active_source_set: String,
    pub configured_external_nav_source_set: String,
    pub observed_ekf_source_set: String,
    pub observed_ekf_source_set_text: String,
    #[serde(default)]
    pub ekf_source_set_switch: BTreeMap<String, Value>,
    pub external_nav_ros_ready: bool,
    pub local_position_valid: Value,
    pub mode: String,
    pub armed: Value,
    #[serde(default)]
    pub bridge_metadata: BTreeMap<String, Value>,
    #[serde(default)]
    pub mavlink_external_nav_metadata: BTreeMap<String, Value>,
    #[serde(default)]
    pub external_nav_metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SourceSetState {
    pub posxy: String,
    pub velxy: String,
    pub velz: String,
    pub yaw: String,
    pub posz: String,
}

impl Default for SourceSetState {
    fn default() -> Self {
        Self {
            posxy: "unknown".to_string(),
            velxy: "unknown".to_string(),
            velz: "unknown".to_string(),
            yaw: "unknown".to_string(),
            posz: "unknown".to_string(),
        }
    }
}

impl TopicProbe for HostTopicProbe {
    fn collect(&self, project: &ProjectConfig, _task_id: &str) -> Result<UpstreamEvidence> {
        let output = match Command::new("ros2").args(["topic", "list", "-t"]).output() {
            Ok(output) => output,
            Err(error) if error.kind() == ErrorKind::NotFound => {
                return Ok(blocked_upstream("topic_probe_failed:ros2_not_found"));
            }
            Err(error) => return Ok(blocked_upstream(format!("topic_probe_failed:{error}"))),
        };
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Ok(blocked_upstream(format!(
                "topic_probe_failed:{}",
                stderr.trim()
            )));
        }
        Ok(build_upstream_from_topic_list(
            project,
            &String::from_utf8_lossy(&output.stdout),
        ))
    }
}

#[instrument(skip(project, task_config, input, probe))]
pub fn run_common_doctor(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    input: CommonDoctorInput,
    probe: &dyn TopicProbe,
) -> Result<CommonDoctorSummary> {
    let upstream = match input.upstream_json.as_deref() {
        Some(path) => load_upstream(path)?,
        None => probe.collect(project, &task_config.id)?,
    };
    if let Some(path) = input.upstream_output.as_deref() {
        write_json(path, &upstream, "common-doctor upstream evidence")?;
    }
    let summary = build_common_doctor_summary(project, task_config, upstream);
    let path = input
        .summary_path
        .unwrap_or_else(|| default_summary_path(project, &task_config.id));
    write_json(&path, &summary, "real common-doctor summary")?;
    write_contract_outputs(&path, project, &summary)?;
    info!(
        ok = summary.ok,
        blocked = summary.blocked,
        task = summary.task_name,
        path = %path.display(),
        "wrote real common-doctor summary"
    );
    Ok(summary)
}

fn write_contract_outputs(
    summary_path: &Path,
    project: &ProjectConfig,
    summary: &CommonDoctorSummary,
) -> Result<()> {
    let doctor = contracts::doctor_result(
        &summary.task_name,
        summary.ok,
        &summary.blockers,
        vec![
            ("required_topics_present", summary.upstream.ok),
            ("common_state_valid", summary.common_state.ok),
            (
                "external_nav_ready",
                summary.common_state.external_nav_ros_ready,
            ),
        ],
    );
    contracts::write_json(
        &summary_path.with_file_name("doctor_result.json"),
        &doctor,
        "real common-doctor result",
    )?;
    contracts::write_json(
        &summary_path.with_file_name("source_evidence.json"),
        &contracts::source_evidence(project),
        "real source evidence",
    )
}

pub fn build_common_doctor_summary(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    upstream: UpstreamEvidence,
) -> CommonDoctorSummary {
    let common_state = build_common_state(project, &upstream);
    let blockers = dedupe(
        upstream
            .blockers
            .iter()
            .cloned()
            .chain(common_state.blockers.iter().cloned())
            .collect(),
    );
    CommonDoctorSummary {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        blockers,
        task_name: task_config.id.clone(),
        common_doctor_claim: "evaluated".to_string(),
        arm_claim: "not_evaluated".to_string(),
        takeoff_claim: "not_evaluated".to_string(),
        landing_claim: "not_evaluated".to_string(),
        companion_claim: "not_started".to_string(),
        checked_at: utc_now(),
        fcu_bridge_mode: project.prepare.fcu_bridge_mode.clone(),
        upstream,
        common_state,
    }
}

pub fn build_upstream_from_topic_list(
    project: &ProjectConfig,
    topic_list: &str,
) -> UpstreamEvidence {
    let observed = parse_ros2_topic_list(topic_list);
    let mut required_topics = BTreeMap::new();
    let mut blockers = Vec::new();

    for topic in required_topics_for_project(project) {
        match observed.get(&topic) {
            Some(type_name) => {
                required_topics.insert(
                    topic,
                    TopicEvidence {
                        metadata: BTreeMap::new(),
                        present: Some(true),
                        fresh: Some(true),
                        type_name: Some(type_name.clone()),
                        frame_id: None,
                    },
                );
            }
            None => {
                blockers.push(format!("required_topic_missing:{topic}"));
                required_topics.insert(
                    topic,
                    TopicEvidence {
                        metadata: BTreeMap::new(),
                        present: Some(false),
                        fresh: Some(false),
                        type_name: None,
                        frame_id: None,
                    },
                );
            }
        }
    }

    for topic in observed.keys() {
        for pattern in &project.sources.forbidden_simulation_input_topics {
            if wildcard_match(pattern, topic) {
                blockers.push(format!("forbidden_simulation_topic_present:{topic}"));
            }
        }
    }
    blockers = dedupe(blockers);
    UpstreamEvidence {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        blockers,
        required_topics,
    }
}

fn build_common_state(project: &ProjectConfig, upstream: &UpstreamEvidence) -> CommonState {
    let status_metadata = topic_metadata(upstream, &project.task_doctor.fcu_status_topic);
    let bridge_metadata = topic_metadata(upstream, &project.task_doctor.fcu_bridge_state_topic);
    let mavlink_external_nav_metadata = topic_metadata(
        upstream,
        &project.common_doctor.mavlink_external_nav_status_topic,
    );
    let external_nav_metadata =
        topic_metadata(upstream, &project.common_doctor.external_nav_status_topic);
    let mut fcu_and_bridge_metadata = bridge_metadata.clone();
    fcu_and_bridge_metadata.extend(status_metadata.clone());

    let external_nav_ros_ready = bool_value(external_nav_metadata.get("ready"))
        || bool_value(external_nav_metadata.get("external_nav_yaw_ready"))
        || bool_value(mavlink_external_nav_metadata.get("ready"))
        || bool_value(mavlink_external_nav_metadata.get("external_nav_ready"));
    let active_source_set =
        string_metadata_value(&status_metadata, &["active_source_set"]).unwrap_or_default();
    let configured_external_nav_source_set =
        string_metadata_value(&status_metadata, &["configured_external_nav_source_set"])
            .or_else(|| {
                if active_source_set.is_empty() {
                    None
                } else {
                    Some(active_source_set.clone())
                }
            })
            .unwrap_or_else(|| "unknown".to_string());
    let observed_ekf_source_set =
        string_metadata_value(&status_metadata, &["observed_ekf_source_set"])
            .unwrap_or_else(|| "not_observed".to_string());
    let mode = string_metadata_value(&status_metadata, &["mode", "mode_name", "flight_mode"])
        .or_else(|| {
            number_metadata_value(&status_metadata, &["mode_number"]).and_then(arducopter_mode_name)
        })
        .unwrap_or_else(|| "unknown".to_string());
    let armed = bool_metadata_json(&status_metadata, &["armed"])
        .unwrap_or(Value::String("unknown".to_string()));
    let local_position_valid =
        bool_metadata_json(&fcu_and_bridge_metadata, &["local_position_valid"])
            .unwrap_or(Value::String("unknown".to_string()));

    let mut blockers = Vec::new();
    if configured_external_nav_source_set == "SRC2" && !external_nav_ros_ready {
        blockers.push("external_nav_or_gps_source_not_ready".to_string());
    }

    CommonState {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        blockers,
        gps_type: string_metadata_value(&status_metadata, &["GPS_TYPE", "gps_type"])
            .unwrap_or_else(|| "unknown".to_string()),
        gps1_type: string_metadata_value(&status_metadata, &["GPS1_TYPE", "gps1_type"])
            .unwrap_or_else(|| "unknown".to_string()),
        viso_type: string_metadata_value(&status_metadata, &["VISO_TYPE", "viso_type"])
            .unwrap_or_else(|| "unknown".to_string()),
        ek3_src1: source_set_state(&status_metadata, "EK3_SRC1"),
        ek3_src2: source_set_state(&status_metadata, "EK3_SRC2"),
        gps_source_sets: gps_source_sets(&status_metadata),
        active_source_set: if active_source_set.is_empty() {
            observed_ekf_source_set.clone()
        } else {
            active_source_set
        },
        configured_external_nav_source_set,
        observed_ekf_source_set,
        observed_ekf_source_set_text: string_metadata_value(
            &status_metadata,
            &["observed_ekf_source_set_text"],
        )
        .unwrap_or_default(),
        ekf_source_set_switch: object_metadata_value(
            &fcu_and_bridge_metadata,
            &["ekf_source_set_switch"],
        )
        .unwrap_or_default(),
        external_nav_ros_ready,
        local_position_valid,
        mode,
        armed,
        bridge_metadata,
        mavlink_external_nav_metadata,
        external_nav_metadata,
    }
}

fn required_topics_for_project(project: &ProjectConfig) -> Vec<String> {
    dedupe(
        project
            .sources
            .required_real_topics
            .iter()
            .cloned()
            .chain([
                project.task_doctor.fcu_status_topic.clone(),
                project.task_doctor.fcu_bridge_state_topic.clone(),
                project.common_doctor.external_nav_status_topic.clone(),
                project
                    .common_doctor
                    .mavlink_external_nav_status_topic
                    .clone(),
            ])
            .filter(|topic| !topic.is_empty())
            .collect(),
    )
}

fn parse_ros2_topic_list(source: &str) -> BTreeMap<String, String> {
    let mut topics = BTreeMap::new();
    for line in source
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
    {
        let Some((topic, rest)) = line.split_once(' ') else {
            topics.insert(line.to_string(), String::new());
            continue;
        };
        let type_name = rest
            .trim()
            .trim_start_matches('[')
            .trim_end_matches(']')
            .to_string();
        topics.insert(topic.to_string(), type_name);
    }
    topics
}

fn topic_metadata(upstream: &UpstreamEvidence, topic: &str) -> BTreeMap<String, Value> {
    upstream
        .required_topics
        .get(topic)
        .map(|evidence| evidence.metadata.clone())
        .unwrap_or_default()
}

fn source_set_state(metadata: &BTreeMap<String, Value>, prefix: &str) -> SourceSetState {
    SourceSetState {
        posxy: string_metadata_value(
            metadata,
            &[&format!("{prefix}_POSXY"), &format!("{prefix}_posxy")],
        )
        .unwrap_or_else(|| "unknown".to_string()),
        velxy: string_metadata_value(
            metadata,
            &[&format!("{prefix}_VELXY"), &format!("{prefix}_velxy")],
        )
        .unwrap_or_else(|| "unknown".to_string()),
        velz: string_metadata_value(
            metadata,
            &[&format!("{prefix}_VELZ"), &format!("{prefix}_velz")],
        )
        .unwrap_or_else(|| "unknown".to_string()),
        yaw: string_metadata_value(
            metadata,
            &[&format!("{prefix}_YAW"), &format!("{prefix}_yaw")],
        )
        .unwrap_or_else(|| "unknown".to_string()),
        posz: string_metadata_value(
            metadata,
            &[&format!("{prefix}_POSZ"), &format!("{prefix}_posz")],
        )
        .unwrap_or_else(|| "unknown".to_string()),
    }
}

fn gps_source_sets(metadata: &BTreeMap<String, Value>) -> Vec<String> {
    let mut sets = Vec::new();
    if source_set_uses_gps(metadata, "EK3_SRC1") {
        sets.push("SRC1".to_string());
    }
    if source_set_uses_gps(metadata, "EK3_SRC2") {
        sets.push("SRC2".to_string());
    }
    sets
}

fn source_set_uses_gps(metadata: &BTreeMap<String, Value>, prefix: &str) -> bool {
    ["POSXY", "VELXY", "VELZ", "POSZ"].iter().any(|field| {
        string_metadata_value(metadata, &[&format!("{prefix}_{field}")])
            .is_some_and(|value| value == "3" || value.eq_ignore_ascii_case("gps"))
    })
}

fn metadata_value<'a>(metadata: &'a BTreeMap<String, Value>, names: &[&str]) -> Option<&'a Value> {
    for name in names {
        if let Some(value) = metadata.get(*name) {
            return Some(value);
        }
    }
    if let Some(Value::Object(parameters)) = metadata.get("parameters") {
        for name in names {
            if let Some(value) = parameters.get(*name) {
                return Some(value);
            }
        }
    }
    None
}

fn string_metadata_value(metadata: &BTreeMap<String, Value>, names: &[&str]) -> Option<String> {
    metadata_value(metadata, names).and_then(string_value)
}

fn number_metadata_value(metadata: &BTreeMap<String, Value>, names: &[&str]) -> Option<i64> {
    metadata_value(metadata, names).and_then(|value| match value {
        Value::Number(number) => number.as_i64(),
        Value::String(text) => text.parse().ok(),
        _ => None,
    })
}

fn bool_metadata_json(metadata: &BTreeMap<String, Value>, names: &[&str]) -> Option<Value> {
    metadata_value(metadata, names).and_then(|value| match value {
        Value::Bool(value) => Some(Value::Bool(*value)),
        Value::Number(number) => Some(Value::Bool(number.as_i64().unwrap_or_default() != 0)),
        Value::String(text) => parse_bool(text).map(Value::Bool),
        _ => None,
    })
}

fn object_metadata_value(
    metadata: &BTreeMap<String, Value>,
    names: &[&str],
) -> Option<BTreeMap<String, Value>> {
    metadata_value(metadata, names).and_then(|value| match value {
        Value::Object(object) => Some(
            object
                .iter()
                .map(|(key, value)| (key.clone(), value.clone()))
                .collect(),
        ),
        _ => None,
    })
}

fn string_value(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => Some(text.clone()),
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(value) => Some(value.to_string()),
        Value::Null | Value::Array(_) | Value::Object(_) => None,
    }
}

fn bool_value(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(value)) => *value,
        Some(Value::Number(number)) => number.as_i64().unwrap_or_default() != 0,
        Some(Value::String(text)) => parse_bool(text).unwrap_or(false),
        _ => false,
    }
}

fn parse_bool(text: &str) -> Option<bool> {
    match text.trim().to_ascii_lowercase().as_str() {
        "true" | "1" | "yes" | "ready" | "ok" => Some(true),
        "false" | "0" | "no" | "not_ready" | "blocked" => Some(false),
        _ => None,
    }
}

fn arducopter_mode_name(mode_number: i64) -> Option<String> {
    let mode = match mode_number {
        0 => "STABILIZE",
        2 => "ALT_HOLD",
        3 => "AUTO",
        4 => "GUIDED",
        5 => "LOITER",
        6 => "RTL",
        9 => "LAND",
        11 => "DRIFT",
        13 => "SPORT",
        14 => "FLIP",
        15 => "AUTOTUNE",
        16 => "POSHOLD",
        17 => "BRAKE",
        18 => "THROW",
        19 => "AVOID_ADSB",
        20 => "GUIDED_NOGPS",
        21 => "SMART_RTL",
        22 => "FLOWHOLD",
        23 => "FOLLOW",
        24 => "ZIGZAG",
        25 => "SYSTEMID",
        26 => "AUTOROTATE",
        27 => "AUTO_RTL",
        _ => return None,
    };
    Some(mode.to_string())
}

fn load_upstream(path: &Path) -> Result<UpstreamEvidence> {
    let source = fs::read_to_string(path)
        .with_context(|| format!("read common-doctor upstream evidence {}", path.display()))?;
    match serde_json::from_str::<UpstreamEvidence>(&source) {
        Ok(upstream) => Ok(upstream),
        Err(upstream_error) => {
            let value = serde_json::from_str::<Value>(&source).with_context(|| {
                format!("parse common-doctor upstream evidence {}", path.display())
            })?;
            let Some(upstream) = value.get("upstream") else {
                return Err(upstream_error).with_context(|| {
                    format!("parse common-doctor upstream evidence {}", path.display())
                });
            };
            serde_json::from_value(upstream.clone())
                .with_context(|| format!("parse common-doctor summary upstream {}", path.display()))
        }
    }
}

fn blocked_upstream(blocker: impl Into<String>) -> UpstreamEvidence {
    UpstreamEvidence {
        ok: false,
        blocked: true,
        blockers: vec![blocker.into()],
        required_topics: BTreeMap::new(),
    }
}

fn write_json<T: Serialize>(path: &Path, value: &T, label: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create {label} dir {}", parent.display()))?;
    }
    fs::write(path, serde_json::to_string_pretty(value)?)
        .with_context(|| format!("write {label} {}", path.display()))
}

fn default_summary_path(project: &ProjectConfig, task_name: &str) -> PathBuf {
    project
        .paths
        .artifact_root
        .join("common-doctor")
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

fn wildcard_match(pattern: &str, value: &str) -> bool {
    if pattern == "*" {
        return true;
    }
    let mut remainder = value;
    let mut first = true;
    for part in pattern.split('*') {
        if part.is_empty() {
            continue;
        }
        if first && !pattern.starts_with('*') {
            let Some(stripped) = remainder.strip_prefix(part) else {
                return false;
            };
            remainder = stripped;
            first = false;
            continue;
        }
        let Some(index) = remainder.find(part) else {
            return false;
        };
        remainder = &remainder[index + part.len()..];
        first = false;
    }
    pattern.ends_with('*') || remainder.is_empty()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{
        CommonDoctorConfig, OrchestrationConfig, PathConfig, PreflightConfig, PrepareConfig,
        RuntimeConfig, SourceConfig, TaskDoctorConfig,
    };
    use serde_json::json;

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
                required_real_topics: vec!["/scan".to_string(), "/ap/v1/status".to_string()],
                forbidden_simulation_input_topics: vec!["/gazebo/*".to_string()],
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

    fn ready_upstream() -> UpstreamEvidence {
        serde_json::from_value(json!({
            "ok": true,
            "blocked": false,
            "blockers": [],
            "required_topics": {
                "/ap/v1/status": {
                    "metadata": {
                        "mode_number": 0,
                        "armed": false,
                        "local_position_valid": true,
                        "parameters": {
                            "GPS_TYPE": 0,
                            "GPS1_TYPE": 0,
                            "VISO_TYPE": 1,
                            "EK3_SRC1_POSXY": 6,
                            "EK3_SRC1_VELXY": 6,
                            "EK3_SRC1_YAW": 6,
                            "EK3_SRC1_POSZ": 1,
                            "EK3_SRC2_POSXY": 6,
                            "EK3_SRC2_VELXY": 6,
                            "EK3_SRC2_YAW": 6,
                            "EK3_SRC2_POSZ": 1
                        },
                        "configured_external_nav_source_set": "SRC2"
                    }
                },
                "/external_nav/status": {
                    "metadata": {
                        "ready": true
                    }
                },
                "/mavlink_external_nav/status": {
                    "metadata": {}
                }
            }
        }))
        .expect("upstream")
    }

    #[test]
    fn common_doctor_extracts_fcu_external_nav_state() {
        let summary = build_common_doctor_summary(&project(), &task_config(), ready_upstream());

        assert!(summary.ok);
        assert_eq!(summary.common_state.mode, "STABILIZE");
        assert_eq!(
            summary.common_state.configured_external_nav_source_set,
            "SRC2"
        );
        assert!(summary.common_state.external_nav_ros_ready);
        assert_eq!(summary.common_state.gps_type, "0");
        assert_eq!(summary.common_state.ek3_src1.posxy, "6");
    }

    #[test]
    fn common_doctor_blocks_src2_without_external_nav_ready() {
        let mut upstream = ready_upstream();
        upstream
            .required_topics
            .get_mut("/external_nav/status")
            .expect("external nav")
            .metadata
            .insert("ready".to_string(), Value::Bool(false));

        let summary = build_common_doctor_summary(&project(), &task_config(), upstream);

        assert!(!summary.ok);
        assert_eq!(
            summary.blockers,
            vec!["external_nav_or_gps_source_not_ready"]
        );
    }

    #[test]
    fn common_doctor_blocks_without_upstream_evidence() {
        let summary =
            build_common_doctor_summary(&project(), &task_config(), UpstreamEvidence::default());

        assert!(!summary.ok);
        assert_eq!(summary.blockers, vec!["upstream_evidence_missing"]);
        assert_eq!(summary.common_state.mode, "unknown");
    }

    #[test]
    fn common_doctor_topic_list_probe_builds_upstream_evidence() {
        let upstream = build_upstream_from_topic_list(
            &project(),
            "/scan [sensor_msgs/msg/LaserScan]\n/ap/v1/status [std_msgs/msg/String]\n/gazebo/model_states [gazebo_msgs/msg/ModelStates]\n",
        );

        assert!(!upstream.ok);
        assert_eq!(
            upstream.blockers,
            vec![
                "required_topic_missing:/navlab/mavlink/status",
                "required_topic_missing:/external_nav/status",
                "required_topic_missing:/mavlink_external_nav/status",
                "forbidden_simulation_topic_present:/gazebo/model_states"
            ]
        );
        assert_eq!(
            upstream.required_topics["/scan"].type_name.as_deref(),
            Some("sensor_msgs/msg/LaserScan")
        );
    }

    #[test]
    fn run_common_doctor_writes_summary_and_upstream_output() {
        let mut probe = MockTopicProbe::new();
        probe
            .expect_collect()
            .returning(|_, _| Ok(ready_upstream()));
        let temp = tempfile::tempdir().expect("tempdir");
        let summary_path = temp.path().join("summary.json");
        let upstream_path = temp.path().join("upstream.json");

        let summary = run_common_doctor(
            &project(),
            &task_config(),
            CommonDoctorInput {
                upstream_json: None,
                summary_path: Some(summary_path.clone()),
                upstream_output: Some(upstream_path.clone()),
            },
            &probe,
        )
        .expect("summary");

        assert!(summary.ok);
        assert!(summary_path.is_file());
        assert!(upstream_path.is_file());
    }

    #[test]
    fn common_doctor_summary_json_contract_is_stable() {
        let summary = build_common_doctor_summary(&project(), &task_config(), ready_upstream());

        insta::assert_json_snapshot!(summary, {
            ".checked_at" => "[checked_at]"
        }, @r###"
        {
          "ok": true,
          "blocked": false,
          "blockers": [],
          "task_name": "motor-debug",
          "common_doctor_claim": "evaluated",
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
                  "armed": false,
                  "configured_external_nav_source_set": "SRC2",
                  "local_position_valid": true,
                  "mode_number": 0,
                  "parameters": {
                    "EK3_SRC1_POSXY": 6,
                    "EK3_SRC1_POSZ": 1,
                    "EK3_SRC1_VELXY": 6,
                    "EK3_SRC1_YAW": 6,
                    "EK3_SRC2_POSXY": 6,
                    "EK3_SRC2_POSZ": 1,
                    "EK3_SRC2_VELXY": 6,
                    "EK3_SRC2_YAW": 6,
                    "GPS1_TYPE": 0,
                    "GPS_TYPE": 0,
                    "VISO_TYPE": 1
                  }
                },
                "present": null,
                "fresh": null,
                "type_name": null,
                "frame_id": null
              },
              "/external_nav/status": {
                "metadata": {
                  "ready": true
                },
                "present": null,
                "fresh": null,
                "type_name": null,
                "frame_id": null
              },
              "/mavlink_external_nav/status": {
                "metadata": {},
                "present": null,
                "fresh": null,
                "type_name": null,
                "frame_id": null
              }
            }
          },
          "common_state": {
            "ok": true,
            "blocked": false,
            "blockers": [],
            "gps_type": "0",
            "gps1_type": "0",
            "viso_type": "1",
            "ek3_src1": {
              "posxy": "6",
              "velxy": "6",
              "velz": "unknown",
              "yaw": "6",
              "posz": "1"
            },
            "ek3_src2": {
              "posxy": "6",
              "velxy": "6",
              "velz": "unknown",
              "yaw": "6",
              "posz": "1"
            },
            "gps_source_sets": [],
            "active_source_set": "not_observed",
            "configured_external_nav_source_set": "SRC2",
            "observed_ekf_source_set": "not_observed",
            "observed_ekf_source_set_text": "",
            "ekf_source_set_switch": {},
            "external_nav_ros_ready": true,
            "local_position_valid": true,
            "mode": "STABILIZE",
            "armed": false,
            "bridge_metadata": {},
            "mavlink_external_nav_metadata": {},
            "external_nav_metadata": {
              "ready": true
            }
          }
        }
        "###);
    }
}
