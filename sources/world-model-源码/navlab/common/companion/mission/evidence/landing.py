"""Landing evidence and descent-profile helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

DEFAULT_LANDING_MAX_POST_TOUCHDOWN_BOUNCE_M = 0.04

DEFAULT_LANDING_RANGEFINDER_OUTLIER_MIN_M = 0.45

DEFAULT_LANDING_RANGEFINDER_OUTLIER_MAX_NEIGHBOR_DT_SEC = 1.0

DEFAULT_LANDING_RANGEFINDER_MAX_ABOVE_LOCAL_M = 0.75

DEFAULT_LANDING_RANGEFINDER_LOCAL_CROSSCHECK_MAX_HEIGHT_M = 1.25

DEFAULT_LANDING_RANGEFINDER_MAX_RATE_MPS = 0.5

LandingDescentSample = (
    tuple[float, float | None, float | None, float | None] | tuple[float, float | None, float | None, float | None, str]
)


@dataclass(frozen=True, slots=True)
class LandingDescentSetpoint:
    """Local-NED setpoint for guided landing descent."""

    x_m: float
    y_m: float
    z_ned_m: float
    yaw_rad: float
    effective_descent_rate_mps: float


@dataclass(slots=True)
class LandingEvidenceRecorder:
    """Own landing evidence collected across the landing stage."""

    started_at_monotonic: float | None = None
    state: str = "not_started"
    descent_started_at_monotonic: float | None = None
    start_z_ned: float | None = None
    descent_samples: list[LandingDescentSample] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    touchdown_confirmed: bool = False
    touchdown_candidate_since: float | None = None
    touchdown_confirmed_time: float | None = None
    land_command_sent: bool = False
    land_command_sent_time: float | None = None
    fcu_land_param_requests_sent: bool = False
    fcu_land_params: dict[str, float] = field(default_factory=dict)
    mode_before_land: int | None = None
    mode_after_land: int | None = None
    land_mode_seen: bool = False
    land_mode_seen_elapsed_sec: float | None = None
    force_disarm_used: bool = False
    frozen_hover_evidence: dict[str, object] = field(default_factory=dict)

    def start(self, now_monotonic: float, *, state: str = "task_body_complete") -> None:
        """Mark the beginning of the landing phase."""

        self.started_at_monotonic = now_monotonic
        self.state = state

    def start_with_hover_evidence(
        self,
        now_monotonic: float,
        *,
        frozen_hover_evidence: dict[str, object],
        state: str = "task_body_complete",
    ) -> None:
        """Mark landing start and freeze hover evidence for landing summaries."""

        self.start(now_monotonic, state=state)
        self.frozen_hover_evidence = dict(frozen_hover_evidence)

    def start_descent(self, now_monotonic: float, *, current_z_ned: float | None, fallback_z_ned: float) -> None:
        """Mark descent start and record the z origin once."""

        if self.descent_started_at_monotonic is not None:
            return
        self.descent_started_at_monotonic = now_monotonic
        self.start_z_ned = current_z_ned if current_z_ned is not None else fallback_z_ned

    def append_descent_sample(
        self,
        *,
        now_monotonic: float,
        height_m: float | None,
        range_m: float | None,
        vz_mps: float | None,
        source: str,
    ) -> None:
        """Append one bounded landing descent sample."""

        self.descent_samples.append((now_monotonic, height_m, range_m, vz_mps, source))
        self.descent_samples = self.descent_samples[-2000:]

    def append_descent_sample_from_pose(
        self,
        *,
        now_monotonic: float,
        current_range_m: float | None,
        ground_range_m: float | None,
        current_z_ned: float | None,
        ground_z_ned: float | None,
        current_vz_mps: float | None,
    ) -> None:
        """Append one descent sample using the standard landing evidence source selection."""

        height_m, source = landing_descent_evidence_height_and_source_m(
            current_range_m=current_range_m,
            ground_range_m=ground_range_m,
            current_z_ned=current_z_ned,
            ground_z_ned=ground_z_ned,
        )
        self.append_descent_sample(
            now_monotonic=now_monotonic,
            height_m=height_m,
            range_m=current_range_m,
            vz_mps=current_vz_mps,
            source=source,
        )

    def descent_profile(self, *, max_descent_rate_mps: float, touchdown_altitude_m: float) -> dict[str, object]:
        """Summarize the bounded descent evidence buffer."""

        return summarize_landing_descent_profile(
            self.descent_samples,
            max_descent_rate_mps=max_descent_rate_mps,
            touchdown_altitude_m=touchdown_altitude_m,
        )

    def update_touchdown_candidate(
        self,
        *,
        now_monotonic: float,
        raw_candidate: bool,
        landed_state_on_ground: bool,
        confirm_sec: float,
    ) -> bool:
        """Debounce touchdown evidence and return whether touchdown is confirmed."""

        if landed_state_on_ground:
            self.touchdown_confirmed = True
            self.touchdown_confirmed_time = self.touchdown_confirmed_time or now_monotonic
            return True
        if not raw_candidate:
            self.touchdown_candidate_since = None
            return False
        if self.touchdown_candidate_since is None:
            self.touchdown_candidate_since = now_monotonic
        ready = now_monotonic - self.touchdown_candidate_since >= max(0.0, confirm_sec)
        if ready and not self.touchdown_confirmed:
            self.touchdown_confirmed = True
            self.touchdown_confirmed_time = now_monotonic
        return ready

    def mark_land_command_sent(self, *, now_monotonic: float, mode_before_land: int | None) -> None:
        """Record the first outgoing LAND command."""

        if self.land_command_sent:
            return
        self.land_command_sent = True
        self.land_command_sent_time = now_monotonic
        self.mode_before_land = mode_before_land

    def mark_land_mode_seen(self, elapsed_sec: float | None) -> None:
        """Record the first observed LAND mode after command handoff."""

        if self.land_mode_seen:
            return
        self.land_mode_seen = True
        self.land_mode_seen_elapsed_sec = elapsed_sec

    def mark_mode_after_land(self, mode: int) -> None:
        """Record the first observed post-LAND mode."""

        if self.mode_after_land is None:
            self.mode_after_land = mode


def build_landing_intent_payload(
    *,
    source: str,
    policy: str,
    reason: str,
    updated_ms: int,
) -> dict[str, object]:
    """Build the compact landing intent payload published at handoff."""

    return {
        "source": source,
        "kind": "land_in_place",
        "policy": policy,
        "reason": reason,
        "updated_ms": updated_ms,
    }


def landing_descent_target_z_ned(
    *,
    start_z_ned: float,
    ground_z_ned: float,
    elapsed_sec: float,
    descent_rate_mps: float,
    current_z_ned: float | None = None,
    setpoint_lookahead_sec: float | None = None,
) -> float:
    """Compute a bounded local-NED descent setpoint toward ground."""

    if descent_rate_mps <= 0 or not math.isfinite(descent_rate_mps):
        raise ValueError("descent_rate_mps must be positive and finite")
    target = start_z_ned + max(0.0, elapsed_sec) * descent_rate_mps
    target = min(target, ground_z_ned)
    if (
        current_z_ned is not None
        and math.isfinite(current_z_ned)
        and setpoint_lookahead_sec is not None
        and math.isfinite(setpoint_lookahead_sec)
        and setpoint_lookahead_sec > 0.0
    ):
        max_step_ahead = descent_rate_mps * setpoint_lookahead_sec
        target = min(target, min(current_z_ned + max_step_ahead, ground_z_ned))
    return target


def landing_effective_descent_rate_mps(
    *,
    nominal_descent_rate_mps: float,
    rangefinder_relative_height_m: float | None,
    slowdown_altitude_m: float,
    near_ground_descent_rate_mps: float,
) -> float:
    """Slow the descent rate near ground when rangefinder height is available."""

    if nominal_descent_rate_mps <= 0 or not math.isfinite(nominal_descent_rate_mps):
        raise ValueError("nominal_descent_rate_mps must be positive and finite")
    effective_rate = nominal_descent_rate_mps
    range_height = _finite_float(rangefinder_relative_height_m)
    if (
        range_height is not None
        and range_height <= slowdown_altitude_m
        and near_ground_descent_rate_mps > 0.0
        and math.isfinite(near_ground_descent_rate_mps)
    ):
        effective_rate = min(effective_rate, near_ground_descent_rate_mps)
    return effective_rate


def _axis_or_current(value: float | None, current: float | None) -> float:
    """Return the held axis if available, otherwise the current axis."""

    if value is not None and math.isfinite(value):
        return float(value)
    if current is not None and math.isfinite(current):
        return float(current)
    return 0.0


def compute_landing_descent_setpoint(
    *,
    hold_x_m: float | None,
    hold_y_m: float | None,
    hold_yaw_rad: float | None,
    current_x_m: float | None,
    current_y_m: float | None,
    current_yaw_rad: float | None,
    start_z_ned: float | None,
    fallback_start_z_ned: float,
    ground_z_ned: float | None,
    descent_started_at_monotonic: float | None,
    now_monotonic: float,
    nominal_descent_rate_mps: float,
    rangefinder_relative_height_m: float | None,
    slowdown_altitude_m: float,
    near_ground_descent_rate_mps: float,
    current_z_ned: float | None,
    setpoint_lookahead_sec: float,
) -> LandingDescentSetpoint:
    """Compute the guided landing descent setpoint from recorder/runtime state."""

    start_z = start_z_ned if start_z_ned is not None else fallback_start_z_ned
    ground_z = ground_z_ned if ground_z_ned is not None else 0.0
    descent_elapsed = (
        0.0 if descent_started_at_monotonic is None else max(0.0, now_monotonic - descent_started_at_monotonic)
    )
    effective_descent_rate = landing_effective_descent_rate_mps(
        nominal_descent_rate_mps=nominal_descent_rate_mps,
        rangefinder_relative_height_m=rangefinder_relative_height_m,
        slowdown_altitude_m=slowdown_altitude_m,
        near_ground_descent_rate_mps=near_ground_descent_rate_mps,
    )
    return LandingDescentSetpoint(
        x_m=_axis_or_current(hold_x_m, current_x_m),
        y_m=_axis_or_current(hold_y_m, current_y_m),
        z_ned_m=landing_descent_target_z_ned(
            start_z_ned=start_z,
            ground_z_ned=ground_z,
            elapsed_sec=descent_elapsed,
            descent_rate_mps=effective_descent_rate,
            current_z_ned=current_z_ned,
            setpoint_lookahead_sec=setpoint_lookahead_sec,
        ),
        yaw_rad=_axis_or_current(hold_yaw_rad, current_yaw_rad),
        effective_descent_rate_mps=effective_descent_rate,
    )


def landing_descent_height_m(z_ned: float | None, ground_z_ned: float | None) -> float | None:
    """Convert local NED z into positive height above the recorded ground z."""

    if z_ned is None or ground_z_ned is None:
        return None
    height = float(ground_z_ned) - float(z_ned)
    return max(0.0, height) if math.isfinite(height) else None


def _finite_float(value: float | None) -> float | None:
    """Return a finite float or None."""

    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def landing_descent_evidence_height_and_source_m(
    *,
    current_range_m: float | None,
    ground_range_m: float | None,
    current_z_ned: float | None,
    ground_z_ned: float | None,
    rangefinder_max_above_local_m: float = DEFAULT_LANDING_RANGEFINDER_MAX_ABOVE_LOCAL_M,
    rangefinder_local_crosscheck_max_height_m: float = DEFAULT_LANDING_RANGEFINDER_LOCAL_CROSSCHECK_MAX_HEIGHT_M,
) -> tuple[float | None, str]:
    """Select landing height evidence and describe the selected source."""

    local_height = landing_descent_height_m(current_z_ned, ground_z_ned)
    current_range = _finite_float(current_range_m)
    ground_range = _finite_float(ground_range_m)
    if current_range is not None and ground_range is not None and current_range >= 0.0 and ground_range >= 0.0:
        range_height = max(0.0, current_range - ground_range)
        if (
            local_height is not None
            and local_height <= rangefinder_local_crosscheck_max_height_m
            and range_height > local_height + rangefinder_max_above_local_m
        ):
            return local_height, "fcu_local_z_after_rangefinder_high_outlier"
        return range_height, "rangefinder_relative_height"
    return local_height, "fcu_local_z_fallback"


def landing_descent_evidence_height_m(
    *,
    current_range_m: float | None,
    ground_range_m: float | None,
    current_z_ned: float | None,
    ground_z_ned: float | None,
) -> float | None:
    """Return only the selected landing height evidence value."""

    height, _source = landing_descent_evidence_height_and_source_m(
        current_range_m=current_range_m,
        ground_range_m=ground_range_m,
        current_z_ned=current_z_ned,
        ground_z_ned=ground_z_ned,
    )
    return height


def landing_touchdown_candidate(
    *,
    landed_state_on_ground: bool,
    current_range_m: float | None,
    current_z_ned: float | None,
    current_vz_mps: float | None,
    touchdown_altitude_m: float,
    touchdown_vertical_speed_mps: float,
) -> bool:
    """Return whether landing evidence is stable enough to consider touchdown."""

    if landed_state_on_ground:
        return True
    vz_ok = current_vz_mps is None or abs(current_vz_mps) <= touchdown_vertical_speed_mps
    if current_range_m is not None and math.isfinite(current_range_m):
        return bool(current_range_m <= touchdown_altitude_m and vz_ok)
    z_ok = current_z_ned is not None and current_z_ned >= -touchdown_altitude_m
    return bool(z_ok and vz_ok)


def _landing_descent_sample_fields(
    sample: LandingDescentSample,
) -> tuple[float, float | None, float | None, float | None, str]:
    """Normalize legacy and source-tagged landing descent samples."""

    t, height, range_m, vz = sample[:4]
    if len(sample) >= 5:
        source = str(sample[4])
    else:
        range_value = _finite_float(range_m)
        source = (
            "rangefinder_relative_height" if range_value is not None and range_value >= 0.0 else "fcu_local_z_fallback"
        )
    return float(t), height, range_m, vz, source


def summarize_landing_descent_profile(
    samples: Sequence[LandingDescentSample],
    *,
    max_descent_rate_mps: float,
    touchdown_altitude_m: float,
    max_post_touchdown_bounce_m: float = DEFAULT_LANDING_MAX_POST_TOUCHDOWN_BOUNCE_M,
    rangefinder_outlier_min_m: float = DEFAULT_LANDING_RANGEFINDER_OUTLIER_MIN_M,
    rangefinder_outlier_max_neighbor_dt_sec: float = DEFAULT_LANDING_RANGEFINDER_OUTLIER_MAX_NEIGHBOR_DT_SEC,
    rangefinder_max_rate_mps: float = DEFAULT_LANDING_RANGEFINDER_MAX_RATE_MPS,
) -> dict[str, object]:
    """Summarize landing descent speed, bounce, and sensor outliers."""

    parsed_samples = [_landing_descent_sample_fields(sample) for sample in samples]
    source_counts: dict[str, int] = {}
    for _t, _height, _range_m, _vz, source in parsed_samples:
        source_counts[source] = source_counts.get(source, 0) + 1
    raw_heights = [
        (idx, float(t), float(height), None if _range_m is None else float(_range_m), source)
        for idx, (t, height, _range_m, _vz, source) in enumerate(parsed_samples)
        if height is not None and math.isfinite(float(height))
    ]
    outlier_indices: set[int] = set()
    outlier_details: list[dict[str, float | int]] = []
    outlier_jump_m = max(0.0, rangefinder_outlier_min_m)
    for prev_sample, sample, next_sample in zip(raw_heights, raw_heights[1:], raw_heights[2:]):
        prev_idx, prev_t, prev_height, _prev_range, _prev_source = prev_sample
        idx, t, height, range_m, source = sample
        next_idx, next_t, next_height, _next_range, _next_source = next_sample
        if source != "rangefinder_relative_height":
            continue
        if range_m is None or not math.isfinite(range_m):
            continue
        if t - prev_t > rangefinder_outlier_max_neighbor_dt_sec:
            continue
        if next_t - t > rangefinder_outlier_max_neighbor_dt_sec:
            continue
        # 只过滤孤立的向上尖峰；连续真实快速下降仍会保留并触发 speed gate。
        if (
            height - prev_height > outlier_jump_m
            and height - next_height > outlier_jump_m
            and abs(prev_height - next_height) <= outlier_jump_m
        ):
            outlier_indices.add(idx)
            outlier_details.append(
                {
                    "sample_index": idx,
                    "time_sec": t,
                    "height_m": height,
                    "raw_range_m": range_m,
                    "prev_height_m": prev_height,
                    "next_height_m": next_height,
                    "prev_sample_index": prev_idx,
                    "next_sample_index": next_idx,
                }
            )
    rate_outlier_details: list[dict[str, float | int | str]] = []
    while True:
        current_heights = [sample for sample in raw_heights if sample[0] not in outlier_indices]
        rejected: dict[str, float | int | str] | None = None
        for prev_sample, sample in zip(current_heights, current_heights[1:]):
            prev_idx, prev_t, prev_height, _prev_range, prev_source = prev_sample
            idx, t, height, _range_m, source = sample
            if prev_source != "rangefinder_relative_height" or source != "rangefinder_relative_height":
                continue
            dt = t - prev_t
            if dt <= 0:
                continue
            rate_mps = abs(height - prev_height) / dt
            if rate_mps <= rangefinder_max_rate_mps:
                continue
            rejected_idx, rejected_t, rejected_height = (prev_idx, prev_t, prev_height)
            kept_idx, kept_t, kept_height = (idx, t, height)
            if height > prev_height:
                rejected_idx, rejected_t, rejected_height = (idx, t, height)
                kept_idx, kept_t, kept_height = (prev_idx, prev_t, prev_height)
            rejected = {
                "sample_index": rejected_idx,
                "time_sec": rejected_t,
                "height_m": rejected_height,
                "neighbor_sample_index": kept_idx,
                "neighbor_time_sec": kept_t,
                "neighbor_height_m": kept_height,
                "abs_rate_mps": rate_mps,
                "height_source": source,
            }
            break
        if rejected is None:
            break
        outlier_indices.add(int(rejected["sample_index"]))
        rate_outlier_details.append(rejected)
    valid_height_records = [
        (t, height, source) for idx, t, height, _range_m, source in raw_heights if idx not in outlier_indices
    ]
    valid_heights = [(t, height) for t, height, _source in valid_height_records]
    valid_vz = [
        (t, None if height is None else float(height), float(vz))
        for idx, (t, height, _range_m, vz, _source) in enumerate(parsed_samples)
        if idx not in outlier_indices and vz is not None and math.isfinite(float(vz))
    ]
    touchdown_vz = [vz for _t, height, vz in valid_vz if height is not None and height <= touchdown_altitude_m]
    height_rates: list[tuple[float, float, float, float, float, str]] = []
    for (prev_t, prev_height, prev_source), (t, height, source) in zip(valid_height_records, valid_height_records[1:]):
        dt = t - prev_t
        if dt <= 0:
            continue
        if prev_source == source and prev_height > touchdown_altitude_m:
            height_rates.append((max(0.0, (prev_height - height) / dt), prev_t, t, prev_height, height, source))
    high_height_rate_windows = [
        (prev_t, t) for speed, prev_t, t, _prev_height, _height, _source in height_rates if speed > max_descent_rate_mps
    ]
    vertical_velocity_outliers: list[dict[str, float | str]] = []
    controlled_speeds = []
    for t, height, vz in valid_vz:
        if height is not None and height <= touchdown_altitude_m:
            continue
        if vz <= max_descent_rate_mps:
            controlled_speeds.append(
                {"source": "vertical_velocity", "speed_mps": vz, "time_sec": t, "height_m": height}
            )
            continue
        if not valid_heights or any(start - 0.10 <= t <= end + 0.10 for start, end in high_height_rate_windows):
            controlled_speeds.append(
                {"source": "vertical_velocity", "speed_mps": vz, "time_sec": t, "height_m": height}
            )
            continue
        vertical_velocity_outliers.append(
            {
                "source": "vertical_velocity_uncorroborated",
                "speed_mps": vz,
                "time_sec": t,
                "height_m": height,
            }
        )
    controlled_speeds.extend(
        {
            "source": "height_rate",
            "speed_mps": speed,
            "from_time_sec": prev_t,
            "to_time_sec": t,
            "from_height_m": prev_height,
            "to_height_m": height,
            "height_source": source,
        }
        for speed, prev_t, t, prev_height, height, source in height_rates
    )
    max_speed_entry = max(controlled_speeds, key=lambda entry: float(entry["speed_mps"])) if controlled_speeds else None
    max_downward_speed = float(max_speed_entry["speed_mps"]) if max_speed_entry is not None else None
    max_touchdown_downward_speed = max(touchdown_vz) if touchdown_vz else None
    first_touchdown = next(
        ((t, h, source) for t, h, source in valid_height_records if h <= touchdown_altitude_m),
        None,
    )
    post_touchdown_max_height = None
    post_touchdown_bounce = None
    if first_touchdown is not None:
        first_t, first_h, first_source = first_touchdown
        post_heights = [height for t, height, source in valid_height_records if t >= first_t and source == first_source]
        if post_heights:
            post_touchdown_max_height = max(post_heights)
            post_touchdown_bounce = max(0.0, post_touchdown_max_height - first_h)
    speed_ok = max_downward_speed is not None and max_downward_speed <= max_descent_rate_mps
    bounce_ok = post_touchdown_bounce is None or post_touchdown_bounce <= max_post_touchdown_bounce_m
    return {
        "ok": len(valid_heights) >= 2 and speed_ok and bounce_ok,
        "sample_count": len(samples),
        "raw_height_sample_count": len(raw_heights),
        "height_sample_count": len(valid_heights),
        "filtered_height_sample_count": len(outlier_indices),
        "rangefinder_raw_sample_count": sum(
            1
            for _t, _height, range_m, _vz, _source in parsed_samples
            if range_m is not None and math.isfinite(float(range_m)) and float(range_m) >= 0.0
        ),
        "fallback_height_sample_count": sum(
            1
            for _t, height, _range_m, _vz, source in parsed_samples
            if height is not None and source != "rangefinder_relative_height"
        ),
        "height_source_counts": source_counts,
        "duration_sec": 0.0 if len(samples) < 2 else max(0.0, samples[-1][0] - samples[0][0]),
        "start_height_m": valid_heights[0][1] if valid_heights else None,
        "end_height_m": valid_heights[-1][1] if valid_heights else None,
        "min_height_m": min((height for _t, height in valid_heights), default=None),
        "max_height_m": max((height for _t, height in valid_heights), default=None),
        "max_downward_speed_mps": max_downward_speed,
        "max_downward_speed_source": max_speed_entry,
        "max_touchdown_downward_speed_mps": max_touchdown_downward_speed,
        "max_descent_rate_mps": max_descent_rate_mps,
        "speed_ok": speed_ok,
        "height_source": "rangefinder_relative_height_preferred",
        "rangefinder_outlier_count": len(outlier_indices),
        "rangefinder_rate_outlier_count": len(rate_outlier_details),
        "vertical_velocity_outlier_count": len(vertical_velocity_outliers),
        "rangefinder_outlier_min_m": rangefinder_outlier_min_m,
        "rangefinder_outlier_max_neighbor_dt_sec": rangefinder_outlier_max_neighbor_dt_sec,
        "rangefinder_max_rate_mps": rangefinder_max_rate_mps,
        "rangefinder_outliers": outlier_details[:10],
        "rangefinder_rate_outliers": rate_outlier_details[:10],
        "vertical_velocity_outliers": vertical_velocity_outliers[:10],
        "touchdown_altitude_m": touchdown_altitude_m,
        "post_touchdown_max_height_m": post_touchdown_max_height,
        "post_touchdown_bounce_m": post_touchdown_bounce,
        "max_post_touchdown_bounce_m": max_post_touchdown_bounce_m,
        "bounce_ok": bounce_ok,
    }
