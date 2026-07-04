from __future__ import annotations

import pytest

from navlab.sim.gazebo_sensor.airframe_disturbance import (
    AirframeDisturbanceGateThresholds,
    AirframeDisturbanceProfile,
    apply_profile_to_iris_sdf,
    estimate_disturbance_metrics,
    profile_from_library,
    validate_profile,
)

SDF = """<?xml version='1.0'?>
<sdf version="1.9">
  <model name="iris_with_lidar">
    <plugin name="ArduPilotPlugin" filename="ArduPilotPlugin">
      <control channel="0">
        <jointName>rotor_0_joint</jointName><multiplier>838</multiplier><p_gain>0.20</p_gain>
      </control>
      <control channel="1">
        <jointName>rotor_1_joint</jointName><multiplier>838</multiplier><p_gain>0.20</p_gain>
      </control>
      <control channel="2">
        <jointName>rotor_2_joint</jointName><multiplier>-838</multiplier><p_gain>0.20</p_gain>
      </control>
      <control channel="3">
        <jointName>rotor_3_joint</jointName><multiplier>-838</multiplier><p_gain>0.20</p_gain>
      </control>
    </plugin>
  </model>
</sdf>
"""


def test_profile_validation_blocks_array_length_mismatch() -> None:
    profile = AirframeDisturbanceProfile(
        name="bad",
        motor_count=4,
        thrust_multipliers=(1.0, 1.0),
        esc_lag_ms=(0.0, 0.0, 0.0, 0.0),
    )

    assert "airframe_disturbance_config_invalid: thrust_multipliers length must match motor_count" in validate_profile(
        profile
    )


def test_profile_validation_blocks_large_multiplier_without_hard_allowance() -> None:
    profile = profile_from_library("hard_bias")
    thresholds = AirframeDisturbanceGateThresholds(max_abs_thrust_multiplier_delta=0.05)

    blockers = validate_profile(profile, thresholds, allow_hard_profile=False)

    assert any(blocker.startswith("airframe_thrust_multiplier_delta_too_high") for blocker in blockers)
    assert validate_profile(profile, thresholds, allow_hard_profile=True) == []


def test_apply_profile_to_iris_sdf_modifies_motor_multipliers_and_plugin_esc_lag() -> None:
    profile = profile_from_library("nominal_realistic")

    rendered, summary = apply_profile_to_iris_sdf(SDF, profile)

    assert "NavLab P12 airframe disturbance profile" in rendered
    assert "<multiplier>812.86</multiplier>" in rendered
    assert "<multiplier>863.14</multiplier>" in rendered
    assert "<multiplier>-838</multiplier>" in rendered
    assert "<escTimeConstantMs>35</escTimeConstantMs>" in rendered
    assert "<frequencyCutoff>" not in rendered
    assert summary["applied_controls"][0]["esc_lag_model"] == "plugin_first_order"
    assert summary["applied_controls"][1]["esc_time_constant_ms"] == 35.0


def test_apply_profile_to_iris_sdf_requires_enough_controls() -> None:
    profile = profile_from_library("nominal_realistic")

    with pytest.raises(ValueError, match="expected 4 controls"):
        apply_profile_to_iris_sdf("<sdf><model name='x'/></sdf>", profile)


def test_estimated_hard_profile_fails_with_clear_blocker() -> None:
    metrics = estimate_disturbance_metrics(profile_from_library("hard_bias"))

    assert metrics["ok"] is False
    assert "map_artifact_risk_too_high" in metrics["blockers"] or "scan_drop_ratio_too_high" in metrics["blockers"]
