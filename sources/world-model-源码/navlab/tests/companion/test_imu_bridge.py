from __future__ import annotations

import json
from math import isclose
from types import SimpleNamespace

from navlab.real.companion.nodes.imu_bridge import (
    GRAVITY_MPS2,
    ImuBridgeStatus,
    encode_imu_status,
    sample_from_highres_imu,
    sample_from_raw_imu,
    sample_from_scaled_imu,
    state_for_imu_status,
)


def test_sample_from_highres_imu_keeps_si_units() -> None:
    msg = SimpleNamespace(xacc=1.0, yacc=2.0, zacc=9.8, xgyro=0.1, ygyro=0.2, zgyro=0.3)

    sample = sample_from_highres_imu(msg)

    assert sample.source_message == "HIGHRES_IMU"
    assert isclose(sample.linear_acceleration_z, 9.8)
    assert isclose(sample.angular_velocity_z, 0.3)
    assert sample.raw_units is False


def test_sample_from_scaled_imu_converts_millig_and_millirad_per_sec() -> None:
    msg = SimpleNamespace(xacc=0, yacc=0, zacc=1000, xgyro=10, ygyro=20, zgyro=30)

    sample = sample_from_scaled_imu(msg)

    assert sample.source_message == "SCALED_IMU"
    assert isclose(sample.linear_acceleration_z, GRAVITY_MPS2)
    assert isclose(sample.angular_velocity_x, 0.01)
    assert isclose(sample.angular_velocity_z, 0.03)


def test_sample_from_raw_imu_marks_raw_units() -> None:
    msg = SimpleNamespace(xacc=1, yacc=2, zacc=3, xgyro=4, ygyro=5, zgyro=6)

    sample = sample_from_raw_imu(msg)

    assert sample.source_message == "RAW_IMU"
    assert sample.raw_units is True


def test_state_for_imu_status_matches_existing_bridge_states() -> None:
    assert state_for_imu_status(present=False, fresh=False, rate_ok=False) == "waiting_for_fcu_imu_source"
    assert state_for_imu_status(present=True, fresh=False, rate_ok=True) == "stale_fcu_imu_source"
    assert state_for_imu_status(present=True, fresh=True, rate_ok=False) == "low_rate_fcu_imu_source"
    assert state_for_imu_status(present=True, fresh=True, rate_ok=True) == "streaming_fcu_imu"


def test_encode_imu_status_matches_external_nav_ready_contract() -> None:
    payload = encode_imu_status(
        ImuBridgeStatus(
            state="streaming_fcu_imu",
            ready=True,
            source_label="fcu_mavlink",
            source_message="HIGHRES_IMU",
            input_present=True,
            input_fresh=True,
            input_age_ms=12.3456,
            input_rate_hz=50.0,
            input_rate_ok=True,
            min_rate_hz=4.0,
            output_topic="/imu/data",
            output_frame_id="fcu_imu",
            count=10,
            raw_fallback_count=0,
        )
    )

    data = json.loads(payload)
    assert data["ready"] is True
    assert data["state"] == "streaming_fcu_imu"
    assert data["source"]["message"] == "HIGHRES_IMU"
    assert data["input"]["age_ms"] == 12.346
    assert data["output"]["topic"] == "/imu/data"
