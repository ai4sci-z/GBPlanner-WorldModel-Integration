use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use serde::Serialize;
use serde_json::{Value, json};
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tracing::{info, instrument, warn};

use crate::config::{ProjectConfig, TaskConfig};
use crate::contracts;
use crate::runtime::{MotorDebugRuntimeReport, MotorDebugRuntimeRequest, real_motor_debug_runtime};
use crate::tasks::{RealTask, RunOptions};
use crate::ui::{print_key_value, print_title};
use crate::workflows::{
    NavLabFsmArtifactRef, NavLabFsmState as MotorDebugFsmState,
    NavLabFsmSummary as MotorDebugFsmSummary, NavLabFsmTransition as MotorDebugFsmTransition,
    NavLabFsmTransitionInput, RealWorkflowSummary, dry_run_workflow, navlab_fsm_state,
    navlab_fsm_summary, navlab_fsm_transition, runtime_workflow,
    workflow_from_doctor_chain_with_runtime, write_navlab_fsm_artifact,
};

pub const TASK_RESULT_SCHEMA_VERSION: &str = "navlab.runtime.task_result.v1";
pub const REQUIRED_GUIDED_MODE_NAME: &str = "GUIDED";
pub const ARDUCOPTER_GUIDED_MODE_ID: u32 = 4;
pub const MAV_CMD_COMPONENT_ARM_DISARM: u32 = 400;
pub const MAV_RESULT_ACCEPTED: u32 = 0;
pub const MAV_RESULT_FAILED: u32 = 4;

