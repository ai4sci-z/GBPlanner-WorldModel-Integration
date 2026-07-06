#!/usr/bin/env python3
# 终审:summary.json 的 ok/status/blockers + exploration/landing/return-home 关键指标。
# 用法: summary_verdict.py <run_dir>
import sys, os, json

run = sys.argv[1]
s = json.load(open(os.path.join(run, "summary.json")))
print("ok =", s.get("ok"))
print("status =", s.get("status"))
print("blockers =", s.get("blockers"))
print("blockerCodes =", s.get("blockerCodes"))
print("warnings =", s.get("warnings"))

m = (s.get("metrics") or {}).get("gate") or {}
exp = m.get("exploration") or {}
print("\n-- exploration --")
for k in ("accepted_goals", "min_accepted_goals", "path_length_m", "min_path_length_m"):
    print(" ", k, "=", exp.get(k))
ctl = m.get("controller") or {}
print("\n-- controller --")
print("  ready =", ctl.get("ready"), " bootstrap_ready =", ctl.get("bootstrap_ready"))
tk = ((ctl.get("bootstrap") or {}).get("takeoff") or {})
print("  takeoff.ok =", tk.get("ok"), " height_m =", (tk.get("height") or {}).get("height_m"))
slam = m.get("slam") or {}
print("\n-- slam --")
print("  ready =", slam.get("ready"))

ev = (s.get("evidence") or {}).get("landingEvidence") or {}
print("\n-- landing --")
print("  ok =", (ev.get("landing") or {}).get("ok"), " blockers =", ev.get("blockers"))

print("\n-- probes --")
for po in (s.get("evidence") or {}).get("probeOutputs") or []:
    pl = po.get("payload") or {}
    print("  node=%s ok=%s blockers=%s" % (pl.get("node"), po.get("ok"), pl.get("blockers")))
