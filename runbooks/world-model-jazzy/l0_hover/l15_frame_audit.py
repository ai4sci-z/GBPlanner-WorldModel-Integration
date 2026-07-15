#!/usr/bin/env python3
"""L1.5 frame audit: is the fed external-nav position a REFLECTION of truth?

Hypothesis under test (2026-07-16, root-cause domain = external-nav feed):
  external_nav.py ros_enu_position_to_mavlink_local_frd() returns (y, -x, -z).
  For ANY right-handed z-up source frame this produces a LEFT-HANDED (det=-1,
  reflected) NED position, while the yaw path (pi/2 - yaw) is a proper
  rotation. Position=reflection + yaw=rotation is irreconcilable with the
  IMU inertial reference -> EKF innovation divergence -> flip.

Measurement (no new runs needed): in a flip-run dataflash BIN compare
  VISP.PX/PY   (vision position fed to EK3, logged by AP_VisualOdom)
  SIM2.PN/PE   (SITL's own truth position in NED; fallback SIM lat/lng)
Least-squares fit a 2x2 matrix M mapping truth->fed XY and report det(M).
  det ~ +1 -> proper rotation (feed frame-consistent, hypothesis REFUTED)
  det ~ -1 -> reflection (hypothesis CONFIRMED)
Also reports yaw consistency: VISP.Yaw delta vs SIM.Yaw delta.

Run inside official-baseline container (pymavlink available):
  docker run --rm -v <rundir>/sitl/logs:/logs \
    -v <this dir>:/tools <official-baseline-image> \
    python3 /tools/l15_frame_audit.py /logs/00000001.BIN
"""
import math
import sys

from pymavlink import mavutil

DEG = 180.0 / math.pi


def collect(binpath):
    m = mavutil.mavlink_connection(binpath)
    visp = []  # (t, px, py, pz, yaw_deg)
    sim2 = []  # (t, pn, pe, pd)
    simy = []  # (t, yaw_deg)
    types = {}
    while True:
        msg = m.recv_match(type=["VISP", "SIM2", "SIM"], blocking=False)
        if msg is None:
            break
        typ = msg.get_type()
        types[typ] = types.get(typ, 0) + 1
        t = getattr(msg, "TimeUS", None)
        if t is None:
            continue
        t = t / 1e6
        if typ == "VISP":
            visp.append((t, float(msg.PX), float(msg.PY), float(msg.PZ),
                         float(getattr(msg, "Yaw", float("nan")))))
        elif typ == "SIM2":
            sim2.append((t, float(msg.PN), float(msg.PE), float(msg.PD)))
        elif typ == "SIM":
            simy.append((t, float(msg.Yaw)))
    return visp, sim2, simy, types


def interp(series, t):
    """Linear interpolation of a list[(t, *vals)] at time t; None outside."""
    lo, hi = 0, len(series) - 1
    if t < series[0][0] or t > series[hi][0]:
        return None
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= t:
            lo = mid
        else:
            hi = mid
    t0, t1 = series[lo][0], series[hi][0]
    if t1 <= t0:
        return series[lo][1:]
    a = (t - t0) / (t1 - t0)
    return tuple(v0 + a * (v1 - v0) for v0, v1 in zip(series[lo][1:], series[hi][1:]))


def fit2x2(pairs):
    """Least squares M: truth(n,e) -> fed(x,y), centered. pairs=[(tn,te,fx,fy)]."""
    n = len(pairs)
    mn = sum(p[0] for p in pairs) / n
    me = sum(p[1] for p in pairs) / n
    mx = sum(p[2] for p in pairs) / n
    my = sum(p[3] for p in pairs) / n
    snn = sne = see = 0.0
    sxn = sxe = syn = sye = 0.0
    for tn, te, fx, fy in pairs:
        dn, de, dx, dy = tn - mn, te - me, fx - mx, fy - my
        snn += dn * dn
        sne += dn * de
        see += de * de
        sxn += dx * dn
        sxe += dx * de
        syn += dy * dn
        sye += dy * de
    det_a = snn * see - sne * sne
    if abs(det_a) < 1e-12:
        return None
    inv = ((see / det_a, -sne / det_a), (-sne / det_a, snn / det_a))
    m00 = sxn * inv[0][0] + sxe * inv[1][0]
    m01 = sxn * inv[0][1] + sxe * inv[1][1]
    m10 = syn * inv[0][0] + sye * inv[1][0]
    m11 = syn * inv[0][1] + sye * inv[1][1]
    return ((m00, m01), (m10, m11))


