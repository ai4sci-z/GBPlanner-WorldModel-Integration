#!/usr/bin/env python3
"""L1/L1.5 bisect verdict: FULL-WINDOW dataflash BIN replay.

Unlike l0_bin_verdict.py (first-arm-window only — known trap, see
l1_bringup_evidence_2026-07-15.md §1), this walks EVERY arm..disarm window
and reports per-window armed duration, roll/pitch peaks while armed,
takeoff events, crash-check errors and notable MSG lines. It renders a
table for the L0(stable)/L2(flip) comparison; it does NOT gate.

Runs inside the official-baseline container (pymavlink available):
  docker run --rm -v <rundir>/sitl/logs:/logs -v <here>:/tools \
    navlab/official-baseline:jazzy-latest python3 /tools/l1_bin_full_window.py /logs/00000001.BIN
"""
import json
import math
import sys

from pymavlink import mavutil

DEG = 180.0 / math.pi


def replay(binpath):
    m = mavutil.mavlink_connection(binpath)
    windows = []          # list of dicts
    cur = None            # open window
    events = []           # (t, ev_id) all EV messages
    errs = []             # (t, subsys, ecode)
    msgs = []             # (t, text)
    last_t = None
    while True:
        msg = m.recv_match(type=["EV", "ERR", "ATT", "MSG"], blocking=False)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", None)
        if t is None:
            continue
        t = t / 1e6
        last_t = t
        typ = msg.get_type()
        if typ == "EV":
            ev = int(msg.Id)
            events.append((t, ev))
            if ev == 10:  # ARMED
                cur = {"arm_t": t, "roll_peak": 0.0, "pitch_peak": 0.0,
                       "ev": [], "disarm_t": None}
                windows.append(cur)
            elif ev == 11:  # DISARMED
                if cur is not None:
                    cur["disarm_t"] = t
                    cur = None
            elif cur is not None:
                cur["ev"].append((round(t, 1), ev))
        elif typ == "ATT" and cur is not None:
            cur["roll_peak"] = max(cur["roll_peak"], abs(float(msg.Roll)))
            cur["pitch_peak"] = max(cur["pitch_peak"], abs(float(msg.Pitch)))
        elif typ == "ERR":
            errs.append((round(t, 1), int(msg.Subsys), int(msg.ECode)))
        elif typ == "MSG":
            text = msg.Message if isinstance(msg.Message, str) else msg.Message.decode(errors="replace")
            msgs.append((round(t, 1), text))
    return windows, events, errs, msgs, last_t


def main():
    binpath = sys.argv[1]
    windows, events, errs, msgs, last_t = replay(binpath)
    crash = [e for e in errs if e[1] == 12 and e[2] != 0]  # CRASH_CHECK
    crash_msgs = [x for x in msgs if "crash" in x[1].lower()]
    out = {"bin": binpath, "log_end_s": round(last_t, 1) if last_t else None,
           "n_arm_windows": len(windows), "windows": [], "crash_err": crash,
           "crash_msgs": crash_msgs}
    for i, w in enumerate(windows, 1):
        end = w["disarm_t"] if w["disarm_t"] is not None else last_t
        out["windows"].append({
            "idx": i,
            "arm_t": round(w["arm_t"], 1),
            "disarm_t": round(w["disarm_t"], 1) if w["disarm_t"] is not None else None,
            "armed_s": round(end - w["arm_t"], 1),
            "truncated_by_log_end": w["disarm_t"] is None,
            "roll_peak_deg": round(w["roll_peak"], 1),
            "pitch_peak_deg": round(w["pitch_peak"], 1),
            "ev_in_window": w["ev"],
        })
    print(json.dumps(out, ensure_ascii=False, indent=1))
    # last few MSG lines help explain terminal state
    print("--- last MSG lines ---", file=sys.stderr)
    for t, s in msgs[-12:]:
        print(f"{t:9.1f}  {s}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
