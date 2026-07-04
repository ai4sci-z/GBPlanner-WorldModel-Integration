from __future__ import annotations

from pathlib import Path

import pytest

from navlab.sim.companion.nodes.scan_reference_correction import decide_correction


def _status(
    *,
    active: bool = True,
    intent_x: float = -0.2,
    intent_y: float = 0.0,
    axes: list[str] | None = None,
    consecutive: int = 20,
    phase4b_ok: bool = True,
):
    axes = axes or ["x"]
    return {
        "phase4b_consistency_ok": phase4b_ok,
        "phase4b_consistency_source": "unit_test",
        "correction_eligibility": {
            "correction_allowed": active,
            "allowed_axes": axes,
        },
        "correction_intent": {
            "active": active,
            "phase4b_consistency_ok": phase4b_ok,
            "phase4b_consistency_source": "unit_test",
            "axes": axes,
            "blockers": [],
            "correction_x_m": intent_x,
            "correction_y_m": intent_y,
            "correction_magnitude_m": (intent_x**2 + intent_y**2) ** 0.5,
            "max_correction_m": 0.25,
            "consecutive_allowed_samples": consecutive,
            "required_consecutive_allowed_samples": 20,
        },
    }


def _history(x: float = -0.2, y: float = 0.0, n: int = 5):
    return [(x, y, 0.25) for _ in range(n)]


def test_runtime_correction_is_fail_closed_outside_hover_hold() -> None:
    decision = decide_correction(
        _status(),
        hover_phase="complete",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=_history(),
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert not decision.correction_applied
    assert decision.measurement_delta_magnitude_m == 0.0
    assert "scan_reference_runtime_not_hover_hold" in decision.blockers


def test_runtime_correction_can_preheat_during_hover_settle() -> None:
    decision = decide_correction(
        _status(intent_x=-0.16),
        hover_phase="hover_settle",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=_history(x=-0.16, y=0.0, n=5),
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert decision.correction_applied
    assert decision.measurement_delta_x_m == pytest.approx(0.16)
    assert decision.blockers == ()


def test_runtime_correction_requires_consistent_history() -> None:
    decision = decide_correction(
        _status(),
        hover_phase="hover_hold",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=_history(n=2),
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert not decision.correction_applied
    assert "scan_reference_runtime_consistency_window_short" in decision.blockers


def test_runtime_correction_outputs_measurement_delta_opposite_of_intent() -> None:
    decision = decide_correction(
        _status(intent_x=-0.2, intent_y=0.0),
        hover_phase="hover_hold",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=_history(x=-0.2, y=0.0, n=5),
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert decision.correction_applied
    assert decision.source_intent_x_m == pytest.approx(-0.2)
    assert decision.measurement_delta_x_m == pytest.approx(0.2)
    assert decision.measurement_delta_y_m == 0.0
    assert decision.blockers == ()
    assert decision.axes == ("x",)


def test_runtime_correction_blocks_sign_flips_and_full_saturation() -> None:
    decision = decide_correction(
        _status(intent_x=-0.25),
        hover_phase="hover_hold",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=[
            (-0.25, 0.0, 0.25),
            (0.25, 0.0, 0.25),
            (-0.25, 0.0, 0.25),
            (0.25, 0.0, 0.25),
            (-0.25, 0.0, 0.25),
        ],
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert not decision.correction_applied
    assert "scan_reference_runtime_x_sign_flips" in decision.blockers
    assert "scan_reference_runtime_saturation_ratio_high" in decision.blockers


def test_runtime_correction_blocks_only_flipping_axis_when_other_axis_is_stable() -> None:
    decision = decide_correction(
        _status(intent_x=-0.18, intent_y=0.12, axes=["x", "y"]),
        hover_phase="hover_hold",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=[
            (-0.18, 0.12, 0.25),
            (-0.19, -0.12, 0.25),
            (-0.18, 0.11, 0.25),
            (-0.19, -0.11, 0.25),
            (-0.18, 0.12, 0.25),
        ],
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert decision.correction_applied
    assert decision.axes == ("x",)
    assert decision.blocked_axes == ("y",)
    assert "scan_reference_runtime_y_sign_flips" in decision.axis_blockers["y"]
    assert decision.measurement_delta_x_m == pytest.approx(0.18)
    assert decision.measurement_delta_y_m == 0.0


def test_runtime_correction_requires_phase4b_consistency_input() -> None:
    decision = decide_correction(
        _status(intent_x=-0.2, phase4b_ok=False),
        hover_phase="hover_hold",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=_history(x=-0.2, y=0.0, n=5),
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert not decision.correction_applied
    assert "scan_reference_runtime_phase4b_consistency_missing" in decision.blockers
    assert decision.phase4b_consistency_ok is False


def test_runtime_correction_can_use_stable_scan_measurement_when_intent_is_capped() -> None:
    status = _status(active=True, intent_x=-0.25, phase4b_ok=False, consecutive=0)
    status.update(
        {
            "quality_good": True,
            "x_m": 0.42,
            "y_m": 0.0,
            "correction_eligibility": {
                "correction_allowed": True,
                "allowed_axes": ["x"],
            },
        }
    )

    decision = decide_correction(
        status,
        hover_phase="hover_hold",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        runtime_history=[(0.40, 0.0, 0.0), (0.41, 0.0, 0.0), (0.42, 0.0, 0.0), (0.42, 0.0, 0.0), (0.42, 0.0, 0.0)],
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert decision.correction_applied
    assert decision.measurement_delta_x_m == pytest.approx(0.25)
    assert decision.measurement_delta_magnitude_m == pytest.approx(0.25)
    assert decision.axes == ("x",)
    assert decision.phase4b_consistency_ok is True
    assert decision.phase4b_consistency_source == "scan_reference_runtime_measurement_window"


def test_runtime_measurement_delta_has_separate_plausibility_limit() -> None:
    status = _status(active=True, intent_x=-0.25, phase4b_ok=False, consecutive=0)
    status.update(
        {
            "quality_good": True,
            "x_m": 0.70,
            "y_m": 0.0,
            "correction_eligibility": {
                "correction_allowed": True,
                "allowed_axes": ["x"],
            },
        }
    )

    decision = decide_correction(
        status,
        hover_phase="hover_hold",
        status_age_ms=10.0,
        max_status_age_ms=400.0,
        max_correction_m=0.25,
        max_measurement_delta_m=1.25,
        runtime_history=[(0.68, 0.0, 0.0), (0.69, 0.0, 0.0), (0.70, 0.0, 0.0), (0.70, 0.0, 0.0), (0.70, 0.0, 0.0)],
        min_runtime_consistency_samples=5,
        min_direction_cosine=0.7,
        max_axis_sign_flips=0,
        max_saturation_ratio=0.95,
    )

    assert decision.correction_applied
    assert decision.measurement_delta_x_m == pytest.approx(0.70)
    assert decision.measurement_delta_magnitude_m == pytest.approx(0.70)
    assert decision.phase4b_consistency_source == "scan_reference_runtime_measurement_window"


def test_corrected_odom_publisher_uses_reliable_qos_for_external_nav_bridge() -> None:
    source = Path("navlab/sim/companion/nodes/scan_reference_correction.py").read_text()

    assert "ReliabilityPolicy.RELIABLE" in source
    assert "create_publisher(Odometry, args.output_odom_topic, corrected_odom_qos)" in source
    assert "create_subscription(Odometry, args.slam_odom_topic, self._handle_odom, qos_profile_sensor_data)" in source