def main():
    binpath = sys.argv[1]
    visp, sim2, simy, types = collect(binpath)
    print(f"message counts: {types}")
    if not visp:
        print("FATAL: no VISP messages (external nav not logged?)")
        return 2
    truth = sim2
    if not truth:
        print("FATAL: no SIM2 truth position; extend tool for SIM lat/lng")
        return 2

    # Sample truth at VISP timestamps; keep samples with real XY excursion.
    all_pairs = []
    for t, px, py, pz, yaw in visp:
        tv = interp(truth, t)
        if tv is None:
            continue
        all_pairs.append((tv[0], tv[1], px, py, t, pz, tv[2]))
    if len(all_pairs) < 50:
        print(f"FATAL: only {len(all_pairs)} matched samples")
        return 2

    # Pre-crash window: keep samples until truth XY departs >1.5m from its
    # start (the flip skid drags the vehicle far; the informative divergent
    # oscillation lives below that, where the 0.25 m/s feed slew limit is
    # also mostly transparent).
    n0, e0 = all_pairs[0][0], all_pairs[0][1]
    pairs = []
    for p in all_pairs:
        if math.hypot(p[0] - n0, p[1] - e0) > 1.5:
            break
        pairs.append(p)
    print(f"pre-crash window: {len(pairs)}/{len(all_pairs)} samples "
          f"(t {pairs[0][4]:.1f}..{pairs[-1][4]:.1f}s)")
    if len(pairs) < 50:
        print("FATAL: pre-crash window too short")
        return 2

    span_n = max(p[0] for p in pairs) - min(p[0] for p in pairs)
    span_e = max(p[1] for p in pairs) - min(p[1] for p in pairs)
    print(f"matched samples: {len(pairs)}  truth spans: N={span_n:.3f}m E={span_e:.3f}m")
    if max(span_n, span_e) < 0.05:
        print("WARNING: <5cm truth excursion; fit may be noise-dominated")

    fit = fit2x2([(p[0], p[1], p[2], p[3]) for p in pairs])
    if fit is None:
        print("FATAL: degenerate truth trajectory (no XY excursion)")
        return 2
    (m00, m01), (m10, m11) = fit
    det = m00 * m11 - m01 * m10
    print("\nLS fit  fed_XY = M @ truth_NE  (centered):")
    print(f"  M = [[{m00:+.3f}, {m01:+.3f}],")
    print(f"       [{m10:+.3f}, {m11:+.3f}]]   det = {det:+.3f}")

    # Residual RMS of the fit vs naive candidates.
    def rms(f):
        s = 0.0
        for tn, te, fx, fy, *_ in pairs:
            gx, gy = f(tn, te)
            s += (gx - fx) ** 2 + (gy - fy) ** 2
        return math.sqrt(s / len(pairs))

    mnx = sum(p[0] for p in pairs) / len(pairs)
    mex = sum(p[1] for p in pairs) / len(pairs)
    mfx = sum(p[2] for p in pairs) / len(pairs)
    mfy = sum(p[3] for p in pairs) / len(pairs)

    candidates = {
        "identity      (n, e)": lambda n, e: (mfx + (n - mnx), mfy + (e - mex)),
        "reflect swap  (-e,-n)": lambda n, e: (mfx - (e - mex), mfy - (n - mnx)),
        "swap          (e, n)": lambda n, e: (mfx + (e - mex), mfy + (n - mnx)),
        "rot180        (-n,-e)": lambda n, e: (mfx - (n - mnx), mfy - (e - mex)),
        "rot+90        (-e, n)": lambda n, e: (mfx - (e - mex), mfy + (n - mnx)),
        "rot-90        (e, -n)": lambda n, e: (mfx + (e - mex), mfy - (n - mnx)),
        "reflectN      (n, -e)": lambda n, e: (mfx + (n - mnx), mfy - (e - mex)),
        "reflectE      (-n, e)": lambda n, e: (mfx - (n - mnx), mfy + (e - mex)),
    }
    print("\ncandidate mapping residual RMS (lower = better):")
    for name, f in sorted(candidates.items(), key=lambda kv: rms(kv[1])):
        print(f"  {name:24s} {rms(f):8.4f} m")

    # Step-direction test — immune to the radial slew limit (it rescales the
    # step vector but preserves its direction). For a proper rotation,
    # angle(fed step) - angle(truth step) = const; for a reflection,
    # angle(fed step) + angle(truth step) = const. Whichever has the tighter
    # circular spread wins.
    diffs = []
    sums = []
    for a, b in zip(pairs, pairs[2:]):
        dtn, dte = b[0] - a[0], b[1] - a[1]
        dfx, dfy = b[2] - a[2], b[3] - a[3]
        if math.hypot(dtn, dte) < 0.02 or math.hypot(dfx, dfy) < 0.02:
            continue
        at = math.atan2(dte, dtn)
        af = math.atan2(dfy, dfx)
        diffs.append(af - at)
        sums.append(af + at)

    def circ_spread(angles):
        c = sum(math.cos(a) for a in angles) / len(angles)
        s = sum(math.sin(a) for a in angles) / len(angles)
        r = math.hypot(c, s)  # 1 = perfectly concentrated
        return r, math.atan2(s, c)

    if len(diffs) >= 30:
        r_rot, mu_rot = circ_spread(diffs)
        r_ref, mu_ref = circ_spread(sums)
        print(f"\nstep-direction test ({len(diffs)} steps >2cm):")
        print(f"  rotation model   (af-at=const): concentration R={r_rot:.3f}  const={mu_rot*DEG:+7.1f} deg")
        print(f"  reflection model (af+at=const): concentration R={r_ref:.3f}  const={mu_ref*DEG:+7.1f} deg")
        if r_ref > r_rot + 0.1:
            print("  => REFLECTION wins (frame bug CONFIRMED by directions)")
        elif r_rot > r_ref + 0.1:
            print("  => rotation wins (reflection hypothesis REFUTED by directions)")
        else:
            print("  => inconclusive")
    else:
        print(f"\nstep-direction test: only {len(diffs)} usable steps, skipped")

    # Yaw consistency: fed yaw delta vs truth yaw delta.
    if simy and not math.isnan(visp[0][4]):
        y_pairs = []
        for t, _, _, _, yaw in visp:
            tv = interp(simy, t)
            if tv is not None and not math.isnan(yaw):
                y_pairs.append((yaw, tv[0]))
        if len(y_pairs) > 50:
            f0, t0 = y_pairs[0]
            errs = []
            for f, tt in y_pairs:
                df = (f - f0 + 540.0) % 360.0 - 180.0
                dt_ = (tt - t0 + 540.0) % 360.0 - 180.0
                errs.append((df - dt_ + 540.0) % 360.0 - 180.0)
            mean_abs = sum(abs(e) for e in errs) / len(errs)
            peak = max(abs(e) for e in errs)
            print(f"\nyaw delta consistency (fed vs truth): mean|err|={mean_abs:.2f} deg  peak={peak:.2f} deg")
            print("  (small => yaw feed rotation-consistent; position verdict above decides)")

    print("\nVERDICT:")
    if det < -0.5:
        print("  det ~ -1  => fed position is a REFLECTION of truth — frame bug CONFIRMED")
    elif det > 0.5:
        print("  det ~ +1  => fed position is a proper rotation of truth — reflection hypothesis REFUTED")
    else:
        print("  |det| << 1 => degenerate/noisy; need more XY excursion")
    return 0


if __name__ == "__main__":
    sys.exit(main())
