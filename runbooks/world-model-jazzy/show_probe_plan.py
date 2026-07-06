#!/usr/bin/env python3
# 打印 runtime_plan.json 里探针容器定义(image/env/network/entrypoint)+ probe spec timeout。
# 用法: show_probe_plan.py <run_dir> [probe_name]
import sys, os, json

run = sys.argv[1]
want = sys.argv[2] if len(sys.argv) > 2 else "frame_contract_probe"

plan = json.load(open(os.path.join(run, "runtime_plan.json")))

def walk(o, path=""):
    if isinstance(o, dict):
        if want in json.dumps(o.get("name", ""), ensure_ascii=False) or o.get("name") == want:
            print("==== node at", path, "====")
            slim = {k: v for k, v in o.items() if k not in ("script", "content", "payload")}
            print(json.dumps(slim, indent=2, ensure_ascii=False, sort_keys=True)[:4000])
        for k, v in o.items():
            walk(v, path + "/" + str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, path + "[%d]" % i)

walk(plan)

# probe json spec 里的 timeout
p = os.path.join(run, "probes", want + ".json")
if os.path.exists(p):
    d = json.load(open(p))
    spec = d.get("spec") or {}
    print("\n==== probe spec keys ====")
    for k, v in sorted(spec.items()):
        print(" ", k, "=", str(v)[:120])
