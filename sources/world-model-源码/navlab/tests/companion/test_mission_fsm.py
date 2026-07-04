from __future__ import annotations

from navlab.common.companion.mission.fsm import (
    MissionPhaseRecorder,
    mission_phase_state_for_hover_phase,
    mission_phase_state_for_landing_state,
)


def test_mission_phase_maps_hover_and_landing_states() -> None:
    assert mission_phase_state_for_hover_phase("takeoff") == "S4 takeoff"
    assert mission_phase_state_for_hover_phase("hover_hold") == "S6 hover_hold"
    assert mission_phase_state_for_hover_phase("unknown") == "S_abort"
    assert mission_phase_state_for_landing_state("pre_land_hold") == "S7 pre_land_hold"
    assert mission_phase_state_for_landing_state("landing_complete") == "S12 landing_complete"
    assert mission_phase_state_for_landing_state("bad_state") == "S_abort"


def test_mission_phase_recorder_tracks_history_and_current_state() -> None:
    recorder = MissionPhaseRecorder(started_at_monotonic=100.0)

    recorder.transition(now_monotonic=101.0, state="S1 wait_nav_ready", reason="waiting_for_slam")
    recorder.transition(now_monotonic=104.0, state="S4 takeoff", reason="taking_off", guard="takeoff")

    snapshot = recorder.snapshot(now_monotonic=105.0)

    assert snapshot.state == "S4 takeoff"
    assert snapshot.state_entered_at_sec == 4.0
    assert snapshot.last_transition_reason == "taking_off"
    history = snapshot.history
    assert history[0].state == "S0 wait_runtime"
    assert history[0].duration_sec == 1.0
    assert history[1].state == "S1 wait_nav_ready"
    assert history[-1].state == "S4 takeoff"
    assert history[-1].exited_at_sec is None
    assert snapshot.to_dict()["history"][-1]["state"] == "S4 takeoff"
