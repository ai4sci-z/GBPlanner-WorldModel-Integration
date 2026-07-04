use std::io::ErrorKind;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use mavlink::dialects::ardupilotmega as apm;
use mavlink::{MavConnection, MavHeader};
use serde::Serialize;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};

use crate::tasks::{
    ARDUCOPTER_GUIDED_MODE_ID, CommandAckEvaluation, MAV_CMD_COMPONENT_ARM_DISARM,
    MavlinkStatusText, evaluate_command_ack,
};
use crate::workflows::{
    NavLabFsmState, NavLabFsmSummary, NavLabFsmTransition, NavLabFsmTransitionInput,
    navlab_fsm_state, navlab_fsm_summary, navlab_fsm_transition,
};

const DEFAULT_TARGET_SYSTEM: u8 = 1;
const DEFAULT_TARGET_COMPONENT: u8 = 0;
const DEFAULT_SOURCE_SYSTEM: u8 = 255;
const DEFAULT_SOURCE_COMPONENT: u8 = 190;
const MAV_MODE_FLAG_CUSTOM_MODE_ENABLED: f32 = 1.0;

#[derive(Debug, Clone)]
pub struct MotorDebugRuntimeRequest {
    pub endpoint: String,
    pub motor_percent: f64,
    pub motor_sec: f64,
    pub target_system: u8,
    pub target_component: u8,
    pub heartbeat_timeout: Duration,
    pub ack_timeout: Duration,
    pub mode_timeout: Duration,
}

#[derive(Debug, Clone)]
pub struct RealHoverRuntimeRequest {
    pub task_id: String,
    pub endpoint: String,
    pub target_altitude_m: f64,
    pub hover_health_stable_sec: f64,
    pub hover_hold_sec: f64,
    pub target_system: u8,
    pub target_component: u8,
    pub heartbeat_timeout: Duration,
    pub ack_timeout: Duration,
    pub mode_timeout: Duration,
}

