"""Landing stage policy and acceptance helpers."""

from __future__ import annotations

from dataclasses import dataclass

from navlab.common.companion.mission.command_adapter import request_mission_command
from navlab.common.companion.mission.context import MissionContext
from navlab.common.companion.mission.fsm import mission_phase_state_for_landing_state
from navlab.common.companion.mission.pipeline import StageResult

LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER = "ap_land_mode_after_hover"

LANDING_POLICY_GUIDED_DESCENT = "guided_descent"

LANDING_POLICY_LAND_IN_PLACE = "land_in_place"

FCU_LAND_PARAM_NAMES = (
    "LAND_SPEED",
    "LAND_SPD_MS",
    "LAND_SPEED_HIGH",
    "LAND_SPD_HIGH_MS",
    "LAND_ALT_LOW_M",
    "SURFTRAK_TC",
    "SURFTRAK_GLDST",
    "SURFTRAK_GLSAM",
    "EK3_SRC1_POSZ",
    "EK3_RNG_USE_HGT",
)


@dataclass(frozen=True, slots=True)
class LandingStageConfig:
    """Configuration for the executable landing stage."""

    landing_policy: str = LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER
    pre_land_hold_sec: float = 1.0
    max_landing_duration_sec: float = 30.0
    require_disarm: bool = True
    require_motors_safe: bool = True
    force_disarm_grace_sec: float = 3.0


def landing_policy_uses_ap_land_mode(policy: str) -> bool:
    """Return whether landing is delegated to ArduCopter LAND mode."""

    return policy == LANDING_POLICY_AP_LAND_MODE_AFTER_HOVER


def should_use_guided_descent_before_land(
    *,
    landing_policy: str,
    land_command_sent: bool,
    touchdown_ready: bool,
) -> bool:
    """Return whether the project should guide descent before LAND command."""

    return not landing_policy_uses_ap_land_mode(landing_policy) and not land_command_sent and not touchdown_ready


def should_command_land_this_tick(
    *,
    landing_policy: str,
    land_command_sent: bool,
    touchdown_ready: bool,
    command_due: bool,
) -> bool:
    """Return whether this tick should send or retry MAV_CMD_NAV_LAND."""

    if land_command_sent:
        return command_due
    if landing_policy_uses_ap_land_mode(landing_policy):
        return True
    return touchdown_ready


def should_send_disarm_after_touchdown(
    *,
    touchdown_confirmed: bool,
    disarmed: bool,
    require_disarm: bool,
    touchdown_confirmed_elapsed_sec: float | None,
    force_disarm_grace_sec: float,
) -> bool:
    """Return whether touchdown has waited long enough to force disarm."""

    if not require_disarm or disarmed or not touchdown_confirmed:
        return False
    if touchdown_confirmed_elapsed_sec is None:
        return False
    return touchdown_confirmed_elapsed_sec >= max(0.0, force_disarm_grace_sec)


def fcu_land_params_report(params: dict[str, float]) -> dict[str, object]:
    """Summarize FCU landing parameters for mission summary output."""

    return {
        "requested": list(FCU_LAND_PARAM_NAMES),
        "values": {name: params[name] for name in FCU_LAND_PARAM_NAMES if name in params},
        "missing": [name for name in FCU_LAND_PARAM_NAMES if name not in params],
        "ekf_posz_is_rangefinder": params.get("EK3_SRC1_POSZ") == 10,
        "ekf_rng_use_hgt_enabled": params.get("EK3_RNG_USE_HGT") not in (None, -1),
    }


def landing_controller_for_state(
    landing_state: str,
    *,
    landing_policy: str = LANDING_POLICY_GUIDED_DESCENT,
) -> str:
    """Describe which controller owns the current landing state."""

    if landing_state == "not_started":
        return "not_started"
    if landing_state in {"task_body_complete", "pre_land_hold"}:
        return "pending"
    if landing_policy_uses_ap_land_mode(landing_policy):
        return "ap_land_mode"
    return "guided_descent"


def landing_descent_profile_enforced(landing_policy: str) -> bool:
    """Return whether descent profile quality is a hard acceptance gate."""

    return not landing_policy_uses_ap_land_mode(landing_policy)


def landing_handoff_confirmed(
    *,
    landing_policy: str,
    land_command_sent: bool,
    land_command_accepted: bool,
    land_mode_seen: bool,
) -> bool:
    """Return whether AP LAND mode handoff has command or mode evidence."""

    if not landing_policy_uses_ap_land_mode(landing_policy):
        return True
    return bool(land_command_sent and (land_command_accepted or land_mode_seen))


