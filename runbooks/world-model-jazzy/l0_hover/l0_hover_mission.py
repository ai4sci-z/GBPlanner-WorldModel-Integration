#!/usr/bin/env python3
"""L0 hover mission driver (GATE-4b bisection, layer L0).

Runs INSIDE the official-baseline container. Official positioning baseline
(GPS+compass EKF), no SLAM / no external nav. Drives: wait-ready -> GUIDED ->
arm -> takeoff -> hover N sec -> LAND -> wait disarm. OBSERVE ONLY: never
aborts early on anomaly; everything is recorded and judged later from the
dataflash BIN over the FULL window (no early-sampling green).
"""
import argparse
import json
import sys
import time

from pymavlink import mavutil


def log(events, name, **kw):
    ev = {"t_wall": time.time(), "event": name, **kw}
    events.append(ev)
    print(f"[l0] {name} {kw}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="tcp:127.0.0.1:5760")
    ap.add_argument("--alt", type=float, default=0.5)
    ap.add_argument("--hover-sec", type=float, default=60.0)
    ap.add_argument("--ready-timeout", type=float, default=180.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    events = []
    verdict_inputs = {"alt": args.alt, "hover_sec": args.hover_sec, "endpoint": args.endpoint}
    rc = 0
    m = mavutil.mavlink_connection(args.endpoint)

    # B17 lesson: wait for the AUTOPILOT's heartbeat (not any GCS peer), so
    # target_system is real before we send commands.
    deadline = time.time() + args.ready_timeout
    while True:
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=5.0)
        if hb and hb.type != mavutil.mavlink.MAV_TYPE_GCS and (hb.get_srcSystem() or 0) != 0:
            m.target_system = hb.get_srcSystem()
            m.target_component = hb.get_srcComponent() or 1
            break
        if time.time() > deadline:
            log(events, "fatal_no_autopilot_heartbeat")
            json.dump({"inputs": verdict_inputs, "events": events, "driver_rc": 2}, open(args.out, "w"), indent=1)
            return 2
    log(events, "heartbeat", sysid=m.target_system, compid=m.target_component)

    # SITL's extra serial ports broadcast heartbeats only; telemetry must be
    # requested explicitly (mavproxy on 5760 requests its own streams).
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    for msg_id, us in ((mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT, 250000),
                       (mavutil.mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 500000),
                       (mavutil.mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED, 250000),
                       (mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE, 250000)):
        m.mav.command_long_send(m.target_system, m.target_component,
                                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                float(msg_id), float(us), 0, 0, 0, 0, 0)
    log(events, "streams_requested")

    # Readiness: GPS 3D fix + EKF predicting position (official baseline owns
    # its sources; we only wait, we do not inject anything).
    gps_ok = ekf_ok = False
    while time.time() < deadline and not (gps_ok and ekf_ok):
        msg = m.recv_match(type=["GPS_RAW_INT", "EKF_STATUS_REPORT"], blocking=True, timeout=5.0)
        if msg is None:
            continue
        if msg.get_type() == "GPS_RAW_INT" and msg.fix_type >= 3 and not gps_ok:
            gps_ok = True
            log(events, "gps_3d_fix", sats=msg.satellites_visible)
        if msg.get_type() == "EKF_STATUS_REPORT":
            need = (mavutil.mavlink.EKF_PRED_POS_HORIZ_ABS | mavutil.mavlink.EKF_POS_VERT_ABS)
            if (msg.flags & need) == need and not ekf_ok:
                ekf_ok = True
                log(events, "ekf_pos_ok", flags=msg.flags)
    if not (gps_ok and ekf_ok):
        log(events, "fatal_not_ready", gps_ok=gps_ok, ekf_ok=ekf_ok)
        json.dump({"inputs": verdict_inputs, "events": events, "driver_rc": 3}, open(args.out, "w"), indent=1)
        return 3

    # GUIDED
    mode_id = m.mode_mapping()["GUIDED"]
    for _ in range(30):
        m.set_mode(mode_id)
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2.0)
        if hb and hb.custom_mode == mode_id:
            break
    else:
        log(events, "fatal_mode_not_guided")
        json.dump({"inputs": verdict_inputs, "events": events, "driver_rc": 4}, open(args.out, "w"), indent=1)
        return 4
    log(events, "mode_guided")

    # Arm (retry until prearm passes or timeout)
    armed = False
    arm_deadline = time.time() + 60.0
    while time.time() < arm_deadline and not armed:
        m.mav.command_long_send(m.target_system, m.target_component,
                                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        ack = m.recv_match(type="COMMAND_ACK", blocking=True, timeout=3.0)
        if ack and ack.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM and ack.result == 0:
            armed = True
    if not armed:
        log(events, "fatal_arm_refused")
        json.dump({"inputs": verdict_inputs, "events": events, "driver_rc": 5}, open(args.out, "w"), indent=1)
        return 5
    log(events, "armed")

    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, args.alt)
    ack = m.recv_match(type="COMMAND_ACK", blocking=True, timeout=5.0)
    log(events, "takeoff_cmd", ack=(ack.result if ack else None))

    # Observe: hover window + margin, measured in SIM time (the autopilot's
    # time_boot_ms under lockstep) — wall-clock windows shrink by the real-time
    # factor (take3: 85 wall s = 28.5 sim s at RTF~0.33). No intervention.
    window_sim = args.hover_sec + 25.0  # climb + land margin; verdict uses BIN
    t_wall_start = time.time()
    t_wall_cap = t_wall_start + window_sim * 12.0  # runaway fallback only
    sim0 = sim_now = None
    samples = []
    was_armed = True
    while time.time() < t_wall_cap:
        msg = m.recv_match(type=["LOCAL_POSITION_NED", "ATTITUDE", "HEARTBEAT"], blocking=True, timeout=2.0)
        if msg is None:
            continue
        t = time.time()
        mt = msg.get_type()
        tb = getattr(msg, "time_boot_ms", None)
        if tb:
            sim_now = tb / 1000.0
            if sim0 is None:
                sim0 = sim_now
            elif sim_now - sim0 >= window_sim:
                break
        if mt == "LOCAL_POSITION_NED":
            samples.append({"t": t, "t_sim": sim_now, "x": msg.x, "y": msg.y, "z": msg.z})
        elif mt == "ATTITUDE":
            samples.append({"t": t, "t_sim": sim_now, "roll": msg.roll, "pitch": msg.pitch})
        elif mt == "HEARTBEAT":
            # Only the autopilot's own heartbeat carries a meaningful armed
            # flag; mavproxy's GCS heartbeat shares the link and would
            # otherwise read as a constant disarm.
            if msg.get_srcSystem() != m.target_system or msg.type == mavutil.mavlink.MAV_TYPE_GCS:
                continue
            now_armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            if was_armed and not now_armed:
                log(events, "disarmed_during_window", t_wall=t)  # flip signature; keep observing
            was_armed = now_armed
    wall_elapsed = time.time() - t_wall_start
    sim_elapsed = (sim_now - sim0) if (sim0 is not None and sim_now is not None) else None
    rtf = (sim_elapsed / wall_elapsed) if (sim_elapsed and wall_elapsed > 0) else None
    log(events, "hover_window_done", n_samples=len(samples),
        sim_elapsed=round(sim_elapsed, 1) if sim_elapsed else None,
        wall_elapsed=round(wall_elapsed, 1), rtf=round(rtf, 3) if rtf else None)

    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_NAV_LAND, 0, 0, 0, 0, 0, 0, 0, 0)
    log(events, "land_cmd")
    land_deadline = time.time() + 180.0  # wall clock; generous for low RTF
    disarmed = False
    while time.time() < land_deadline:
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2.0)
        if hb and not (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            disarmed = True
            break
    log(events, "disarmed_after_land" if disarmed else "land_timeout")

    json.dump({"inputs": verdict_inputs, "events": events, "samples": samples, "driver_rc": rc},
              open(args.out, "w"), indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