#[derive(Debug, Clone, Serialize)]
pub struct MotorDebugRuntimeReport {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub connection_endpoint: String,
    pub target_system: u8,
    pub target_component: u8,
    pub initial_heartbeat: Option<MavlinkHeartbeat>,
    pub guided_mode: GuidedModeRuntimeReport,
    pub arm_ack: Option<CommandAckEvaluation>,
    pub disarm_ack: Option<CommandAckEvaluation>,
    pub shutdown_claim: String,
    pub throttle_command_claim: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RealHoverRuntimeReport {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub connection_endpoint: String,
    pub target_system: u8,
    pub target_component: u8,
    pub initial_heartbeat: Option<MavlinkHeartbeat>,
    pub guided_mode: GuidedModeRuntimeReport,
    pub arm_ack: Option<CommandAckEvaluation>,
    pub takeoff_ack: Option<CommandAckEvaluation>,
    pub land_ack: Option<CommandAckEvaluation>,
    pub disarm_ack: Option<CommandAckEvaluation>,
    pub fsm: NavLabFsmSummary,
    pub landing_claim: String,
    pub shutdown_claim: String,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct MavlinkHeartbeat {
    pub system_id: u8,
    pub component_id: u8,
    pub custom_mode: u32,
    pub base_mode_bits: u8,
}

#[derive(Debug, Clone, Serialize)]
pub struct GuidedModeRuntimeReport {
    pub ok: bool,
    pub mode_id: u32,
    pub command_ack: Option<CommandAckEvaluation>,
    pub observed_heartbeat: Option<MavlinkHeartbeat>,
    pub blockers: Vec<String>,
}

pub trait MotorDebugMavlink {
    fn send_set_guided(&mut self, target_system: u8, target_component: u8) -> Result<()>;
    fn send_arm_disarm(&mut self, target_system: u8, target_component: u8, arm: bool)
    -> Result<()>;
    fn send_takeoff(
        &mut self,
        _target_system: u8,
        _target_component: u8,
        _altitude_m: f64,
    ) -> Result<()> {
        Err(anyhow::anyhow!(
            "send_takeoff is not implemented for this MAVLink adapter"
        ))
    }
    fn send_land(&mut self, _target_system: u8, _target_component: u8) -> Result<()> {
        Err(anyhow::anyhow!(
            "send_land is not implemented for this MAVLink adapter"
        ))
    }
    fn next_event(&mut self, timeout: Duration) -> Result<Option<MavlinkEvent>>;
}

#[derive(Debug, Clone, PartialEq)]
pub enum MavlinkEvent {
    Heartbeat(MavlinkHeartbeat),
    CommandAck(CommandAckEvaluation),
    StatusText(MavlinkStatusText),
}

pub struct ArdupilotMegaConnection {
    connection: mavlink::Connection<apm::MavMessage>,
}

impl ArdupilotMegaConnection {
    pub fn connect(endpoint: &str) -> Result<Self> {
        let connection = mavlink::connect::<apm::MavMessage>(endpoint)
            .with_context(|| format!("connect MAVLink endpoint {endpoint}"))?;
        Ok(Self { connection })
    }
}

impl MotorDebugMavlink for ArdupilotMegaConnection {
    fn send_set_guided(&mut self, target_system: u8, target_component: u8) -> Result<()> {
        let message = apm::MavMessage::COMMAND_LONG(apm::COMMAND_LONG_DATA {
            target_system,
            target_component,
            command: apm::MavCmd::MAV_CMD_DO_SET_MODE,
            confirmation: 0,
            param1: MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            param2: ARDUCOPTER_GUIDED_MODE_ID as f32,
            param3: 0.0,
            param4: 0.0,
            param5: 0.0,
            param6: 0.0,
            param7: 0.0,
        });
        self.connection
            .send(&source_header(), &message)
            .context("send MAV_CMD_DO_SET_MODE GUIDED")?;
        Ok(())
    }

    fn send_arm_disarm(
        &mut self,
        target_system: u8,
        target_component: u8,
        arm: bool,
    ) -> Result<()> {
        let message = apm::MavMessage::COMMAND_LONG(apm::COMMAND_LONG_DATA {
            target_system,
            target_component,
            command: apm::MavCmd::MAV_CMD_COMPONENT_ARM_DISARM,
            confirmation: 0,
            param1: if arm { 1.0 } else { 0.0 },
            param2: 0.0,
            param3: 0.0,
            param4: 0.0,
            param5: 0.0,
            param6: 0.0,
            param7: 0.0,
        });
        self.connection
            .send(&source_header(), &message)
            .context("send MAV_CMD_COMPONENT_ARM_DISARM")?;
        Ok(())
    }

    fn send_takeoff(
        &mut self,
        target_system: u8,
        target_component: u8,
        altitude_m: f64,
    ) -> Result<()> {
        let message = apm::MavMessage::COMMAND_LONG(apm::COMMAND_LONG_DATA {
            target_system,
            target_component,
            command: apm::MavCmd::MAV_CMD_NAV_TAKEOFF,
            confirmation: 0,
            param1: 0.0,
            param2: 0.0,
            param3: 0.0,
            param4: 0.0,
            param5: 0.0,
            param6: 0.0,
            param7: altitude_m as f32,
        });
        self.connection
            .send(&source_header(), &message)
            .context("send MAV_CMD_NAV_TAKEOFF")?;
        Ok(())
    }

    fn send_land(&mut self, target_system: u8, target_component: u8) -> Result<()> {
        let message = apm::MavMessage::COMMAND_LONG(apm::COMMAND_LONG_DATA {
            target_system,
            target_component,
            command: apm::MavCmd::MAV_CMD_NAV_LAND,
            confirmation: 0,
            param1: 0.0,
            param2: 0.0,
            param3: 0.0,
            param4: 0.0,
            param5: 0.0,
            param6: 0.0,
            param7: 0.0,
        });
        self.connection
            .send(&source_header(), &message)
            .context("send MAV_CMD_NAV_LAND")?;
        Ok(())
    }

    fn next_event(&mut self, timeout: Duration) -> Result<Option<MavlinkEvent>> {
        let deadline = Instant::now() + timeout;
        loop {
            match self.connection.try_recv() {
                Ok((header, message)) => return Ok(event_from_message(header, message)),
                Err(mavlink::error::MessageReadError::Io(error))
                    if matches!(error.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) =>
                {
                    if Instant::now() >= deadline {
                        return Ok(None);
                    }
                    thread::sleep(Duration::from_millis(20));
                }
                Err(error) => return Err(error).context("receive MAVLink message"),
            }
        }
    }
}

pub fn run_motor_debug_runtime(
    connection: &mut dyn MotorDebugMavlink,
    request: &MotorDebugRuntimeRequest,
) -> Result<MotorDebugRuntimeReport> {
    let mut blockers = Vec::new();
    let initial_heartbeat = wait_for_heartbeat(connection, request.heartbeat_timeout)?;
    if initial_heartbeat.is_none() {
        blockers.push("motor_debug_heartbeat_timeout".to_string());
    }

    let guided_mode = if blockers.is_empty() {
        set_guided_and_wait(connection, request)?
    } else {
        GuidedModeRuntimeReport {
            ok: false,
            mode_id: ARDUCOPTER_GUIDED_MODE_ID,
            command_ack: None,
            observed_heartbeat: None,
            blockers: vec!["motor_debug_guided_mode_not_attempted_without_heartbeat".to_string()],
        }
    };
    blockers.extend(guided_mode.blockers.clone());

    let mut arm_ack = None;
    let mut disarm_ack = None;
    let mut shutdown_claim = "not_requested".to_string();
    let mut throttle_command_claim = "not_sent".to_string();

    if blockers.is_empty() {
        connection.send_arm_disarm(request.target_system, request.target_component, true)?;
        arm_ack = wait_for_command_ack(
            connection,
            MAV_CMD_COMPONENT_ARM_DISARM,
            request.ack_timeout,
        )?;
        if let Some(ack) = &arm_ack {
            blockers.extend(crate::tasks::command_rejection_blockers(
                "motor_debug_arm_rejected",
                ack,
            ));
        } else {
            blockers.push("motor_debug_arm_ack_timeout".to_string());
        }
    }

    if blockers.is_empty() {
        throttle_command_claim = "not_sent_armed_idle_only".to_string();
        thread::sleep(Duration::from_secs_f64(request.motor_sec));
    }

    if arm_ack.as_ref().is_some_and(|ack| ack.accepted) {
        connection.send_arm_disarm(request.target_system, request.target_component, false)?;
        disarm_ack = wait_for_command_ack(
            connection,
            MAV_CMD_COMPONENT_ARM_DISARM,
            request.ack_timeout,
        )?;
        shutdown_claim = match &disarm_ack {
            Some(ack) if ack.accepted => "disarm_accepted".to_string(),
            Some(ack) => {
                blockers.extend(crate::tasks::command_rejection_blockers(
                    "motor_debug_disarm_rejected",
                    ack,
                ));
                "disarm_rejected".to_string()
            }
            None => {
                blockers.push("motor_debug_disarm_ack_timeout".to_string());
                "disarm_ack_timeout".to_string()
            }
        };
    }

    blockers = dedupe(blockers);
    Ok(MotorDebugRuntimeReport {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        blockers,
        connection_endpoint: request.endpoint.clone(),
        target_system: request.target_system,
        target_component: request.target_component,
        initial_heartbeat,
        guided_mode,
        arm_ack,
        disarm_ack,
        shutdown_claim,
        throttle_command_claim,
    })
}

pub fn real_motor_debug_runtime(
    request: &MotorDebugRuntimeRequest,
) -> Result<MotorDebugRuntimeReport> {
    let mut connection = ArdupilotMegaConnection::connect(&request.endpoint)?;
    run_motor_debug_runtime(&mut connection, request)
}

pub fn run_real_hover_runtime(
    connection: &mut dyn MotorDebugMavlink,
    request: &RealHoverRuntimeRequest,
) -> Result<RealHoverRuntimeReport> {
    let mut recorder = RealHoverRuntimeFsm::new(request);
    let mut blockers = Vec::new();
    let initial_heartbeat = wait_for_heartbeat(connection, request.heartbeat_timeout)?;
    if initial_heartbeat.is_some() {
        recorder.enter(
            "runtime_ready",
            "heartbeat_observed",
            serde_json::json!({"heartbeat": initial_heartbeat}),
        );
    } else {
        blockers.push("real_hover_heartbeat_timeout".to_string());
        recorder.block(
            "runtime_ready",
            "guided",
            "heartbeat_ready",
            "real_hover_heartbeat_timeout",
            blockers.first().cloned(),
            serde_json::json!({"initial_heartbeat": initial_heartbeat}),
        );
    }

    let guided_mode = if blockers.is_empty() {
        set_guided_and_wait_hover(connection, request)?
    } else {
        GuidedModeRuntimeReport {
            ok: false,
            mode_id: ARDUCOPTER_GUIDED_MODE_ID,
            command_ack: None,
            observed_heartbeat: None,
            blockers: vec!["real_hover_guided_mode_not_attempted_without_heartbeat".to_string()],
        }
    };
    if blockers.is_empty() && guided_mode.ok {
        recorder.transition(
            "runtime_ready",
            "guided",
            "guided_confirmed",
            "guided_ack_and_heartbeat_observed",
            serde_json::json!({
                "ack": guided_mode.command_ack,
                "observed_heartbeat": guided_mode.observed_heartbeat,
            }),
        );
    } else if blockers.is_empty() {
        blockers.extend(guided_mode.blockers.clone());
        recorder.block(
            "runtime_ready",
            "guided",
            "guided_confirmed",
            guided_mode
                .blockers
                .first()
                .map(String::as_str)
                .unwrap_or("real_hover_guided_mode_not_confirmed"),
            blockers.first().cloned(),
            serde_json::json!({
                "ack": guided_mode.command_ack,
                "observed_heartbeat": guided_mode.observed_heartbeat,
                "guided_blockers": guided_mode.blockers,
            }),
        );
    }

    let mut arm_ack = None;
    let mut takeoff_ack = None;
    let mut land_ack = None;
    let mut disarm_ack = None;
    let mut landing_claim = "not_requested".to_string();
    let mut shutdown_claim = "not_requested".to_string();

    if blockers.is_empty() {
        connection.send_arm_disarm(request.target_system, request.target_component, true)?;
        arm_ack = wait_for_command_ack(
            connection,
            MAV_CMD_COMPONENT_ARM_DISARM,
            request.ack_timeout,
        )?;
        if let Some(ack) = &arm_ack {
            blockers.extend(crate::tasks::command_rejection_blockers(
                "real_hover_arm_rejected",
                ack,
            ));
        } else {
            blockers.push("real_hover_arm_ack_timeout".to_string());
        }
        if blockers.is_empty() {
            recorder.transition(
                "guided",
                "armed",
                "arm_confirmed",
                "arm_ack_accepted",
                serde_json::json!({"ack": arm_ack}),
            );
        } else {
            recorder.block(
                "guided",
                "armed",
                "arm_confirmed",
                "real_hover_arm_not_confirmed",
                blockers.first().cloned(),
                serde_json::json!({"ack": arm_ack}),
            );
        }
    }

    if blockers.is_empty() {
        connection.send_takeoff(
            request.target_system,
            request.target_component,
            request.target_altitude_m,
        )?;
        takeoff_ack = wait_for_command_ack(
            connection,
            apm::MavCmd::MAV_CMD_NAV_TAKEOFF as u32,
            request.ack_timeout,
        )?;
        if let Some(ack) = &takeoff_ack {
            blockers.extend(crate::tasks::command_rejection_blockers(
                "real_hover_takeoff_rejected",
                ack,
            ));
        } else {
            blockers.push("real_hover_takeoff_ack_timeout".to_string());
        }
        if blockers.is_empty() {
            recorder.transition(
                "armed",
                "takeoff",
                "takeoff_confirmed",
                "takeoff_ack_accepted",
                serde_json::json!({
                    "ack": takeoff_ack,
                    "target_altitude_m": request.target_altitude_m,
                }),
            );
        } else {
            recorder.block(
                "armed",
                "takeoff",
                "takeoff_confirmed",
                "real_hover_takeoff_not_confirmed",
                blockers.first().cloned(),
                serde_json::json!({
                    "ack": takeoff_ack,
                    "target_altitude_m": request.target_altitude_m,
                }),
            );
        }
    }

    if blockers.is_empty() {
        thread::sleep(Duration::from_secs_f64(request.hover_health_stable_sec));
        recorder.transition(
            "takeoff",
            "hover_health_hold",
            "hover_health_stable",
            "hover_health_stable_window_elapsed",
            serde_json::json!({"stable_sec": request.hover_health_stable_sec}),
        );
        thread::sleep(Duration::from_secs_f64(request.hover_hold_sec));
        recorder.transition(
            "hover_health_hold",
            "hover_hold",
            "hover_hold_elapsed",
            "hover_hold_window_elapsed",
            serde_json::json!({"hold_sec": request.hover_hold_sec}),
        );
    }

    if blockers.is_empty() {
        connection.send_land(request.target_system, request.target_component)?;
        land_ack = wait_for_command_ack(
            connection,
            apm::MavCmd::MAV_CMD_NAV_LAND as u32,
            request.ack_timeout,
        )?;
        if let Some(ack) = &land_ack {
            blockers.extend(crate::tasks::command_rejection_blockers(
                "real_hover_land_rejected",
                ack,
            ));
        } else {
            blockers.push("real_hover_land_ack_timeout".to_string());
        }
        if blockers.is_empty() {
            landing_claim = "land_accepted".to_string();
            recorder.transition(
                "hover_hold",
                "landing",
                "landing_started",
                "land_ack_accepted",
                serde_json::json!({"ack": land_ack}),
            );
        } else {
            landing_claim = "land_not_confirmed".to_string();
            recorder.block(
                "hover_hold",
                "landing",
                "landing_started",
                "real_hover_land_not_confirmed",
                blockers.first().cloned(),
                serde_json::json!({"ack": land_ack}),
            );
        }
    }

    if blockers.is_empty() {
        connection.send_arm_disarm(request.target_system, request.target_component, false)?;
        disarm_ack = wait_for_command_ack(
            connection,
            MAV_CMD_COMPONENT_ARM_DISARM,
            request.ack_timeout,
        )?;
        if let Some(ack) = &disarm_ack {
            blockers.extend(crate::tasks::command_rejection_blockers(
                "real_hover_disarm_rejected",
                ack,
            ));
        } else {
            blockers.push("real_hover_disarm_ack_timeout".to_string());
        }
        if blockers.is_empty() {
            shutdown_claim = "disarm_accepted".to_string();
            recorder.transition(
                "landing",
                "disarmed",
                "disarm_confirmed",
                "disarm_ack_accepted",
                serde_json::json!({"ack": disarm_ack}),
            );
            recorder.transition(
                "disarmed",
                "completed",
                "task_completed",
                "real_hover_completed",
                serde_json::json!({
                    "landing_claim": landing_claim,
                    "shutdown_claim": shutdown_claim,
                }),
            );
        } else {
            shutdown_claim = "disarm_not_confirmed".to_string();
            recorder.block(
                "landing",
                "disarmed",
                "disarm_confirmed",
                "real_hover_disarm_not_confirmed",
                blockers.first().cloned(),
                serde_json::json!({"ack": disarm_ack}),
            );
        }
    }

    blockers = dedupe(blockers);
    let ok = blockers.is_empty();
    Ok(RealHoverRuntimeReport {
        ok,
        blocked: !ok,
        blockers: blockers.clone(),
        connection_endpoint: request.endpoint.clone(),
        target_system: request.target_system,
        target_component: request.target_component,
        initial_heartbeat,
        guided_mode,
        arm_ack,
        takeoff_ack,
        land_ack,
        disarm_ack,
        fsm: recorder.summary(ok, blockers),
        landing_claim,
        shutdown_claim,
    })
}

pub fn real_hover_runtime(request: &RealHoverRuntimeRequest) -> Result<RealHoverRuntimeReport> {
    let mut connection = ArdupilotMegaConnection::connect(&request.endpoint)?;
    run_real_hover_runtime(&mut connection, request)
}

impl MotorDebugRuntimeRequest {
    pub fn new(endpoint: String, motor_percent: f64, motor_sec: f64) -> Self {
        Self {
            endpoint,
            motor_percent,
            motor_sec,
            target_system: DEFAULT_TARGET_SYSTEM,
            target_component: DEFAULT_TARGET_COMPONENT,
            heartbeat_timeout: Duration::from_secs(10),
            ack_timeout: Duration::from_secs(5),
            mode_timeout: Duration::from_secs(5),
        }
    }
}

impl RealHoverRuntimeRequest {
    pub fn new(
        task_id: String,
        endpoint: String,
        target_altitude_m: f64,
        hover_health_stable_sec: f64,
        hover_hold_sec: f64,
    ) -> Self {
        Self {
            task_id,
            endpoint,
            target_altitude_m,
            hover_health_stable_sec,
            hover_hold_sec,
            target_system: DEFAULT_TARGET_SYSTEM,
            target_component: DEFAULT_TARGET_COMPONENT,
            heartbeat_timeout: Duration::from_secs(10),
            ack_timeout: Duration::from_secs(5),
            mode_timeout: Duration::from_secs(5),
        }
    }
}

struct RealHoverRuntimeFsm {
    task_id: String,
    states: Vec<NavLabFsmState>,
    transitions: Vec<NavLabFsmTransition>,
    current_state: String,
    failed_state: Option<String>,
}

impl RealHoverRuntimeFsm {
    fn new(request: &RealHoverRuntimeRequest) -> Self {
        Self {
            task_id: request.task_id.clone(),
            states: Vec::new(),
            transitions: Vec::new(),
            current_state: "runtime_ready".to_string(),
            failed_state: None,
        }
    }

    fn enter(&mut self, state: &str, reason: &str, evidence: serde_json::Value) {
        self.current_state = state.to_string();
        self.states
            .push(runtime_fsm_state(state, &utc_now(), reason, evidence));
    }

    fn transition(
        &mut self,
        from_state: &str,
        to_state: &str,
        event: &str,
        reason_code: &str,
        evidence: serde_json::Value,
    ) {
        self.current_state = to_state.to_string();
        self.states.push(runtime_fsm_state(
            to_state,
            &utc_now(),
            reason_code,
            evidence.clone(),
        ));
        self.transitions.push(self.transition_payload(
            from_state,
            to_state,
            event,
            reason_code,
            true,
            None,
            evidence,
        ));
    }

    fn block(
        &mut self,
        from_state: &str,
        to_state: &str,
        event: &str,
        reason_code: &str,
        blocker: Option<String>,
        evidence: serde_json::Value,
    ) {
        self.failed_state = Some(to_state.to_string());
        self.transitions.push(self.transition_payload(
            from_state,
            to_state,
            event,
            reason_code,
            false,
            blocker,
            evidence,
        ));
    }

    fn transition_payload(
        &self,
        from_state: &str,
        to_state: &str,
        event: &str,
        reason_code: &str,
        ok: bool,
        blocker: Option<String>,
        evidence: serde_json::Value,
    ) -> NavLabFsmTransition {
        let _ = blocker;
        navlab_fsm_transition(NavLabFsmTransitionInput {
            from_state: from_state.to_string(),
            to_state: to_state.to_string(),
            trigger: event.to_string(),
            reason_code: reason_code.to_string(),
            ok,
            evidence,
            at: utc_now(),
        })
    }

    fn summary(self, ok: bool, blockers: Vec<String>) -> NavLabFsmSummary {
        navlab_fsm_summary(
            self.task_id,
            "real-hover",
            "",
            self.current_state,
            "actual",
            ok,
            !ok,
            self.states,
            self.transitions,
            blockers,
            self.failed_state,
        )
    }
}

fn runtime_fsm_state(
    state: &str,
    entered_at: &str,
    reason: &str,
    evidence: serde_json::Value,
) -> NavLabFsmState {
    let _ = evidence;
    navlab_fsm_state(
        state,
        state == "completed",
        reason == "blocked_before_entering",
        Some(format!("{entered_at}:{reason}")),
    )
}

fn set_guided_and_wait(
    connection: &mut dyn MotorDebugMavlink,
    request: &MotorDebugRuntimeRequest,
) -> Result<GuidedModeRuntimeReport> {
    connection.send_set_guided(request.target_system, request.target_component)?;
    let command_ack = wait_for_command_ack(
        connection,
        apm::MavCmd::MAV_CMD_DO_SET_MODE as u32,
        request.ack_timeout,
    )?;
    let observed_heartbeat = wait_for_guided_heartbeat(connection, request.mode_timeout)?;
    let mut blockers = Vec::new();

    match &command_ack {
        Some(ack) => blockers.extend(crate::tasks::command_rejection_blockers(
            "motor_debug_guided_mode_rejected",
            ack,
        )),
        None => blockers.push("motor_debug_guided_mode_ack_timeout".to_string()),
    }
    if observed_heartbeat.is_none() {
        blockers.push("motor_debug_guided_mode_heartbeat_timeout".to_string());
    }

    blockers = dedupe(blockers);
    Ok(GuidedModeRuntimeReport {
        ok: blockers.is_empty(),
        mode_id: ARDUCOPTER_GUIDED_MODE_ID,
        command_ack,
        observed_heartbeat,
        blockers,
    })
}

fn set_guided_and_wait_hover(
    connection: &mut dyn MotorDebugMavlink,
    request: &RealHoverRuntimeRequest,
) -> Result<GuidedModeRuntimeReport> {
    connection.send_set_guided(request.target_system, request.target_component)?;
    let command_ack = wait_for_command_ack(
        connection,
        apm::MavCmd::MAV_CMD_DO_SET_MODE as u32,
        request.ack_timeout,
    )?;
    let observed_heartbeat = wait_for_guided_heartbeat(connection, request.mode_timeout)?;
    let mut blockers = Vec::new();

    match &command_ack {
        Some(ack) => blockers.extend(crate::tasks::command_rejection_blockers(
            "real_hover_guided_mode_rejected",
            ack,
        )),
        None => blockers.push("real_hover_guided_mode_ack_timeout".to_string()),
    }
    if observed_heartbeat.is_none() {
        blockers.push("real_hover_guided_mode_heartbeat_timeout".to_string());
    }

    blockers = dedupe(blockers);
    Ok(GuidedModeRuntimeReport {
        ok: blockers.is_empty(),
        mode_id: ARDUCOPTER_GUIDED_MODE_ID,
        command_ack,
        observed_heartbeat,
        blockers,
    })
}

fn wait_for_heartbeat(
    connection: &mut dyn MotorDebugMavlink,
    timeout: Duration,
) -> Result<Option<MavlinkHeartbeat>> {
    let deadline = Instant::now() + timeout;
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Ok(None);
        }
        if let Some(MavlinkEvent::Heartbeat(heartbeat)) = connection.next_event(remaining)? {
            return Ok(Some(heartbeat));
        }
    }
}

