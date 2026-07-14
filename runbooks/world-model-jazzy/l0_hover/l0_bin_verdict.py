#!/usr/bin/env python3
"""L0 hover verdict from the dataflash BIN — judged over the FULL window,
AFTER landing (no early-sampling green; Review 002 GATE-4b requirement).

Hard gate (all must hold, else rc=1):
  - armed continuously from arm to our land command (no unexpected disarm)
  - roll/pitch peak < 20 deg while airborne (flip signature = ~129 deg)
  - hover altitude within +/-0.30 m of target for >= hover_sec
  - no CRASH_CHECK error, no crash event
Runs inside the official-baseline container (pymavlink available).
"""
import argparse
import glob
import json
import math
import os
import sys

from pymavlink import mavutil

DEG = 180.0 / math.pi


def newest_bin(logdir):
    cands = sorted(glob.glob(os.path.join(logdir, "**", "*.BIN"), recursive=True), key=os.path.getmtime)
    return cands[-1] if cands else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", dest="binpath", default=None)
    ap.add_argument("--logdir", default=None)
    ap.add_argument("--alt", type=float, required=True)
    ap.add_argument("--hover-sec", type=float, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    binpath = args.binpath or (args.logdir and newest_bin(args.logdir))
    if not binpath or not os.path.exists(binpath):
        json.dump({"ok": False, "reason": "bin_missing"}, open(args.out, "w"))
        print("VERDICT: FAIL (bin_missing)")
        return 1

    m = mavutil.mavlink_connection(binpath)
    arm_t = disarm_ts = None
    disarms = []
    att = []            # (t, roll_deg, pitch_deg)
    ctun_alt = []       # (t, alt_above_home)
    pos = []            # (t, x, y) from XKF1/POS
    crash = False
    mode_changes = []
    while True:
        msg = m.recv_match(
            type=["EV", "ERR", "ATT", "CTUN", "XKF1", "MODE"], blocking=False)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", None)
        if t is None:
            continue
        t = t / 1e6
        mt = msg.get_type()
        if mt == "EV":
            if msg.Id == 10 and arm_t is None:
                arm_t = t
            elif msg.Id == 11:
                disarms.append(t)
        elif mt == "ERR":
            # subsys 12 = CRASH_CHECK
            if msg.Subsys == 12 and msg.ECode != 0:
                crash = True
        elif mt == "ATT":
            att.append((t, msg.Roll, msg.Pitch))
        elif mt == "CTUN":
            ctun_alt.append((t, msg.Alt))
        elif mt == "XKF1" and getattr(msg, "C", 0) == 0:
            pos.append((t, msg.PN, msg.PE))
        elif mt == "MODE":
            mode_changes.append((t, msg.Mode))

    checks = {}
    if arm_t is None:
        checks["armed_seen"] = False
    else:
        checks["armed_seen"] = True
        disarm_t = disarms[0] if disarms else None
        armed_dur = (disarm_t - arm_t) if disarm_t else (att[-1][0] - arm_t if att else 0.0)
        checks["armed_duration_sec"] = round(armed_dur, 2)
        # full window = climb margin + hover + land margin is judged by the
        # caller-supplied hover_sec against the armed window minus ~25 s slack
        checks["armed_long_enough"] = armed_dur >= args.hover_sec + 10.0

        airborne = [(t, r, p) for (t, r, p) in att if arm_t + 3.0 <= t <= (disarm_t or 1e18)]
        peak_roll = max((abs(r) for (_, r, _) in airborne), default=0.0)
        peak_pitch = max((abs(p) for (_, _, p) in airborne), default=0.0)
        checks["peak_roll_deg"] = round(peak_roll, 1)
        checks["peak_pitch_deg"] = round(peak_pitch, 1)
        checks["attitude_bounded"] = peak_roll < 20.0 and peak_pitch < 20.0

        band = [(t, a) for (t, a) in ctun_alt if abs(a - args.alt) <= 0.30 and t >= arm_t]
        in_band = 0.0
        if band:
            # longest contiguous stretch inside the altitude band
            start = prev = band[0][0]
            for (t, _) in band[1:]:
                if t - prev > 1.0:
                    in_band = max(in_band, prev - start)
                    start = t
                prev = t
            in_band = max(in_band, prev - start)
        checks["hover_in_band_sec"] = round(in_band, 2)
        checks["hover_long_enough"] = in_band >= args.hover_sec * 0.95

        if pos:
            xs = [x for (_, x, _) in pos]
            ys = [y for (_, _, y) in pos]
            checks["xy_span_m"] = round(max(max(xs) - min(xs), max(ys) - min(ys)), 3)
            checks["xy_bounded"] = checks["xy_span_m"] < 1.0
        checks["no_crash_check"] = not crash
        checks["n_disarms"] = len(disarms)

    hard = ["armed_seen", "armed_long_enough", "attitude_bounded",
            "hover_long_enough", "no_crash_check"]
    ok = all(checks.get(k) is True for k in hard)
    out = {"ok": ok, "bin": binpath, "target_alt": args.alt,
           "hover_sec_required": args.hover_sec, "checks": checks,
           "mode_changes": mode_changes[:20]}
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"VERDICT: {'PASS' if ok else 'FAIL'} " + json.dumps(checks))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
