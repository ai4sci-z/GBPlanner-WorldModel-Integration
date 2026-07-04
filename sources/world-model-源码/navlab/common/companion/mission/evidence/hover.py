"""Hover evidence summarization helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from navlab.common.companion.mission.context import MissionContext

HoverPoseSample = tuple[float, float, float, float]
HoverAltitudeSample = dict[str, float | None]


@dataclass(frozen=True, slots=True)
class HoverDriftSummary:
    """Summary of pose drift over the selected hover evidence window."""

    sample_count: int
    duration_sec: float
    horizontal_span_m: float
    z_span_m: float
    horizontal_drift_m: float
    z_drift_m: float

    @property
    def ok(self) -> bool:
        """Return whether enough samples exist to evaluate drift."""

        return self.sample_count >= 2


def classify_hover_drift(
    drift: HoverDriftSummary,
    *,
    max_horizontal_drift_m: float,
) -> str:
    """Classify hover drift against the configured horizontal threshold."""

    if not drift.ok or max_horizontal_drift_m <= 0 or not math.isfinite(drift.horizontal_drift_m):
        return "unusable"
    ratio = drift.horizontal_drift_m / max_horizontal_drift_m
    if ratio <= 0.25:
        return "tight"
    if ratio <= 0.50:
        return "nominal"
    if ratio <= 1.0:
        return "marginal"
    return "unstable"


def classify_hover_slo_tier(value_m: float, *, target_m: float, hard_cap_m: float) -> str:
    """Classify one horizontal hover metric against target and hard cap."""

    if target_m <= 0 or hard_cap_m <= 0 or target_m > hard_cap_m or not math.isfinite(value_m):
        return "unusable"
    if value_m <= target_m:
        return "green"
    if value_m <= hard_cap_m:
        return "yellow"
    return "red"


def summarize_hover_altitude_crosscheck(
    samples: list[dict[str, float | None]],
    *,
    target_alt_m: float,
    tolerance_m: float,
) -> dict[str, object]:
    """Compare FCU, external-nav, and rangefinder height evidence."""

    latest = samples[-1] if samples else {}
    fcu_height = latest.get("fcu_local_height_m")
    external_height = latest.get("external_nav_height_m")
    rangefinder_height = latest.get("rangefinder_relative_height_m")

    def abs_diff(left: float | None, right: float | None) -> float | None:
        """Return absolute difference when both values are present."""

        if left is None or right is None:
            return None
        return abs(float(left) - float(right))

    def target_error(value: float | None) -> float | None:
        """Return absolute error against the configured target altitude."""

        return abs_diff(value, target_alt_m)

    diffs = {
        "fcu_vs_external_abs_m": abs_diff(fcu_height, external_height),
        "fcu_vs_rangefinder_abs_m": abs_diff(fcu_height, rangefinder_height),
        "external_vs_rangefinder_abs_m": abs_diff(external_height, rangefinder_height),
        "fcu_target_error_m": target_error(fcu_height),
        "external_target_error_m": target_error(external_height),
        "rangefinder_target_error_m": target_error(rangefinder_height),
    }
    missing = [
        name
        for name, value in {
            "fcu_local_height_m": fcu_height,
            "external_nav_height_m": external_height,
            "rangefinder_relative_height_m": rangefinder_height,
        }.items()
        if value is None
    ]
    over_tolerance = [name for name, value in diffs.items() if value is not None and float(value) > tolerance_m]
    ok = len(samples) >= 2 and not missing and not over_tolerance
    return {
        "ok": ok,
        "sample_count": len(samples),
        "target_alt_m": target_alt_m,
        "tolerance_m": tolerance_m,
        "sources": {
            "fcu_local_z_ned": latest.get("fcu_local_z_ned"),
            "fcu_local_height_m": fcu_height,
            "external_nav_height_m": external_height,
            "rangefinder_range_m": latest.get("rangefinder_range_m"),
            "rangefinder_relative_height_m": rangefinder_height,
        },
        "diffs": diffs,
        "missing_sources": missing,
        "over_tolerance": over_tolerance,
    }


def summarize_hover_drift(samples: list[tuple[float, float, float, float]]) -> HoverDriftSummary:
    """Summarize horizontal and vertical drift from hover pose samples."""

    if len(samples) < 2:
        return HoverDriftSummary(
            sample_count=len(samples),
            duration_sec=0.0,
            horizontal_span_m=math.inf,
            z_span_m=math.inf,
            horizontal_drift_m=math.inf,
            z_drift_m=math.inf,
        )
    xs = [sample[1] for sample in samples]
    ys = [sample[2] for sample in samples]
    zs = [sample[3] for sample in samples]
    start = samples[0]
    end = samples[-1]
    return HoverDriftSummary(
        sample_count=len(samples),
        duration_sec=max(0.0, end[0] - start[0]),
        horizontal_span_m=math.hypot(max(xs) - min(xs), max(ys) - min(ys)),
        z_span_m=max(zs) - min(zs),
        horizontal_drift_m=math.hypot(end[1] - start[1], end[2] - start[2]),
        z_drift_m=abs(end[3] - start[3]),
    )


def json_safe_number(value: float | int | None) -> float | int | None:
    """Convert non-finite numbers to None for JSON output."""

    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass(frozen=True, slots=True)
class HoverEvidenceWindow:
    """Selected hover evidence samples for summary and acceptance checks."""

    pose_samples: list[HoverPoseSample]
    altitude_samples: list[HoverAltitudeSample]


@dataclass(frozen=True, slots=True)
class HoverCompletionEvaluation:
    """Final hover-body acceptance evidence."""

    ok: bool
    reason: str
    drift: HoverDriftSummary
    altitude_crosscheck: dict[str, object]
    acceptance: dict[str, object]

    def frozen_hover_evidence(self, *, takeoff_ack_ok: bool, crash_detected: bool) -> dict[str, object]:
        """Return the hover evidence payload frozen at landing handoff."""

        return {
            "takeoff_ack_ok": takeoff_ack_ok,
            "hover_altitude_crosscheck": self.altitude_crosscheck,
            "hover_drift": {
                "sample_count": self.drift.sample_count,
                "duration_sec": self.drift.duration_sec,
                "horizontal_span_m": json_safe_number(self.drift.horizontal_span_m),
                "z_span_m": json_safe_number(self.drift.z_span_m),
                "horizontal_drift_m": json_safe_number(self.drift.horizontal_drift_m),
                "z_drift_m": json_safe_number(self.drift.z_drift_m),
            },
            "hover_acceptance": dict(self.acceptance),
            "hover_body_ok": self.ok,
            "hover_body_reason": self.reason,
            "crash_detected": crash_detected,
        }


class HoverEvidenceRecorder:
    """Own hover evidence sample windows and selected best hover segment."""

    def __init__(self) -> None:
        """Create an empty hover evidence recorder."""

        self._active_started_at: float | None = None
        self._pose_samples: list[HoverPoseSample] = []
        self._altitude_samples: list[HoverAltitudeSample] = []
        self._best_pose_samples: list[HoverPoseSample] = []
        self._best_altitude_samples: list[HoverAltitudeSample] = []
        self._segment_count = 0

    @property
    def active_started_at(self) -> float | None:
        """Monotonic timestamp for the current hover segment, when active."""

        return self._active_started_at

    @property
    def segment_count(self) -> int:
        """Number of hover-hold segments observed."""

        return self._segment_count

    def update_phase(self, *, phase: str, now_monotonic: float, terminal: bool) -> bool:
        """Update segment lifecycle for a mission phase and return whether a segment started."""

        if phase != "hover_hold" and self._active_started_at is not None and not terminal:
            self.remember_segment()
            self._active_started_at = None
            self.clear_active()
            return False
        if phase == "hover_hold" and self._active_started_at is None:
            self._active_started_at = now_monotonic
            self._segment_count += 1
            self.clear_active()
            return True
        return False

    def clear_active(self) -> None:
        """Clear samples from the currently active segment."""

        self._pose_samples.clear()
        self._altitude_samples.clear()

    def append_sample(
        self,
        *,
        now_monotonic: float,
        x_m: float,
        y_m: float,
        z_ned_m: float,
        elapsed_sec: float,
        fcu_local_z_ned: float | None,
        fcu_local_height_m: float | None,
        external_nav_height_m: float | None,
        rangefinder_range_m: float | None,
        rangefinder_relative_height_m: float | None,
    ) -> None:
        """Append one pose and altitude evidence sample to the active hover segment."""

        self._pose_samples.append((now_monotonic, x_m, y_m, z_ned_m))
        self._altitude_samples.append(
            {
                "elapsed_sec": elapsed_sec,
                "fcu_local_z_ned": fcu_local_z_ned,
                "fcu_local_height_m": fcu_local_height_m,
                "external_nav_height_m": external_nav_height_m,
                "rangefinder_range_m": rangefinder_range_m,
                "rangefinder_relative_height_m": rangefinder_relative_height_m,
            }
        )

    def record_context(self, ctx: MissionContext, *, phase: str, terminal: bool) -> bool:
        """Update segment lifecycle and append one hover sample from mission context."""

        started = self.update_phase(phase=phase, now_monotonic=ctx.clock.now_monotonic, terminal=terminal)
        pose = ctx.state.pose
        if phase == "hover_hold" and pose.x_m is not None and pose.y_m is not None:
            self.append_sample(
                now_monotonic=ctx.clock.now_monotonic,
                x_m=pose.x_m,
                y_m=pose.y_m,
                z_ned_m=pose.z_ned_m or 0.0,
                elapsed_sec=ctx.clock.elapsed_sec,
                fcu_local_z_ned=pose.z_ned_m,
                fcu_local_height_m=pose.fcu_local_height_m,
                external_nav_height_m=pose.external_nav_height_m,
                rangefinder_range_m=pose.rangefinder_range_m,
                rangefinder_relative_height_m=pose.rangefinder_relative_height_m,
            )
        return started

    def remember_segment(self) -> None:
        """Remember the active segment when it is better than the previous best segment."""

        if not self._pose_samples:
            return
        current = summarize_hover_drift(self._pose_samples)
        best = summarize_hover_drift(self._best_pose_samples)
        if current.duration_sec >= best.duration_sec:
            self._best_pose_samples = list(self._pose_samples)
            self._best_altitude_samples = list(self._altitude_samples)

    def selected_window(self) -> HoverEvidenceWindow:
        """Return the best currently available hover evidence window."""

        candidates: list[HoverEvidenceWindow] = []
        if self._best_pose_samples:
            candidates.append(
                HoverEvidenceWindow(
                    pose_samples=list(self._best_pose_samples),
                    altitude_samples=list(self._best_altitude_samples),
                )
            )
        if self._pose_samples:
            candidates.append(
                HoverEvidenceWindow(
                    pose_samples=list(self._pose_samples),
                    altitude_samples=list(self._altitude_samples),
                )
            )
        if not candidates:
            return HoverEvidenceWindow(
                pose_samples=list(self._pose_samples),
                altitude_samples=list(self._altitude_samples),
            )
        return max(candidates, key=lambda window: summarize_hover_drift(window.pose_samples).duration_sec)

    def evaluate_completion(
        self,
        *,
        target_alt_m: float,
        altitude_tolerance_m: float,
        hold_sec: float,
        duration_tolerance_sec: float,
        max_horizontal_drift_m: float,
        max_altitude_drift_m: float,
        local_position_count: int,
        crash_detected: bool,
        hover_span_target_m: float | None = None,
        hover_span_hard_cap_m: float | None = None,
        slam_quality: str = "",
        slam_quality_reason: str = "",
        slam_quality_loss_duration_sec: float = 0.0,
        external_nav_loss_duration_sec: float = 0.0,
        mavlink_external_nav_loss_duration_sec: float = 0.0,
    ) -> HoverCompletionEvaluation:
        """Evaluate final hover-body acceptance from selected evidence."""

        window = self.selected_window()
        drift = summarize_hover_drift(window.pose_samples)
        altitude_crosscheck = summarize_hover_altitude_crosscheck(
            window.altitude_samples,
            target_alt_m=target_alt_m,
            tolerance_m=altitude_tolerance_m,
        )
        sample_count_ok = drift.ok
        altitude_ok = altitude_crosscheck["ok"] is True
        duration_ok = drift.duration_sec >= hold_sec - duration_tolerance_sec
        target_m = hover_span_target_m if hover_span_target_m and hover_span_target_m > 0 else max_horizontal_drift_m
        hard_cap_m = (
            hover_span_hard_cap_m if hover_span_hard_cap_m and hover_span_hard_cap_m > 0 else max_horizontal_drift_m
        )
        horizontal_drift_tier = classify_hover_slo_tier(
            drift.horizontal_drift_m,
            target_m=target_m,
            hard_cap_m=hard_cap_m,
        )
        horizontal_span_tier = classify_hover_slo_tier(
            drift.horizontal_span_m,
            target_m=target_m,
            hard_cap_m=hard_cap_m,
        )
        horizontal_drift_ok = horizontal_drift_tier in ("green", "yellow")
        horizontal_span_ok = horizontal_span_tier in ("green", "yellow")
        z_span_ok = drift.z_span_m <= max_altitude_drift_m
        local_position_ok = local_position_count > 0
        no_slam_quality_loss_after_airborne = slam_quality_loss_duration_sec <= 0.0
        no_external_nav_loss_after_airborne = external_nav_loss_duration_sec <= 0.0
        no_mavlink_external_nav_loss_after_airborne = mavlink_external_nav_loss_duration_sec <= 0.0
        slam_quality_jump_seen = slam_quality == "jump" or slam_quality_reason == "pose_or_yaw_jump"
        no_slam_quality_jump_in_hover_window = not slam_quality_jump_seen
        acceptance = {
            "sample_count_ok": sample_count_ok,
            "altitude_ok": altitude_ok,
            "duration_ok": duration_ok,
            "horizontal_drift_ok": horizontal_drift_ok,
            "horizontal_span_ok": horizontal_span_ok,
            "horizontal_drift_target_ok": horizontal_drift_tier == "green",
            "horizontal_span_target_ok": horizontal_span_tier == "green",
            "horizontal_drift_hard_cap_ok": horizontal_drift_ok,
            "horizontal_span_hard_cap_ok": horizontal_span_ok,
            "horizontal_drift_tier": horizontal_drift_tier,
            "horizontal_span_tier": horizontal_span_tier,
            "hover_span_target_m": target_m,
            "hover_span_hard_cap_m": hard_cap_m,
            "z_span_ok": z_span_ok,
            "local_position_ok": local_position_ok,
            "crash_free": not crash_detected,
            "no_slam_quality_loss_after_airborne": no_slam_quality_loss_after_airborne,
            "no_external_nav_loss_after_airborne": no_external_nav_loss_after_airborne,
            "no_mavlink_external_nav_loss_after_airborne": no_mavlink_external_nav_loss_after_airborne,
            "no_slam_quality_jump_in_hover_window": no_slam_quality_jump_in_hover_window,
            "slam_quality": slam_quality,
            "slam_quality_reason": slam_quality_reason,
            "slam_quality_loss_duration_sec": slam_quality_loss_duration_sec,
            "external_nav_loss_duration_sec": external_nav_loss_duration_sec,
            "mavlink_external_nav_loss_duration_sec": mavlink_external_nav_loss_duration_sec,
        }
        ok = all(
            bool(acceptance[key])
            for key in (
                "sample_count_ok",
                "altitude_ok",
                "duration_ok",
                "horizontal_drift_ok",
                "horizontal_span_ok",
                "z_span_ok",
                "local_position_ok",
                "crash_free",
                "no_slam_quality_loss_after_airborne",
                "no_external_nav_loss_after_airborne",
                "no_mavlink_external_nav_loss_after_airborne",
                "no_slam_quality_jump_in_hover_window",
            )
        )
        return HoverCompletionEvaluation(
            ok=bool(ok),
            reason="hover_complete" if ok else _hover_completion_failure_reason(acceptance),
            drift=drift,
            altitude_crosscheck=altitude_crosscheck,
            acceptance=acceptance,
        )


def _hover_completion_failure_reason(acceptance: dict[str, object]) -> str:
    """Return the first actionable hover acceptance failure reason."""

    checks = (
        ("sample_count_ok", "hover_samples_missing"),
        ("altitude_ok", "hover_altitude_unstable"),
        ("duration_ok", "hover_duration_short"),
        ("horizontal_drift_ok", "hover_drift_unstable"),
        ("horizontal_span_ok", "hover_span_unstable"),
        ("z_span_ok", "hover_altitude_span_unstable"),
        ("local_position_ok", "hover_local_position_missing"),
        ("crash_free", "hover_crash_detected"),
        ("no_slam_quality_loss_after_airborne", "slam_quality_lost_after_airborne"),
        ("no_external_nav_loss_after_airborne", "external_nav_lost_after_airborne"),
        ("no_mavlink_external_nav_loss_after_airborne", "mavlink_external_nav_lost_after_airborne"),
        ("no_slam_quality_jump_in_hover_window", "slam_quality_jump_in_hover_window"),
    )
    for key, reason in checks:
        if acceptance.get(key) is not True:
            return reason
    return "hover_unstable"
