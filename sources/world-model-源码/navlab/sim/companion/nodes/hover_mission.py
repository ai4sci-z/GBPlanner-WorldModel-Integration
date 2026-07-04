from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections.abc import Sequence

from navlab.common.companion.mission.command_adapter import MissionCommandRuntime
from navlab.common.companion.mission.context import (
    LandingRuntimeSnapshot,
    LandingState,
    MissionClock,
    MissionContext,
    apply_runtime_snapshot_to_context,
)
from navlab.common.companion.mission.evidence.hover import (
    HoverCompletionEvaluation,
    HoverEvidenceRecorder,
)
from navlab.common.companion.mission.evidence.landing import (
    LandingEvidenceRecorder,
    build_landing_intent_payload,
    compute_landing_descent_setpoint,
    landing_descent_evidence_height_and_source_m,
    landing_touchdown_candidate,
)
from navlab.common.companion.mission.evidence.summary import (
    build_hover_status_payload,
)
from navlab.common.companion.mission.fsm import (
    MissionPhaseRecorder,
    MissionPhaseSnapshot,
    mission_phase_state_for_landing_state,
)
from navlab.common.companion.mission.hover_landing import (
    HoverMissionPipelineRunner,
    HoverPipelineConfig,
    HoverTickRuntime,
    LandingTickPreparation,
)
from navlab.common.companion.mission.pipeline import FlightPipeline
from navlab.common.companion.mission.runtime_state import (
    MavlinkRuntimeCollections,
    MavlinkRuntimeState,
    MissionRuntimeAdapterConfig,
    MissionRuntimeStateAdapter,
    apply_bounded_mavlink_collections,
    mavlink_runtime_update,
)
from navlab.common.companion.mission.stages.hover import (
    HoverDecision,
    HoverHealthGateConfig,
    HoverHoldConfig,
    HoverHoldStage,
    HoverInputs,
    HoverRequirements,
    capture_hold_anchor,
    hold_yaw_or_current,
    hover_hold_setpoint_axes,
)
from navlab.common.companion.mission.stages.landing import (
    FCU_LAND_PARAM_NAMES,
    LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
    LANDING_POLICY_GUIDED_DESCENT,
    LANDING_POLICY_LAND_IN_PLACE,
    LandingStage,
    LandingStageConfig,
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
from navlab.sim.companion.mission.mavlink_commands import (
    DEFAULT_ORIGIN_ALT_M,
    DEFAULT_ORIGIN_LAT_DEG,
    DEFAULT_ORIGIN_LON_DEG,
    command_ack_accepted,
    command_ack_rejected,
    command_arm,
    command_takeoff,
    mode_number,
    send_gcs_heartbeat,
    send_local_position_yaw_setpoint,
    set_arming_check,
    set_ekf_origin,
    set_home_position,
    set_mode,
)
from navlab.sim.companion.mission.mavlink_commands import (
    command_disarm as _command_disarm,
)
from navlab.sim.companion.mission.mavlink_commands import (
    command_land as _command_land,
)
from navlab.sim.companion.mission.mavlink_commands import (
    request_param_read as _request_param_read,
)
from navlab.sim.companion.runtime.status import DEFAULT_SIM_LOG_TOPIC, encode_sim_log

os.environ.setdefault("MAVLINK20", "1")
HOVER_DURATION_TOLERANCE_SEC = 0.25
DEFAULT_LANDING_DESCENT_RATE_MPS = 0.12
DEFAULT_LANDING_LAND_COMMAND_ALTITUDE_M = 0.18
DEFAULT_LANDING_MAX_DESCENT_RATE_MPS = 0.60
DEFAULT_LANDING_SLOWDOWN_ALTITUDE_M = 0.60
DEFAULT_LANDING_NEAR_GROUND_DESCENT_RATE_MPS = 0.01


def _operator_confirm_value(payload: str) -> bool | None:
    """Parse operator confirm messages from a bool/string/JSON payload."""

    text = payload.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = text
    if isinstance(parsed, dict):
        parsed = parsed.get("confirm", parsed.get("confirmed", parsed.get("proceed")))
    if isinstance(parsed, bool):
        return parsed
    if isinstance(parsed, str):
        value = parsed.strip().lower()
        if value in {"1", "true", "yes", "confirm", "confirmed", "continue", "proceed"}:
            return True
        if value in {"0", "false", "no", "cancel", "hold", "stop"}:
            return False
    return None


def _request_hover_streams(connection, target_system: int, target_component: int) -> None:
    from pymavlink.dialects.v20 import ardupilotmega as mavlink

    for message_id, hz in (
        (mavlink.MAVLINK_MSG_ID_HEARTBEAT, 2.0),
        (mavlink.MAVLINK_MSG_ID_ATTITUDE, 10.0),
        (mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED, 10.0),
        (mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 4.0),
        (mavlink.MAVLINK_MSG_ID_EXTENDED_SYS_STATE, 4.0),
        (mavlink.MAVLINK_MSG_ID_DISTANCE_SENSOR, 10.0),
        (mavlink.MAVLINK_MSG_ID_GPS_GLOBAL_ORIGIN, 1.0),
        (mavlink.MAVLINK_MSG_ID_HOME_POSITION, 1.0),
        (mavlink.MAVLINK_MSG_ID_STATUSTEXT, 2.0),
    ):
        connection.mav.command_long_send(
            target_system,
            target_component,
            mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            message_id,
            int(1_000_000.0 / hz),
            0,
            0,
            0,
            0,
            0,
        )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run NavLab FCU-controlled hover mission via MAVLink setpoints.")
    parser.add_argument("--endpoint", default="tcp:sitl:5765")
    parser.add_argument("--duration-sec", type=float, default=90.0)
    parser.add_argument("--summary-file", default="")
    parser.add_argument("--mode", default="GUIDED")
    parser.add_argument("--takeoff-alt-m", type=float, default=0.45)
    parser.add_argument("--min-airborne-alt-m", type=float, default=0.10)
    parser.add_argument("--preflight-ready-sec", type=float, default=5.0)
    parser.add_argument("--max-wait-ready-sec", type=float, default=35.0)
    parser.add_argument("--hover-settle-sec", type=float, default=2.0)
    parser.add_argument("--hover-altitude-tolerance-m", type=float, default=0.18)
    parser.add_argument("--hover-hold-sec", type=float, default=20.0)
    parser.add_argument("--hover-health-min-observation-sec", type=float, default=10.0)
    parser.add_argument("--hover-health-stable-required-sec", type=float, default=5.0)
    parser.add_argument("--hover-health-max-wait-sec", type=float, default=60.0)
    parser.add_argument("--operator-confirm-required", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--operator-confirm-timeout-sec", type=float, default=60.0)
    parser.add_argument("--operator-confirm-topic", default="/navlab/hover/operator_confirm")
    parser.add_argument("--operator-confirm-received", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--max-horizontal-drift-m", type=float, default=1.0)
    parser.add_argument("--hover-span-target-m", type=float, default=0.0)
    parser.add_argument("--hover-span-hard-cap-m", type=float, default=0.0)
    parser.add_argument("--max-altitude-drift-m", type=float, default=0.6)
    parser.add_argument("--origin-lat-deg", type=float, default=DEFAULT_ORIGIN_LAT_DEG)
    parser.add_argument("--origin-lon-deg", type=float, default=DEFAULT_ORIGIN_LON_DEG)
    parser.add_argument("--origin-alt-m", type=float, default=DEFAULT_ORIGIN_ALT_M)
    parser.add_argument("--source-system", type=int, default=255)
    parser.add_argument("--source-component", type=int, default=190)
    parser.add_argument("--status-topic", default="/navlab/hover/status")
    parser.add_argument("--landing-status-topic", default="/navlab/landing/status")
    parser.add_argument("--landing-intent-topic", default="/navlab/landing/intent")
    parser.add_argument("--sim-log-topic", default=DEFAULT_SIM_LOG_TOPIC)
    parser.add_argument("--external-nav-status-topic", default="/external_nav/status")
    parser.add_argument("--mavlink-external-nav-status-topic", default="/mavlink_external_nav/status")
    parser.add_argument("--imu-status-topic", default="/imu/status")
    parser.add_argument("--mavlink-status-topic", default="/navlab/mavlink/status")
    parser.add_argument("--status-timeout-sec", type=float, default=1.0)
    parser.add_argument("--external-nav-loss-grace-sec", type=float, default=1.0)
    parser.add_argument("--setpoint-rate-hz", type=float, default=5.0)
    parser.add_argument(
        "--landing-policy",
        choices=[
            LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
            LANDING_POLICY_GUIDED_DESCENT,
            LANDING_POLICY_LAND_IN_PLACE,
        ],
        default=LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER,
    )
    parser.add_argument("--pre-land-hold-sec", type=float, default=2.0)
    parser.add_argument("--max-landing-duration-sec", type=float, default=35.0)
    parser.add_argument("--landing-descent-rate-mps", type=float, default=DEFAULT_LANDING_DESCENT_RATE_MPS)
    parser.add_argument(
        "--landing-land-command-altitude-m",
        type=float,
        default=DEFAULT_LANDING_LAND_COMMAND_ALTITUDE_M,
    )
    parser.add_argument("--landing-setpoint-lookahead-sec", type=float, default=0.5)
    parser.add_argument("--landing-slowdown-altitude-m", type=float, default=DEFAULT_LANDING_SLOWDOWN_ALTITUDE_M)
    parser.add_argument(
        "--landing-near-ground-descent-rate-mps",
        type=float,
        default=DEFAULT_LANDING_NEAR_GROUND_DESCENT_RATE_MPS,
    )
    parser.add_argument("--max-landing-descent-rate-mps", type=float, default=DEFAULT_LANDING_MAX_DESCENT_RATE_MPS)
    parser.add_argument("--touchdown-altitude-m", type=float, default=0.12)
    parser.add_argument("--touchdown-vertical-speed-mps", type=float, default=0.08)
    parser.add_argument("--touchdown-confirm-sec", type=float, default=0.5)
    parser.add_argument("--force-disarm-grace-sec", type=float, default=3.0)
    parser.add_argument("--force-disarm-after-touchdown", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-disarm", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-motors-safe", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-external-nav", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-imu-status", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--send-position-setpoints", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--disable-arming-checks", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force-arm", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--simulate-mode-arm", action=argparse.BooleanOptionalAction, default=False)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    args.hover_span_target_m = args.hover_span_target_m or args.max_horizontal_drift_m
    args.hover_span_hard_cap_m = args.hover_span_hard_cap_m or args.max_horizontal_drift_m
    if (
        args.hover_span_target_m <= 0
        or args.hover_span_hard_cap_m <= 0
        or not math.isfinite(args.hover_span_target_m)
        or not math.isfinite(args.hover_span_hard_cap_m)
        or args.hover_span_target_m > args.hover_span_hard_cap_m
    ):
        raise SystemExit("invalid hover SLO policy: require 0 < hover-span-target-m <= hover-span-hard-cap-m")

    try:
        import rclpy
        from pymavlink import mavutil
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
        from rclpy.node import Node
        from std_msgs.msg import String
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mavlink_hover_mission_controller requires ROS2 and pymavlink. Run it from the NavLab companion image."
        ) from exc

    class HoverMissionCommandAdapter:
        """Command side-effect adapter used by reusable prefix stages."""

        def __init__(self, controller: MavlinkHoverMissionController) -> None:
            self._controller = controller

        def _has_target(self) -> bool:
            controller = self._controller
            return controller._runtime.target_system is not None and controller._runtime.target_component is not None

        def request_guided_mode(self, ctx: MissionContext) -> bool:
            controller = self._controller
            now = ctx.clock.now_monotonic
            if not self._has_target() or now < controller._command_runtime.next_mode_command:
                return False
            set_mode(controller._connection, controller._runtime.target_system, controller.mode_number)
            controller._count_sent_command("set_mode_guided")
            controller._command_runtime.next_mode_command = now + 1.0
            return True

        def request_arm(self, ctx: MissionContext) -> bool:
            controller = self._controller
            now = ctx.clock.now_monotonic
            if not self._has_target() or now < controller._command_runtime.next_arm_command:
                return False
            command_arm(
                controller._connection,
                controller._runtime.target_system,
                controller._runtime.target_component,
                args.force_arm,
            )
            controller._count_sent_command("arm")
            controller._command_runtime.next_arm_command = now + 2.0
            return True

        def request_takeoff(self, ctx: MissionContext) -> bool:
            controller = self._controller
            now = ctx.clock.now_monotonic
            if not self._has_target() or now < controller._command_runtime.next_takeoff_command:
                return False
            command_takeoff(
                controller._connection,
                controller._runtime.target_system,
                controller._runtime.target_component,
                args.takeoff_alt_m,
            )
            controller._count_sent_command("takeoff")
            controller._command_runtime.next_takeoff_command = now + 2.0
            return True

        def send_hold_setpoint(self, ctx: MissionContext) -> bool:
            controller = self._controller
            before = controller._command_runtime.setpoints_sent
            controller._send_hold_setpoint(ctx.clock.now_monotonic)
            return controller._command_runtime.setpoints_sent > before

        def send_landing_descent_setpoint(self, ctx: MissionContext) -> bool:
            controller = self._controller
            before = controller._command_runtime.setpoints_sent
            controller._send_landing_descent_setpoint(ctx.clock.now_monotonic)
            return controller._command_runtime.setpoints_sent > before

        def request_land(self, ctx: MissionContext) -> bool:
            controller = self._controller
            now = ctx.clock.now_monotonic
            if not self._has_target() or now < controller._command_runtime.next_land_command:
                return False
            first_land_command = not controller._landing_evidence.land_command_sent
            if first_land_command:
                controller._landing_evidence.mark_land_command_sent(
                    now_monotonic=now,
                    mode_before_land=controller._runtime.current_custom_mode,
                )
                controller._request_fcu_land_params()
            _command_land(
                controller._connection, controller._runtime.target_system, controller._runtime.target_component
            )
            controller._count_sent_command("land")
            controller._command_runtime.next_land_command = now + 2.0
            ctx.state.landing.land_command_sent = True
            if first_land_command:
                controller._record_mission_phase(
                    now,
                    mission_phase_state_for_landing_state("land_command_sent"),
                    "command_land",
                    guard="land_command_sent",
                )
            return True

        def request_disarm(self, ctx: MissionContext) -> bool:
            controller = self._controller
            now = ctx.clock.now_monotonic
            if not self._has_target() or now < controller._command_runtime.next_disarm_command:
                return False
            _command_disarm(
                controller._connection,
                controller._runtime.target_system,
                controller._runtime.target_component,
                force=args.force_disarm_after_touchdown,
            )
            controller._landing_evidence.force_disarm_used = controller._landing_evidence.force_disarm_used or bool(
                args.force_disarm_after_touchdown
            )
            controller._count_sent_command("disarm")
            controller._command_runtime.next_disarm_command = now + 2.0
            return True

    class MavlinkHoverMissionController(Node):
        def __init__(self) -> None:
            super().__init__("mavlink_hover_mission_controller")
            self._connection = mavutil.mavlink_connection(
                args.endpoint,
                source_system=args.source_system,
                source_component=args.source_component,
                dialect="ardupilotmega",
            )
            self._status_pub = self.create_publisher(String, args.status_topic, 10)
            self._landing_status_pub = self.create_publisher(String, args.landing_status_topic, 10)
            self._landing_intent_pub = self.create_publisher(String, args.landing_intent_topic, 10)
            self._sim_log_pub = self.create_publisher(String, args.sim_log_topic, 10)
            self.create_subscription(String, args.external_nav_status_topic, self._handle_external_nav_status, 10)
            self.create_subscription(
                String,
                args.mavlink_external_nav_status_topic,
                self._handle_mavlink_external_nav_status,
                10,
            )
            self.create_subscription(String, args.imu_status_topic, self._handle_imu_status, 10)
            self.create_subscription(String, args.mavlink_status_topic, self._handle_mavlink_status, 10)
            self.create_subscription(String, args.operator_confirm_topic, self._handle_operator_confirm, 10)
            self.mode_number = mode_number(args.mode)
            self._started = time.monotonic()
            self._runtime = MavlinkRuntimeState()
            self._mission_runtime_config = MissionRuntimeAdapterConfig(
                status_timeout_sec=args.status_timeout_sec,
                require_external_nav=args.require_external_nav,
                require_imu_status=args.require_imu_status,
                simulate_mode_arm=args.simulate_mode_arm,
                takeoff_alt_m=args.takeoff_alt_m,
            )
            self._mission_runtime = MissionRuntimeStateAdapter(started_at_monotonic=self._started)
            self._command_runtime = MissionCommandRuntime()
            self._landing_evidence = LandingEvidenceRecorder()
            self._summary_runtime = HoverMissionSummaryRuntime(
                HoverMissionSummaryConfig(
                    summary_file=args.summary_file,
                    mode=args.mode,
                    mode_number=self.mode_number,
                    takeoff_alt_m=args.takeoff_alt_m,
                    hover_altitude_tolerance_m=args.hover_altitude_tolerance_m,
                    hover_hold_sec=args.hover_hold_sec,
                    hover_health_min_observation_sec=args.hover_health_min_observation_sec,
                    hover_health_stable_required_sec=args.hover_health_stable_required_sec,
                    hover_health_max_wait_sec=args.hover_health_max_wait_sec,
                    operator_confirm_required=args.operator_confirm_required,
                    operator_confirm_timeout_sec=args.operator_confirm_timeout_sec,
                    hover_duration_tolerance_sec=HOVER_DURATION_TOLERANCE_SEC,
                    max_horizontal_drift_m=args.max_horizontal_drift_m,
                    hover_span_target_m=args.hover_span_target_m or args.max_horizontal_drift_m,
                    hover_span_hard_cap_m=args.hover_span_hard_cap_m or args.max_horizontal_drift_m,
                    max_altitude_drift_m=args.max_altitude_drift_m,
                    preflight_ready_sec=args.preflight_ready_sec,
                    max_wait_ready_sec=args.max_wait_ready_sec,
                    hover_settle_sec=args.hover_settle_sec,
                    require_external_nav=args.require_external_nav,
                    require_imu_status=args.require_imu_status,
                    send_position_setpoints=args.send_position_setpoints,
                    landing_policy=args.landing_policy,
                    require_disarm=args.require_disarm,
                    require_motors_safe=args.require_motors_safe,
                    touchdown_confirm_sec=args.touchdown_confirm_sec,
                    force_disarm_grace_sec=args.force_disarm_grace_sec,
                    force_disarm_after_touchdown=args.force_disarm_after_touchdown,
                    landing_setpoint_lookahead_sec=args.landing_setpoint_lookahead_sec,
                    landing_slowdown_altitude_m=args.landing_slowdown_altitude_m,
                    landing_near_ground_descent_rate_mps=args.landing_near_ground_descent_rate_mps,
                    max_landing_descent_rate_mps=args.max_landing_descent_rate_mps,
                    touchdown_altitude_m=args.touchdown_altitude_m,
                )
            )
            self._next_request = 0.0
            self._next_heartbeat = 0.0
            self._next_origin_command = 0.0
            self._mission_phase = MissionPhaseRecorder(started_at_monotonic=self._started)
            prefix_config = FlightPrefixConfig(
                preflight_ready_sec=args.preflight_ready_sec,
                max_wait_ready_sec=args.max_wait_ready_sec,
                external_nav_loss_grace_sec=args.external_nav_loss_grace_sec,
                require_external_nav=args.require_external_nav,
                require_fcu_external_nav=args.require_external_nav,
                require_imu_status=args.require_imu_status,
                takeoff_alt_m=args.takeoff_alt_m,
                hover_altitude_tolerance_m=args.hover_altitude_tolerance_m,
            )
            self._mission_context = MissionContext(
                clock=MissionClock(started_at_monotonic=self._started, now_monotonic=self._started)
            )
            self._mission_context.state.hover.operator_confirm_received = args.operator_confirm_received
            self._mission_context.io.command_adapter = HoverMissionCommandAdapter(self)
            prefix_pipeline = FlightPipeline(
                [
                    RuntimeReadyStage(prefix_config),
                    GuidedModeStage(),
                    ArmStage(),
                    TakeoffStage(prefix_config),
                ]
            )
            hover_body_stage = HoverHoldStage(
                HoverHoldConfig(
                    preflight_ready_sec=args.preflight_ready_sec,
                    hover_settle_sec=args.hover_settle_sec,
                    hover_hold_sec=args.hover_hold_sec,
                    takeoff_alt_m=args.takeoff_alt_m,
                    hover_altitude_tolerance_m=args.hover_altitude_tolerance_m,
                    send_position_setpoints=args.send_position_setpoints,
                    requirements=HoverRequirements(
                        require_external_nav=args.require_external_nav,
                        require_fcu_external_nav=args.require_external_nav,
                        require_imu_status=args.require_imu_status,
                        external_nav_loss_grace_sec=args.external_nav_loss_grace_sec,
                    ),
                    health_gate=HoverHealthGateConfig(
                        min_observation_sec=args.hover_health_min_observation_sec,
                        stable_required_sec=args.hover_health_stable_required_sec,
                        max_wait_sec=args.hover_health_max_wait_sec,
                        operator_confirm_required=args.operator_confirm_required,
                        operator_confirm_timeout_sec=args.operator_confirm_timeout_sec,
                    ),
                )
            )
            landing_stage = LandingStage(
                LandingStageConfig(
                    landing_policy=args.landing_policy,
                    pre_land_hold_sec=args.pre_land_hold_sec,
                    max_landing_duration_sec=args.max_landing_duration_sec,
                    require_disarm=args.require_disarm,
                    require_motors_safe=args.require_motors_safe,
                    force_disarm_grace_sec=args.force_disarm_grace_sec,
                )
            )
            self._status_history: list[dict[str, object]] = []
            self._mavlink_collections = MavlinkRuntimeCollections()
            self._hover_evidence = HoverEvidenceRecorder()
            self._mission_pipeline = HoverMissionPipelineRunner(
                prefix_pipeline=prefix_pipeline,
                hover_stage=hover_body_stage,
                landing_stage=landing_stage,
                hover_evidence=self._hover_evidence,
                landing_evidence=self._landing_evidence,
                hover_config=HoverPipelineConfig(
                    max_wait_ready_sec=args.max_wait_ready_sec,
                    takeoff_alt_m=args.takeoff_alt_m,
                    hover_altitude_tolerance_m=args.hover_altitude_tolerance_m,
                    hover_hold_sec=args.hover_hold_sec,
                    duration_tolerance_sec=HOVER_DURATION_TOLERANCE_SEC,
                    max_horizontal_drift_m=args.max_horizontal_drift_m,
                    hover_span_target_m=args.hover_span_target_m or args.max_horizontal_drift_m,
                    hover_span_hard_cap_m=args.hover_span_hard_cap_m or args.max_horizontal_drift_m,
                    max_altitude_drift_m=args.max_altitude_drift_m,
                ),
            )
            self.create_timer(0.05, self._tick)
            self.get_logger().info(f"hover mission controller started endpoint={args.endpoint}")

        def _record_mission_phase(
            self,
            now: float,
            state: str,
            reason: str,
            *,
            guard: str | None = None,
            blocker: str | None = None,
        ) -> None:
            self._mission_phase.transition(
                now_monotonic=now,
                state=state,
                reason=reason,
                guard=guard,
                blocker=blocker,
            )

        def _mission_phase_snapshot(self) -> MissionPhaseSnapshot:
            return self._mission_phase.snapshot(now_monotonic=time.monotonic())

        def _stop_vehicle(self) -> None:
            if self._runtime.target_system is None or self._runtime.target_component is None:
                return
            _command_disarm(self._connection, self._runtime.target_system, self._runtime.target_component)
            self._count_sent_command("disarm")

        def _request_fcu_land_params(self) -> None:
            if (
                self._runtime.target_system is None
                or self._runtime.target_component is None
                or self._landing_evidence.fcu_land_param_requests_sent
            ):
                return
            for name in FCU_LAND_PARAM_NAMES:
                _request_param_read(self._connection, self._runtime.target_system, self._runtime.target_component, name)
            self._landing_evidence.fcu_land_param_requests_sent = True

        def _handle_external_nav_status(self, msg: String) -> None:
            now = time.monotonic()
            update = self._mission_runtime.apply_external_nav_status(msg.data, now_monotonic=now)
            snapshot = update.snapshot
            if update.changed and snapshot is not None:
                event = snapshot.event
                self.get_logger().info(
                    "external_nav status "
                    f"ready={snapshot.ready} "
                    f"state={snapshot.state} "
                    f"slam_quality={snapshot.slam_quality} "
                    f"slam_reason={snapshot.slam_quality_reason} "
                    f"input={event['input_topic']} "
                    f"rate_hz={event['rate_hz']} "
                    f"rate_ok={event['rate_ok']} "
                    f"frame_ok={event['frame_ok']}"
                )

        def _handle_imu_status(self, msg: String) -> None:
            self._mission_runtime.apply_imu_status(msg.data, now_monotonic=time.monotonic())

        def _handle_mavlink_external_nav_status(self, msg: String) -> None:
            self._mission_runtime.apply_mavlink_external_nav_status(msg.data, now_monotonic=time.monotonic())

        def _handle_mavlink_status(self, msg: String) -> None:
            self._mission_runtime.apply_mavlink_status(msg.data, mode_number=self.mode_number)

        def _handle_operator_confirm(self, msg: String) -> None:
            value = _operator_confirm_value(msg.data)
            if value is None:
                self.get_logger().warning("ignored invalid operator confirm payload")
                return
            hover = self._mission_context.state.hover
            if not value:
                hover.operator_confirm_received = False
                return
            if hover.operator_confirm_allowed and hover.health_band == "green":
                hover.operator_confirm_received = True
                self.get_logger().info("operator confirmed hover health proceed")
                return
            hover.operator_confirm_received = False
            self.get_logger().warning("operator confirm ignored because hover health is not green/allowed")

        def _tick(self) -> None:
            now = time.monotonic()
            if self._mission_pipeline.landing_started:
                self._tick_landing(now)
                return
            if now - self._started >= args.duration_sec:
                if self._runtime.armed_seen or self._runtime.airborne_seen:
                    self._mission_context.state.hover.body_ok = False
                    self._mission_context.state.hover.body_reason = "duration_timeout"
                    self._start_landing(now)
                    return
                self._stop_vehicle()
                self.write_summary(ok=False, reason="duration_timeout", landing_ok=False)
                rclpy.try_shutdown()
                return
            self._drain_mavlink()
            if self._runtime.crash_detected:
                self._stop_vehicle()
                self.write_summary(ok=False, reason="crash_detected", landing_ok=False)
                rclpy.try_shutdown()
                return
            if now >= self._next_heartbeat:
                send_gcs_heartbeat(self._connection)
                self._next_heartbeat = now + 1.0
            if (
                self._runtime.target_system is not None
                and self._runtime.target_component is not None
                and now >= self._next_request
            ):
                _request_hover_streams(self._connection, self._runtime.target_system, self._runtime.target_component)
                if args.disable_arming_checks:
                    set_arming_check(self._connection, self._runtime.target_system, self._runtime.target_component, 0)
                self._next_request = now + 2.0
            if (
                self._runtime.target_system is not None
                and self._runtime.target_component is not None
                and now >= self._next_origin_command
            ):
                if not self._runtime.gps_global_origin_seen:
                    set_ekf_origin(
                        self._connection,
                        self._runtime.target_system,
                        args.origin_lat_deg,
                        args.origin_lon_deg,
                        args.origin_alt_m,
                    )
                    self._count_sent_command("set_gps_global_origin")
                if not self._runtime.home_position_seen:
                    set_home_position(
                        self._connection,
                        self._runtime.target_system,
                        self._runtime.target_component,
                        args.origin_lat_deg,
                        args.origin_lon_deg,
                        args.origin_alt_m,
                    )
                    self._count_sent_command("set_home_position")
                self._next_origin_command = now + 2.0

            inputs = self._mission_runtime.build_hover_inputs(
                now_monotonic=now,
                config=self._mission_runtime_config,
                runtime=self._runtime,
                collections=self._mavlink_collections,
                target_z_ned=self._target_z_ned(),
                fcu_local_height_m=self._fcu_local_height_m(),
                rangefinder_relative_height_m=self._rangefinder_relative_height_m(),
                hover_started_at_monotonic=self._hover_evidence.active_started_at,
            )
            apply_runtime_snapshot_to_context(
                self._mission_context,
                self._mission_runtime.runtime_snapshot(
                    now_monotonic=now,
                    inputs=inputs,
                    runtime=self._runtime,
                    command_runtime=self._command_runtime,
                    collections=self._mavlink_collections,
                    fcu_local_height_m=self._fcu_local_height_m(inputs.current_z_ned),
                ),
            )
            outcome = self._mission_pipeline.tick_hover(
                self._mission_context,
                HoverTickRuntime(
                    now_monotonic=now,
                    inputs=inputs,
                    local_position_count=self._runtime.message_counts.get("LOCAL_POSITION_NED", 0),
                    crash_detected=self._runtime.crash_detected,
                ),
                record_fsm=self._record_mission_phase,
                publish_status=self._publish_status,
                begin_landing=lambda landing_now, completion: self._start_landing(
                    landing_now,
                    hover_completion=completion,
                ),
            )
            if outcome.status == "preflight_timeout":
                self._stop_vehicle()
                self.write_summary(ok=False, reason="preflight_timeout", landing_ok=False)
                rclpy.try_shutdown()
                return

        def _start_landing(self, now: float, *, hover_completion: HoverCompletionEvaluation | None = None) -> None:
            self._mission_pipeline.mark_landing_started()
            if hover_completion is None:
                hover_completion = self._hover_evidence.evaluate_completion(
                    target_alt_m=args.takeoff_alt_m,
                    altitude_tolerance_m=args.hover_altitude_tolerance_m,
                    hold_sec=args.hover_hold_sec,
                    duration_tolerance_sec=HOVER_DURATION_TOLERANCE_SEC,
                    max_horizontal_drift_m=args.max_horizontal_drift_m,
                    max_altitude_drift_m=args.max_altitude_drift_m,
                    local_position_count=self._runtime.message_counts.get("LOCAL_POSITION_NED", 0),
                    crash_detected=self._runtime.crash_detected,
                    hover_span_target_m=args.hover_span_target_m,
                    hover_span_hard_cap_m=args.hover_span_hard_cap_m,
                )
            self._landing_evidence.start_with_hover_evidence(
                now,
                frozen_hover_evidence=hover_completion.frozen_hover_evidence(
                    takeoff_ack_ok=command_ack_accepted(
                        self._mavlink_collections.command_acks,
                        mavlink.MAV_CMD_NAV_TAKEOFF,
                        self._mavlink_collections.accepted_command_ids,
                    ),
                    crash_detected=self._runtime.crash_detected,
                ),
            )
            self._record_mission_phase(
                now,
                mission_phase_state_for_landing_state(self._landing_evidence.state),
                self._mission_context.state.hover.body_reason or "task_body_complete",
                guard=self._landing_evidence.state,
            )
            intent = String()
            intent.data = json.dumps(
                build_landing_intent_payload(
                    source="mavlink_hover_mission_controller",
                    policy=args.landing_policy,
                    reason=self._mission_context.state.hover.body_reason,
                    updated_ms=int(time.time() * 1000),
                ),
                separators=(",", ":"),
                sort_keys=True,
            )
            self._landing_intent_pub.publish(intent)
            self._publish_landing_status()

        def _tick_landing(self, now: float) -> None:
            outcome = self._mission_pipeline.tick_landing(
                self._mission_context,
                now_monotonic=now,
                prepare_landing_tick=self._prepare_landing_tick,
                record_fsm=self._record_mission_phase,
            )
            if outcome.stop_vehicle:
                self._stop_vehicle()
            if outcome.publish_status:
                self._publish_landing_status()
            if outcome.record_task_success:
                self._record_mission_phase(
                    now,
                    "S13 task_success",
                    "task_success",
                    guard="task_success",
                )
            if outcome.shutdown:
                self.write_summary(
                    ok=outcome.summary_ok,
                    reason=outcome.reason,
                    landing_ok=outcome.summary_landing_ok,
                )
                rclpy.try_shutdown()
                return

        def _prepare_landing_tick(self, now: float) -> LandingTickPreparation:
            if self._runtime.target_system is None or self._runtime.target_component is None:
                return LandingTickPreparation(target_available=False)
            self._drain_mavlink()
            elapsed = (
                0.0
                if self._landing_evidence.started_at_monotonic is None
                else now - self._landing_evidence.started_at_monotonic
            )
            land_command_accepted = command_ack_accepted(
                self._mavlink_collections.command_acks,
                mavlink.MAV_CMD_NAV_LAND,
                self._mavlink_collections.accepted_command_ids,
            )
            touchdown_ready = False
            if elapsed >= args.pre_land_hold_sec:
                self._landing_evidence.start_descent(
                    now,
                    current_z_ned=self._runtime.current_z,
                    fallback_z_ned=-args.takeoff_alt_m,
                )
                self._record_landing_descent_sample(now)
                touchdown_ready = self._touchdown_candidate(now)
            descent_profile = self._landing_descent_profile()
            snapshot = self._landing_runtime_snapshot(
                now=now,
                elapsed_sec=elapsed,
                touchdown_ready=touchdown_ready,
                descent_profile=descent_profile,
                land_command_accepted=land_command_accepted,
            )
            return LandingTickPreparation(target_available=True, snapshot=snapshot)

        def _send_hold_setpoint(self, now: float) -> None:
            if (
                not args.send_position_setpoints
                or self._runtime.target_system is None
                or self._runtime.target_component is None
                or now < self._command_runtime.next_setpoint
            ):
                return
            hover = self._mission_context.state.hover
            hover.hold_x_m, hover.hold_y_m, hover.hold_yaw_rad = capture_hold_anchor(
                hover.hold_x_m,
                hover.hold_y_m,
                hover.hold_yaw_rad,
                self._runtime.current_x,
                self._runtime.current_y,
                self._runtime.current_yaw_rad,
            )
            target_x, target_y, target_z = hover_hold_setpoint_axes(
                hold_x=hover.hold_x_m,
                hold_y=hover.hold_y_m,
                current_x=self._runtime.current_x,
                current_y=self._runtime.current_y,
                current_z=self._runtime.current_z,
                target_z_ned=-args.takeoff_alt_m,
            )
            send_local_position_yaw_setpoint(
                self._connection,
                self._runtime.target_system,
                self._runtime.target_component,
                target_x,
                target_y,
                target_z,
                hold_yaw_or_current(hover.hold_yaw_rad, self._runtime.current_yaw_rad),
            )
            self._command_runtime.count_setpoint()
            self._command_runtime.next_setpoint = now + (1.0 / args.setpoint_rate_hz)

        def _send_landing_descent_setpoint(self, now: float) -> None:
            if (
                not args.send_position_setpoints
                or self._runtime.target_system is None
                or self._runtime.target_component is None
                or now < self._command_runtime.next_setpoint
            ):
                return
            hover = self._mission_context.state.hover
            hover.hold_x_m, hover.hold_y_m, hover.hold_yaw_rad = capture_hold_anchor(
                hover.hold_x_m,
                hover.hold_y_m,
                hover.hold_yaw_rad,
                self._runtime.current_x,
                self._runtime.current_y,
                self._runtime.current_yaw_rad,
            )
            setpoint = compute_landing_descent_setpoint(
                hold_x_m=hover.hold_x_m,
                hold_y_m=hover.hold_y_m,
                hold_yaw_rad=hover.hold_yaw_rad,
                current_x_m=self._runtime.current_x,
                current_y_m=self._runtime.current_y,
                current_yaw_rad=self._runtime.current_yaw_rad,
                start_z_ned=self._landing_evidence.start_z_ned,
                fallback_start_z_ned=-args.takeoff_alt_m,
                ground_z_ned=self._runtime.ground_z_ned,
                descent_started_at_monotonic=self._landing_evidence.descent_started_at_monotonic,
                now_monotonic=now,
                nominal_descent_rate_mps=args.landing_descent_rate_mps,
                rangefinder_relative_height_m=self._rangefinder_relative_height_m(),
                slowdown_altitude_m=args.landing_slowdown_altitude_m,
                near_ground_descent_rate_mps=args.landing_near_ground_descent_rate_mps,
                current_z_ned=self._runtime.current_z,
                setpoint_lookahead_sec=args.landing_setpoint_lookahead_sec,
            )
            send_local_position_yaw_setpoint(
                self._connection,
                self._runtime.target_system,
                self._runtime.target_component,
                setpoint.x_m,
                setpoint.y_m,
                setpoint.z_ned_m,
                setpoint.yaw_rad,
            )
            self._command_runtime.count_setpoint()
            self._command_runtime.next_setpoint = now + (1.0 / args.setpoint_rate_hz)

        def _record_landing_descent_sample(self, now: float) -> None:
            self._landing_evidence.append_descent_sample_from_pose(
                now_monotonic=now,
                current_range_m=self._runtime.current_range_m,
                ground_range_m=self._runtime.ground_range_m,
                current_z_ned=self._runtime.current_z,
                ground_z_ned=self._runtime.ground_z_ned,
                current_vz_mps=self._runtime.current_vz,
            )

        def _landing_descent_profile(self) -> dict[str, object]:
            return self._landing_evidence.descent_profile(
                max_descent_rate_mps=args.max_landing_descent_rate_mps,
                touchdown_altitude_m=args.touchdown_altitude_m,
            )

        def _raw_touchdown_candidate(self) -> bool:
            touchdown_height, _touchdown_height_source = landing_descent_evidence_height_and_source_m(
                current_range_m=self._runtime.current_range_m,
                ground_range_m=self._runtime.ground_range_m,
                current_z_ned=self._runtime.current_z,
                ground_z_ned=self._runtime.ground_z_ned,
            )
            return landing_touchdown_candidate(
                landed_state_on_ground=self._runtime.landed_state == mavlink.MAV_LANDED_STATE_ON_GROUND,
                current_range_m=touchdown_height,
                current_z_ned=self._runtime.current_z,
                current_vz_mps=self._runtime.current_vz,
                touchdown_altitude_m=args.touchdown_altitude_m,
                touchdown_vertical_speed_mps=args.touchdown_vertical_speed_mps,
            )

        def _touchdown_candidate(self, now: float) -> bool:
            return self._landing_evidence.update_touchdown_candidate(
                now_monotonic=now,
                raw_candidate=self._raw_touchdown_candidate(),
                landed_state_on_ground=self._runtime.landed_state == mavlink.MAV_LANDED_STATE_ON_GROUND,
                confirm_sec=args.touchdown_confirm_sec,
            )

        def _drain_mavlink(self) -> None:
            while True:
                msg = self._connection.recv_match(blocking=False)
                if msg is None:
                    return
                now = time.monotonic()
                update = mavlink_runtime_update(
                    msg,
                    mode_number=self.mode_number,
                    land_command_sent=self._landing_evidence.land_command_sent,
                    mode_before_land=self._landing_evidence.mode_before_land,
                    land_command_sent_time=self._landing_evidence.land_command_sent_time,
                    started_at_monotonic=self._started,
                    now_monotonic=now,
                    ground_z_ned=self._runtime.ground_z_ned,
                    ground_range_m=self._runtime.ground_range_m,
                    min_airborne_alt_m=args.min_airborne_alt_m,
                )
                self._runtime.apply_update(update, now_monotonic=now)
                apply_bounded_mavlink_collections(self._mavlink_collections, update)
                if update.mode_after_land is not None and self._landing_evidence.mode_after_land is None:
                    self._landing_evidence.mark_mode_after_land(update.mode_after_land)
                if update.land_mode_seen and not self._landing_evidence.land_mode_seen:
                    self._landing_evidence.mark_land_mode_seen(update.land_mode_seen_elapsed_sec)
                if update.fcu_land_param is not None:
                    name, value = update.fcu_land_param
                    self._landing_evidence.fcu_land_params[name] = value

        def _fcu_local_height_m(self, z_ned: float | None = None) -> float | None:
            z = self._runtime.current_z if z_ned is None else z_ned
            if z is None:
                return None
            if self._runtime.ground_z_ned is not None:
                return float(self._runtime.ground_z_ned) - float(z)
            return -float(z)

        def _rangefinder_relative_height_m(self) -> float | None:
            if self._runtime.current_range_m is None or self._runtime.ground_range_m is None:
                return None
            return max(0.0, float(self._runtime.current_range_m) - float(self._runtime.ground_range_m))

        def _landing_runtime_snapshot(
            self,
            *,
            now: float,
            elapsed_sec: float,
            touchdown_ready: bool,
            descent_profile: dict[str, object],
            land_command_accepted: bool,
        ) -> LandingRuntimeSnapshot:
            return LandingRuntimeSnapshot(
                now_monotonic=now,
                landing=LandingState(
                    policy=args.landing_policy,
                    state=self._landing_evidence.state,
                    started_at_monotonic=self._landing_evidence.started_at_monotonic,
                    elapsed_sec=elapsed_sec,
                    blockers=list(self._landing_evidence.blockers),
                    land_command_sent=self._landing_evidence.land_command_sent,
                    land_command_accepted=land_command_accepted,
                    land_command_rejected=command_ack_rejected(
                        self._mavlink_collections.command_acks,
                        mavlink.MAV_CMD_NAV_LAND,
                    ),
                    land_mode_seen=self._landing_evidence.land_mode_seen,
                    command_due=now >= self._command_runtime.next_land_command,
                    touchdown_confirmed=self._landing_evidence.touchdown_confirmed,
                    touchdown_ready=touchdown_ready,
                    touchdown_confirmed_elapsed_sec=(
                        None
                        if self._landing_evidence.touchdown_confirmed_time is None
                        else now - self._landing_evidence.touchdown_confirmed_time
                    ),
                    descent_profile_ok=descent_profile.get("ok") is True,
                    disarmed=not self._runtime.armed_seen,
                    disarmed_confirmed=not self._runtime.armed_seen,
                    motors_safe=(not self._runtime.armed_seen) if args.require_motors_safe else True,
                    disarm_due=now >= self._command_runtime.next_disarm_command,
                ),
            )

        def _prefix_pipeline_status(self) -> dict[str, object]:
            return self._mission_pipeline.prefix_pipeline_status(self._mission_context)

        def _target_z_ned(self) -> float:
            ground_z = self._runtime.ground_z_ned if self._runtime.ground_z_ned is not None else 0.0
            return ground_z - args.takeoff_alt_m

        def _publish_status(self, decision: HoverDecision, inputs: HoverInputs) -> None:
            status_payload = build_hover_status_payload(
                phase=decision.phase,
                reason=decision.reason,
                fsm_snapshot=self._mission_phase_snapshot(),
                prefix_pipeline=self._prefix_pipeline_status(),
                inputs=inputs,
                slam_quality_reason=self._mission_runtime.external_nav_slam_quality_reason,
                setpoints_sent_count=self._command_runtime.setpoints_sent,
                local_position_count=self._runtime.message_counts.get("LOCAL_POSITION_NED", 0),
                rangefinder_count=self._rangefinder_count(),
                current_yaw_rad=self._runtime.current_yaw_rad,
                hold_x=self._mission_context.state.hover.hold_x_m,
                hold_y=self._mission_context.state.hover.hold_y_m,
                hold_yaw_rad=self._mission_context.state.hover.hold_yaw_rad,
                hover_health=self._hover_health_payload(decision, inputs),
            )
            self._status_history.append(status_payload)
            self._status_history = self._status_history[-80:]
            msg = String()
            msg.data = json.dumps(status_payload, separators=(",", ":"), sort_keys=True)
            self._status_pub.publish(msg)
            sim_log = String()
            sim_log.data = encode_sim_log(
                source="mavlink_hover_mission_controller",
                event=decision.reason,
                mission_state="complete" if decision.terminal else "running",
                phase=decision.phase,
                current_x=inputs.current_x,
                current_y=inputs.current_y,
                current_z_ned=inputs.current_z_ned,
                current_yaw_rad=self._runtime.current_yaw_rad,
                setpoints_sent_count=self._command_runtime.setpoints_sent,
            )
            self._sim_log_pub.publish(sim_log)

        def _hover_health_payload(self, decision: HoverDecision, inputs: HoverInputs) -> dict[str, object]:
            hover = self._mission_context.state.hover
            confirm_elapsed_sec = (
                None
                if hover.operator_confirm_started_at_monotonic is None
                else max(0.0, time.monotonic() - hover.operator_confirm_started_at_monotonic)
            )
            return {
                "phase": hover.health_phase
                or ("hover_health_hold" if decision.phase == "hover_hold" else decision.phase),
                "runtime_phase_alias": decision.phase,
                "band": hover.health_band,
                "reason": hover.health_reason or decision.reason,
                "observed_sec": hover.health_observed_sec,
                "stable_sec": hover.health_stable_sec,
                "operator_confirm_required": args.operator_confirm_required,
                "operator_confirm_allowed": hover.operator_confirm_allowed,
                "operator_confirm_received": hover.operator_confirm_received,
                "operator_confirm_elapsed_sec": confirm_elapsed_sec,
                "sim_auto_continue_allowed": (
                    hover.health_band == "green"
                    and not args.operator_confirm_required
                    and hover.health_phase == "sim_auto_continue"
                ),
                "real_operator_confirm_allowed": hover.operator_confirm_allowed,
                "min_observation_sec": args.hover_health_min_observation_sec,
                "stable_required_sec": args.hover_health_stable_required_sec,
                "max_wait_sec": args.hover_health_max_wait_sec,
                "operator_confirm_timeout_sec": args.operator_confirm_timeout_sec,
            }

        def _landing_summary(self) -> dict[str, object]:
            return self._summary_runtime.landing_summary(
                now_monotonic=time.monotonic(),
                fsm_snapshot=self._mission_phase_snapshot(),
                runtime=self._runtime,
                collections=self._mavlink_collections,
                landing_evidence=self._landing_evidence,
                started_at_monotonic=self._started,
            )

        def _publish_landing_status(self) -> None:
            self._record_mission_phase(
                time.monotonic(),
                mission_phase_state_for_landing_state(self._landing_evidence.state),
                self._landing_evidence.state,
                guard=self._landing_evidence.state,
            )
            msg = String()
            msg.data = json.dumps(self._landing_summary(), separators=(",", ":"), sort_keys=True)
            self._landing_status_pub.publish(msg)

        def _rangefinder_count(self) -> int:
            return self._runtime.message_counts.get("DISTANCE_SENSOR", 0) + self._runtime.message_counts.get(
                "RANGEFINDER", 0
            )

        def _count_sent_command(self, name: str) -> None:
            self._command_runtime.count(name)

        def write_summary(self, *, ok: bool, reason: str, landing_ok: bool) -> None:
            if not args.summary_file:
                return
            summary = self._summary_runtime.build_final_summary(
                ok=ok,
                reason=reason,
                landing_ok=landing_ok,
                now_monotonic=time.monotonic(),
                started_at_monotonic=self._started,
                fsm_snapshot=self._mission_phase_snapshot(),
                prefix_pipeline=self._prefix_pipeline_status(),
                status_history=self._status_history,
                ctx=self._mission_context,
                runtime_adapter=self._mission_runtime,
                runtime_adapter_config=self._mission_runtime_config,
                runtime=self._runtime,
                command_runtime=self._command_runtime,
                collections=self._mavlink_collections,
                hover_evidence=self._hover_evidence,
                landing_evidence=self._landing_evidence,
            )
            self._summary_runtime.write_final_summary(summary_file=args.summary_file, summary=summary)

    rclpy.init(args=None)
    node = MavlinkHoverMissionController()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
