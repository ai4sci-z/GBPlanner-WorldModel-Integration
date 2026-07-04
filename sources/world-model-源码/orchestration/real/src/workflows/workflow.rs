use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

use crate::workflows::doctor_chain::DoctorChainSummary;

pub const REAL_WORKFLOW_SCHEMA_VERSION: &str = "navlab.real.workflow.v1";

#[derive(Debug, Clone, Serialize)]
pub struct WorkflowNodeResult {
    pub id: String,
    pub kind: String,
    pub deps: Vec<String>,
    pub required: bool,
    pub mode: String,
    pub domain: String,
    pub side_effect_policy: String,
    pub summary_path: String,
    pub artifact_paths: Vec<String>,
    pub status: String,
    pub ok: bool,
    pub blocked: bool,
    pub skipped: bool,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub skip_reason: String,
    pub blockers: Vec<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub warnings: Vec<String>,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub artifacts: BTreeMap<String, String>,
    pub evidence: serde_json::Value,
    pub started_at: String,
    pub finished_at: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RealWorkflowSummary {
    pub schema_version: String,
    pub task_id: String,
    pub run_id: String,
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub nodes: Vec<WorkflowNodeResult>,
    pub created_at: String,
}

impl RealWorkflowSummary {
    pub fn from_nodes(
        task_id: impl Into<String>,
        run_id: impl Into<String>,
        nodes: Vec<WorkflowNodeResult>,
    ) -> Self {
        let nodes = apply_workflow_dependencies(nodes);
        let blockers = blockers_from_nodes(&nodes);
        Self {
            schema_version: REAL_WORKFLOW_SCHEMA_VERSION.to_string(),
            task_id: task_id.into(),
            run_id: run_id.into(),
            ok: blockers.is_empty(),
            blocked: !blockers.is_empty(),
            blockers,
            nodes,
            created_at: utc_now(),
        }
    }
}

pub fn workflow_from_doctor_chain(
    task_id: &str,
    run_id: &str,
    chain: &DoctorChainSummary,
    include_runtime_node: bool,
) -> RealWorkflowSummary {
    if include_runtime_node && !chain.ok {
        let mut workflow = workflow_from_doctor_chain_with_runtime(task_id, run_id, chain, None);
        workflow.nodes.push(not_reached_node(
            "runtime-execute",
            "runtime-execute",
            vec!["task-doctor.json"],
            vec!["summary.json", "task_result.json"],
            "blocked_before_runtime_by_upstream_workflow",
        ));
        workflow.nodes.push(not_reached_node(
            "gate-evaluate",
            "gate-evaluate",
            vec!["summary.json", "task_result.json"],
            vec!["summary.json"],
            "blocked_before_gate_by_upstream_workflow",
        ));
        RealWorkflowSummary::from_nodes(task_id, run_id, workflow.nodes)
    } else {
        workflow_from_doctor_chain_with_runtime(
            task_id,
            run_id,
            chain,
            include_runtime_node.then_some((true, Vec::new(), "ready_to_execute")),
        )
    }
}

pub fn workflow_from_doctor_chain_with_runtime(
    task_id: &str,
    run_id: &str,
    chain: &DoctorChainSummary,
    runtime: Option<(bool, Vec<String>, &str)>,
) -> RealWorkflowSummary {
    let mut nodes = Vec::new();
    nodes.push(node(
        "preflight",
        "preflight",
        chain.preflight.ok,
        chain.preflight.blockers.clone(),
        vec!["project_config"],
        vec!["preflight.json", "doctor_result.json"],
        serde_json::json!({
            "claim": chain.preflight.preflight_claim,
            "runtime_mode": chain.preflight.runtime_mode,
            "runtime_backend": chain.preflight.runtime_backend,
        }),
    ));
    nodes.push(optional_node(
        "prepare",
        "prepare",
        chain.prepare.as_ref().map(|summary| {
            (
                summary.ok,
                summary.blockers.clone(),
                serde_json::json!({
                    "claim": summary.prepare_claim,
                    "dry_run": summary.dry_run,
                    "service_count": summary.service_count,
                }),
            )
        }),
        vec!["preflight.json"],
        vec!["prepare.json"],
    ));
    nodes.push(optional_node(
        "common-doctor",
        "common-doctor",
        chain.common_doctor.as_ref().map(|summary| {
            (
                summary.ok,
                summary.blockers.clone(),
                serde_json::json!({
                    "fcu_bridge_mode": summary.fcu_bridge_mode,
                    "common_mode": summary.common_state.mode,
                }),
            )
        }),
        vec!["prepare.json"],
        vec!["common-doctor.json", "upstream.json"],
    ));
    nodes.push(optional_node(
        "task-doctor",
        "task-doctor",
        chain.task_doctor.as_ref().map(|summary| {
            (
                summary.ok,
                summary.blockers.clone(),
                serde_json::json!({
                    "claim": summary.task_doctor_claim,
                    "fcu_bridge_mode": summary.fcu_bridge_mode,
                }),
            )
        }),
        vec!["common-doctor.json", "upstream.json"],
        vec!["task-doctor.json"],
    ));
    if let Some((runtime_ok, runtime_blockers, runtime_claim)) = runtime {
        if runtime_claim.starts_with("dry_run_") {
            nodes.push(not_reached_node(
                "runtime-execute",
                "runtime-execute",
                vec!["task-doctor.json"],
                vec!["summary.json", "task_result.json"],
                runtime_claim,
            ));
        } else {
            nodes.push(node(
                "runtime-execute",
                "runtime-execute",
                runtime_ok,
                runtime_blockers,
                vec!["task-doctor.json"],
                vec!["summary.json", "task_result.json"],
                serde_json::json!({
                    "claim": runtime_claim
                }),
            ));
        }
    }
    nodes.push(not_reached_node(
        "gate-evaluate",
        "gate-evaluate",
        vec!["summary.json", "task_result.json"],
        vec!["summary.json"],
        "gate_evaluate_not_configured_for_real_task",
    ));
    RealWorkflowSummary::from_nodes(task_id, run_id, nodes)
}

pub fn dry_run_workflow(task_id: &str, run_id: &str) -> RealWorkflowSummary {
    dry_run_workflow_with_runtime_claim(task_id, run_id, "dry_run_no_motor_side_effect")
}

pub fn dry_run_workflow_with_runtime_claim(
    task_id: &str,
    run_id: &str,
    runtime_claim: &str,
) -> RealWorkflowSummary {
    RealWorkflowSummary::from_nodes(
        task_id,
        run_id,
        vec![
            node(
                "preflight",
                "preflight",
                true,
                Vec::new(),
                vec!["project_config"],
                vec!["preflight.json"],
                serde_json::json!({"claim": "planned_not_sampled_in_task_dry_run"}),
            ),
            node(
                "prepare",
                "prepare",
                true,
                Vec::new(),
                vec!["preflight.json"],
                vec!["prepare.json"],
                serde_json::json!({"claim": "planned_not_started_in_task_dry_run"}),
            ),
            node(
                "common-doctor",
                "common-doctor",
                true,
                Vec::new(),
                vec!["prepare.json"],
                vec!["common-doctor.json"],
                serde_json::json!({"claim": "planned_not_sampled_in_task_dry_run"}),
            ),
            node(
                "task-doctor",
                "task-doctor",
                true,
                Vec::new(),
                vec!["common-doctor.json"],
                vec!["task-doctor.json"],
                serde_json::json!({"claim": "planned_not_sampled_in_task_dry_run"}),
            ),
            not_reached_node(
                "runtime-execute",
                "runtime-execute",
                vec!["task_plan.json"],
                vec!["summary.json", "task_result.json"],
                runtime_claim,
            ),
            not_reached_node(
                "gate-evaluate",
                "gate-evaluate",
                vec!["summary.json", "task_result.json"],
                vec!["summary.json"],
                "gate_evaluate_not_executed_in_task_dry_run",
            ),
        ],
    )
}

pub fn runtime_workflow(
    task_id: &str,
    run_id: &str,
    ok: bool,
    blockers: Vec<String>,
    claim: &str,
) -> RealWorkflowSummary {
    RealWorkflowSummary::from_nodes(
        task_id,
        run_id,
        vec![
            node(
                "preflight",
                "preflight",
                true,
                Vec::new(),
                vec!["project_config"],
                vec!["preflight.json"],
                serde_json::json!({"claim": "planned_not_sampled_without_doctor_chain"}),
            ),
            node(
                "prepare",
                "prepare",
                true,
                Vec::new(),
                vec!["preflight.json"],
                vec!["prepare.json"],
                serde_json::json!({"claim": "planned_not_started_without_doctor_chain"}),
            ),
            node(
                "common-doctor",
                "common-doctor",
                true,
                Vec::new(),
                vec!["prepare.json"],
                vec!["common-doctor.json"],
                serde_json::json!({"claim": "planned_not_sampled_without_doctor_chain"}),
            ),
            node(
                "task-doctor",
                "task-doctor",
                true,
                Vec::new(),
                vec!["common-doctor.json"],
                vec!["task-doctor.json"],
                serde_json::json!({"claim": "planned_not_sampled_without_doctor_chain"}),
            ),
            node(
                "runtime-execute",
                "runtime-execute",
                ok,
                blockers,
                vec!["task_plan.json"],
                vec!["summary.json", "task_result.json"],
                serde_json::json!({"claim": claim}),
            ),
            not_reached_node(
                "gate-evaluate",
                "gate-evaluate",
                vec!["summary.json", "task_result.json"],
                vec!["summary.json"],
                "gate_evaluate_not_configured_for_real_task",
            ),
        ],
    )
}

fn optional_node(
    node_id: &str,
    stage: &str,
    result: Option<(bool, Vec<String>, serde_json::Value)>,
    inputs: Vec<&str>,
    outputs: Vec<&str>,
) -> WorkflowNodeResult {
    match result {
        Some((ok, blockers, evidence)) => {
            node(node_id, stage, ok, blockers, inputs, outputs, evidence)
        }
        None => not_reached_node(
            node_id,
            stage,
            inputs,
            outputs,
            "upstream_node_blocked_before_this_stage",
        ),
    }
}

fn not_reached_node(
    node_id: &str,
    stage: &str,
    inputs: Vec<&str>,
    outputs: Vec<&str>,
    claim: &str,
) -> WorkflowNodeResult {
    let mode = if claim.contains("dry_run") {
        "dry_run"
    } else {
        "live"
    };
    WorkflowNodeResult {
        id: node_id.to_string(),
        kind: stage.to_string(),
        deps: workflow_deps(node_id),
        required: true,
        mode: mode.to_string(),
        domain: "real".to_string(),
        side_effect_policy: side_effect_policy(stage).to_string(),
        summary_path: summary_path(&outputs),
        artifact_paths: strings(outputs.clone()),
        status: "skipped".to_string(),
        ok: false,
        blocked: false,
        skipped: true,
        skip_reason: claim.to_string(),
        blockers: Vec::new(),
        warnings: Vec::new(),
        inputs: strings(inputs),
        outputs: strings(outputs.clone()),
        artifacts: artifacts_from_outputs(&outputs),
        evidence: serde_json::json!({"claim": claim}),
        started_at: utc_now(),
        finished_at: utc_now(),
        created_at: utc_now(),
    }
}

fn node(
    node_id: &str,
    stage: &str,
    ok: bool,
    blockers: Vec<String>,
    inputs: Vec<&str>,
    outputs: Vec<&str>,
    evidence: serde_json::Value,
) -> WorkflowNodeResult {
    let status = if blockers.is_empty() && ok {
        "ok".to_string()
    } else {
        "blocked".to_string()
    };
    WorkflowNodeResult {
        id: node_id.to_string(),
        kind: stage.to_string(),
        deps: workflow_deps(node_id),
        required: true,
        mode: "live".to_string(),
        domain: "real".to_string(),
        side_effect_policy: side_effect_policy(stage).to_string(),
        summary_path: summary_path(&outputs),
        artifact_paths: strings(outputs.clone()),
        status,
        ok,
        blocked: !blockers.is_empty(),
        skipped: false,
        skip_reason: String::new(),
        blockers,
        warnings: Vec::new(),
        inputs: strings(inputs),
        outputs: strings(outputs.clone()),
        artifacts: artifacts_from_outputs(&outputs),
        evidence,
        started_at: utc_now(),
        finished_at: utc_now(),
        created_at: utc_now(),
    }
}

fn apply_workflow_dependencies(nodes: Vec<WorkflowNodeResult>) -> Vec<WorkflowNodeResult> {
    let mut blocked = BTreeSet::new();
    let mut result = Vec::with_capacity(nodes.len());
    for mut node in nodes {
        if node.required {
            if let Some(dep) = node.deps.iter().find(|dep| blocked.contains(*dep)).cloned() {
                node.status = "skipped".to_string();
                node.ok = false;
                node.blocked = false;
                node.skipped = true;
                node.skip_reason = format!("blocked_by_dependency:{dep}");
                node.blockers.clear();
                if let serde_json::Value::Object(ref mut object) = node.evidence {
                    object.insert(
                        "skip_reason".to_string(),
                        serde_json::Value::String(node.skip_reason.clone()),
                    );
                }
            }
        }
        if node.blocked {
            blocked.insert(node.id.clone());
        }
        result.push(node);
    }
    result
}

fn blockers_from_nodes(nodes: &[WorkflowNodeResult]) -> Vec<String> {
    let mut seen = BTreeSet::new();
    let mut result = Vec::new();
    for node in nodes {
        for blocker in &node.blockers {
            let value = format!("{}:{}", node.id, blocker);
            if seen.insert(value.clone()) {
                result.push(value);
            }
        }
    }
    result
}

fn workflow_deps(node_id: &str) -> Vec<String> {
    match node_id {
        "prepare" => strings(vec!["preflight"]),
        "common-doctor" => strings(vec!["prepare"]),
        "task-doctor" => strings(vec!["common-doctor"]),
        "runtime-execute" => strings(vec!["task-doctor"]),
        "gate-evaluate" => strings(vec!["runtime-execute"]),
        _ => Vec::new(),
    }
}

fn side_effect_policy(stage: &str) -> &str {
    match stage {
        "preflight" | "common-doctor" | "task-doctor" | "gate-evaluate" => "none",
        "prepare" => "prepare_resource",
        "runtime-execute" => "hardware_command",
        _ => "none",
    }
}

fn summary_path(outputs: &[&str]) -> String {
    artifacts_from_outputs(outputs)
        .get("summary")
        .cloned()
        .or_else(|| outputs.first().map(|value| value.to_string()))
        .unwrap_or_default()
}

fn artifacts_from_outputs(outputs: &[&str]) -> BTreeMap<String, String> {
    let mut artifacts = BTreeMap::new();
    for output in outputs {
        match output.rsplit('/').next().unwrap_or(output) {
            "preflight.json"
            | "prepare.json"
            | "common-doctor.json"
            | "task-doctor.json"
            | "workflow_summary.json"
            | "summary.json" => {
                artifacts.insert("summary".to_string(), output.to_string());
            }
            "doctor_result.json" => {
                artifacts.insert("doctor_result".to_string(), output.to_string());
            }
            "task_plan.json" => {
                artifacts.insert("task_plan".to_string(), output.to_string());
            }
            "task_result.json" => {
                artifacts.insert("task_result".to_string(), output.to_string());
            }
            _ => {}
        }
    }
    artifacts
}

fn strings(values: Vec<&str>) -> Vec<String> {
    values.into_iter().map(str::to_string).collect()
}

fn utc_now() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "unknown".to_string())
}