def landing_acceptance_ok(
    *,
    landing_policy: str,
    land_command_sent: bool,
    land_command_accepted: bool,
    land_mode_seen: bool,
    touchdown_confirmed: bool,
    disarmed: bool,
    motors_safe: bool,
    require_disarm: bool,
    require_motors_safe: bool,
    descent_profile_ok: bool,
) -> bool:
    """Evaluate the final landing acceptance gate."""

    handoff_ok = landing_handoff_confirmed(
        landing_policy=landing_policy,
        land_command_sent=land_command_sent,
        land_command_accepted=land_command_accepted,
        land_mode_seen=land_mode_seen,
    )
    if not handoff_ok:
        return False
    descent_ok = True if not landing_descent_profile_enforced(landing_policy) else descent_profile_ok
    return bool(
        touchdown_confirmed
        and (disarmed if require_disarm else True)
        and (motors_safe if require_motors_safe else True)
        and descent_ok
    )


class LandingStage:
    """Execute landing policy decisions and request landing side effects."""

    name = "landing"

    def __init__(self, config: LandingStageConfig) -> None:
        """Create the landing stage."""

        self._config = config

    def tick(self, ctx: MissionContext) -> StageResult:
        """Evaluate one landing tick using context state and command adapters."""

        state = ctx.state.landing
        elapsed = state.elapsed_sec
        if elapsed > self._config.max_landing_duration_sec:
            state.state = "landing_timeout"
            return StageResult.abort(
                "landing_timeout",
                fsm_state="S_abort",
                blocker="landing_timeout",
                evidence={"state": state.state},
            )
        if elapsed < self._config.pre_land_hold_sec:
            state.state = "pre_land_hold"
            command_sent = request_mission_command(ctx, "send_hold_setpoint")
            return StageResult.running(
                "pre_land_hold",
                fsm_state=mission_phase_state_for_landing_state(state.state),
                evidence={"state": state.state, "command_sent": command_sent},
            )
        if should_use_guided_descent_before_land(
            landing_policy=self._config.landing_policy,
            land_command_sent=state.land_command_sent,
            touchdown_ready=state.touchdown_ready,
        ):
            state.state = "guided_descent"
            command_sent = request_mission_command(ctx, "send_landing_descent_setpoint")
            return StageResult.running(
                "guided_descent",
                fsm_state=mission_phase_state_for_landing_state(state.state),
                evidence={"state": state.state, "command_sent": command_sent},
            )
        land_command_sent_this_tick = False
        if should_command_land_this_tick(
            landing_policy=self._config.landing_policy,
            land_command_sent=state.land_command_sent,
            touchdown_ready=state.touchdown_ready,
            command_due=state.command_due,
        ):
            state.state = "land_command_sent"
            land_command_sent_this_tick = request_mission_command(ctx, "request_land")
        if state.land_command_rejected:
            state.state = "landing_command_rejected"
            return StageResult.abort(
                "landing_command_rejected",
                fsm_state="S_abort",
                blocker="landing_command_rejected",
                evidence={"state": state.state, "command_sent": land_command_sent_this_tick},
            )

        touchdown_confirmed = state.touchdown_confirmed or state.touchdown_ready
        if state.state != "land_command_sent":
            state.state = "touchdown_candidate" if touchdown_confirmed else "descent_monitoring"
        disarm_sent = False
        if (
            should_send_disarm_after_touchdown(
                touchdown_confirmed=touchdown_confirmed,
                disarmed=state.disarmed,
                require_disarm=self._config.require_disarm,
                touchdown_confirmed_elapsed_sec=state.touchdown_confirmed_elapsed_sec,
                force_disarm_grace_sec=self._config.force_disarm_grace_sec,
            )
            and state.disarm_due
        ):
            state.state = "disarm_requested"
            disarm_sent = request_mission_command(ctx, "request_disarm")

        landing_ok = landing_acceptance_ok(
            landing_policy=self._config.landing_policy,
            land_command_sent=state.land_command_sent or land_command_sent_this_tick,
            land_command_accepted=state.land_command_accepted,
            land_mode_seen=state.land_mode_seen,
            touchdown_confirmed=touchdown_confirmed,
            disarmed=state.disarmed,
            motors_safe=state.motors_safe,
            require_disarm=self._config.require_disarm,
            require_motors_safe=self._config.require_motors_safe,
            descent_profile_ok=state.descent_profile_ok,
        )
        evidence = {
            "state": state.state,
            "land_command_sent_this_tick": land_command_sent_this_tick,
            "disarm_sent": disarm_sent,
            "landing_ok": landing_ok,
        }
        if landing_ok:
            state.state = "landing_complete"
            evidence["state"] = state.state
            return StageResult.complete(
                "landing_complete",
                fsm_state=mission_phase_state_for_landing_state(state.state),
                evidence=evidence,
            )
        return StageResult.running(
            state.state,
            fsm_state=mission_phase_state_for_landing_state(state.state),
            evidence=evidence,
        )
