use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::Serialize;
use serde_json::{Value, json};
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tracing::{info, instrument};

use crate::config::{PrepareServiceConfig, ProjectConfig, TaskConfig};
use crate::contracts;
use crate::runtime::{ProcessBackend, RuntimeHandle, ServiceSpec};

const SIMULATION_TOKENS: &[&str] = &[
    "gazebo",
    "sitl",
    "gazebo-sensor",
    "/scan_ideal",
    "/sim/x2/status",
];

#[derive(Debug, Clone)]
pub struct PrepareInput {
    pub dry_run: Option<bool>,
    pub allow_live: bool,
    pub summary_path: Option<PathBuf>,
}

#[derive(Debug)]
pub struct PreparePhaseResult {
    pub summary: PrepareSummary,
    pub backend: ProcessBackend,
    pub handles: Vec<RuntimeHandle>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PrepareSummary {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub task_name: String,
    pub prepare_claim: String,
    pub companion_claim: String,
    pub checked_at: String,
    pub artifact_dir: String,
    pub process_log_dir: String,
    pub dry_run: bool,
    pub fcu_bridge_mode: FcuBridgeModeSummary,
    pub mavlink_router: MavlinkRouterSummary,
    pub geographiclib: GeographicLibSummary,
    pub service_plan: Vec<PrepareServicePlan>,
    pub started_services: Vec<StartedServiceSummary>,
    pub service_count: usize,
    pub readiness: ReadinessSummary,
}

#[derive(Debug, Clone, Serialize)]
pub struct FcuBridgeModeSummary {
    pub name: String,
    pub description: String,
    pub required_topics: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MavlinkRouterSummary {
    pub serial: String,
    pub baud: u32,
    pub local_endpoint: String,
    pub serial_provenance: SerialProvenance,
    pub endpoint_probe: Value,
}

#[derive(Debug, Clone, Serialize)]
pub struct SerialProvenance {
    pub ok: bool,
    pub source: String,
    pub value: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub blocker: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct GeographicLibSummary {
    pub geoid: String,
    pub system_path: String,
    pub system_present: bool,
    pub local_path: String,
    pub local_present: bool,
    pub env_data: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PrepareServicePlan {
    pub name: String,
    pub enabled: bool,
    pub required: bool,
    pub command: Vec<String>,
    pub cwd: String,
    pub env: BTreeMap<String, String>,
    pub startup_timeout_sec: f64,
    pub health_topics: Vec<String>,
    pub shutdown_policy: String,
    pub direct_serial_access_allowed: bool,
    pub log_path: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StartedServiceSummary {
    pub backend: String,
    pub service_name: String,
    pub identifier: String,
    pub command: Vec<String>,
    pub started_at: f64,
    pub log_path: String,
    pub pid: Option<u32>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ReadinessSummary {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub task_name: String,
    pub checked_at: String,
    pub required_topics: BTreeMap<String, RequiredTopicReadiness>,
    pub forbidden_simulation_topics: Vec<String>,
    pub skipped: bool,
    pub skip_reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RequiredTopicReadiness {
    pub present: bool,
    #[serde(rename = "type")]
    pub type_name: String,
    pub expected_type: String,
    pub fresh: bool,
    pub frame_id: String,
    pub expected_frame_id: String,
    pub source_claim: String,
    pub metadata: BTreeMap<String, Value>,
}

#[instrument(skip(project, task_config, input))]
pub fn run_prepare(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    input: PrepareInput,
) -> Result<PrepareSummary> {
    if input.allow_live && !input.dry_run.unwrap_or(project.prepare.dry_run) {
        let result = start_prepare_phase(project, task_config, input)?;
        let summary = result.summary.clone();
        stop_prepare_phase(&result)?;
        return Ok(summary);
    }
    let summary = build_prepare_summary(project, task_config, input.dry_run);
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
        "wrote real prepare summary"
    );
    Ok(summary)
}

pub fn start_prepare_phase(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    input: PrepareInput,
) -> Result<PreparePhaseResult> {
    let mut summary = build_prepare_summary_with_live_policy(
        project,
        task_config,
        input.dry_run,
        input.allow_live,
    );
    let backend = ProcessBackend::new(&summary.process_log_dir, summary.dry_run);
    let mut handles = Vec::new();

    if summary.ok && !summary.dry_run {
        for plan in &summary.service_plan {
            match backend.start_service(service_spec_from_plan(plan)) {
                Ok(handle) => {
                    summary
                        .started_services
                        .push(started_service_summary(&handle));
                    handles.push(handle);
                }
                Err(error) => {
                    summary.blockers.push(format!(
                        "prepare_service_start_failed:{}:{error}",
                        plan.name
                    ));
                    summary.blockers = dedupe(summary.blockers);
                    summary.ok = false;
                    summary.blocked = true;
                    break;
                }
            }
        }
    }

    let path = input
        .summary_path
        .unwrap_or_else(|| default_summary_path(project, &task_config.id));
    write_summary(&path, &summary)?;
    write_doctor_result(&path, &summary)?;
    info!(
        ok = summary.ok,
        blocked = summary.blocked,
        task = summary.task_name,
        started_services = summary.started_services.len(),
        path = %path.display(),
        "wrote real prepare phase summary"
    );
    Ok(PreparePhaseResult {
        summary,
        backend,
        handles,
    })
}

pub fn stop_prepare_phase(result: &PreparePhaseResult) -> Result<()> {
    for handle in result.handles.iter().rev() {
        result.backend.stop(handle, 5.0)?;
    }
    Ok(())
}

pub fn build_prepare_summary(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    dry_run_override: Option<bool>,
) -> PrepareSummary {
    build_prepare_summary_with_live_policy(project, task_config, dry_run_override, false)
}

fn build_prepare_summary_with_live_policy(
    project: &ProjectConfig,
    task_config: &TaskConfig,
    dry_run_override: Option<bool>,
    allow_live: bool,
) -> PrepareSummary {
    let dry_run = dry_run_override.unwrap_or(project.prepare.dry_run);
    let run_id = run_id();
    let artifact_dir = project.prepare.summary_artifact_dir.join(&run_id);
    let process_log_dir = project.prepare.process_log_dir.join(&run_id);
    let (mode_summary, mode_blockers) = fcu_bridge_mode_summary(project);
    let services = prepare_services(project, &task_config.id, &process_log_dir);
    let readiness = dry_run_readiness(project, task_config);
    let mut blockers = Vec::new();
    blockers.extend(mode_blockers);
    blockers.extend(validate_prepare_services(project, &services));
    if !dry_run && !allow_live {
        blockers.push("prepare_live_execution_requires_explicit_allow_live_or_dry_run".to_string());
    }
    blockers = dedupe(blockers);

    PrepareSummary {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        blockers,
        task_name: task_config.id.clone(),
        prepare_claim: if dry_run {
            "planned".to_string()
        } else if allow_live {
            "started".to_string()
        } else {
            "blocked_live_execution_requires_allow_live".to_string()
        },
        companion_claim: "not_started".to_string(),
        checked_at: utc_now(),
        artifact_dir: artifact_dir.display().to_string(),
        process_log_dir: process_log_dir.display().to_string(),
        dry_run,
        fcu_bridge_mode: mode_summary,
        mavlink_router: MavlinkRouterSummary {
            serial: project.prepare.mavlink_router_serial_port.clone(),
            baud: project.prepare.mavlink_router_baud,
            local_endpoint: project.prepare.mavlink_router_local_endpoint.clone(),
            serial_provenance: serial_provenance(project),
            endpoint_probe: json!({
                "ok": dry_run,
                "skipped": true,
                "reason": if dry_run { "dry_run" } else { "deferred_to_readiness_probe" }
            }),
        },
        geographiclib: geographiclib_summary(),
        service_count: services.len(),
        service_plan: services,
        started_services: Vec::new(),
        readiness,
    }
}

pub fn required_upstream_topics(project: &ProjectConfig, task_id: &str) -> Vec<String> {
    let mut topics = project.prepare.required_upstream_topics.clone();
    let (mode_summary, _) = fcu_bridge_mode_summary(project);
    topics.extend(mode_summary.required_topics);
    topics.extend([
        "/slam/odom".to_string(),
        "/navlab/slam/status".to_string(),
        project.prepare.fcu_bridge_state_topic.clone(),
    ]);
    topics.extend(project.prepare.external_nav_yaw_status_topics.clone());
    if project.prepare.height_rangefinder_required
        && matches!(
            task_id,
            "doctor" | "hover" | "exploration" | "scan-robustness"
        )
    {
        topics.extend([
            "/rangefinder/down/range".to_string(),
            "/rangefinder/down/status".to_string(),
        ]);
    }
    if task_id == "motor-debug" {
        topics.retain(|topic| {
            !matches!(
                topic.as_str(),
                "/rangefinder/down/range" | "/rangefinder/down/status"
            )
        });
    }
    dedupe(
        topics
            .into_iter()
            .filter(|topic| !topic.is_empty())
            .collect(),
    )
}

pub fn prepare_services(
    project: &ProjectConfig,
    task_id: &str,
    process_log_dir: &Path,
) -> Vec<PrepareServicePlan> {
    let selected = match project
        .prepare
        .fcu_bridge_mode
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "navlab_mavlink" => vec![
            "mavlink_router",
            "navlab_mavlink_bridge",
            "lidar",
            "slam",
            "rangefinder_bridge",
        ],
        _ => vec![
            "mavlink_router",
            "navlab_mavlink_bridge",
            "mavros",
            "lidar",
            "slam",
            "rangefinder_bridge",
        ],
    };
    selected
        .into_iter()
        .filter(|name| !(task_id == "motor-debug" && *name == "rangefinder_bridge"))
        .filter_map(|name| service_config(project, name).map(|service| (name, service)))
        .filter(|(_, service)| service.enabled)
        .map(|(name, service)| service_plan(name, service, process_log_dir))
        .collect()
}

pub fn service_spec_from_plan(plan: &PrepareServicePlan) -> ServiceSpec {
    ServiceSpec {
        name: plan.name.clone(),
        command: plan.command.clone(),
        image: None,
        env: plan.env.clone(),
        cwd: if plan.cwd.is_empty() {
            None
        } else {
            Some(PathBuf::from(&plan.cwd))
        },
        required: plan.required,
        log_path: Some(PathBuf::from(&plan.log_path)),
    }
}

fn started_service_summary(handle: &RuntimeHandle) -> StartedServiceSummary {
    StartedServiceSummary {
        backend: handle.backend.clone(),
        service_name: handle.service_name.clone(),
        identifier: handle.identifier.clone(),
        command: handle.command.clone(),
        started_at: handle.started_at,
        log_path: handle
            .log_path
            .as_ref()
            .map(|path| path.display().to_string())
            .unwrap_or_default(),
        pid: handle.pid,
    }
}

fn validate_prepare_services(
    project: &ProjectConfig,
    services: &[PrepareServicePlan],
) -> Vec<String> {
    let mut blockers = Vec::new();
    if !services
        .iter()
        .any(|service| service.name == "mavlink_router")
    {
        blockers.push("prepare_required_service_missing:mavlink_router".to_string());
    }
    let provenance = serial_provenance(project);
    if !provenance.ok {
        if let Some(blocker) = provenance.blocker {
            blockers.push(blocker);
        }
    }
    for service in services {
        if service.name == "companion" {
            blockers.push("prepare_must_not_start_companion".to_string());
        }
        if service.required && service.command.is_empty() {
            blockers.push(format!("prepare_service_command_missing:{}", service.name));
        }
        let command_text = service.command.join(" ").to_ascii_lowercase();
        for token in SIMULATION_TOKENS {
            if command_text.contains(token) {
                blockers.push(format!(
                    "prepare_service_uses_simulation_token:{}:{token}",
                    service.name
                ));
            }
        }
        let direct_serial = !project.prepare.mavlink_router_serial_port.is_empty()
            && service
                .command
                .iter()
                .any(|arg| arg.contains(&project.prepare.mavlink_router_serial_port));
        if service.name != "mavlink_router"
            && direct_serial
            && !service.direct_serial_access_allowed
        {
            blockers.push(format!(
                "prepare_service_direct_fcu_serial_forbidden:{}:{}",
                service.name, project.prepare.mavlink_router_serial_port
            ));
        }
    }
    dedupe(blockers)
}

fn fcu_bridge_mode_summary(project: &ProjectConfig) -> (FcuBridgeModeSummary, Vec<String>) {
    let name = project.prepare.fcu_bridge_mode.trim().to_ascii_lowercase();
    match name.as_str() {
        "navlab_mavlink" => (
            FcuBridgeModeSummary {
                name,
                description: "NavLab MAVLink router plus NavLab MAVLink bridge topics; no MAVROS or /ap/v1 DDS required.".to_string(),
                required_topics: vec![
                    "/navlab/mavlink/status".to_string(),
                    "/navlab/fcu/local_position_pose".to_string(),
                    "/mavlink_external_nav/status".to_string(),
                    "/external_nav/status".to_string(),
                    "/rangefinder/down/range".to_string(),
                    "/rangefinder/down/status".to_string(),
                ],
            },
            Vec::new(),
        ),
        other => (
            FcuBridgeModeSummary {
                name: other.to_string(),
                description: String::new(),
                required_topics: Vec::new(),
            },
            vec![format!(
                "fcu_bridge_mode_unknown:{other}:supported=navlab_mavlink"
            )],
        ),
    }
}

fn dry_run_readiness(project: &ProjectConfig, task_config: &TaskConfig) -> ReadinessSummary {
    let required_topics = required_upstream_topics(project, &task_config.id)
        .into_iter()
        .map(|topic| {
            let expected_type = expected_topic_types(project)
                .get(&topic)
                .cloned()
                .unwrap_or_default();
            let expected_frame_id = expected_topic_frames(project)
                .get(&topic)
                .cloned()
                .unwrap_or_default();
            (
                topic,
                RequiredTopicReadiness {
                    present: false,
                    type_name: String::new(),
                    expected_type,
                    fresh: false,
                    frame_id: String::new(),
                    expected_frame_id,
                    source_claim: String::new(),
                    metadata: BTreeMap::new(),
                },
            )
        })
        .collect();
    ReadinessSummary {
        ok: true,
        blocked: false,
        blockers: Vec::new(),
        task_name: task_config.id.clone(),
        checked_at: utc_now(),
        required_topics,
        forbidden_simulation_topics: project.prepare.forbidden_simulation_topics.clone(),
        skipped: true,
        skip_reason: "dry_run_plan_only".to_string(),
    }
}

fn expected_topic_types(project: &ProjectConfig) -> BTreeMap<String, String> {
    BTreeMap::from([
        ("/scan".to_string(), "sensor_msgs/msg/LaserScan".to_string()),
        ("/imu/data".to_string(), "sensor_msgs/msg/Imu".to_string()),
        ("/imu".to_string(), "sensor_msgs/msg/Imu".to_string()),
        ("/imu/status".to_string(), "std_msgs/msg/String".to_string()),
        ("/tf".to_string(), "tf2_msgs/msg/TFMessage".to_string()),
        (
            "/tf_static".to_string(),
            "tf2_msgs/msg/TFMessage".to_string(),
        ),
        (
            "/slam/odom".to_string(),
            "nav_msgs/msg/Odometry".to_string(),
        ),
        (
            "/navlab/slam/status".to_string(),
            "std_msgs/msg/String".to_string(),
        ),
        (
            project.common_doctor.external_nav_status_topic.clone(),
            "std_msgs/msg/String".to_string(),
        ),
        (
            project.prepare.fcu_bridge_state_topic.clone(),
            "std_msgs/msg/String".to_string(),
        ),
        (
            project
                .common_doctor
                .mavlink_external_nav_status_topic
                .clone(),
            "std_msgs/msg/String".to_string(),
        ),
        (
            "/rangefinder/down/range".to_string(),
            "sensor_msgs/msg/Range".to_string(),
        ),
        (
            "/rangefinder/down/status".to_string(),
            "std_msgs/msg/String".to_string(),
        ),
    ])
}

fn expected_topic_frames(_project: &ProjectConfig) -> BTreeMap<String, String> {
    BTreeMap::from([
        ("/scan".to_string(), "laser_frame".to_string()),
        ("/slam/odom".to_string(), "odom".to_string()),
    ])
}

fn serial_provenance(project: &ProjectConfig) -> SerialProvenance {
    let value = project
        .prepare
        .mavlink_router_serial_port
        .trim()
        .to_string();
    if value.is_empty() {
        return SerialProvenance {
            ok: false,
            source: "prepare.mavlink_router_serial_port".to_string(),
            value,
            blocker: Some("prepare_mavlink_router_serial_missing".to_string()),
        };
    }
    if value.contains("gazebo") || value.contains("sitl") {
        return SerialProvenance {
            ok: false,
            source: "prepare.mavlink_router_serial_port".to_string(),
            value: value.clone(),
            blocker: Some(format!("prepare_mavlink_router_serial_simulation:{value}")),
        };
    }
    SerialProvenance {
        ok: true,
        source: "prepare.mavlink_router_serial_port".to_string(),
        value,
        blocker: None,
    }
}

fn geographiclib_summary() -> GeographicLibSummary {
    let system = Path::new("/usr/share/GeographicLib/geoids/egm96-5.pgm");
    let local = Path::new("build/geographiclib/geoids/egm96-5.pgm");
    GeographicLibSummary {
        geoid: "egm96-5".to_string(),
        system_path: system.display().to_string(),
        system_present: system.exists(),
        local_path: local.display().to_string(),
        local_present: local.exists(),
        env_data: if local.exists() {
            "build/geographiclib".to_string()
        } else {
            String::new()
        },
    }
}

fn service_config<'a>(project: &'a ProjectConfig, name: &str) -> Option<&'a PrepareServiceConfig> {
    match name {
        "mavlink_router" => Some(&project.prepare.mavlink_router),
        "navlab_mavlink_bridge" => Some(&project.prepare.navlab_mavlink_bridge),
        "mavros" => Some(&project.prepare.mavros),
        "lidar" => Some(&project.prepare.lidar),
        "slam" => Some(&project.prepare.slam),
        "rangefinder_bridge" => Some(&project.prepare.rangefinder_bridge),
        _ => None,
    }
}

fn service_plan(
    name: &str,
    service: &PrepareServiceConfig,
    process_log_dir: &Path,
) -> PrepareServicePlan {
    PrepareServicePlan {
        name: name.to_string(),
        enabled: service.enabled,
        required: service.required,
        command: service.command.clone(),
        cwd: service.cwd.clone(),
        env: service.env.clone(),
        startup_timeout_sec: service.startup_timeout_sec,
        health_topics: service.health_topics.clone(),
        shutdown_policy: service.shutdown_policy.clone(),
        direct_serial_access_allowed: service.direct_serial_access_allowed,
        log_path: process_log_dir
            .join(format!("{name}.log"))
            .display()
            .to_string(),
    }
}

fn write_summary(path: &Path, summary: &PrepareSummary) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create prepare artifact dir {}", parent.display()))?;
    }
    fs::write(path, serde_json::to_string_pretty(summary)?)
        .with_context(|| format!("write real prepare summary {}", path.display()))
}

fn write_doctor_result(summary_path: &Path, summary: &PrepareSummary) -> Result<()> {
    let result = contracts::doctor_result(
        &summary.task_name,
        summary.ok,
        &summary.blockers,
        vec![
            ("service_plan_valid", summary.service_count > 0),
            (
                "fcu_bridge_mode_valid",
                summary.fcu_bridge_mode.name == "navlab_mavlink",
            ),
            ("readiness_plan_valid", summary.readiness.ok),
        ],
    );
    contracts::write_json(
        &summary_path.with_file_name("doctor_result.json"),
        &result,
        "real prepare doctor result",
    )
}

fn default_summary_path(project: &ProjectConfig, task_name: &str) -> PathBuf {
    project
        .paths
        .artifact_root
        .join("prepare")
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

    fn task_config(id: &str) -> TaskConfig {
        TaskConfig {
            id: id.to_string(),
            family: "real".to_string(),
            description: "test".to_string(),
            capabilities: vec![],
            task: BTreeMap::new(),
            safety: BTreeMap::new(),
        }
    }

    #[test]
    fn prepare_dry_run_plans_navlab_mavlink_services() {
        let summary = build_prepare_summary(&project(), &task_config("hover"), Some(true));

        assert!(summary.ok);
        assert_eq!(summary.prepare_claim, "planned");
        assert_eq!(summary.service_count, 5);
        assert_eq!(summary.service_plan[0].name, "mavlink_router");
        assert!(
            summary
                .readiness
                .required_topics
                .contains_key("/rangefinder/down/range")
        );
    }

    #[test]
    fn prepare_motor_debug_omits_rangefinder_bridge_and_topics() {
        let summary = build_prepare_summary(&project(), &task_config("motor-debug"), Some(true));

        assert!(summary.ok);
        assert_eq!(summary.service_count, 4);
        assert!(
            !summary
                .service_plan
                .iter()
                .any(|service| service.name == "rangefinder_bridge")
        );
        assert!(
            !summary
                .readiness
                .required_topics
                .contains_key("/rangefinder/down/range")
        );
    }

    #[test]
    fn prepare_live_execution_is_fail_closed_until_process_backend_migrates() {
        let summary = build_prepare_summary(&project(), &task_config("motor-debug"), Some(false));

        assert!(!summary.ok);
        assert_eq!(
            summary.blockers,
            vec!["prepare_live_execution_requires_explicit_allow_live_or_dry_run"]
        );
    }

    #[test]
    fn prepare_blocks_service_simulation_tokens() {
        let mut project = project();
        project.prepare.lidar.command = vec![
            "ros2".to_string(),
            "launch".to_string(),
            "gazebo".to_string(),
        ];

        let summary = build_prepare_summary(&project, &task_config("hover"), Some(true));

        assert!(!summary.ok);
        assert!(
            summary
                .blockers
                .contains(&"prepare_service_uses_simulation_token:lidar:gazebo".to_string())
        );
    }

    #[test]
    fn prepare_service_plan_maps_to_process_service_spec() {
        let summary = build_prepare_summary(&project(), &task_config("motor-debug"), Some(true));
        let spec = service_spec_from_plan(&summary.service_plan[0]);

        assert_eq!(spec.name, "mavlink_router");
        assert_eq!(spec.command[0], "mavlink-routerd");
        assert!(spec.image.is_none());
        assert!(spec.required);
        assert!(
            spec.log_path
                .as_ref()
                .expect("log path")
                .ends_with("mavlink_router.log")
        );
        spec.validate_for_process().expect("valid process spec");
    }

    #[test]
    fn prepare_live_phase_starts_and_stops_process_backend_services() {
        let mut project = project();
        project.prepare.mavlink_router.command = vec![
            "sh".to_string(),
            "-c".to_string(),
            "printf 'ready\\n'; sleep 30".to_string(),
        ];
        project.prepare.navlab_mavlink_bridge.enabled = false;
        project.prepare.lidar.enabled = false;
        project.prepare.slam.enabled = false;
        project.prepare.rangefinder_bridge.enabled = false;
        let temp = tempfile::tempdir().expect("tempdir");

        let result = start_prepare_phase(
            &project,
            &task_config("motor-debug"),
            PrepareInput {
                dry_run: Some(false),
                allow_live: true,
                summary_path: Some(temp.path().join("summary.json")),
            },
        )
        .expect("phase");

        assert!(result.summary.ok);
        assert_eq!(result.summary.prepare_claim, "started");
        assert_eq!(result.summary.started_services.len(), 1);
        assert_eq!(result.handles.len(), 1);
        assert!(temp.path().join("summary.json").is_file());
        stop_prepare_phase(&result).expect("stop");
    }

    #[test]
    fn prepare_summary_json_contract_is_stable() {
        let summary = build_prepare_summary(&project(), &task_config("motor-debug"), Some(true));

        insta::assert_json_snapshot!(summary, {
            ".checked_at" => "[checked_at]",
            ".readiness.checked_at" => "[checked_at]",
            ".artifact_dir" => "[artifact_dir]",
            ".process_log_dir" => "[process_log_dir]",
            ".service_plan[].log_path" => "[log_path]",
            ".geographiclib.system_present" => "[system_present]",
            ".geographiclib.local_present" => "[local_present]",
            ".geographiclib.env_data" => "[env_data]"
        }, @r###"
        {
          "ok": true,
          "blocked": false,
          "blockers": [],
          "task_name": "motor-debug",
          "prepare_claim": "planned",
          "companion_claim": "not_started",
          "checked_at": "[checked_at]",
          "artifact_dir": "[artifact_dir]",
          "process_log_dir": "[process_log_dir]",
          "dry_run": true,
          "fcu_bridge_mode": {
            "name": "navlab_mavlink",
            "description": "NavLab MAVLink router plus NavLab MAVLink bridge topics; no MAVROS or /ap/v1 DDS required.",
            "required_topics": [
              "/navlab/mavlink/status",
              "/navlab/fcu/local_position_pose",
              "/mavlink_external_nav/status",
              "/external_nav/status",
              "/rangefinder/down/range",
              "/rangefinder/down/status"
            ]
          },
          "mavlink_router": {
            "serial": "/dev/ttyUSB1",
            "baud": 115200,
            "local_endpoint": "127.0.0.1:14550",
            "serial_provenance": {
              "ok": true,
              "source": "prepare.mavlink_router_serial_port",
              "value": "/dev/ttyUSB1"
            },
            "endpoint_probe": {
              "ok": true,
              "reason": "dry_run",
              "skipped": true
            }
          },
          "geographiclib": {
            "geoid": "egm96-5",
            "system_path": "/usr/share/GeographicLib/geoids/egm96-5.pgm",
            "system_present": "[system_present]",
            "local_path": "build/geographiclib/geoids/egm96-5.pgm",
            "local_present": "[local_present]",
            "env_data": "[env_data]"
          },
          "service_plan": [
            {
              "name": "mavlink_router",
              "enabled": true,
              "required": true,
              "command": [
                "mavlink-routerd",
                "-e",
                "127.0.0.1:14550",
                "/dev/ttyUSB1:115200"
              ],
              "cwd": "",
              "env": {},
              "startup_timeout_sec": 8.0,
              "health_topics": [],
              "shutdown_policy": "stop_on_wrapper_exit",
              "direct_serial_access_allowed": false,
              "log_path": "[log_path]"
            },
            {
              "name": "navlab_mavlink_bridge",
              "enabled": true,
              "required": true,
              "command": [
                "uv",
                "run",
                "--project",
                "orchestration",
                "python",
                "-m",
                "navlab.real.companion.nodes.mavlink_bridge",
                "--ros-distro",
                "humble",
                "--mavlink-endpoint",
                "tcp:127.0.0.1:14550"
              ],
              "cwd": "",
              "env": {},
              "startup_timeout_sec": 8.0,
              "health_topics": [
                "/navlab/mavlink/status",
                "/navlab/fcu/local_position_pose",
                "/mavlink_external_nav/status",
                "/imu/data",
                "/imu/status"
              ],
              "shutdown_policy": "stop_on_wrapper_exit",
              "direct_serial_access_allowed": false,
              "log_path": "[log_path]"
            },
            {
              "name": "lidar",
              "enabled": true,
              "required": true,
              "command": [
                "bash",
                "-lc",
                "source /opt/ros/humble/setup.bash && source install/setup.bash && PYTHONPATH=.:$PYTHONPATH /usr/bin/python3 -m navlab.real.companion.nodes.ydlidar_x2_scan --port /dev/ttyUSB0 --baud 115200 --scan-topic /scan --frame-id laser_frame"
              ],
              "cwd": "",
              "env": {},
              "startup_timeout_sec": 8.0,
              "health_topics": [
                "/scan"
              ],
              "shutdown_policy": "stop_on_wrapper_exit",
              "direct_serial_access_allowed": false,
              "log_path": "[log_path]"
            },
            {
              "name": "slam",
              "enabled": true,
              "required": true,
              "command": [
                "ros2",
                "launch",
                "navlab_slam_bringup",
                "navlab_slam_bringup.launch.py",
                "use_sim_time:=false",
                "launch_fake_odom:=false",
                "launch_cartographer_backend:=true",
                "publish_placeholder_odom:=false",
                "cartographer_configuration_basename:=navlab_cartographer_2d_real.lua",
                "scan_topic:=/scan",
                "imu_source_topic:=/imu/data",
                "imu_topic:=/imu",
                "cartographer_odometry_topic:=/cartographer/odometry_input",
                "odom_topic:=/slam/odom",
                "external_nav_input_odom_topic:=/slam/odom",
                "require_imu_for_external_nav:=false",
                "require_height_for_external_nav:=false",
                "laser_frame:=laser_frame",
                "imu_frame:=imu_link",
                "base_frame:=base_link"
              ],
              "cwd": "",
              "env": {},
              "startup_timeout_sec": 8.0,
              "health_topics": [
                "/imu",
                "/slam/odom",
                "/navlab/slam/status",
                "/external_nav/status"
              ],
              "shutdown_policy": "stop_on_wrapper_exit",
              "direct_serial_access_allowed": false,
              "log_path": "[log_path]"
            }
          ],
          "started_services": [],
          "service_count": 4,
          "readiness": {
            "ok": true,
            "blocked": false,
            "blockers": [],
            "task_name": "motor-debug",
            "checked_at": "[checked_at]",
            "required_topics": {
              "/external_nav/status": {
                "present": false,
                "type": "",
                "expected_type": "std_msgs/msg/String",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/imu": {
                "present": false,
                "type": "",
                "expected_type": "sensor_msgs/msg/Imu",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/imu/data": {
                "present": false,
                "type": "",
                "expected_type": "sensor_msgs/msg/Imu",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/mavlink_external_nav/status": {
                "present": false,
                "type": "",
                "expected_type": "std_msgs/msg/String",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/navlab/fcu/local_position_pose": {
                "present": false,
                "type": "",
                "expected_type": "",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/navlab/mavlink/status": {
                "present": false,
                "type": "",
                "expected_type": "std_msgs/msg/String",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/navlab/slam/status": {
                "present": false,
                "type": "",
                "expected_type": "std_msgs/msg/String",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/scan": {
                "present": false,
                "type": "",
                "expected_type": "sensor_msgs/msg/LaserScan",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "laser_frame",
                "source_claim": "",
                "metadata": {}
              },
              "/slam/odom": {
                "present": false,
                "type": "",
                "expected_type": "nav_msgs/msg/Odometry",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "odom",
                "source_claim": "",
                "metadata": {}
              },
              "/tf": {
                "present": false,
                "type": "",
                "expected_type": "tf2_msgs/msg/TFMessage",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              },
              "/tf_static": {
                "present": false,
                "type": "",
                "expected_type": "tf2_msgs/msg/TFMessage",
                "fresh": false,
                "frame_id": "",
                "expected_frame_id": "",
                "source_claim": "",
                "metadata": {}
              }
            },
            "forbidden_simulation_topics": [
              "/gazebo/*",
              "/scan_ideal",
              "/sim/x2/status",
              "/rangefinder/down/scan_ideal"
            ],
            "skipped": true,
            "skip_reason": "dry_run_plan_only"
          }
        }
        "###);
    }
}