fn wait_for_guided_heartbeat(
    connection: &mut dyn MotorDebugMavlink,
    timeout: Duration,
) -> Result<Option<MavlinkHeartbeat>> {
    let deadline = Instant::now() + timeout;
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Ok(None);
        }
        if let Some(MavlinkEvent::Heartbeat(heartbeat)) = connection.next_event(remaining)?
            && heartbeat.custom_mode == ARDUCOPTER_GUIDED_MODE_ID
        {
            return Ok(Some(heartbeat));
        }
    }
}

fn wait_for_command_ack(
    connection: &mut dyn MotorDebugMavlink,
    command: u32,
    timeout: Duration,
) -> Result<Option<CommandAckEvaluation>> {
    let deadline = Instant::now() + timeout;
    let mut status_text = Vec::new();
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Ok(None);
        }
        match connection.next_event(remaining)? {
            Some(MavlinkEvent::CommandAck(ack)) if ack.command == command => {
                return Ok(Some(CommandAckEvaluation { status_text, ..ack }));
            }
            Some(MavlinkEvent::StatusText(status)) => status_text.push(status),
            Some(_) | None => {}
        }
    }
}

fn event_from_message(header: MavHeader, message: apm::MavMessage) -> Option<MavlinkEvent> {
    match message {
        apm::MavMessage::HEARTBEAT(data) => Some(MavlinkEvent::Heartbeat(MavlinkHeartbeat {
            system_id: header.system_id,
            component_id: header.component_id,
            custom_mode: data.custom_mode,
            base_mode_bits: data.base_mode.bits(),
        })),
        apm::MavMessage::COMMAND_ACK(data) => Some(MavlinkEvent::CommandAck(evaluate_command_ack(
            data.command as u32,
            data.result as u32,
            0,
            Vec::new(),
        ))),
        apm::MavMessage::STATUSTEXT(data) => Some(MavlinkEvent::StatusText(MavlinkStatusText {
            severity: data.severity as u8,
            text: data.text.to_str().unwrap_or("").to_string(),
        })),
        _ => None,
    }
}