#[derive(Debug, Clone, Default)]
pub struct MotorDebugOverrides {
    pub motor_percent: Option<f64>,
    pub motor_sec: Option<f64>,
    pub motor_count: Option<u32>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct OperatorConfirmations {
    pub manual_takeover: bool,
    pub kill_switch: bool,
    pub safe_area: bool,
    pub no_props: bool,
    pub props_installed: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct OperatorSafetyEvaluation {
    pub ok: bool,
    pub blocked: bool,
    pub manual_takeover_confirmed: bool,
    pub kill_switch_confirmed: bool,
    pub safe_area_confirmed: bool,
    pub no_props_confirmed: bool,
    pub blockers: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MotorDebugPlan {
    pub task_id: String,
    pub motor_percent: f64,
    pub motor_sec: f64,
    pub motor_count: u32,
    pub safety: MotorDebugSafety,
    pub claim: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct MotorDebugRuntimeSummary {
    pub schema_version: String,
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub task: String,
    pub claim: String,
    pub no_takeoff: bool,
    pub requires_no_props: bool,
    pub guided_mode_required: bool,
    pub required_mode: String,
    pub spin_mode: String,
    pub throttle_command_claim: String,
    pub motor_percent: f64,
    pub motor_sec: f64,
    pub motor_count: u32,
    pub steps: Vec<Value>,
    pub shutdown: String,
    pub landing_claim: String,
    pub serial: String,
    pub connection_endpoint: String,
    pub baud: u32,
    pub arm_claim: String,
    pub takeoff_claim: String,
    pub guided_mode_claim: String,
    pub shutdown_claim: String,
    pub guided_mode: Value,
    pub command_plan: MotorDebugCommandPlan,
    pub acks: Vec<Value>,
    pub fsm_artifacts: Vec<NavLabFsmArtifactRef>,
    pub runtime_report: Option<MotorDebugRuntimeReport>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operator_safety: Option<OperatorSafetyEvaluation>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub workflow: Option<RealWorkflowSummary>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MotorDebugSafety {
    pub confirm_manual_takeover: bool,
    pub confirm_kill_switch: bool,
    pub confirm_safe_area: bool,
    pub confirm_no_props: bool,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct GuidedModeEvaluation {
    pub ok: bool,
    pub mode_name: String,
    pub mode_id: u32,
    pub mode_mapping_has_mode: bool,
    pub mode_mapping_mode_id: Option<u32>,
    pub observed_mode_id: Option<u32>,
    pub blockers: Vec<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct MotorDebugCommandLong {
    pub target_system: u8,
    pub target_component: u8,
    pub command: u32,
    pub confirmation: u8,
    pub param1: f64,
    pub param2: f64,
    pub param3: f64,
    pub param4: f64,
    pub param5: f64,
    pub param6: f64,
    pub param7: f64,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct MotorDebugCommandPlan {
    pub guided_mode_id: u32,
    pub arm_command: MotorDebugCommandLong,
    pub disarm_command: MotorDebugCommandLong,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct MavlinkStatusText {
    pub severity: u8,
    pub text: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct CommandAckEvaluation {
    pub command: u32,
    pub result: u32,
    pub result_name: String,
    pub accepted: bool,
    pub result_param2: u32,
    pub status_text: Vec<MavlinkStatusText>,
}

pub struct MotorDebugTask;

#[async_trait::async_trait]
impl RealTask for MotorDebugTask {
    fn id(&self) -> &'static str {
        "motor-debug"
    }

    #[instrument(skip(self, project, config, options))]
    async fn run(
        &self,
        project: &ProjectConfig,
        config: &TaskConfig,
        options: RunOptions,
    ) -> Result<()> {
        if config.family != "real" {
            bail!(
                "motor-debug config family must be real, got {}",
                config.family
            );
        }
        let plan = build_plan(config, options.motor_debug.clone())?;
        info!(
            task_id = plan.task_id,
            motor_percent = plan.motor_percent,
            motor_sec = plan.motor_sec,
            motor_count = plan.motor_count,
            dry_run = options.dry_run,
            "prepared motor-debug task"
        );
        print_title("NavLab Real Motor Debug");
        print_key_value("runtime_mode", &project.runtime.mode);
        print_key_value("backend", &project.runtime.backend);
        print_key_value("dry_run", &options.dry_run.to_string());
        println!("{}", serde_json::to_string_pretty(&plan)?);
        let artifact_dir = resolve_artifact_dir(project, &options);
        let run_id = run_id_from_artifact_dir(&artifact_dir);
        let summary_path = resolve_summary_path(project, &options);
        write_task_request(&artifact_dir, project, config)?;
        write_task_plan(&artifact_dir, project, config, &plan)?;
        if let Some(chain) = &options.doctor_chain {
            if !chain.ok {
                let workflow = crate::workflows::workflow_from_doctor_chain(
                    &plan.task_id,
                    &run_id,
                    chain,
                    true,
                );
                let mut summary = build_blocked_summary(
                    project,
                    &plan,
                    "blocked_by_doctor_chain",
                    workflow.blockers.clone(),
                );
                summary.workflow = Some(workflow.clone());
                write_workflow_summary(&artifact_dir, &workflow)?;
                attach_navlab_fsm_artifact(&artifact_dir, &run_id, &plan, &mut summary)?;
                write_runtime_summary(&summary_path, &summary)?;
                write_task_result(&summary_path, project, &plan, &summary)?;
                println!("{}", serde_json::to_string_pretty(&summary)?);
                bail!(
                    "real motor-debug blocked by workflow: {}; summary written to {}",
                    summary.blockers.join(", "),
                    summary_path.display()
                );
            }
        }
        if options.dry_run {
            let workflow = if let Some(chain) = &options.doctor_chain {
                workflow_from_doctor_chain_with_runtime(
                    &plan.task_id,
                    &run_id,
                    chain,
                    Some((true, Vec::new(), "dry_run_no_motor_side_effect")),
                )
            } else {
                dry_run_workflow(&plan.task_id, &run_id)
            };
            let mut summary = build_dry_run_summary(project, &plan);
            summary.workflow = Some(workflow.clone());
            write_workflow_summary(&artifact_dir, &workflow)?;
            attach_navlab_fsm_artifact(&artifact_dir, &run_id, &plan, &mut summary)?;
            write_runtime_summary(&summary_path, &summary)?;
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
            write_runtime_summary(&summary_path, &summary)?;
            write_task_result(&summary_path, project, &plan, &summary)?;
            println!("{}", serde_json::to_string_pretty(&summary)?);
            bail!(
                "real motor-debug blocked before motor test: {}; summary written to {}",
                summary.blockers.join(", "),
                summary_path.display()
            );
        }
        let runtime_request = MotorDebugRuntimeRequest::new(
            mavlink_router_endpoint(project),
            plan.motor_percent,
            plan.motor_sec,
        );
        let runtime = real_motor_debug_runtime(&runtime_request);
        let summary = match runtime {
            Ok(report) => build_runtime_summary(project, &plan, report),
            Err(error) => build_runtime_error_summary(project, &plan, &error.to_string()),
        };
        let mut summary = summary;
        let workflow = if let Some(chain) = &options.doctor_chain {
            workflow_from_doctor_chain_with_runtime(
                &plan.task_id,
                &run_id,
                chain,
                Some((summary.ok, summary.blockers.clone(), summary.claim.as_str())),
            )
        } else {
            runtime_workflow(
                &plan.task_id,
                &run_id,
                summary.ok,
                summary.blockers.clone(),
                summary.claim.as_str(),
            )
        };
        summary.workflow = Some(workflow.clone());
        write_workflow_summary(&artifact_dir, &workflow)?;
        attach_navlab_fsm_artifact(&artifact_dir, &run_id, &plan, &mut summary)?;
        write_runtime_summary(&summary_path, &summary)?;
        write_task_result(&summary_path, project, &plan, &summary)?;
        println!("{}", serde_json::to_string_pretty(&summary)?);
        if summary.ok {
            Ok(())
        } else {
            warn!("live motor-debug blocked");
            bail!(
                "live motor-debug blocked: {}; summary written to {}",
                summary.blockers.join(", "),
                summary_path.display()
            )
        }
    }
}

pub fn build_plan(config: &TaskConfig, overrides: MotorDebugOverrides) -> Result<MotorDebugPlan> {
    let motor_percent = overrides
        .motor_percent
        .unwrap_or_else(|| number_or_default(config.task.get("motor_percent"), 5.0));
    let motor_sec = overrides
        .motor_sec
        .unwrap_or_else(|| number_or_default(config.task.get("motor_sec"), 5.0));
    let motor_count = overrides
        .motor_count
        .unwrap_or_else(|| unsigned_or_default(config.task.get("motor_count"), 4));
    if motor_percent <= 0.0 {
        bail!("motor_percent must be positive");
    }
    if motor_sec <= 0.0 {
        bail!("motor_sec must be positive");
    }
    if motor_count == 0 {
        bail!("motor_count must be positive");
    }
    Ok(MotorDebugPlan {
        task_id: config.id.clone(),
        motor_percent,
        motor_sec,
        motor_count,
        safety: MotorDebugSafety {
            confirm_manual_takeover: bool_or_default(
                config.safety.get("confirm_manual_takeover"),
                true,
            ),
            confirm_kill_switch: bool_or_default(config.safety.get("confirm_kill_switch"), true),
            confirm_safe_area: bool_or_default(config.safety.get("confirm_safe_area"), true),
            confirm_no_props: bool_or_default(config.safety.get("confirm_no_props"), true),
        },
        claim: "dry_run_plan".to_string(),
    })
}

pub fn evaluate_operator_safety(
    plan: &MotorDebugPlan,
    confirmations: &OperatorConfirmations,
) -> OperatorSafetyEvaluation {
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
    if plan.safety.confirm_no_props && !confirmations.no_props {
        blockers.push("operator_no_props_not_confirmed".to_string());
    }
    OperatorSafetyEvaluation {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        manual_takeover_confirmed: confirmations.manual_takeover,
        kill_switch_confirmed: confirmations.kill_switch,
        safe_area_confirmed: confirmations.safe_area,
        no_props_confirmed: confirmations.no_props,
        blockers,
    }
}

pub fn mavlink_router_endpoint(project: &ProjectConfig) -> String {
    let endpoint = project.prepare.mavlink_router_local_endpoint.trim();
    if ["udp:", "udpin:", "udpout:", "tcp:"]
        .iter()
        .any(|prefix| endpoint.starts_with(prefix))
    {
        return endpoint.to_string();
    }
    let (host, port) = endpoint.split_once(':').unwrap_or((endpoint, ""));
    format!(
        "udpin:{}:{}",
        if host.is_empty() { "127.0.0.1" } else { host },
        if port.is_empty() { "14550" } else { port }
    )
}

pub fn build_runtime_not_migrated_summary(
    project: &ProjectConfig,
    plan: &MotorDebugPlan,
) -> MotorDebugRuntimeSummary {
    MotorDebugRuntimeSummary {
        schema_version: TASK_RESULT_SCHEMA_VERSION.to_string(),
        ok: false,
        blocked: true,
        blockers: vec!["motor_debug_rust_mavlink_runtime_not_migrated".to_string()],
        task: "motor-debug".to_string(),
        claim: "runtime_blocked_not_migrated".to_string(),
        no_takeoff: true,
        requires_no_props: true,
        guided_mode_required: true,
        required_mode: REQUIRED_GUIDED_MODE_NAME.to_string(),
        spin_mode: "armed_idle".to_string(),
        throttle_command_claim: "not_sent".to_string(),
        motor_percent: plan.motor_percent,
        motor_sec: plan.motor_sec,
        motor_count: plan.motor_count,
        steps: vec![
            json!({"step": "arm", "claim": "start_all_motors_at_fcu_armed_idle"}),
            json!({"step": "hold", "duration_sec": plan.motor_sec}),
            json!({"step": "disarm", "claim": "stop_all_motors"}),
        ],
        shutdown: "send_disarm_after_idle_spin".to_string(),
        landing_claim: "not_evaluated_no_takeoff".to_string(),
        serial: project.prepare.mavlink_router_serial_port.clone(),
        connection_endpoint: mavlink_router_endpoint(project),
        baud: project.prepare.mavlink_router_baud,
        arm_claim: "not_requested".to_string(),
        takeoff_claim: "not_evaluated".to_string(),
        guided_mode_claim: "not_evaluated".to_string(),
        shutdown_claim: "not_evaluated".to_string(),
        guided_mode: json!({}),
        command_plan: motor_debug_command_plan(),
        acks: Vec::new(),
        fsm_artifacts: Vec::new(),
        runtime_report: None,
        operator_safety: None,
        workflow: None,
    }
}

pub fn build_dry_run_summary(
    project: &ProjectConfig,
    plan: &MotorDebugPlan,
) -> MotorDebugRuntimeSummary {
    let mut summary = build_runtime_not_migrated_summary(project, plan);
    summary.ok = true;
    summary.blocked = false;
    summary.blockers = Vec::new();
    summary.claim = "dry_run_plan_only".to_string();
    summary.shutdown_claim = "not_evaluated_dry_run".to_string();
    summary.guided_mode_claim = "not_evaluated_dry_run".to_string();
    summary
}

pub fn build_blocked_summary(
    project: &ProjectConfig,
    plan: &MotorDebugPlan,
    claim: &str,
    blockers: Vec<String>,
) -> MotorDebugRuntimeSummary {
    let mut summary = build_runtime_not_migrated_summary(project, plan);
    summary.blockers = blockers;
    summary.claim = claim.to_string();
    summary
}

pub fn build_runtime_summary(
    project: &ProjectConfig,
    plan: &MotorDebugPlan,
    report: MotorDebugRuntimeReport,
) -> MotorDebugRuntimeSummary {
    MotorDebugRuntimeSummary {
        schema_version: TASK_RESULT_SCHEMA_VERSION.to_string(),
        ok: report.ok,
        blocked: report.blocked,
        blockers: report.blockers.clone(),
        task: "motor-debug".to_string(),
        claim: if report.ok {
            "runtime_executed".to_string()
        } else {
            "runtime_blocked".to_string()
        },
        no_takeoff: true,
        requires_no_props: true,
        guided_mode_required: true,
        required_mode: REQUIRED_GUIDED_MODE_NAME.to_string(),
        spin_mode: "armed_idle".to_string(),
        throttle_command_claim: report.throttle_command_claim.clone(),
        motor_percent: plan.motor_percent,
        motor_sec: plan.motor_sec,
        motor_count: plan.motor_count,
        steps: vec![
            json!({"step": "set_guided", "claim": "send_mav_cmd_do_set_mode_guided"}),
            json!({"step": "arm", "claim": "start_all_motors_at_fcu_armed_idle"}),
            json!({"step": "hold", "duration_sec": plan.motor_sec}),
            json!({"step": "disarm", "claim": "stop_all_motors"}),
        ],
        shutdown: "send_disarm_after_idle_spin".to_string(),
        landing_claim: "not_evaluated_no_takeoff".to_string(),
        serial: project.prepare.mavlink_router_serial_port.clone(),
        connection_endpoint: report.connection_endpoint.clone(),
        baud: project.prepare.mavlink_router_baud,
        arm_claim: ack_claim(report.arm_ack.as_ref()),
        takeoff_claim: "not_evaluated".to_string(),
        guided_mode_claim: if report.guided_mode.ok {
            "guided_confirmed_by_ack_and_heartbeat".to_string()
        } else {
            "guided_not_confirmed".to_string()
        },
        shutdown_claim: report.shutdown_claim.clone(),
        guided_mode: serde_json::to_value(&report.guided_mode).unwrap_or_else(|_| json!({})),
        command_plan: motor_debug_command_plan(),
        acks: runtime_acks(&report),
        fsm_artifacts: Vec::new(),
        runtime_report: Some(report),
        operator_safety: None,
        workflow: None,
    }
}

pub fn build_runtime_error_summary(
    project: &ProjectConfig,
    plan: &MotorDebugPlan,
    error: &str,
) -> MotorDebugRuntimeSummary {
    let mut summary = build_runtime_not_migrated_summary(project, plan);
    summary.blockers = vec![format!("motor_debug_mavlink_runtime_error:{error}")];
    summary.claim = "runtime_error".to_string();
    summary
}

fn build_planned_fsm(plan: &MotorDebugPlan) -> MotorDebugFsmSummary {
    let states = motor_debug_fsm_states()
        .iter()
        .map(|state| {
            fsm_state(
                state,
                "planned",
                "planned_dry_run_no_motor_side_effect",
                json!({
                    "motor_percent": plan.motor_percent,
                    "motor_sec": plan.motor_sec,
                    "motor_count": plan.motor_count,
                }),
            )
        })
        .collect();
    let transitions = vec![
        fsm_transition(
            plan,
            "runtime_ready",
            "guided",
            "guided_confirmed",
            "guided_ack_and_heartbeat_planned",
            true,
            None,
            json!({"request": "MAV_CMD_DO_SET_MODE", "mode": REQUIRED_GUIDED_MODE_NAME}),
            "planned",
        ),
        fsm_transition(
            plan,
            "guided",
            "armed",
            "arm_confirmed",
            "arm_ack_accepted_planned",
            true,
            None,
            json!({"request": "MAV_CMD_COMPONENT_ARM_DISARM", "param1": 1.0}),
            "planned",
        ),
        fsm_transition(
            plan,
            "armed",
            "motor_spin_hold",
            "hold_started",
            "armed_idle_hold_planned",
            true,
            None,
            json!({"duration_sec": plan.motor_sec, "throttle_command_claim": "not_sent_armed_idle_only"}),
            "planned",
        ),
        fsm_transition(
            plan,
            "motor_spin_hold",
            "disarmed",
            "disarm_confirmed",
            "disarm_ack_accepted_planned",
            true,
            None,
            json!({"request": "MAV_CMD_COMPONENT_ARM_DISARM", "param1": 0.0}),
            "planned",
        ),
        fsm_transition(
            plan,
            "disarmed",
            "completed",
            "task_completed",
            "motor_debug_completed_planned",
            true,
            None,
            json!({"no_takeoff": true, "landing_claim": "not_evaluated_no_takeoff"}),
            "planned",
        ),
    ];
    navlab_fsm_summary(
        plan.task_id.clone(),
        "motor-debug",
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

fn build_not_started_fsm(
    plan: &MotorDebugPlan,
    reason: &str,
    blockers: &[String],
) -> MotorDebugFsmSummary {
    let blocker = blockers.first().cloned();
    let states = motor_debug_fsm_states()
        .iter()
        .map(|state| {
            let state_reason = if *state == "runtime_ready" {
                reason
            } else {
                "not_reached_after_blocker"
            };
            fsm_state(
                state,
                if *state == "runtime_ready" {
                    "blocked_before_entering"
                } else {
                    "not_entered"
                },
                state_reason,
                json!({"blockers": blockers}),
            )
        })
        .collect();
    let transitions = vec![fsm_transition(
        plan,
        "runtime_ready",
        "guided",
        "runtime_ready",
        reason,
        false,
        blocker,
        json!({"runtime_started": false, "blockers": blockers}),
        "blocked_before_entering",
    )];
    navlab_fsm_summary(
        plan.task_id.clone(),
        "motor-debug",
        "",
        "runtime_ready",
        "blocked_before_runtime",
        false,
        true,
        states,
        transitions,
        blockers.to_vec(),
        Some("runtime_ready".to_string()),
    )
}

fn build_actual_fsm(
    plan: &MotorDebugPlan,
    report: &MotorDebugRuntimeReport,
) -> MotorDebugFsmSummary {
    let at = fsm_now();
    let mut entered = std::collections::BTreeMap::new();
    let mut transitions = Vec::new();
    let mut current_state = "runtime_ready".to_string();
    let mut failed_state = None;

    if report.initial_heartbeat.is_some() {
        entered.insert(
            "runtime_ready",
            (
                "heartbeat_observed",
                json!({"heartbeat": report.initial_heartbeat}),
            ),
        );
    } else {
        failed_state = Some("runtime_ready".to_string());
        transitions.push(fsm_transition(
            plan,
            "runtime_ready",
            "guided",
            "heartbeat_ready",
            "motor_debug_heartbeat_timeout",
            false,
            first_blocker(report),
            json!({"initial_heartbeat": report.initial_heartbeat}),
            &at,
        ));
    }

    if failed_state.is_none() {
        if report.guided_mode.ok {
            entered.insert(
                "guided",
                (
                    "guided_ack_and_heartbeat_observed",
                    json!({
                        "request": "MAV_CMD_DO_SET_MODE",
                        "ack": report.guided_mode.command_ack,
                        "observed_heartbeat": report.guided_mode.observed_heartbeat,
                    }),
                ),
            );
            current_state = "guided".to_string();
            transitions.push(fsm_transition(
                plan,
                "runtime_ready",
                "guided",
                "guided_confirmed",
                "guided_ack_and_heartbeat_observed",
                true,
                None,
                json!({
                    "request_sent": true,
                    "ack": report.guided_mode.command_ack,
                    "observed_heartbeat": report.guided_mode.observed_heartbeat,
                }),
                &at,
            ));
        } else {
            failed_state = Some("guided".to_string());
            transitions.push(fsm_transition(
                plan,
                "runtime_ready",
                "guided",
                "guided_confirmed",
                guided_failure_reason(report),
                false,
                first_blocker(report),
                json!({
                    "request_sent": true,
                    "ack": report.guided_mode.command_ack,
                    "observed_heartbeat": report.guided_mode.observed_heartbeat,
                    "guided_blockers": report.guided_mode.blockers,
                }),
                &at,
            ));
        }
    }

    if failed_state.is_none() {
        if report.arm_ack.as_ref().is_some_and(|ack| ack.accepted) {
            entered.insert(
                "armed",
                (
                    "arm_ack_accepted",
                    json!({"request": "MAV_CMD_COMPONENT_ARM_DISARM", "ack": report.arm_ack}),
                ),
            );
            current_state = "armed".to_string();
            transitions.push(fsm_transition(
                plan,
                "guided",
                "armed",
                "arm_confirmed",
                "arm_ack_accepted",
                true,
                None,
                json!({"request_sent": true, "ack": report.arm_ack}),
                &at,
            ));
        } else {
            failed_state = Some("armed".to_string());
            transitions.push(fsm_transition(
                plan,
                "guided",
                "armed",
                "arm_confirmed",
                arm_failure_reason(report),
                false,
                first_blocker(report),
                json!({"request_sent": true, "ack": report.arm_ack}),
                &at,
            ));
        }
    }

    if failed_state.is_none() {
        entered.insert(
            "motor_spin_hold",
            (
                "armed_idle_hold_elapsed",
                json!({
                    "duration_sec": plan.motor_sec,
                    "motor_percent": plan.motor_percent,
                    "throttle_command_claim": report.throttle_command_claim,
                }),
            ),
        );
        current_state = "motor_spin_hold".to_string();
        transitions.push(fsm_transition(
            plan,
            "armed",
            "motor_spin_hold",
            "hold_started",
            "armed_idle_hold_elapsed",
            true,
            None,
            json!({
                "duration_sec": plan.motor_sec,
                "throttle_command_claim": report.throttle_command_claim,
            }),
            &at,
        ));

        if report.disarm_ack.as_ref().is_some_and(|ack| ack.accepted) {
            entered.insert(
                "disarmed",
                (
                    "disarm_ack_accepted",
                    json!({"request": "MAV_CMD_COMPONENT_ARM_DISARM", "ack": report.disarm_ack}),
                ),
            );
            transitions.push(fsm_transition(
                plan,
                "motor_spin_hold",
                "disarmed",
                "disarm_confirmed",
                "disarm_ack_accepted",
                true,
                None,
                json!({"request_sent": true, "ack": report.disarm_ack}),
                &at,
            ));
            entered.insert(
                "completed",
                (
                    "motor_debug_completed",
                    json!({"shutdown_claim": report.shutdown_claim, "no_takeoff": true}),
                ),
            );
            current_state = "completed".to_string();
            transitions.push(fsm_transition(
                plan,
                "disarmed",
                "completed",
                "task_completed",
                "motor_debug_completed",
                true,
                None,
                json!({"shutdown_claim": report.shutdown_claim, "landing_claim": "not_evaluated_no_takeoff"}),
                &at,
            ));
        } else {
            failed_state = Some("disarmed".to_string());
            transitions.push(fsm_transition(
                plan,
                "motor_spin_hold",
                "disarmed",
                "disarm_confirmed",
                disarm_failure_reason(report),
                false,
                first_blocker(report),
                json!({"request_sent": true, "ack": report.disarm_ack, "shutdown_claim": report.shutdown_claim}),
                &at,
            ));
        }
    }

    let states = motor_debug_fsm_states()
        .iter()
        .map(|state| {
            if let Some((reason, evidence)) = entered.get(state) {
                fsm_state(state, &at, reason, evidence.clone())
            } else {
                let reason = if failed_state.as_deref() == Some(*state) {
                    "blocked_before_entering"
                } else {
                    "not_reached_after_blocker"
                };
                fsm_state(state, "not_entered", reason, json!({}))
            }
        })
        .collect();

    navlab_fsm_summary(
        plan.task_id.clone(),
        "motor-debug",
        "",
        current_state,
        "actual",
        report.ok,
        report.blocked,
        states,
        transitions,
        report.blockers.clone(),
        failed_state,
    )
}

fn motor_debug_fsm_states() -> [&'static str; 6] {
    [
        "runtime_ready",
        "guided",
        "armed",
        "motor_spin_hold",
        "disarmed",
        "completed",
    ]
}

fn fsm_state(state: &str, entered_at: &str, reason: &str, evidence: Value) -> MotorDebugFsmState {
    let _ = evidence;
    navlab_fsm_state(
        state,
        state == "completed",
        reason == "blocked_before_entering",
        Some(format!("{entered_at}:{reason}")),
    )
}

fn fsm_transition(
    plan: &MotorDebugPlan,
    from_state: &str,
    to_state: &str,
    event: &str,
    reason_code: &str,
    ok: bool,
    blocker: Option<String>,
    evidence: Value,
    at: &str,
) -> MotorDebugFsmTransition {
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

fn first_blocker(report: &MotorDebugRuntimeReport) -> Option<String> {
    report.blockers.first().cloned()
}

fn guided_failure_reason(report: &MotorDebugRuntimeReport) -> &str {
    report
        .guided_mode
        .blockers
        .first()
        .map(String::as_str)
        .unwrap_or("motor_debug_guided_mode_not_confirmed")
}

fn arm_failure_reason(report: &MotorDebugRuntimeReport) -> &str {
    match &report.arm_ack {
        Some(ack) if !ack.accepted => "motor_debug_arm_rejected",
        None => "motor_debug_arm_ack_timeout",
        _ => "motor_debug_arm_not_confirmed",
    }
}

fn disarm_failure_reason(report: &MotorDebugRuntimeReport) -> &str {
    match &report.disarm_ack {
        Some(ack) if !ack.accepted => "motor_debug_disarm_rejected",
        None => "motor_debug_disarm_ack_timeout",
        _ => "motor_debug_disarm_not_confirmed",
    }
}

fn fsm_now() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "unknown".to_string())
}

fn ack_claim(ack: Option<&CommandAckEvaluation>) -> String {
    match ack {
        Some(ack) if ack.accepted => "accepted".to_string(),
        Some(ack) => format!("rejected:{}", ack.result_name),
        None => "not_requested".to_string(),
    }
}

fn runtime_acks(report: &MotorDebugRuntimeReport) -> Vec<Value> {
    let mut acks = Vec::new();
    if let Some(ack) = &report.guided_mode.command_ack {
        acks.push(json!({"stage": "guided_mode", "ack": ack}));
    }
    if let Some(ack) = &report.arm_ack {
        acks.push(json!({"stage": "arm", "ack": ack}));
    }
    if let Some(ack) = &report.disarm_ack {
        acks.push(json!({"stage": "disarm", "ack": ack}));
    }
    acks
}

pub fn evaluate_guided_mode(
    mode_mapping: &BTreeMap<String, u32>,
    observed_custom_modes: &[u32],
) -> GuidedModeEvaluation {
    let mapped_mode = mode_mapping.get(REQUIRED_GUIDED_MODE_NAME).copied();
    let observed_mode_id = observed_custom_modes.last().copied();
    let ok = observed_custom_modes.contains(&ARDUCOPTER_GUIDED_MODE_ID);
    let blockers = if ok {
        Vec::new()
    } else {
        vec![format!(
            "motor_debug_guided_mode_not_observed:{}",
            REQUIRED_GUIDED_MODE_NAME
        )]
    };

    GuidedModeEvaluation {
        ok,
        mode_name: REQUIRED_GUIDED_MODE_NAME.to_string(),
        mode_id: ARDUCOPTER_GUIDED_MODE_ID,
        mode_mapping_has_mode: mapped_mode.is_some(),
        mode_mapping_mode_id: mapped_mode,
        observed_mode_id,
        blockers,
    }
}

pub fn motor_debug_command_plan() -> MotorDebugCommandPlan {
    MotorDebugCommandPlan {
        guided_mode_id: ARDUCOPTER_GUIDED_MODE_ID,
        arm_command: arm_disarm_command(1, 0, true),
        disarm_command: arm_disarm_command(1, 0, false),
    }
}

pub fn arm_disarm_command(
    target_system: u8,
    target_component: u8,
    arm: bool,
) -> MotorDebugCommandLong {
    MotorDebugCommandLong {
        target_system,
        target_component,
        command: MAV_CMD_COMPONENT_ARM_DISARM,
        confirmation: 0,
        param1: if arm { 1.0 } else { 0.0 },
        param2: 0.0,
        param3: 0.0,
        param4: 0.0,
        param5: 0.0,
        param6: 0.0,
        param7: 0.0,
    }
}

pub fn evaluate_command_ack(
    command: u32,
    result: u32,
    result_param2: u32,
    status_text: Vec<MavlinkStatusText>,
) -> CommandAckEvaluation {
    CommandAckEvaluation {
        command,
        result,
        result_name: mav_result_name(result),
        accepted: result == MAV_RESULT_ACCEPTED,
        result_param2,
        status_text,
    }
}

pub fn command_rejection_blockers(prefix: &str, ack: &CommandAckEvaluation) -> Vec<String> {
    if ack.accepted {
        return Vec::new();
    }

    let mut blockers = vec![format!("{}:{}", prefix, ack.result_name)];
    blockers.extend(
        ack.status_text
            .iter()
            .map(|status| format!("{}_status:{}", prefix, status.text)),
    );
    blockers
}

fn mav_result_name(result: u32) -> String {
    match result {
        MAV_RESULT_ACCEPTED => "MAV_RESULT_ACCEPTED".to_string(),
        MAV_RESULT_FAILED => "MAV_RESULT_FAILED".to_string(),
        1 => "MAV_RESULT_TEMPORARILY_REJECTED".to_string(),
        2 => "MAV_RESULT_DENIED".to_string(),
        3 => "MAV_RESULT_UNSUPPORTED".to_string(),
        5 => "MAV_RESULT_IN_PROGRESS".to_string(),
        6 => "MAV_RESULT_CANCELLED".to_string(),
        value => format!("MAV_RESULT_UNKNOWN_{value}"),
    }
}

fn resolve_summary_path(project: &ProjectConfig, options: &RunOptions) -> PathBuf {
    if let Some(path) = &options.summary_path {
        return path.clone();
    }
    resolve_artifact_dir(project, options).join("summary.json")
}

fn resolve_artifact_dir(project: &ProjectConfig, options: &RunOptions) -> PathBuf {
    if let Some(path) = &options.summary_path {
        if let Some(parent) = path.parent() {
            return parent.to_path_buf();
        }
    }
    options.artifact_dir.clone().unwrap_or_else(|| {
        project
            .paths
            .artifact_root
            .join("motor-debug")
            .join(run_id())
    })
}

fn write_runtime_summary(path: &Path, summary: &MotorDebugRuntimeSummary) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create motor-debug artifact dir {}", parent.display()))?;
    }
    fs::write(path, serde_json::to_string_pretty(summary)?)
        .with_context(|| format!("write motor-debug runtime summary {}", path.display()))
}

fn attach_navlab_fsm_artifact(
    artifact_dir: &Path,
    run_id: &str,
    plan: &MotorDebugPlan,
    summary: &mut MotorDebugRuntimeSummary,
) -> Result<()> {
    let fsm = build_fsm_for_summary(plan, summary);
    let (_fsm_summary, reference) = write_navlab_fsm_artifact(artifact_dir, &fsm, run_id)?;
    summary.fsm_artifacts = vec![reference];
    Ok(())
}

fn build_fsm_for_summary(
    plan: &MotorDebugPlan,
    summary: &MotorDebugRuntimeSummary,
) -> MotorDebugFsmSummary {
    if let Some(report) = summary.runtime_report.as_ref() {
        return build_actual_fsm(plan, report);
    }
    if summary.ok && summary.claim == "dry_run_plan_only" {
        return build_planned_fsm(plan);
    }
    build_not_started_fsm(plan, &summary.claim, &summary.blockers)
}

fn write_task_plan(
    artifact_dir: &Path,
    project: &ProjectConfig,
    task: &TaskConfig,
    plan: &MotorDebugPlan,
) -> Result<()> {
    let run_id = run_id_from_artifact_dir(artifact_dir);
    let value = json!({
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
    });
    contracts::write_json(
        &artifact_dir.join("task_plan.json"),
        &value,
        "real motor-debug task plan",
    )
}

fn write_workflow_summary(artifact_dir: &Path, workflow: &RealWorkflowSummary) -> Result<()> {
    let value = serde_json::to_value(workflow).unwrap_or_else(|_| json!({}));
    contracts::write_json(
        &artifact_dir.join("dag").join("workflow_summary.json"),
        &value,
        "real motor-debug workflow summary",
    )
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
        "real task request",
    )
}

fn write_task_result(
    summary_path: &Path,
    project: &ProjectConfig,
    plan: &MotorDebugPlan,
    summary: &MotorDebugRuntimeSummary,
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
        mavlink_acks: mavlink_ack_contracts(summary),
        details: serde_json::to_value(summary).unwrap_or_else(|_| json!({})),
    });
    contracts::write_json(
        &artifact_dir.join("task_result.json"),
        &result,
        "real motor-debug task result",
    )
}

fn mavlink_ack_contracts(summary: &MotorDebugRuntimeSummary) -> Vec<Value> {
    summary
        .acks
        .iter()
        .filter_map(|entry| {
            let stage = entry
                .get("stage")
                .and_then(Value::as_str)
                .unwrap_or("unknown");
            let ack = entry.get("ack")?;
            let result = ack
                .get("result_name")
                .and_then(Value::as_str)
                .unwrap_or("UNKNOWN");
            let result_code = ack
                .get("result")
                .and_then(Value::as_u64)
                .and_then(|value| u32::try_from(value).ok())
                .unwrap_or_default();
            let accepted = ack
                .get("accepted")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            let statustext = ack
                .get("status_text")
                .and_then(Value::as_array)
                .and_then(|items| items.first())
                .and_then(|item| item.get("text"))
                .and_then(Value::as_str)
                .unwrap_or("");
            Some(contracts::mavlink_ack(
                mavlink_ack_command(stage),
                result,
                result_code,
                accepted,
                "GUIDED",
                "GUIDED",
                statustext,
            ))
        })
        .collect()
}

fn mavlink_ack_command(stage: &str) -> &'static str {
    match stage {
        "guided_mode" => "SET_GUIDED",
        "arm" => "ARM",
        "disarm" => "DISARM",
        _ => "UNKNOWN",
    }
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

fn unsigned_or_default(value: Option<&Value>, default: u32) -> u32 {
    value
        .and_then(Value::as_u64)
        .and_then(|value| u32::try_from(value).ok())
        .unwrap_or(default)
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
    use rstest::rstest;
    use serde_json::json;

    fn task_config() -> TaskConfig {
        TaskConfig {
            id: "motor-debug".to_string(),
            family: "real".to_string(),
            description: "test".to_string(),
            capabilities: vec![],
            task: serde_json::from_value(json!({
                "motor_percent": 5.0,
                "motor_sec": 5.0,
                "motor_count": 4
            }))
            .expect("task map"),
            safety: serde_json::from_value(json!({
                "confirm_manual_takeover": true,
                "confirm_kill_switch": true,
                "confirm_safe_area": true,
                "confirm_no_props": true
            }))
            .expect("safety map"),
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
            preflight: PreflightConfig::default(),
            prepare: PrepareConfig::default(),
            common_doctor: CommonDoctorConfig::default(),
            task_doctor: TaskDoctorConfig::default(),
        }
    }

    #[test]
    fn motor_debug_plan_uses_cli_overrides() {
        let plan = build_plan(
            &task_config(),
            MotorDebugOverrides {
                motor_percent: Some(6.0),
                motor_sec: Some(2.0),
                motor_count: Some(3),
            },
        )
        .expect("plan");
        assert_eq!(plan.motor_percent, 6.0);
        assert_eq!(plan.motor_sec, 2.0);
        assert_eq!(plan.motor_count, 3);
    }

    #[test]
    fn motor_debug_plan_json_contract_is_stable() {
        let plan = build_plan(
            &task_config(),
            MotorDebugOverrides {
                motor_percent: Some(6.0),
                motor_sec: Some(2.0),
                motor_count: Some(4),
            },
        )
        .expect("plan");

        insta::assert_json_snapshot!(plan, @r###"
        {
          "task_id": "motor-debug",
          "motor_percent": 6.0,
          "motor_sec": 2.0,
          "motor_count": 4,
          "safety": {
            "confirm_manual_takeover": true,
            "confirm_kill_switch": true,
            "confirm_safe_area": true,
            "confirm_no_props": true
          },
          "claim": "dry_run_plan"
        }
        "###);
    }

    #[test]
    fn motor_debug_operator_safety_blocks_missing_confirmations() {
        let plan = build_plan(&task_config(), MotorDebugOverrides::default()).expect("plan");
        let safety = evaluate_operator_safety(&plan, &OperatorConfirmations::default());

        assert!(!safety.ok);
        assert_eq!(
            safety.blockers,
            vec![
                "operator_manual_takeover_not_confirmed",
                "operator_kill_switch_not_confirmed",
                "operator_safe_area_not_confirmed",
                "operator_no_props_not_confirmed"
            ]
        );
    }

    #[test]
    fn motor_debug_operator_safety_passes_with_all_confirmations() {
        let plan = build_plan(&task_config(), MotorDebugOverrides::default()).expect("plan");
        let safety = evaluate_operator_safety(
            &plan,
            &OperatorConfirmations {
                manual_takeover: true,
                kill_switch: true,
                safe_area: true,
                no_props: true,
                props_installed: false,
            },
        );

        assert!(safety.ok);
        assert!(safety.blockers.is_empty());
    }

    #[test]
    fn motor_debug_mavlink_router_endpoint_matches_python_policy() {
        let mut project = project();

        project.prepare.mavlink_router_local_endpoint = "127.0.0.1:14550".to_string();
        assert_eq!(mavlink_router_endpoint(&project), "udpin:127.0.0.1:14550");

        project.prepare.mavlink_router_local_endpoint = "tcp:127.0.0.1:14550".to_string();
        assert_eq!(mavlink_router_endpoint(&project), "tcp:127.0.0.1:14550");

        project.prepare.mavlink_router_local_endpoint = ":14555".to_string();
        assert_eq!(mavlink_router_endpoint(&project), "udpin:127.0.0.1:14555");
    }

    #[test]
    fn motor_debug_runtime_not_migrated_summary_contract_is_stable() {
        let plan = build_plan(
            &task_config(),
            MotorDebugOverrides {
                motor_percent: Some(6.0),
                motor_sec: Some(2.0),
                motor_count: Some(4),
            },
        )
        .expect("plan");
        let summary = build_runtime_not_migrated_summary(&project(), &plan);
        let fsm = build_fsm_for_summary(&plan, &summary);
        assert_eq!(fsm.mode, "blocked_before_runtime");
        assert_eq!(fsm.failed_state.as_deref(), Some("runtime_ready"));
        assert_eq!(fsm.transitions[0].to_state, "guided");
        assert_eq!(summary.schema_version, TASK_RESULT_SCHEMA_VERSION);
        assert!(!summary.ok);
        assert!(summary.blocked);
        assert_eq!(
            summary.blockers,
            vec!["motor_debug_rust_mavlink_runtime_not_migrated"]
        );
        assert_eq!(summary.task, "motor-debug");
        assert_eq!(summary.claim, "runtime_blocked_not_migrated");
        assert!(summary.no_takeoff);
        assert!(summary.requires_no_props);
        assert_eq!(summary.required_mode, "GUIDED");
        assert_eq!(summary.spin_mode, "armed_idle");
        assert_eq!(summary.throttle_command_claim, "not_sent");
        assert_eq!(summary.motor_percent, 6.0);
        assert_eq!(summary.motor_sec, 2.0);
        assert_eq!(summary.motor_count, 4);
        assert_eq!(summary.steps.len(), 3);
        assert_eq!(summary.shutdown, "send_disarm_after_idle_spin");
        assert_eq!(summary.landing_claim, "not_evaluated_no_takeoff");
        assert_eq!(summary.arm_claim, "not_requested");
        assert_eq!(summary.takeoff_claim, "not_evaluated");
        assert_eq!(summary.guided_mode_claim, "not_evaluated");
        assert_eq!(summary.shutdown_claim, "not_evaluated");
        assert_eq!(
            summary.command_plan.guided_mode_id,
            ARDUCOPTER_GUIDED_MODE_ID
        );
        assert!(summary.acks.is_empty());
        assert!(summary.runtime_report.is_none());
    }

    #[tokio::test]
    async fn motor_debug_dry_run_writes_plan_workflow_summary_and_result() {
        let temp = tempfile::tempdir().expect("tempdir");
        let task = MotorDebugTask;
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
        assert_eq!(summary["ok"], true);
        assert_eq!(summary["claim"], "dry_run_plan_only");
        assert_eq!(summary["workflow"]["nodes"][0]["id"], "preflight");
        assert_eq!(summary["workflow"]["nodes"][4]["id"], "runtime-execute");
        let fsm: Value = serde_json::from_str(
            &fs::read_to_string(
                temp.path()
                    .join("runtime")
                    .join("task_motor_debug_fsm.json"),
            )
            .expect("fsm"),
        )
        .expect("fsm json");
        assert_eq!(fsm["schema_version"], "navlab.fsm.v1");
        assert_eq!(fsm["mode"], "planned");
        assert_eq!(fsm["states"][0]["state"], "runtime_ready");
        assert_eq!(fsm["transitions"][0]["from_state"], "runtime_ready");
        assert_eq!(fsm["transitions"][0]["to_state"], "guided");
        assert_eq!(fsm["transitions"][2]["to_state"], "motor_spin_hold");
    }

    #[test]
    fn motor_debug_runtime_summary_derives_actual_fsm() {
        let plan = build_plan(&task_config(), MotorDebugOverrides::default()).expect("plan");
        let summary = build_runtime_summary(&project(), &plan, successful_runtime_report());
        let fsm = build_fsm_for_summary(&plan, &summary);

        assert_eq!(fsm.mode, "actual");
        assert!(fsm.ok);
        assert_eq!(fsm.state, "completed");
        assert_eq!(fsm.failed_state, None);
        assert_eq!(
            fsm.states
                .iter()
                .map(|state| state.state.as_str())
                .collect::<Vec<_>>(),
            vec![
                "runtime_ready",
                "guided",
                "armed",
                "motor_spin_hold",
                "disarmed",
                "completed"
            ]
        );
        assert_eq!(fsm.transitions.len(), 5);
        assert_eq!(fsm.transitions[1].from_state, "guided");
        assert_eq!(fsm.transitions[1].to_state, "armed");
        assert_eq!(
            fsm.transitions[1].reason_code.as_deref(),
            Some("arm_ack_accepted")
        );
    }

    #[test]
    fn motor_debug_runtime_summary_fsm_points_to_failed_state() {
        let plan = build_plan(&task_config(), MotorDebugOverrides::default()).expect("plan");
        let mut report = successful_runtime_report();
        report.ok = false;
        report.blocked = true;
        report.blockers = vec!["motor_debug_arm_rejected:MAV_RESULT_FAILED".to_string()];
        report.arm_ack = Some(evaluate_command_ack(
            MAV_CMD_COMPONENT_ARM_DISARM,
            MAV_RESULT_FAILED,
            0,
            Vec::new(),
        ));
        report.disarm_ack = None;
        report.shutdown_claim = "not_requested".to_string();
        report.throttle_command_claim = "not_sent".to_string();

        let summary = build_runtime_summary(&project(), &plan, report);
        let fsm = build_fsm_for_summary(&plan, &summary);

        assert!(!fsm.ok);
        assert_eq!(fsm.state, "guided");
        assert_eq!(fsm.failed_state.as_deref(), Some("armed"));
        let failed = fsm.transitions.last().expect("failed transition");
        assert_eq!(failed.from_state, "guided");
        assert_eq!(failed.to_state, "armed");
        assert_eq!(
            failed.reason_code.as_deref(),
            Some("motor_debug_arm_rejected")
        );
    }

    #[tokio::test]
    async fn motor_debug_operator_safety_block_writes_summary_before_error() {
        let temp = tempfile::tempdir().expect("tempdir");
        let task = MotorDebugTask;
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

        assert!(error.to_string().contains("summary written to"));
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
        assert_eq!(summary["ok"], false);
        assert_eq!(summary["claim"], "blocked_by_operator_safety");
        assert_eq!(summary["workflow"]["nodes"][4]["id"], "runtime-execute");
        assert_eq!(
            summary["workflow"]["nodes"][4]["blockers"][0],
            "operator_manual_takeover_not_confirmed"
        );
        assert_eq!(
            summary["workflow"]["nodes"][5]["skip_reason"],
            "blocked_by_dependency:runtime-execute"
        );
        let fsm: Value = serde_json::from_str(
            &fs::read_to_string(
                temp.path()
                    .join("runtime")
                    .join("task_motor_debug_fsm.json"),
            )
            .expect("fsm"),
        )
        .expect("fsm json");
        assert_eq!(fsm["failed_state"], "runtime_ready");
    }

    fn successful_runtime_report() -> MotorDebugRuntimeReport {
        let heartbeat = crate::runtime::MavlinkHeartbeat {
            system_id: 1,
            component_id: 1,
            custom_mode: ARDUCOPTER_GUIDED_MODE_ID,
            base_mode_bits: 1,
        };
        MotorDebugRuntimeReport {
            ok: true,
            blocked: false,
            blockers: Vec::new(),
            connection_endpoint: "udpin:127.0.0.1:14550".to_string(),
            target_system: 1,
            target_component: 0,
            initial_heartbeat: Some(crate::runtime::MavlinkHeartbeat {
                custom_mode: 0,
                ..heartbeat.clone()
            }),
            guided_mode: crate::runtime::GuidedModeRuntimeReport {
                ok: true,
                mode_id: ARDUCOPTER_GUIDED_MODE_ID,
                command_ack: Some(evaluate_command_ack(
                    mavlink::dialects::ardupilotmega::MavCmd::MAV_CMD_DO_SET_MODE as u32,
                    MAV_RESULT_ACCEPTED,
                    0,
                    Vec::new(),
                )),
                observed_heartbeat: Some(heartbeat),
                blockers: Vec::new(),
            },
            arm_ack: Some(evaluate_command_ack(
                MAV_CMD_COMPONENT_ARM_DISARM,
                MAV_RESULT_ACCEPTED,
                0,
                Vec::new(),
            )),
            disarm_ack: Some(evaluate_command_ack(
                MAV_CMD_COMPONENT_ARM_DISARM,
                MAV_RESULT_ACCEPTED,
                0,
                Vec::new(),
            )),
            shutdown_claim: "disarm_accepted".to_string(),
            throttle_command_claim: "not_sent_armed_idle_only".to_string(),
        }
    }

    #[test]
    fn motor_debug_guided_mode_evaluation_uses_arducopter_guided_id() {
        let mapping = BTreeMap::from([(REQUIRED_GUIDED_MODE_NAME.to_string(), 15)]);

        let result = evaluate_guided_mode(&mapping, &[0, ARDUCOPTER_GUIDED_MODE_ID]);

        assert!(result.ok);
        assert_eq!(result.mode_id, ARDUCOPTER_GUIDED_MODE_ID);
        assert_eq!(result.mode_mapping_mode_id, Some(15));
        assert_eq!(result.observed_mode_id, Some(ARDUCOPTER_GUIDED_MODE_ID));
        assert!(result.blockers.is_empty());
    }

    #[test]
    fn motor_debug_guided_mode_evaluation_blocks_when_guided_is_not_observed() {
        let mapping = BTreeMap::from([("STABILIZE".to_string(), 0)]);

        let result = evaluate_guided_mode(&mapping, &[0]);

        assert!(!result.ok);
        assert!(!result.mode_mapping_has_mode);
        assert_eq!(result.mode_mapping_mode_id, None);
        assert_eq!(result.observed_mode_id, Some(0));
        assert_eq!(
            result.blockers,
            vec!["motor_debug_guided_mode_not_observed:GUIDED"]
        );
    }

    #[test]
    fn motor_debug_command_plan_matches_python_arm_disarm_policy() {
        let plan = motor_debug_command_plan();

        assert_eq!(plan.guided_mode_id, 4);
        assert_eq!(plan.arm_command.command, MAV_CMD_COMPONENT_ARM_DISARM);
        assert_eq!(plan.arm_command.param1, 1.0);
        assert_eq!(plan.arm_command.param2, 0.0);
        assert_eq!(plan.disarm_command.command, MAV_CMD_COMPONENT_ARM_DISARM);
        assert_eq!(plan.disarm_command.param1, 0.0);
        assert_eq!(plan.disarm_command.param2, 0.0);
    }

    #[test]
    fn motor_debug_command_ack_blockers_include_result_and_statustext() {
        let ack = evaluate_command_ack(
            MAV_CMD_COMPONENT_ARM_DISARM,
            MAV_RESULT_FAILED,
            0,
            vec![MavlinkStatusText {
                severity: 3,
                text: "PreArm: safety switch".to_string(),
            }],
        );

        let blockers = command_rejection_blockers("motor_debug_arm_rejected", &ack);

        assert!(!ack.accepted);
        assert_eq!(ack.result_name, "MAV_RESULT_FAILED");
        assert_eq!(
            blockers,
            vec![
                "motor_debug_arm_rejected:MAV_RESULT_FAILED",
                "motor_debug_arm_rejected_status:PreArm: safety switch"
            ]
        );
    }

    #[rstest]
    #[case::bad_percent(
        MotorDebugOverrides {
            motor_percent: Some(0.0),
            ..MotorDebugOverrides::default()
        },
        "motor_percent must be positive"
    )]
    #[case::bad_duration(
        MotorDebugOverrides {
            motor_sec: Some(0.0),
            ..MotorDebugOverrides::default()
        },
        "motor_sec must be positive"
    )]
    #[case::bad_motor_count(
        MotorDebugOverrides {
            motor_count: Some(0),
            ..MotorDebugOverrides::default()
        },
        "motor_count must be positive"
    )]
    fn motor_debug_plan_rejects_invalid_values(
        #[case] overrides: MotorDebugOverrides,
        #[case] expected: &str,
    ) {
        let error = build_plan(&task_config(), overrides).expect_err("invalid plan");

        assert_eq!(error.to_string(), expected);
    }
}
