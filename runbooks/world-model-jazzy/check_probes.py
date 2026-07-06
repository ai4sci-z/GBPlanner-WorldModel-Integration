#!/usr/bin/env python3
# 查 imu_probe / frame_contract_probe 具体缺哪些话题。用法: check_probes.py <run_dir>
import json, sys, os
run = sys.argv[1]
for name in ["imu_probe", "frame_contract_probe"]:
    path = os.path.join(run, "probes", name + ".json")
    print("==========", name)
    if not os.path.exists(path):
        print("  (no file)")
        continue
    d = json.load(open(path))
    print("  ok:", d.get("ok"), " blockers:", d.get("blockers"))
    for topic, samp in (d.get("samples") or {}).items():
        if isinstance(samp, dict):
            print("   -", topic, "ok=", samp.get("ok"), samp.get("failure_kind", ""))
