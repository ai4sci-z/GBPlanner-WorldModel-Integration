use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use serde::Serialize;
use serde_json::{Value, json};
use time::OffsetDateTime;
use tracing::{info, instrument, warn};

use crate::config::{ProjectConfig, TaskConfig};
use crate::contracts;
use crate::tasks::{RealTask, RunOptions};
use crate::ui::{print_key_value, print_title};
use crate::workflows::{
    NavLabFsmArtifactRef, NavLabFsmSummary, NavLabFsmTransition, NavLabFsmTransitionInput,
    RealWorkflowSummary, dry_run_workflow_with_runtime_claim, navlab_fsm_state, navlab_fsm_summary,
    navlab_fsm_transition, runtime_workflow, workflow_from_doctor_chain_with_runtime,
    write_navlab_fsm_artifact,
};

pub const REAL_HOVER_SUMMARY_SCHEMA_VERSION: &str = "navlab.real.hover.summary.v1";

#[derive(Debug, Clone, Serialize)]
pub struct RealHoverPlan {
    pub task_id: String,
    pub target_altitude_m: f64,
    pub hover_hold_sec: f64,
    pub hover_health_stable_sec: f64,
    pub hover_health_max_wait_sec: f64,
    pub hover_span_target_m: f64,
    pub hover_span_hard_cap_m: f64,
    pub max_altitude_error_m: f64,
    pub completion_definition: HoverCompletionDefinition,
    pub safety: RealHoverSafety,
    pub claim: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct HoverCompletionDefinition {
    pub primary: String,
    pub secondary: String,
    pub gate_policy: String,
    pub required_evidence: Vec<String>,
    pub review_only_evidence: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RealHoverSafety {
    pub confirm_manual_takeover: bool,
    pub confirm_kill_switch: bool,
    pub confirm_safe_area: bool,
    pub confirm_props_installed: bool,
    pub props_installed_claim: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RealHoverOperatorSafetyEvaluation {
    pub ok: bool,
    pub blocked: bool,
    pub manual_takeover_confirmed: bool,
    pub kill_switch_confirmed: bool,
    pub safe_area_confirmed: bool,
    pub props_installed_confirmed: bool,
    pub props_policy: String,
    pub blockers: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RealHoverSummary {
    pub schema_version: String,
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub task: String,
    pub claim: String,
    pub plan: RealHoverPlan,
    pub no_sim_dependency: bool,
    pub live_flight_enabled: bool,
    pub source_boundary: Value,
    pub gate_plan: Value,
    pub fsm_artifacts: Vec<NavLabFsmArtifactRef>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operator_safety: Option<RealHoverOperatorSafetyEvaluation>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub workflow: Option<RealWorkflowSummary>,
}

pub struct RealHoverTask;

#[async_trait::async_trait]
impl RealTask for RealHoverTask {
    fn id(&self) -> &'static str {
        "hover"
    }

    #[instrument(skip(self, project, config, options))]
    async fn run(
        &self,
        project: &ProjectConfig,
        config: &TaskConfig,
        options: RunOptions,
    ) -> Result<()> {
        if config.family != "real" {
            bail!("hover config family must be real, got {}", config.family);
        }
        let plan = build_plan(config)?;
        info!(
            task_id = plan.task_id,
            dry_run = options.dry_run,
            "prepared real hover task"
        );
        print_title("NavLab Real Hover");
        print_key_value("runtime_mode", &project.runtime.mode);
        print_key_value("backend", &project.runtime.backend);
        print_key_value("dry_run", &options.dry_run.to_string());
        println!("{}", serde_json::to_string_pretty(&plan)?);

        let artifact_dir = resolve_artifact_dir(project, &options);
        let run_id = run_id_from_artifact_dir(&artifact_dir);
        let summary_path = resolve_summary_path(project, &options);
        write_task_request(&artifact_dir, project, config)?;
        write_task_plan(&artifact_dir, project, config, &plan)?;

        if let Some(chain) = &options.doctor_chain
            && !chain.ok
        {
            let workflow =
                crate::workflows::workflow_from_doctor_chain(&plan.task_id, &run_id, chain, true);
            let mut summary = build_blocked_summary(
                project,
                &plan,
                "blocked_by_doctor_chain",
                workflow.blockers.clone(),
            );
            summary.workflow = Some(workflow.clone());
            write_workflow_summary(&artifact_dir, &workflow)?;
            attach_navlab_fsm_artifact(&artifact_dir, &run_id, &plan, &mut summary)?;
            write_summary(&summary_path, &summary)?;
            write_task_result(&summary_path, project, &plan, &summary)?;
            println!("{}", serde_json::to_string_pretty(&summary)?);
            bail!(
                "real hover blocked by workflow: {}; summary written to {}",
                summary.blockers.join(", "),
                summary_path.display()
            );
        }

        if options.dry_run {
            let workflow = if let Some(chain) = &options.doctor_chain {
                workflow_from_doctor_chain_with_runtime(
                    &plan.task_id,
                    &run_id,
                    chain,
                    Some((true, Vec::new(), "dry_run_no_flight_side_effect")),
                )
            } else {
                dry_run_workflow_with_runtime_claim(
                    &plan.task_id,
                    &run_id,
                    "dry_run_no_flight_side_effect",
                )
            };
            let mut summary = build_dry_run_summary(project, &plan);
            summary.workflow = Some(workflow.clone());
            write_workflow_summary(&artifact_dir, &workflow)?;
            attach_navlab_fsm_artifact(&artifact_dir, &run_id, &plan, &mut summary)?;
            write_summary(&summary_path, &summary)?;
            write_task_result(&summary_path, project, &plan, &summary)?;
            println!("{}", serde_json::to_string_pretty(&summary)?);
            return Ok(());
        }

        let safety = evaluate_operator_safety(&plan, &options.operator_confirmations);
        println!("{}", serde_json::to_string_pretty(&safety)?);
        if safety.blocked {
            let workflow = runtime_workflow(
                &plan.task_id,
                &run_id,
                false,
                safety.blockers.clone(),
                "blocked_by_operator_safety",
            );
            let mut summary = build_blocked_summary(
                project,
                &plan,
                "blocked_by_operator_safety",
                safety.blockers.clone(),
            );
            summary.operator_safety = Some(safety);
            summary.workflow = Some(workflow.clone());
            write_workflow_summary(&artifact_dir, &workflow)?;
            attach_navlab_fsm_artifact(&artifact_dir, &run_id, &plan, &mut summary)?;
            write_summary(&summary_path, &summary)?;
            write_task_result(&summary_path, project, &plan, &summary)?;
            println!("{}", serde_json::to_string_pretty(&summary)?);
            bail!(
                "real hover blocked before flight: {}; summary written to {}",
                summary.blockers.join(", "),
                summary_path.display()
            );
        }

        let workflow = runtime_workflow(
            &plan.task_id,
            &run_id,
            false,
            vec!["real_hover_live_task_not_enabled".to_string()],
            "runtime_blocked_live_hover_not_enabled",
        );
        let mut summary = build_blocked_summary(
            project,
            &plan,
            "runtime_blocked_live_hover_not_enabled",
            vec!["real_hover_live_task_not_enabled".to_string()],
        );
        summary.operator_safety = Some(safety);
        summary.workflow = Some(workflow.clone());
        write_workflow_summary(&artifact_dir, &workflow)?;
        attach_navlab_fsm_artifact(&artifact_dir, &run_id, &plan, &mut summary)?;
        write_summary(&summary_path, &summary)?;
        write_task_result(&summary_path, project, &plan, &summary)?;
        println!("{}", serde_json::to_string_pretty(&summary)?);
        warn!("real hover live task is not enabled");
        bail!(
            "real hover live task is not enabled; summary written to {}",
            summary_path.display()
        )
    }
}

pub fn build_plan(config: &TaskConfig) -> Result<RealHoverPlan> {
    let target_altitude_m = number_or_default(config.task.get("target_altitude_m"), 0.8);
    let hover_hold_sec = number_or_default(config.task.get("hover_hold_sec"), 10.0);
    let hover_health_stable_sec =
        number_or_default(config.task.get("hover_health_stable_sec"), 3.0);
    let hover_health_max_wait_sec =
        number_or_default(config.task.get("hover_health_max_wait_sec"), 20.0);
    let hover_span_target_m = number_or_default(config.task.get("hover_span_target_m"), 0.10);
    let hover_span_hard_cap_m = number_or_default(config.task.get("hover_span_hard_cap_m"), 0.20);
    let max_altitude_error_m = number_or_default(config.task.get("max_altitude_error_m"), 0.15);
    if target_altitude_m <= 0.0 {
        bail!("target_altitude_m must be positive");
    }
    if hover_hold_sec <= 0.0 {
        bail!("hover_hold_sec must be positive");
    }
    if hover_health_stable_sec <= 0.0 {
        bail!("hover_health_stable_sec must be positive");
    }
    if hover_health_max_wait_sec < hover_health_stable_sec {
        bail!("hover_health_max_wait_sec must be >= hover_health_stable_sec");
    }
    if hover_span_target_m <= 0.0 || hover_span_hard_cap_m <= 0.0 {
        bail!("hover span policy must be positive");
    }
    if hover_span_target_m > hover_span_hard_cap_m {
        bail!("hover_span_target_m must be <= hover_span_hard_cap_m");
    }
    Ok(RealHoverPlan {
        task_id: config.id.clone(),
        target_altitude_m,
        hover_hold_sec,
        hover_health_stable_sec,
        hover_health_max_wait_sec,
        hover_span_target_m,
        hover_span_hard_cap_m,
        max_altitude_error_m,
        completion_definition: HoverCompletionDefinition {
            primary: "mavlink_external_nav_and_fcu_local_position".to_string(),
            secondary: "official_dds_pose_if_available".to_string(),
            gate_policy: "mavlink_external_nav_required_official_dds_crosscheck".to_string(),
            required_evidence: vec![
                "/scan fresh real lidar".to_string(),
                "/slam/odom fresh real SLAM".to_string(),
                "/external_nav/status ready".to_string(),
                "/mavlink_external_nav/status ready".to_string(),
                "FCU local position fresh".to_string(),
                "rangefinder/down ready".to_string(),
                "GUIDED arm takeoff ACK evidence".to_string(),
                "hover-health stable window".to_string(),
                "landing and disarm evidence".to_string(),
            ],
            review_only_evidence: vec![
                "official DDS pose crosscheck".to_string(),
                "operator review notes".to_string(),
            ],
        },
        safety: RealHoverSafety {
            confirm_manual_takeover: bool_or_default(
                config.safety.get("confirm_manual_takeover"),
                true,
            ),
            confirm_kill_switch: bool_or_default(config.safety.get("confirm_kill_switch"), true),
            confirm_safe_area: bool_or_default(config.safety.get("confirm_safe_area"), true),
            confirm_props_installed: bool_or_default(
                config.safety.get("confirm_props_installed"),
                true,
            ),
            props_installed_claim: "required_for_hover_not_represented_by_no_props".to_string(),
        },
        claim: "real_hover_plan".to_string(),
    })
}

pub fn evaluate_operator_safety(
    plan: &RealHoverPlan,
    confirmations: &crate::tasks::OperatorConfirmations,
) -> RealHoverOperatorSafetyEvaluation {
    let mut blockers = Vec::new();
    if plan.safety.confirm_manual_takeover && !confirmations.manual_takeover {
        blockers.push("operator_manual_takeover_not_confirmed".to_string());
    }
    if plan.safety.confirm_kill_switch && !confirmations.kill_switch {
        blockers.push("operator_kill_switch_not_confirmed".to_string());
    }
    if plan.safety.confirm_safe_area && !confirmations.safe_area {
        blockers.push("operator_safe_area_not_confirmed".to_string());
    }
    if plan.safety.confirm_props_installed && !confirmations.props_installed {
        blockers.push("operator_props_installed_not_confirmed".to_string());
    }
    RealHoverOperatorSafetyEvaluation {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        manual_takeover_confirmed: confirmations.manual_takeover,
        kill_switch_confirmed: confirmations.kill_switch,
        safe_area_confirmed: confirmations.safe_area,
        props_installed_confirmed: confirmations.props_installed,
        props_policy: "props_required_for_real_hover_no_no_props_shortcut".to_string(),
        blockers,
    }
}

pub fn build_dry_run_summary(project: &ProjectConfig, plan: &RealHoverPlan) -> RealHoverSummary {
    RealHoverSummary {
        schema_version: REAL_HOVER_SUMMARY_SCHEMA_VERSION.to_string(),
        ok: true,
        blocked: false,
        blockers: Vec::new(),
        task: "hover".to_string(),
        claim: "dry_run_plan_only".to_string(),
        plan: plan.clone(),
        no_sim_dependency: true,
        live_flight_enabled: false,
        source_boundary: source_boundary(project),
        gate_plan: gate_plan(plan),
        fsm_artifacts: Vec::new(),
        operator_safety: None,
        workflow: None,
    }
}

pub fn build_blocked_summary(
    project: &ProjectConfig,
    plan: &RealHoverPlan,
    claim: &str,
    blockers: Vec<String>,
) -> RealHoverSummary {
    RealHoverSummary {
        schema_version: REAL_HOVER_SUMMARY_SCHEMA_VERSION.to_string(),
        ok: false,
        blocked: true,
        blockers: blockers.clone(),
        task: "hover".to_string(),
        claim: claim.to_string(),
        plan: plan.clone(),
        no_sim_dependency: true,
        live_flight_enabled: false,
        source_boundary: source_boundary(project),
        gate_plan: gate_plan(plan),
        fsm_artifacts: Vec::new(),
        operator_safety: None,
        workflow: None,
    }
}

fn planned_hover_fsm(plan: &RealHoverPlan) -> NavLabFsmSummary {
    let states = hover_states()
        .iter()
        .map(|state| {
            hover_state(
                *state,
                "planned",
                "planned_dry_run_no_flight_side_effect",
                json!({
                    "target_altitude_m": plan.target_altitude_m,
                    "hover_hold_sec": plan.hover_hold_sec,
                    "completion_definition": plan.completion_definition.gate_policy,
                }),
            )
        })
        .collect();
    let transitions = vec![
        hover_transition(
            plan,
            "runtime_ready",
            "guided",
            "guided_confirmed",
            "guided_ack_planned",
            true,
            None,
            json!({"request": "set_guided"}),
            "planned",
        ),
        hover_transition(
            plan,
            "guided",
            "armed",
            "arm_confirmed",
            "arm_ack_accepted_planned",
            true,
            None,
            json!({"request": "arm"}),
            "planned",
        ),
        hover_transition(
            plan,
            "armed",
            "takeoff",
            "takeoff_confirmed",
            "takeoff_ack_and_altitude_planned",
            true,
            None,
            json!({"target_altitude_m": plan.target_altitude_m}),
            "planned",
        ),
        hover_transition(
            plan,
            "takeoff",
            "hover_health_hold",
            "hover_health_stable",
            "hover_health_stable_window_planned",
            true,
            None,
            json!({"stable_sec": plan.hover_health_stable_sec, "max_wait_sec": plan.hover_health_max_wait_sec}),
            "planned",
        ),
        hover_transition(
            plan,
            "hover_health_hold",
            "hover_hold",
            "hover_hold_started",
            "hover_hold_window_planned",
            true,
            None,
            json!({"hold_sec": plan.hover_hold_sec}),
            "planned",
        ),
        hover_transition(
            plan,
            "hover_hold",
            "landing",
            "landing_started",
            "landing_policy_planned",
            true,
            None,
            json!({"landing_policy": "land_then_disarm"}),
            "planned",
        ),
        hover_transition(
            plan,
            "landing",
            "disarmed",
            "disarm_confirmed",
            "landing_and_disarm_planned",
            true,
            None,
            json!({"require_disarm": true}),
            "planned",
        ),
        hover_transition(
            plan,
            "disarmed",
            "completed",
            "task_completed",
            "real_hover_completed_planned",
            true,
            None,
            json!({"completion_definition": plan.completion_definition.gate_policy}),
            "planned",
        ),
    ];
    navlab_fsm_summary(
        plan.task_id.clone(),
        "real-hover",
        "",
        "completed",
        "planned",
        true,
        false,
        states,
        transitions,
        Vec::new(),
        None,
    )
}

fn blocked_hover_fsm(
    plan: &RealHoverPlan,
    reason: &str,
    blockers: Vec<String>,
) -> NavLabFsmSummary {
    let states = hover_states()
        .iter()
        .map(|state| {
            hover_state(
                *state,
                if *state == "runtime_ready" {
                    "blocked_before_entering"
                } else {
                    "not_entered"
                },
                if *state == "runtime_ready" {
                    reason
                } else {
                    "not_reached_after_blocker"
                },
                json!({"blockers": blockers}),
            )
        })
        .collect();
    let transitions = vec![hover_transition(
        plan,
        "runtime_ready",
        "guided",
        "runtime_ready",
        reason,
        false,
        blockers.first().cloned(),
        json!({"runtime_started": false, "blockers": blockers}),
        "blocked_before_entering",
    )];
    navlab_fsm_summary(
        plan.task_id.clone(),
        "real-hover",
        "",
        "runtime_ready",
        "blocked_before_runtime",
        false,
        true,
        states,
        transitions,
        blockers,
        Some("runtime_ready".to_string()),
    )
}

fn hover_states() -> [&'static str; 9] {
    [
        "runtime_ready",
        "guided",
        "armed",
        "takeoff",
        "hover_health_hold",
        "hover_hold",
        "landing",
        "disarmed",
        "completed",
    ]
}

#[allow(clippy::too_many_arguments)]
fn hover_transition(
    plan: &RealHoverPlan,
    from_state: &str,
    to_state: &str,
    event: &str,
    reason_code: &str,
    ok: bool,
    blocker: Option<String>,
    evidence: Value,
    at: &str,
) -> NavLabFsmTransition {
    let _ = plan;
    let _ = blocker;
    navlab_fsm_transition(NavLabFsmTransitionInput {
        from_state: from_state.to_string(),
        to_state: to_state.to_string(),
        trigger: event.to_string(),
        reason_code: reason_code.to_string(),
        ok,
        evidence,
        at: at.to_string(),
    })
}

fn hover_state(
    state: &str,
    entered_at: &str,
    reason: &str,
    evidence: Value,
) -> crate::workflows::NavLabFsmState {
    let _ = evidence;
    navlab_fsm_state(
        state,
        state == "completed",
        reason == "blocked_before_entering",
        Some(format!("{entered_at}:{reason}")),
    )
}

fn source_boundary(project: &ProjectConfig) -> Value {
    json!({
        "runtime_domain": "real",
        "forbidden_sim_dependency": true,
        "scan_source": project.sources.scan_source_claim,
        "scan_topic": project.sources.scan_source_topic,
        "slam_source": project.sources.slam_source_claim,
        "fcu_source": project.sources.fcu_source_claim,
        "rangefinder_source": project.sources.rangefinder_source_claim,
        "forbidden_simulation_input_topics": project.sources.forbidden_simulation_input_topics,
    })
}

fn gate_plan(plan: &RealHoverPlan) -> Value {
    json!({
        "completion_definition": plan.completion_definition,
        "hover_health": {
            "stable_required_sec": plan.hover_health_stable_sec,
            "max_wait_sec": plan.hover_health_max_wait_sec,
            "span_target_m": plan.hover_span_target_m,
            "span_hard_cap_m": plan.hover_span_hard_cap_m,
            "max_altitude_error_m": plan.max_altitude_error_m,
        },
        "required_evidence": {
            "slam": ["/scan", "/tf", "/tf_static", "/slam/odom", "/navlab/slam/status"],
            "external_nav": ["/external_nav/status", "/mavlink_external_nav/status"],
            "fcu": ["/navlab/mavlink/status", "FCU local position"],
            "height": ["/rangefinder/down/range", "/rangefinder/down/status"],
            "landing": ["land command ACK", "touchdown or landed-state", "disarm ACK"],
        },
        "review_only": {
            "official_dds_pose": "crosscheck_only_not_primary_completion",
        }
    })
}

fn resolve_summary_path(project: &ProjectConfig, options: &RunOptions) -> PathBuf {
    if let Some(path) = &options.summary_path {
        return path.clone();
    }
    resolve_artifact_dir(project, options).join("summary.json")
}

fn resolve_artifact_dir(project: &ProjectConfig, options: &RunOptions) -> PathBuf {
    if let Some(path) = &options.summary_path
        && let Some(parent) = path.parent()
    {
        return parent.to_path_buf();
    }
    options
        .artifact_dir
        .clone()
        .unwrap_or_else(|| project.paths.artifact_root.join("hover").join(run_id()))
}

fn write_summary(path: &Path, summary: &RealHoverSummary) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create real hover artifact dir {}", parent.display()))?;
    }
    fs::write(path, serde_json::to_string_pretty(summary)?)
        .with_context(|| format!("write real hover summary {}", path.display()))
}

fn attach_navlab_fsm_artifact(
    artifact_dir: &Path,
    run_id: &str,
    plan: &RealHoverPlan,
    summary: &mut RealHoverSummary,
) -> Result<()> {
    let fsm = if summary.ok && summary.claim == "dry_run_plan_only" {
        planned_hover_fsm(plan)
    } else {
        blocked_hover_fsm(plan, &summary.claim, summary.blockers.clone())
    };
    let (_fsm_summary, reference) = write_navlab_fsm_artifact(artifact_dir, &fsm, run_id)?;
    summary.fsm_artifacts = vec![reference];
    Ok(())
}

fn write_task_request(
    artifact_dir: &Path,
    project: &ProjectConfig,
    task: &TaskConfig,
) -> Result<()> {
    let run_id = run_id_from_artifact_dir(artifact_dir);
    let request = contracts::task_request(project, task, &run_id, artifact_dir);
    contracts::write_json(
        &artifact_dir.join("task_request.json"),
        &request,
        "real hover task request",
    )
}

fn write_task_plan(
    artifact_dir: &Path,
    project: &ProjectConfig,
    task: &TaskConfig,
    plan: &RealHoverPlan,
) -> Result<()> {
    let run_id = run_id_from_artifact_dir(artifact_dir);
    contracts::write_json(
        &artifact_dir.join("task_plan.json"),
        &json!({
            "schemaVersion": "navlab.real.task_plan.v1",
            "taskId": task.id,
            "runId": run_id,
            "runtimeMode": "RUNTIME_MODE_REAL",
            "artifactDir": artifact_dir.display().to_string(),
            "orchestration": {
                "family": project.orchestration.family,
                "implementation": project.orchestration.implementation,
                "contractVersion": project.orchestration.contract_version,
            },
            "plan": plan,
        }),
        "real hover task plan",
    )
}

fn write_workflow_summary(artifact_dir: &Path, workflow: &RealWorkflowSummary) -> Result<()> {
    let value = serde_json::to_value(workflow).unwrap_or_else(|_| json!({}));
    contracts::write_json(
        &artifact_dir.join("dag").join("workflow_summary.json"),
        &value,
        "real hover workflow summary",
    )
}

fn write_task_result(
    summary_path: &Path,
    project: &ProjectConfig,
    plan: &RealHoverPlan,
    summary: &RealHoverSummary,
) -> Result<()> {
    let artifact_dir = summary_path.parent().unwrap_or_else(|| Path::new("."));
    let run_id = run_id_from_artifact_dir(artifact_dir);
    let result = contracts::task_result(contracts::TaskResultContractInput {
        project,
        task_id: &plan.task_id,
        run_id: &run_id,
        artifact_dir,
        summary_path,
        ok: summary.ok,
        blockers: &summary.blockers,
        mavlink_acks: Vec::new(),
        details: serde_json::to_value(summary).unwrap_or_else(|_| json!({})),
    });
    contracts::write_json(
        &artifact_dir.join("task_result.json"),
        &result,
        "real hover task result",
    )
}

fn run_id_from_artifact_dir(artifact_dir: &Path) -> String {
    artifact_dir
        .file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .unwrap_or("manual")
        .to_string()
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

fn number_or_default(value: Option<&Value>, default: f64) -> f64 {
    value.and_then(Value::as_f64).unwrap_or(default)
}

fn bool_or_default(value: Option<&Value>, default: bool) -> bool {
    value.and_then(Value::as_bool).unwrap_or(default)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{
        CommonDoctorConfig, OrchestrationConfig, PathConfig, PreflightConfig, PrepareConfig,
        RuntimeConfig, SourceConfig, TaskDoctorConfig,
    };

    fn task_config() -> TaskConfig {
        TaskConfig {
            id: "hover".to_string(),
            family: "real".to_string(),
            description: "test".to_string(),
            capabilities: vec![],
            task: serde_json::from_value(json!({
                "target_altitude_m": 0.8,
                "hover_hold_sec": 10.0,
                "hover_health_stable_sec": 3.0,
                "hover_health_max_wait_sec": 20.0,
                "hover_span_target_m": 0.1,
                "hover_span_hard_cap_m": 0.2,
                "max_altitude_error_m": 0.15
            }))
            .expect("task"),
            safety: serde_json::from_value(json!({
                "confirm_manual_takeover": true,
                "confirm_kill_switch": true,
                "confirm_safe_area": true,
                "confirm_props_installed": true
            }))
            .expect("safety"),
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
                scan_source_claim: "ydlidar_x2".to_string(),
                scan_source_topic: "/scan".to_string(),
                fcu_source_claim: "fcu_mavlink".to_string(),
                imu_source_claim: "fcu_mavlink".to_string(),
                rangefinder_source_claim: "fcu_distance_sensor".to_string(),
                slam_source_claim: "cartographer".to_string(),
                required_real_topics: vec![],
                forbidden_simulation_input_topics: vec!["/gazebo/*".to_string()],
            },
            preflight: PreflightConfig::default(),
            prepare: PrepareConfig::default(),
            common_doctor: CommonDoctorConfig::default(),
            task_doctor: TaskDoctorConfig::default(),
        }
    }

    #[test]
    fn real_hover_plan_records_layered_completion_definition() {
        let plan = build_plan(&task_config()).expect("plan");

        assert_eq!(
            plan.completion_definition.primary,
            "mavlink_external_nav_and_fcu_local_position"
        );
        assert_eq!(
            plan.completion_definition.secondary,
            "official_dds_pose_if_available"
        );
        assert_eq!(plan.hover_span_target_m, 0.1);
        assert_eq!(plan.hover_span_hard_cap_m, 0.2);
    }

    #[test]
    fn real_hover_dry_run_summary_has_planned_fsm_and_gate_plan() {
        let plan = build_plan(&task_config()).expect("plan");
        let summary = build_dry_run_summary(&project(), &plan);

        assert!(summary.ok);
        assert!(summary.no_sim_dependency);
        assert!(!summary.live_flight_enabled);
        let fsm = planned_hover_fsm(&plan);
        assert_eq!(fsm.mode, "planned");
        assert_eq!(fsm.state, "completed");
        assert_eq!(fsm.states.len(), 9);
        assert_eq!(fsm.transitions[3].to_state, "hover_health_hold");
        assert_eq!(
            summary.gate_plan["completion_definition"]["gate_policy"],
            "mavlink_external_nav_required_official_dds_crosscheck"
        );
    }

    #[test]
    fn real_hover_operator_safety_requires_props_installed_not_no_props() {
        let plan = build_plan(&task_config()).expect("plan");
        let safety = evaluate_operator_safety(
            &plan,
            &crate::tasks::OperatorConfirmations {
                manual_takeover: true,
                kill_switch: true,
                safe_area: true,
                no_props: true,
                props_installed: false,
            },
        );

        assert!(!safety.ok);
        assert_eq!(
            safety.blockers,
            vec!["operator_props_installed_not_confirmed"]
        );
        assert_eq!(
            safety.props_policy,
            "props_required_for_real_hover_no_no_props_shortcut"
        );
    }

    #[tokio::test]
    async fn real_hover_dry_run_writes_workflow_artifacts() {
        let temp = tempfile::tempdir().expect("tempdir");
        let task = RealHoverTask;

        task.run(
            &project(),
            &task_config(),
            RunOptions {
                dry_run: true,
                artifact_dir: Some(temp.path().to_path_buf()),
                ..RunOptions::default()
            },
        )
        .await
        .expect("dry run");

        assert!(temp.path().join("task_request.json").is_file());
        assert!(temp.path().join("task_plan.json").is_file());
        assert!(
            temp.path()
                .join("dag")
                .join("workflow_summary.json")
                .is_file()
        );
        assert!(temp.path().join("summary.json").is_file());
        assert!(temp.path().join("task_result.json").is_file());
        let summary: Value = serde_json::from_str(
            &fs::read_to_string(temp.path().join("summary.json")).expect("summary"),
        )
        .expect("summary json");
        assert_eq!(summary["task"], "hover");
        let fsm: Value = serde_json::from_str(
            &fs::read_to_string(temp.path().join("runtime").join("task_hover_fsm.json"))
                .expect("fsm"),
        )
        .expect("fsm json");
        assert_eq!(fsm["schema_version"], "navlab.fsm.v1");
        assert_eq!(fsm["mode"], "planned");
        assert_eq!(
            summary["workflow"]["nodes"][4]["evidence"]["claim"],
            "dry_run_no_flight_side_effect"
        );
    }

    #[tokio::test]
    async fn real_hover_live_run_blocks_missing_operator_safety_before_runtime() {
        let temp = tempfile::tempdir().expect("tempdir");
        let task = RealHoverTask;

        let error = task
            .run(
                &project(),
                &task_config(),
                RunOptions {
                    dry_run: false,
                    artifact_dir: Some(temp.path().to_path_buf()),
                    ..RunOptions::default()
                },
            )
            .await
            .expect_err("operator safety should block");

        assert!(error.to_string().contains("blocked before flight"));
        let summary: Value = serde_json::from_str(
            &fs::read_to_string(temp.path().join("summary.json")).expect("summary"),
        )
        .expect("summary json");
        assert_eq!(summary["ok"], false);
        assert_eq!(summary["claim"], "blocked_by_operator_safety");
        assert_eq!(
            summary["blockers"][0],
            "operator_manual_takeover_not_confirmed"
        );
        let fsm: Value = serde_json::from_str(
            &fs::read_to_string(temp.path().join("runtime").join("task_hover_fsm.json"))
                .expect("fsm"),
        )
        .expect("fsm json");
        assert_eq!(fsm["failed_state"], "runtime_ready");
    }

    #[tokio::test]
    async fn real_hover_live_run_fails_closed_after_operator_safety_passes() {
        let temp = tempfile::tempdir().expect("tempdir");
        let task = RealHoverTask;

        let error = task
            .run(
                &project(),
                &task_config(),
                RunOptions {
                    dry_run: false,
                    artifact_dir: Some(temp.path().to_path_buf()),
                    operator_confirmations: crate::tasks::OperatorConfirmations {
                        manual_takeover: true,
                        kill_switch: true,
                        safe_area: true,
                        no_props: false,
                        props_installed: true,
                    },
                    ..RunOptions::default()
                },
            )
            .await
            .expect_err("live hover is not enabled");

        assert!(error.to_string().contains("not enabled"));
        let summary: Value = serde_json::from_str(
            &fs::read_to_string(temp.path().join("summary.json")).expect("summary"),
        )
        .expect("summary json");
        assert_eq!(summary["ok"], false);
        assert_eq!(summary["blockers"][0], "real_hover_live_task_not_enabled");
        assert_eq!(
            summary["operator_safety"]["props_installed_confirmed"],
            true
        );
    }
}
