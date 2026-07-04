"""Runtime state adapters for ROS status JSON and MAVLink messages."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from navlab.common.companion.mission.command_adapter import MissionCommandRuntime
from navlab.common.companion.mission.context import (
    CommandState,
    FcuState,
    HoverState,
    MissionRuntimeSnapshot,
    NavState,
    PoseState,
)
from navlab.common.companion.mission.mavlink_protocol import (
    append_bounded_command_ack,
    command_ack_accepted,
    mavlink,
    mavlink_param_id_to_str,
)
from navlab.common.companion.mission.stages.hover import HoverInputs
from navlab.common.companion.mission.stages.landing import FCU_LAND_PARAM_NAMES

ARDUCOPTER_LAND_MODE_NUMBER = 9


def parse_status_payload(data: str) -> dict[str, object]:
    """Parse one JSON status payload, returning an empty dict on malformed input."""

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True, slots=True)
class ExternalNavStatusSnapshot:
    """Typed snapshot parsed from the external-nav status topic."""

    ready: bool
    state: str
    slam_quality: str
    slam_quality_good: bool
    slam_quality_reason: str
    height_m: float | None
    payload: dict[str, object]
    event: dict[str, object]


@dataclass(frozen=True, slots=True)
class MavlinkExternalNavStatusSnapshot:
    """Typed snapshot parsed from the MAVLink external-nav bridge status topic."""

    ready: bool
    fcu_local_position_ready: bool
    payload: dict[str, object]
    event: dict[str, object]


@dataclass(frozen=True, slots=True)
class MavlinkStatusSnapshot:
    """Typed snapshot parsed from the MAVLink status topic."""

    expected_mode_seen: bool
    armed_seen: bool
    payload: dict[str, object]


@dataclass(slots=True)
class MavlinkRuntimeUpdate:
    """Parsed effects from one MAVLink message."""

    msg_type: str
    target_system: int | None = None
    target_component: int | None = None
    current_custom_mode: int | None = None
    expected_mode_seen: bool | None = None
    armed_seen: bool | None = None
    mode_after_land: int | None = None
    land_mode_seen: bool = False
    land_mode_seen_elapsed_sec: float | None = None
    accepted_command_id: int | None = None
    command_ack: dict[str, int] | None = None
    fcu_land_param: tuple[str, float] | None = None
    statustext: dict[str, int | str] | None = None
    crash_detected: bool = False
    current_x: float | None = None
    current_y: float | None = None
    current_z: float | None = None
    current_vz: float | None = None
    ground_z_ned: float | None = None
    airborne_seen: bool | None = None
    current_yaw_rad: float | None = None
    ekf_flags: int | None = None
    gps_global_origin_seen: bool | None = None
    home_position_seen: bool | None = None
    current_range_m: float | None = None
    ground_range_m: float | None = None
    landed_state: int | None = None
    landed_state_event: dict[str, object] | None = None


@dataclass(slots=True)
class MavlinkRuntimeCollections:
    """Bounded runtime collections updated by MAVLink parsing helpers."""

    accepted_command_ids: set[int] = field(default_factory=set)
    command_acks: list[dict[str, int]] = field(default_factory=list)
    statustext: list[dict[str, int | str]] = field(default_factory=list)


@dataclass(slots=True)
class MavlinkRuntimeState:
    """Owned MAVLink-derived runtime state for one mission controller."""

    target_system: int | None = None
    target_component: int | None = None
    current_custom_mode: int | None = None
    expected_mode_seen: bool = False
    armed_seen: bool = False
    guided_seen_ever: bool = False
    armed_seen_ever: bool = False
    airborne_seen: bool = False
    airborne_started: float | None = None
    current_x: float | None = None
    current_y: float | None = None
    current_z: float | None = None
    ground_z_ned: float | None = None
    current_vz: float | None = None
    current_range_m: float | None = None
    ground_range_m: float | None = None
    current_yaw_rad: float | None = None
    message_counts: dict[str, int] = field(default_factory=dict)
    crash_detected: bool = False
    ekf_flags: list[int] = field(default_factory=list)
    gps_global_origin_seen: bool = False
    home_position_seen: bool = False
    landed_state: int | None = None
    landed_state_timeline: list[dict[str, object]] = field(default_factory=list)

    def apply_update(self, update: MavlinkRuntimeUpdate, *, now_monotonic: float) -> None:
        """Apply one parsed MAVLink update and maintain derived state."""

        self.message_counts[update.msg_type] = self.message_counts.get(update.msg_type, 0) + 1
        if update.target_system is not None:
            self.target_system = update.target_system
        if update.target_component is not None:
            self.target_component = update.target_component
        if update.current_custom_mode is not None:
            self.current_custom_mode = update.current_custom_mode
        if update.expected_mode_seen is not None:
            self.expected_mode_seen = update.expected_mode_seen
        if update.armed_seen is not None:
            self.armed_seen = update.armed_seen
            self.guided_seen_ever = self.guided_seen_ever or self.expected_mode_seen
            self.armed_seen_ever = self.armed_seen_ever or self.armed_seen
        if update.crash_detected:
            self.crash_detected = True
        if update.current_x is not None:
            self.current_x = update.current_x
            self.current_y = update.current_y
            self.current_z = update.current_z
            self.current_vz = update.current_vz
        if update.ground_z_ned is not None and self.ground_z_ned is None:
            self.ground_z_ned = update.ground_z_ned
        if update.airborne_seen:
            self.airborne_seen = True
        if update.current_yaw_rad is not None:
            self.current_yaw_rad = update.current_yaw_rad
        if update.ekf_flags is not None:
            self.ekf_flags.append(update.ekf_flags)
        if update.gps_global_origin_seen:
            self.gps_global_origin_seen = True
        if update.home_position_seen:
            self.home_position_seen = True
        if update.current_range_m is not None:
            self.current_range_m = update.current_range_m
        if update.ground_range_m is not None and self.ground_range_m is None:
            self.ground_range_m = update.ground_range_m
        if update.landed_state is not None:
            self.landed_state = update.landed_state
        if update.landed_state_event is not None:
            self.landed_state_timeline.append(update.landed_state_event)
            self.landed_state_timeline = self.landed_state_timeline[-80:]
        if self.airborne_seen and self.airborne_started is None:
            self.airborne_started = now_monotonic


@dataclass(frozen=True, slots=True)
class MissionRuntimeAdapterConfig:
    """Configuration used to derive mission-ready snapshots from runtime status."""

    status_timeout_sec: float
    require_external_nav: bool
    require_imu_status: bool
    simulate_mode_arm: bool
    takeoff_alt_m: float


@dataclass(frozen=True, slots=True)
class RuntimeStatusUpdate:
    """Result returned after applying one external runtime status message."""

    changed: bool
    snapshot: ExternalNavStatusSnapshot | MavlinkExternalNavStatusSnapshot | MavlinkStatusSnapshot | None


@dataclass(frozen=True, slots=True)
class MissionRuntimeReadinessSummary:
    """Status freshness fields used by final mission summaries."""

    external_nav_ready: bool
    external_nav_status_age_sec: float
    external_nav_status_history: list[dict[str, object]]
    mavlink_external_nav_ready: bool
    fcu_local_position_ready: bool
    mavlink_external_nav_status_age_sec: float
    mavlink_external_nav_status: dict[str, object]
    mavlink_external_nav_status_history: list[dict[str, object]]


@dataclass(slots=True)
class MissionRuntimeStateAdapter:
    """Own ROS status topic state and derive typed mission runtime snapshots."""

    started_at_monotonic: float
    external_nav_ready: bool = False
    last_external_status_monotonic: float = 0.0
    last_external_nav_state: str = ""
    external_nav_slam_quality: str = "bad"
    external_nav_slam_quality_good: bool = False
    external_nav_slam_quality_reason: str = "missing_status"
    last_external_status_payload: dict[str, object] = field(default_factory=dict)
    external_nav_status_history: list[dict[str, object]] = field(default_factory=list)
    slam_quality_loss_started: float | None = None
    external_nav_loss_started: float | None = None
    mavlink_external_nav_ready: bool = False
    fcu_local_position_ready: bool = False
    last_mavlink_external_nav_status_payload: dict[str, object] = field(default_factory=dict)
    last_mavlink_external_nav_status_monotonic: float = 0.0
    mavlink_external_nav_status_history: list[dict[str, object]] = field(default_factory=list)
    mavlink_external_nav_loss_started: float | None = None
    fcu_local_position_loss_started: float | None = None
    imu_ready: bool = False
    last_imu_status_monotonic: float = 0.0
    ready_started: float | None = None
    external_expected_mode_seen: bool = False
    external_armed_seen: bool = False

    def apply_external_nav_status(self, data: str, *, now_monotonic: float) -> RuntimeStatusUpdate:
        """Apply one external-nav status JSON payload."""

        previous_ready = self.external_nav_ready
        previous_state = self.last_external_nav_state
        previous_quality = self.external_nav_slam_quality
        snapshot = external_nav_status_snapshot(data, elapsed_sec=now_monotonic - self.started_at_monotonic)
        self.last_external_status_payload = snapshot.payload
        self.external_nav_ready = snapshot.ready
        self.last_external_nav_state = snapshot.state
        self.external_nav_slam_quality = snapshot.slam_quality
        self.external_nav_slam_quality_good = snapshot.slam_quality_good
        self.external_nav_slam_quality_reason = snapshot.slam_quality_reason
        self.last_external_status_monotonic = now_monotonic
        changed = (
            self.external_nav_ready != previous_ready
            or self.last_external_nav_state != previous_state
            or self.external_nav_slam_quality != previous_quality
        )
        if changed:
            self.external_nav_status_history.append(snapshot.event)
            self.external_nav_status_history = self.external_nav_status_history[-40:]
        return RuntimeStatusUpdate(changed=changed, snapshot=snapshot)

    def apply_mavlink_external_nav_status(self, data: str, *, now_monotonic: float) -> RuntimeStatusUpdate:
        """Apply one MAVLink external-nav bridge status JSON payload."""

        snapshot = mavlink_external_nav_status_snapshot(data, elapsed_sec=now_monotonic - self.started_at_monotonic)
        self.last_mavlink_external_nav_status_payload = snapshot.payload
        self.mavlink_external_nav_ready = snapshot.ready
        self.fcu_local_position_ready = snapshot.fcu_local_position_ready
        self.last_mavlink_external_nav_status_monotonic = now_monotonic
        self.mavlink_external_nav_status_history.append(snapshot.event)
        self.mavlink_external_nav_status_history = self.mavlink_external_nav_status_history[-40:]
        return RuntimeStatusUpdate(changed=True, snapshot=snapshot)

    def apply_imu_status(self, data: str, *, now_monotonic: float) -> None:
        """Apply one IMU status JSON payload."""

        self.imu_ready = parse_status_payload(data).get("ready") is True
        self.last_imu_status_monotonic = now_monotonic

    def apply_mavlink_status(self, data: str, *, mode_number: int) -> RuntimeStatusUpdate:
        """Apply one MAVLink status JSON payload."""

        snapshot = mavlink_status_snapshot(data, mode_number=mode_number)
        self.external_expected_mode_seen = snapshot.expected_mode_seen
        self.external_armed_seen = snapshot.armed_seen
        return RuntimeStatusUpdate(changed=True, snapshot=snapshot)

    def external_nav_height_m(self) -> float | None:
        """Return the last external-nav height estimate when present."""

        height = self.last_external_status_payload.get("height")
        if not isinstance(height, dict):
            return None
        value = height.get("z")
        if not isinstance(value, int | float):
            return None
        value = float(value)
        return value if math.isfinite(value) else None

    def build_hover_inputs(
        self,
        *,
        now_monotonic: float,
        config: MissionRuntimeAdapterConfig,
        runtime: MavlinkRuntimeState,
        collections: MavlinkRuntimeCollections,
        target_z_ned: float,
        fcu_local_height_m: float | None,
        rangefinder_relative_height_m: float | None,
        hover_started_at_monotonic: float | None,
    ) -> HoverInputs:
        """Build hover-stage inputs from owned status and MAVLink runtime state."""

        external_nav_fresh = (
            self.last_external_status_monotonic > 0.0
            and now_monotonic - self.last_external_status_monotonic <= config.status_timeout_sec
        )
        mavlink_external_nav_fresh = (
            self.last_mavlink_external_nav_status_monotonic > 0.0
            and now_monotonic - self.last_mavlink_external_nav_status_monotonic <= config.status_timeout_sec
        )
        imu_fresh = (
            self.last_imu_status_monotonic > 0.0
            and now_monotonic - self.last_imu_status_monotonic <= config.status_timeout_sec
        )
        external_ready = self.external_nav_ready and external_nav_fresh
        slam_quality_good = self.external_nav_slam_quality_good and external_nav_fresh
        mavlink_external_nav_ready = self.mavlink_external_nav_ready and mavlink_external_nav_fresh
        fcu_local_position_ready = self.fcu_local_position_ready and mavlink_external_nav_fresh
        imu_ready = self.imu_ready and imu_fresh
        slam_quality_loss_duration = self._loss_duration_sec(
            now_monotonic,
            slam_quality_good or not runtime.airborne_seen,
            "slam_quality_loss_started",
        )
        external_nav_loss_duration = self._loss_duration_sec(
            now_monotonic,
            external_ready or not runtime.airborne_seen,
            "external_nav_loss_started",
        )
        mavlink_external_nav_loss_duration = self._loss_duration_sec(
            now_monotonic,
            mavlink_external_nav_ready or not runtime.airborne_seen,
            "mavlink_external_nav_loss_started",
        )
        fcu_local_position_loss_duration = self._loss_duration_sec(
            now_monotonic,
            fcu_local_position_ready or not runtime.airborne_seen,
            "fcu_local_position_loss_started",
        )
        ready_for_preflight = (
            (external_ready or not config.require_external_nav)
            and (slam_quality_good or not config.require_external_nav)
            and (mavlink_external_nav_ready or not config.require_external_nav)
            and (fcu_local_position_ready or not config.require_external_nav)
            and (imu_ready or not config.require_imu_status)
        )
        if ready_for_preflight:
            if self.ready_started is None:
                self.ready_started = now_monotonic
        else:
            self.ready_started = None
        ready_elapsed = 0.0 if self.ready_started is None else now_monotonic - self.ready_started
        hover_elapsed = 0.0 if hover_started_at_monotonic is None else now_monotonic - hover_started_at_monotonic
        airborne_elapsed = 0.0 if runtime.airborne_started is None else now_monotonic - runtime.airborne_started
        return HoverInputs(
            external_nav_ready=external_ready,
            mavlink_external_nav_ready=mavlink_external_nav_ready,
            fcu_local_position_ready=fcu_local_position_ready,
            imu_ready=imu_ready,
            slam_quality_good=slam_quality_good,
            slam_quality=self.external_nav_slam_quality if external_nav_fresh else "stale",
            ready_elapsed_sec=ready_elapsed,
            current_yaw_rad=runtime.current_yaw_rad,
            expected_mode_seen=(
                config.simulate_mode_arm or runtime.expected_mode_seen or self.external_expected_mode_seen
            ),
            armed_seen=config.simulate_mode_arm or runtime.armed_seen or self.external_armed_seen,
            airborne_seen=runtime.airborne_seen,
            takeoff_ack_ok=command_ack_accepted(
                collections.command_acks,
                mavlink.MAV_CMD_NAV_TAKEOFF,
                collections.accepted_command_ids,
            ),
            airborne_elapsed_sec=airborne_elapsed,
            hover_elapsed_sec=hover_elapsed,
            current_x=runtime.current_x,
            current_y=runtime.current_y,
            current_z_ned=runtime.current_z,
            current_height_m=runtime.current_range_m,
            external_nav_height_m=self.external_nav_height_m(),
            rangefinder_relative_height_m=rangefinder_relative_height_m,
            target_z_ned=target_z_ned,
            slam_quality_loss_duration_sec=slam_quality_loss_duration,
            external_nav_loss_duration_sec=external_nav_loss_duration,
            mavlink_external_nav_loss_duration_sec=mavlink_external_nav_loss_duration,
            fcu_local_position_loss_duration_sec=fcu_local_position_loss_duration,
        )

    def runtime_snapshot(
        self,
        *,
        now_monotonic: float,
        inputs: HoverInputs,
        runtime: MavlinkRuntimeState,
        command_runtime: MissionCommandRuntime,
        collections: MavlinkRuntimeCollections,
        fcu_local_height_m: float | None,
    ) -> MissionRuntimeSnapshot:
        """Build a typed mission context snapshot from hover inputs and runtime owners."""

        return MissionRuntimeSnapshot(
            now_monotonic=now_monotonic,
            nav=NavState(
                external_nav_ready=inputs.external_nav_ready,
                mavlink_external_nav_ready=inputs.mavlink_external_nav_ready,
                fcu_local_position_ready=inputs.fcu_local_position_ready,
                imu_ready=inputs.imu_ready,
                slam_quality=inputs.slam_quality,
                slam_quality_good=inputs.slam_quality_good,
                slam_quality_reason=self.external_nav_slam_quality_reason,
                ready_elapsed_sec=inputs.ready_elapsed_sec,
                slam_quality_loss_duration_sec=inputs.slam_quality_loss_duration_sec,
                external_nav_loss_duration_sec=inputs.external_nav_loss_duration_sec,
                mavlink_external_nav_loss_duration_sec=inputs.mavlink_external_nav_loss_duration_sec,
                fcu_local_position_loss_duration_sec=inputs.fcu_local_position_loss_duration_sec,
            ),
            fcu=FcuState(
                expected_mode_seen=inputs.expected_mode_seen,
                armed=inputs.armed_seen,
                airborne=inputs.airborne_seen,
                takeoff_ack_ok=inputs.takeoff_ack_ok,
                target_system=runtime.target_system,
                target_component=runtime.target_component,
            ),
            pose=PoseState(
                x_m=inputs.current_x,
                y_m=inputs.current_y,
                z_ned_m=inputs.current_z_ned,
                yaw_rad=inputs.current_yaw_rad,
                height_m=inputs.current_height_m,
                fcu_local_height_m=fcu_local_height_m,
                external_nav_height_m=inputs.external_nav_height_m,
                rangefinder_range_m=runtime.current_range_m,
                rangefinder_relative_height_m=inputs.rangefinder_relative_height_m,
                target_z_ned_m=inputs.target_z_ned,
            ),
            hover=HoverState(
                airborne_elapsed_sec=inputs.airborne_elapsed_sec,
                hover_elapsed_sec=inputs.hover_elapsed_sec,
            ),
            command=CommandState(
                sent_counts=dict(command_runtime.sent_counts),
                accepted_command_ids=set(collections.accepted_command_ids),
                command_acks=list(collections.command_acks),
            ),
        )

    def readiness_summary(
        self,
        *,
        now_monotonic: float,
        config: MissionRuntimeAdapterConfig,
    ) -> MissionRuntimeReadinessSummary:
        """Return status freshness fields for final summaries."""

        external_nav_age_sec = -1.0
        if self.last_external_status_monotonic > 0.0:
            external_nav_age_sec = now_monotonic - self.last_external_status_monotonic
        external_nav_ready = (
            self.external_nav_ready
            and self.last_external_status_monotonic > 0.0
            and external_nav_age_sec <= config.status_timeout_sec
        )
        mavlink_external_nav_age_sec = -1.0
        if self.last_mavlink_external_nav_status_monotonic > 0.0:
            mavlink_external_nav_age_sec = now_monotonic - self.last_mavlink_external_nav_status_monotonic
        mavlink_external_nav_ready = (
            self.mavlink_external_nav_ready
            and self.last_mavlink_external_nav_status_monotonic > 0.0
            and mavlink_external_nav_age_sec <= config.status_timeout_sec
        )
        return MissionRuntimeReadinessSummary(
            external_nav_ready=external_nav_ready,
            external_nav_status_age_sec=external_nav_age_sec,
            external_nav_status_history=list(self.external_nav_status_history),
            mavlink_external_nav_ready=mavlink_external_nav_ready,
            fcu_local_position_ready=self.fcu_local_position_ready and mavlink_external_nav_ready,
            mavlink_external_nav_status_age_sec=mavlink_external_nav_age_sec,
            mavlink_external_nav_status=dict(self.last_mavlink_external_nav_status_payload),
            mavlink_external_nav_status_history=list(self.mavlink_external_nav_status_history),
        )

    def _loss_duration_sec(self, now_monotonic: float, ok: bool, attr_name: str) -> float:
        """Update and return one loss-duration counter."""

        if ok:
            setattr(self, attr_name, None)
            return 0.0
        started = getattr(self, attr_name)
        if started is None:
            setattr(self, attr_name, now_monotonic)
            return 0.0
        return max(0.0, now_monotonic - float(started))


def external_nav_status_snapshot(data: str, *, elapsed_sec: float) -> ExternalNavStatusSnapshot:
    """Parse external-nav status JSON into a typed snapshot and event record."""

    payload = parse_status_payload(data)
    odom = payload.get("odom") if isinstance(payload.get("odom"), dict) else {}
    height = payload.get("height") if isinstance(payload.get("height"), dict) else {}
    height_value = height.get("z") if isinstance(height, dict) else None
    height_m = float(height_value) if isinstance(height_value, int | float) and math.isfinite(height_value) else None
    ready = payload.get("ready") is True
    state = str(payload.get("state") or "")
    slam_quality = str(payload.get("slam_quality") or "bad")
    slam_quality_good = payload.get("slam_quality_good") is True
    slam_quality_reason = str(payload.get("slam_quality_reason") or "")
    event = {
        "elapsed_sec": round(elapsed_sec, 3),
        "ready": ready,
        "state": state,
        "slam_quality": slam_quality,
        "slam_quality_good": slam_quality_good,
        "slam_quality_reason": slam_quality_reason,
        "input_topic": odom.get("input_topic"),
        "rate_hz": odom.get("rate_hz"),
        "rate_ok": odom.get("rate_ok"),
        "frame_ok": odom.get("frame_ok"),
        "age_ms": odom.get("age_ms"),
    }
    return ExternalNavStatusSnapshot(
        ready=ready,
        state=state,
        slam_quality=slam_quality,
        slam_quality_good=slam_quality_good,
        slam_quality_reason=slam_quality_reason,
        height_m=height_m,
        payload=payload,
        event=event,
    )


def mavlink_external_nav_status_snapshot(
    data: str,
    *,
    elapsed_sec: float,
) -> MavlinkExternalNavStatusSnapshot:
    """Parse MAVLink external-nav bridge status JSON into a typed snapshot."""

    payload = parse_status_payload(data)
    ready = payload.get("ready") is True
    fcu_local_position_ready = payload.get("fcu_local_position_ready") is True
    event = {
        "elapsed_sec": round(elapsed_sec, 3),
        "ready": ready,
        "state": payload.get("state"),
        "sent_count": payload.get("sent_count"),
        "local_position_count": payload.get("local_position_count"),
        "local_position_age_ms": payload.get("local_position_age_ms"),
        "fcu_local_position_ready": fcu_local_position_ready,
    }
    return MavlinkExternalNavStatusSnapshot(
        ready=ready,
        fcu_local_position_ready=fcu_local_position_ready,
        payload=payload,
        event=event,
    )


def mavlink_status_snapshot(data: str, *, mode_number: int) -> MavlinkStatusSnapshot:
    """Parse MAVLink status JSON into expected-mode and armed booleans."""

    payload = parse_status_payload(data)
    return MavlinkStatusSnapshot(
        expected_mode_seen=payload.get("mode_number") == mode_number,
        armed_seen=payload.get("armed") is True,
        payload=payload,
    )


def statustext_indicates_crash(text: str) -> bool:
    """Return whether a MAVLink STATUSTEXT reports a crash."""

    return "Crash:" in text


def append_bounded_statustext(
    statustext: list[dict[str, int | str]],
    entry: dict[str, int | str],
    *,
    max_count: int = 120,
) -> None:
    """Append one STATUSTEXT entry while bounding retained history."""

    statustext.append(entry)
    del statustext[: max(0, len(statustext) - max_count)]


def mavlink_runtime_update(
    msg: Any,
    *,
    mode_number: int,
    land_command_sent: bool,
    mode_before_land: int | None,
    land_command_sent_time: float | None,
    started_at_monotonic: float,
    now_monotonic: float,
    ground_z_ned: float | None,
    ground_range_m: float | None,
    min_airborne_alt_m: float,
) -> MavlinkRuntimeUpdate:
    """Parse one MAVLink message into an update object without mutating the node."""

    msg_type = msg.get_type()
    update = MavlinkRuntimeUpdate(msg_type=msg_type)
    if msg_type == "HEARTBEAT" and int(msg.autopilot) != mavlink.MAV_AUTOPILOT_INVALID:
        current_custom_mode = int(msg.custom_mode)
        update.target_system = msg.get_srcSystem()
        update.target_component = msg.get_srcComponent()
        update.current_custom_mode = current_custom_mode
        update.expected_mode_seen = current_custom_mode == mode_number
        update.armed_seen = bool(int(msg.base_mode) & mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        if land_command_sent:
            if current_custom_mode != mode_before_land:
                update.mode_after_land = current_custom_mode
            if current_custom_mode == ARDUCOPTER_LAND_MODE_NUMBER:
                update.land_mode_seen = True
                if land_command_sent_time is not None:
                    update.land_mode_seen_elapsed_sec = max(0.0, now_monotonic - land_command_sent_time)
    elif msg_type == "COMMAND_ACK":
        command = int(msg.command)
        result = int(msg.result)
        if result == 0:
            update.accepted_command_id = command
        update.command_ack = {"command": command, "result": result}
    elif msg_type == "PARAM_VALUE":
        name = mavlink_param_id_to_str(getattr(msg, "param_id", ""))
        if name in FCU_LAND_PARAM_NAMES:
            update.fcu_land_param = (name, float(msg.param_value))
    elif msg_type == "STATUSTEXT":
        text = str(msg.text).rstrip("\x00")
        update.statustext = {"severity": int(msg.severity), "text": text}
        update.crash_detected = statustext_indicates_crash(text)
    elif msg_type == "LOCAL_POSITION_NED":
        update.current_x = float(msg.x)
        update.current_y = float(msg.y)
        update.current_z = float(msg.z)
        update.current_vz = float(getattr(msg, "vz", 0.0))
        update.ground_z_ned = ground_z_ned if ground_z_ned is not None else update.current_z
        if update.ground_z_ned - update.current_z >= min_airborne_alt_m:
            update.airborne_seen = True
    elif msg_type == "ATTITUDE":
        update.current_yaw_rad = float(msg.yaw)
    elif msg_type == "GLOBAL_POSITION_INT":
        if float(msg.relative_alt) / 1000.0 >= min_airborne_alt_m:
            update.airborne_seen = True
    elif msg_type == "EKF_STATUS_REPORT":
        update.ekf_flags = int(msg.flags)
    elif msg_type == "GPS_GLOBAL_ORIGIN":
        update.gps_global_origin_seen = True
    elif msg_type == "HOME_POSITION":
        update.home_position_seen = True
    elif msg_type in {"DISTANCE_SENSOR", "RANGEFINDER"}:
        if hasattr(msg, "current_distance"):
            update.current_range_m = float(msg.current_distance) / 100.0
        elif hasattr(msg, "distance"):
            update.current_range_m = float(msg.distance)
        if ground_range_m is None and update.current_range_m is not None:
            update.ground_range_m = update.current_range_m
    elif msg_type == "EXTENDED_SYS_STATE":
        update.landed_state = int(msg.landed_state)
        update.landed_state_event = {
            "elapsed_sec": round(now_monotonic - started_at_monotonic, 3),
            "landed_state": update.landed_state,
        }
    return update


def apply_bounded_mavlink_collections(
    collections: MavlinkRuntimeCollections,
    update: MavlinkRuntimeUpdate,
) -> None:
    """Apply bounded ACK and STATUSTEXT updates to mutable collections."""

    if update.accepted_command_id is not None:
        collections.accepted_command_ids.add(update.accepted_command_id)
    if update.command_ack is not None:
        append_bounded_command_ack(collections.command_acks, update.command_ack)
    if update.statustext is not None:
        append_bounded_statustext(collections.statustext, update.statustext)