fn source_header() -> MavHeader {
    MavHeader {
        system_id: DEFAULT_SOURCE_SYSTEM,
        component_id: DEFAULT_SOURCE_COMPONENT,
        sequence: 0,
    }
}

fn dedupe(values: Vec<String>) -> Vec<String> {
    let mut deduped = Vec::new();
    for value in values {
        if !deduped.contains(&value) {
            deduped.push(value);
        }
    }
    deduped
}

fn utc_now() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "unknown".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    #[derive(Debug, Default)]
    struct FakeMavlink {
        events: VecDeque<MavlinkEvent>,
        sent_guided: usize,
        sent_arm: usize,
        sent_disarm: usize,
        sent_takeoff: usize,
        sent_land: usize,
    }

    impl MotorDebugMavlink for FakeMavlink {
        fn send_set_guided(&mut self, _target_system: u8, _target_component: u8) -> Result<()> {
            self.sent_guided += 1;
            Ok(())
        }

        fn send_arm_disarm(
            &mut self,
            _target_system: u8,
            _target_component: u8,
            arm: bool,
        ) -> Result<()> {
            if arm {
                self.sent_arm += 1;
            } else {
                self.sent_disarm += 1;
            }
            Ok(())
        }

        fn send_takeoff(
            &mut self,
            _target_system: u8,
            _target_component: u8,
            _altitude_m: f64,
        ) -> Result<()> {
            self.sent_takeoff += 1;
            Ok(())
        }

        fn send_land(&mut self, _target_system: u8, _target_component: u8) -> Result<()> {
            self.sent_land += 1;
            Ok(())
        }

        fn next_event(&mut self, _timeout: Duration) -> Result<Option<MavlinkEvent>> {
            Ok(self.events.pop_front())
        }
    }

    fn request() -> MotorDebugRuntimeRequest {
        MotorDebugRuntimeRequest {
            endpoint: "udpin:127.0.0.1:14550".to_string(),
            motor_percent: 5.0,
            motor_sec: 0.0,
            target_system: 1,
            target_component: 0,
            heartbeat_timeout: Duration::from_millis(1),
            ack_timeout: Duration::from_millis(1),
            mode_timeout: Duration::from_millis(1),
        }
    }

    fn hover_request() -> RealHoverRuntimeRequest {
        RealHoverRuntimeRequest {
            task_id: "hover".to_string(),
            endpoint: "udpin:127.0.0.1:14550".to_string(),
            target_altitude_m: 1.0,
            hover_health_stable_sec: 0.0,
            hover_hold_sec: 0.0,
            target_system: 1,
            target_component: 0,
            heartbeat_timeout: Duration::from_millis(1),
            ack_timeout: Duration::from_millis(1),
            mode_timeout: Duration::from_millis(1),
        }
    }

    fn heartbeat(custom_mode: u32) -> MavlinkEvent {
        MavlinkEvent::Heartbeat(MavlinkHeartbeat {
            system_id: 1,
            component_id: 1,
            custom_mode,
            base_mode_bits: 1,
        })
    }

    fn accepted(command: u32) -> MavlinkEvent {
        MavlinkEvent::CommandAck(evaluate_command_ack(command, 0, 0, Vec::new()))
    }

    fn failed(command: u32) -> MavlinkEvent {
        MavlinkEvent::CommandAck(evaluate_command_ack(command, 4, 0, Vec::new()))
    }

    #[test]
    fn motor_debug_runtime_sends_guided_arm_and_disarm() {
        let mut mavlink = FakeMavlink {
            events: VecDeque::from([
                heartbeat(0),
                accepted(apm::MavCmd::MAV_CMD_DO_SET_MODE as u32),
                heartbeat(ARDUCOPTER_GUIDED_MODE_ID),
                accepted(MAV_CMD_COMPONENT_ARM_DISARM),
                accepted(MAV_CMD_COMPONENT_ARM_DISARM),
            ]),
            ..FakeMavlink::default()
        };

        let report = run_motor_debug_runtime(&mut mavlink, &request()).expect("runtime");

        assert!(report.ok);
        assert_eq!(mavlink.sent_guided, 1);
        assert_eq!(mavlink.sent_arm, 1);
        assert_eq!(mavlink.sent_disarm, 1);
        assert_eq!(report.shutdown_claim, "disarm_accepted");
        assert_eq!(report.throttle_command_claim, "not_sent_armed_idle_only");
    }

    #[test]
    fn motor_debug_runtime_blocks_arm_rejection_and_disarms_not_sent() {
        let mut mavlink = FakeMavlink {
            events: VecDeque::from([
                heartbeat(0),
                accepted(apm::MavCmd::MAV_CMD_DO_SET_MODE as u32),
                heartbeat(ARDUCOPTER_GUIDED_MODE_ID),
                MavlinkEvent::StatusText(MavlinkStatusText {
                    severity: 3,
                    text: "PreArm: safety switch".to_string(),
                }),
                MavlinkEvent::CommandAck(evaluate_command_ack(
                    MAV_CMD_COMPONENT_ARM_DISARM,
                    4,
                    0,
                    Vec::new(),
                )),
            ]),
            ..FakeMavlink::default()
        };

        let report = run_motor_debug_runtime(&mut mavlink, &request()).expect("runtime");

        assert!(!report.ok);
        assert_eq!(mavlink.sent_arm, 1);
        assert_eq!(mavlink.sent_disarm, 0);
        assert_eq!(
            report.blockers,
            vec![
                "motor_debug_arm_rejected:MAV_RESULT_FAILED",
                "motor_debug_arm_rejected_status:PreArm: safety switch"
            ]
        );
    }

    #[test]
    fn motor_debug_runtime_blocks_without_heartbeat() {
        let mut mavlink = FakeMavlink::default();

        let report = run_motor_debug_runtime(&mut mavlink, &request()).expect("runtime");

        assert!(!report.ok);
        assert_eq!(
            report.blockers,
            vec![
                "motor_debug_heartbeat_timeout",
                "motor_debug_guided_mode_not_attempted_without_heartbeat"
            ]
        );
        assert_eq!(mavlink.sent_guided, 0);
        assert_eq!(mavlink.sent_arm, 0);
    }

    #[test]
    fn real_hover_runtime_records_complete_fsm_and_commands() {
        let mut mavlink = FakeMavlink {
            events: VecDeque::from([
                heartbeat(0),
                accepted(apm::MavCmd::MAV_CMD_DO_SET_MODE as u32),
                heartbeat(ARDUCOPTER_GUIDED_MODE_ID),
                accepted(MAV_CMD_COMPONENT_ARM_DISARM),
                accepted(apm::MavCmd::MAV_CMD_NAV_TAKEOFF as u32),
                accepted(apm::MavCmd::MAV_CMD_NAV_LAND as u32),
                accepted(MAV_CMD_COMPONENT_ARM_DISARM),
            ]),
            ..FakeMavlink::default()
        };

        let report = run_real_hover_runtime(&mut mavlink, &hover_request()).expect("runtime");

        assert!(report.ok);
        assert_eq!(mavlink.sent_guided, 1);
        assert_eq!(mavlink.sent_arm, 1);
        assert_eq!(mavlink.sent_takeoff, 1);
        assert_eq!(mavlink.sent_land, 1);
        assert_eq!(mavlink.sent_disarm, 1);
        assert_eq!(report.landing_claim, "land_accepted");
        assert_eq!(report.shutdown_claim, "disarm_accepted");
        assert_eq!(report.fsm.state, "completed");
        assert_eq!(report.fsm.failed_state, None);
        assert_eq!(
            report
                .fsm
                .states
                .iter()
                .map(|state| state.state.as_str())
                .collect::<Vec<_>>(),
            vec![
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
        );
        assert_eq!(
            report
                .fsm
                .transitions
                .iter()
                .map(|transition| (transition.from_state.as_str(), transition.to_state.as_str()))
                .collect::<Vec<_>>(),
            vec![
                ("runtime_ready", "guided"),
                ("guided", "armed"),
                ("armed", "takeoff"),
                ("takeoff", "hover_health_hold"),
                ("hover_health_hold", "hover_hold"),
                ("hover_hold", "landing"),
                ("landing", "disarmed"),
                ("disarmed", "completed"),
            ]
        );
    }

    #[test]
    fn real_hover_runtime_blocks_takeoff_rejection_without_landing_or_disarm() {
        let mut mavlink = FakeMavlink {
            events: VecDeque::from([
                heartbeat(0),
                accepted(apm::MavCmd::MAV_CMD_DO_SET_MODE as u32),
                heartbeat(ARDUCOPTER_GUIDED_MODE_ID),
                accepted(MAV_CMD_COMPONENT_ARM_DISARM),
                failed(apm::MavCmd::MAV_CMD_NAV_TAKEOFF as u32),
            ]),
            ..FakeMavlink::default()
        };

        let report = run_real_hover_runtime(&mut mavlink, &hover_request()).expect("runtime");

        assert!(!report.ok);
        assert_eq!(
            report.blockers,
            vec!["real_hover_takeoff_rejected:MAV_RESULT_FAILED"]
        );
        assert_eq!(mavlink.sent_guided, 1);
        assert_eq!(mavlink.sent_arm, 1);
        assert_eq!(mavlink.sent_takeoff, 1);
        assert_eq!(mavlink.sent_land, 0);
        assert_eq!(mavlink.sent_disarm, 0);
        assert_eq!(report.fsm.state, "armed");
        assert_eq!(report.fsm.failed_state.as_deref(), Some("takeoff"));
        assert_eq!(report.landing_claim, "not_requested");
        assert_eq!(report.shutdown_claim, "not_requested");
    }
}
