"""Common companion mission API for sim/real runtime functional core."""

from __future__ import annotations

from navlab.common.companion.mission.command_adapter import (
    MissionCommandAdapter,
    MissionCommandRuntime,
    request_mission_command,
)
from navlab.common.companion.mission.context import (
    CommandState,
    FcuState,
    HoverState,
    LandingRuntimeSnapshot,
    LandingState,
    MissionClock,
    MissionContext,
    MissionEvidence,
    MissionIO,
    MissionRuntimeSnapshot,
    MissionState,
    NavState,
    PoseState,
    apply_landing_runtime_snapshot_to_context,
    apply_runtime_snapshot_to_context,
)
from navlab.common.companion.mission.evidence.hover import (
    HoverCompletionEvaluation,
    HoverDriftSummary,
    HoverEvidenceRecorder,
    HoverEvidenceWindow,
    classify_hover_drift,
    classify_hover_slo_tier,
    json_safe_number,
    summarize_hover_altitude_crosscheck,
    summarize_hover_drift,
)
from navlab.common.companion.mission.evidence.landing import (
    DEFAULT_LANDING_MAX_POST_TOUCHDOWN_BOUNCE_M,
    DEFAULT_LANDING_RANGEFINDER_LOCAL_CROSSCHECK_MAX_HEIGHT_M,
    DEFAULT_LANDING_RANGEFINDER_MAX_ABOVE_LOCAL_M,
    DEFAULT_LANDING_RANGEFINDER_MAX_RATE_MPS,
    DEFAULT_LANDING_RANGEFINDER_OUTLIER_MAX_NEIGHBOR_DT_SEC,
    DEFAULT_LANDING_RANGEFINDER_OUTLIER_MIN_M,
    LandingDescentSample,
    LandingDescentSetpoint,
    LandingEvidenceRecorder,
    build_landing_intent_payload,
    compute_landing_descent_setpoint,
    landing_descent_evidence_height_and_source_m,
    landing_descent_evidence_height_m,
    landing_descent_height_m,
    landing_descent_target_z_ned,
    landing_effective_descent_rate_mps,
    landing_touchdown_candidate,
    summarize_landing_descent_profile,
)
from navlab.common.companion.mission.evidence.summary import (
    MissionSummaryBuilder,
    MissionSummaryWriter,
    build_hover_status_payload,
    build_landing_summary,
    mission_phase_summary_fields,
)
from navlab.common.companion.mission.fsm import (
    HOVER_PHASE_TO_MISSION_PHASE_STATE,
    LANDING_STATE_TO_MISSION_PHASE_STATE,
    MissionPhaseHistoryEntry,
    MissionPhaseRecorder,
    MissionPhaseSnapshot,
    mission_phase_state_for_hover_phase,
    mission_phase_state_for_landing_state,
)
from navlab.common.companion.mission.hover_landing import (
    HoverMissionPipelineRunner,
    HoverPipelineConfig,
    HoverTickOutcome,
    HoverTickRuntime,
    LandingTickOutcome,
    LandingTickPreparation,
)
from navlab.common.companion.mission.mavlink_protocol import (
    ARDUCOPTER_LAND_MODE_NUMBER,
    append_bounded_command_ack,
    command_ack_accepted,
    command_ack_rejected,
    command_ack_success,
    mavlink,
    mavlink_param_id_to_str,
    mode_number,
)
from navlab.common.companion.mission.pipeline import FlightPipeline, Stage, StageResult, StageStatus
from navlab.common.companion.mission.policy import (
    DeadlineEvaluation,
    GateStatus,
    OperatorConfirmationEvaluation,
    OperatorConfirmationRequirement,
    TargetHardCapEvaluation,
    evaluate_deadline_policy,
    evaluate_operator_confirmations,
    evaluate_target_hard_cap_policy,
    merge_gate_statuses,
    reason_code,
)
from navlab.common.companion.mission.runtime_state import (
    ExternalNavStatusSnapshot,
    MavlinkExternalNavStatusSnapshot,
    MavlinkRuntimeCollections,
    MavlinkRuntimeState,
    MavlinkRuntimeUpdate,
    MavlinkStatusSnapshot,
    MissionRuntimeAdapterConfig,
    MissionRuntimeReadinessSummary,
    MissionRuntimeStateAdapter,
    RuntimeStatusUpdate,
    append_bounded_statustext,
    apply_bounded_mavlink_collections,
    external_nav_status_snapshot,
    mavlink_external_nav_status_snapshot,
    mavlink_runtime_update,
    mavlink_status_snapshot,
    parse_status_payload,
    statustext_indicates_crash,
)
from navlab.common.companion.mission.stages.hover import (
    HoverDecision,
    HoverHealthGateConfig,
    HoverHealthGateResult,
    HoverHoldConfig,
    HoverHoldStage,
    HoverInputs,
    HoverRequirements,
    apply_hover_health_gate,
    capture_hold_anchor,
    classify_hover_health,
    decide_hover,
    height_reaches_target,
    hold_axis_or_current,
    hold_yaw_or_current,
    hover_health_payload,
    hover_hold_setpoint_axes,
    hover_inputs_from_context,
    independent_takeoff_height_reached,
    should_fail_fast_wait_ready,
    should_send_position_hold_setpoint,
)
from navlab.common.companion.mission.stages.landing import (
    FCU_LAND_PARAM_NAMES,
    LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
    LANDING_POLICY_GUIDED_DESCENT,
    LANDING_POLICY_LAND_IN_PLACE,
    LandingStage,
    LandingStageConfig,
    fcu_land_params_report,
    landing_acceptance_ok,
    landing_controller_for_state,
    landing_descent_profile_enforced,
    landing_handoff_confirmed,
    landing_policy_uses_ap_land_mode,
    should_command_land_this_tick,
    should_send_disarm_after_touchdown,
    should_use_guided_descent_before_land,
)
from navlab.common.companion.mission.stages.prefix import (
    ArmStage,
    FlightPrefixConfig,
    GuidedModeStage,
    RuntimeReadyStage,
    TakeoffStage,
)
from navlab.common.companion.mission.summary_runtime import (
    HoverMissionSummaryConfig,
    HoverMissionSummaryRuntime,
)

__all__ = [name for name in globals() if not name.startswith("_") and name != "annotations"]
