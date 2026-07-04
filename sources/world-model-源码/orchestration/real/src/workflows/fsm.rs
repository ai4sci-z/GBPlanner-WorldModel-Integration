use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::Serialize;
use serde_json::{Value, json};
use statig::prelude::*;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

pub const NAVLAB_FSM_SCHEMA_VERSION: &str = "navlab.fsm.v1";

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmSummary {
    pub schema_version: String,
    pub fsm_name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_fsm: Option<NavLabFsmParentRef>,
    pub scope: String,
    pub task_id: String,
    pub run_id: String,
    pub state: String,
    pub mode: String,
    pub ok: bool,
    pub blocked: bool,
    pub states: Vec<NavLabFsmState>,
    pub triggers: Vec<NavLabFsmTrigger>,
    pub transitions: Vec<NavLabFsmTransition>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub guards: Vec<NavLabFsmGuard>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidence: Option<Value>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub reason_codes: Vec<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub blockers: Vec<NavLabFsmBlocker>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub sub_fsms: Vec<NavLabFsmArtifactRef>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artifact_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failed_state: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failed_trigger: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure_reason_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recoverable: Option<bool>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub debug_artifacts: Vec<NavLabFsmDebugArtifact>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmParentRef {
    pub fsm_name: String,
    pub scope: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artifact_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmArtifactRef {
    pub fsm_name: String,
    pub scope: String,
    pub artifact_path: String,
    pub state: String,
    pub ok: bool,
    pub blocked: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub failure_reason_code: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmDebugArtifact {
    pub artifact_type: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmState {
    pub state: String,
    #[serde(skip_serializing_if = "is_false")]
    pub terminal: bool,
    #[serde(skip_serializing_if = "is_false")]
    pub failure: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmTrigger {
    pub trigger: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmTransition {
    pub from_state: String,
    pub to_state: String,
    pub trigger: String,
    pub at: String,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidence: Option<Value>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub guard_results: Vec<NavLabFsmGuard>,
}

#[derive(Debug, Clone)]
pub struct NavLabFsmTransitionInput {
    pub from_state: String,
    pub to_state: String,
    pub trigger: String,
    pub reason_code: String,
    pub ok: bool,
    pub evidence: Value,
    pub at: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmGuard {
    pub name: String,
    pub ok: bool,
    pub required: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub evidence: Option<Value>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NavLabFsmBlocker {
    pub code: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
}

#[derive(Default)]
struct StatigTaskAdapter {
    current_state: String,
}

#[state_machine(initial = "State::recording()")]
impl StatigTaskAdapter {
    #[state]
    fn recording(&mut self) -> Outcome<State> {
        self.current_state = "recording".to_string();
        Handled
    }
}

pub fn navlab_fsm_state(
    state: impl Into<String>,
    terminal: bool,
    failure: bool,
    description: impl Into<Option<String>>,
) -> NavLabFsmState {
    NavLabFsmState {
        state: state.into(),
        terminal,
        failure,
        description: description.into(),
    }
}

pub fn navlab_fsm_transition(input: NavLabFsmTransitionInput) -> NavLabFsmTransition {
    NavLabFsmTransition {
        from_state: input.from_state,
        to_state: input.to_state,
        trigger: input.trigger,
        at: input.at,
        ok: input.ok,
        reason_code: Some(input.reason_code),
        evidence: Some(input.evidence),
        guard_results: Vec::new(),
    }
}

#[allow(clippy::too_many_arguments)]
pub fn navlab_fsm_summary(
    task_id: impl Into<String>,
    fsm_name: impl Into<String>,
    run_id: impl Into<String>,
    state: impl Into<String>,
    mode: impl Into<String>,
    ok: bool,
    blocked: bool,
    states: Vec<NavLabFsmState>,
    transitions: Vec<NavLabFsmTransition>,
    blockers: Vec<String>,
    failed_state: Option<String>,
) -> NavLabFsmSummary {
    let _adapter = StatigTaskAdapter::default().state_machine();
    let mut reason_codes: Vec<String> = transitions
        .iter()
        .filter_map(|transition| transition.reason_code.clone())
        .collect();
    reason_codes.sort();
    reason_codes.dedup();
    let failed_trigger = transitions
        .iter()
        .find(|transition| !transition.ok)
        .map(|transition| transition.trigger.clone());
    let failure_reason_code = transitions
        .iter()
        .find(|transition| !transition.ok)
        .and_then(|transition| transition.reason_code.clone())
        .or_else(|| blockers.first().map(|blocker| blocker_code(blocker)));
    let triggers = transitions
        .iter()
        .map(|transition| NavLabFsmTrigger {
            trigger: transition.trigger.clone(),
            description: transition.reason_code.clone(),
        })
        .collect();
    let mut states = states;
    if blocked && !states.iter().any(|state| state.state == "blocked") {
        states.push(NavLabFsmState {
            state: "blocked".to_string(),
            terminal: true,
            failure: true,
            description: Some("synthetic blocked terminal state".to_string()),
        });
    }
    NavLabFsmSummary {
        schema_version: NAVLAB_FSM_SCHEMA_VERSION.to_string(),
        fsm_name: fsm_name.into(),
        parent_fsm: None,
        scope: "task".to_string(),
        task_id: task_id.into(),
        run_id: run_id.into(),
        state: state.into(),
        mode: mode.into(),
        ok,
        blocked,
        states,
        triggers,
        transitions,
        guards: Vec::new(),
        evidence: Some(json!({"adapter": "statig"})),
        reason_codes,
        blockers: blockers
            .iter()
            .map(|blocker| NavLabFsmBlocker {
                code: blocker_code(blocker),
                message: blocker.clone(),
                source: Some("task".to_string()),
            })
            .collect(),
        sub_fsms: Vec::new(),
        artifact_path: None,
        failed_state,
        failed_trigger,
        failure_reason_code,
        recoverable: blocked.then_some(false),
        debug_artifacts: Vec::new(),
        created_at: utc_now(),
    }
}

pub fn write_navlab_fsm_artifact(
    artifact_dir: &Path,
    fsm_summary: &NavLabFsmSummary,
    run_id: &str,
) -> Result<(NavLabFsmSummary, NavLabFsmArtifactRef)> {
    let file_name = format!(
        "task_{}_fsm.json",
        sanitize_artifact_name(&fsm_summary.task_id)
    );
    let rel_path = PathBuf::from("runtime").join(file_name);
    let path = artifact_dir.join(&rel_path);
    let mut summary = fsm_summary.clone();
    summary.run_id = run_id.to_string();
    summary.artifact_path = Some(rel_path.to_string_lossy().to_string());
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create FSM artifact dir {}", parent.display()))?;
    }
    let data = serde_json::to_vec_pretty(&summary)?;
    fs::write(&path, [data, b"\n".to_vec()].concat())
        .with_context(|| format!("write FSM artifact {}", path.display()))?;
    let reference = NavLabFsmArtifactRef {
        fsm_name: summary.fsm_name.clone(),
        scope: summary.scope.clone(),
        artifact_path: rel_path.to_string_lossy().to_string(),
        state: summary.state.clone(),
        ok: summary.ok,
        blocked: summary.blocked,
        failure_reason_code: summary.failure_reason_code.clone(),
    };
    Ok((summary, reference))
}

fn blocker_code(blocker: &str) -> String {
    blocker
        .split(':')
        .next()
        .unwrap_or("unknown_blocker")
        .trim()
        .to_string()
}

fn sanitize_artifact_name(value: &str) -> String {
    let mut result = String::new();
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() {
            result.push(ch);
        } else {
            result.push('_');
        }
    }
    let result = result.trim_matches('_').to_string();
    if result.is_empty() {
        "unnamed".to_string()
    } else {
        result
    }
}

fn utc_now() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "unknown".to_string())
}

fn is_false(value: &bool) -> bool {
    !*value
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempfile::tempdir;

    #[test]
    fn builds_navlab_fsm_schema_directly() {
        let summary = navlab_fsm_summary(
            "motor-debug",
            "motor-debug",
            "run-1",
            "completed",
            "planned",
            true,
            false,
            vec![navlab_fsm_state(
                "runtime_ready",
                false,
                false,
                Some("planned".to_string()),
            )],
            vec![navlab_fsm_transition(NavLabFsmTransitionInput {
                from_state: "runtime_ready".to_string(),
                to_state: "guided".to_string(),
                trigger: "guided_confirmed".to_string(),
                reason_code: "guided_ack_planned".to_string(),
                ok: true,
                evidence: json!({"ack": "planned"}),
                at: "planned".to_string(),
            })],
            Vec::new(),
            None,
        );

        assert_eq!(summary.schema_version, NAVLAB_FSM_SCHEMA_VERSION);
        assert_eq!(summary.scope, "task");
        assert_eq!(summary.state, "completed");
        assert_eq!(summary.transitions[0].trigger, "guided_confirmed");
        assert_eq!(summary.evidence.unwrap()["adapter"], "statig");
    }

    #[test]
    fn writes_navlab_fsm_artifact() {
        let dir = tempdir().expect("tempdir");
        let summary = navlab_fsm_summary(
            "hover",
            "real-hover",
            "",
            "runtime_ready",
            "blocked_before_runtime",
            false,
            true,
            Vec::new(),
            Vec::new(),
            vec!["real_hover_live_task_not_enabled".to_string()],
            Some("runtime_ready".to_string()),
        );

        let (_summary, reference) =
            write_navlab_fsm_artifact(dir.path(), &summary, "run-1").expect("write fsm");
        assert_eq!(reference.artifact_path, "runtime/task_hover_fsm.json");
        assert!(dir.path().join(reference.artifact_path).exists());
    }
}
