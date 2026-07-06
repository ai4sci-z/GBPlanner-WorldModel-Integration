#!/usr/bin/env python3
# 查证 Codex review 的不自洽点。只读、只打印实测,不改任何东西。
# 用法: verify_codex.py [run_id]
import subprocess, json, os, sys, glob

CLEAN = "/home/ai4s/ws-clean/world-model"
ART = os.path.join(CLEAN, "artifacts/sim/exploration")

def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return (r.stdout or "") + (("\n[stderr] " + r.stderr) if r.stderr.strip() else "")

print("################## 1) GIT 真相 (clean 分支当前工作树) ##################")
print("HEAD:", sh(["git","-C",CLEAN,"rev-parse","--short","HEAD"]).strip())
print("branch:", sh(["git","-C",CLEAN,"branch","--show-current"]).strip())
st = sh(["git","-C",CLEAN,"status","--porcelain"]).strip()
print("git status --porcelain:\n" + (st if st else "(clean, no uncommitted changes)"))
print("\n---- git diff --stat (未提交的工作树改动) ----")
print(sh(["git","-C",CLEAN,"diff","--stat"]).strip() or "(none)")

print("\n---- git grep 三个 hack 字符串 (当前工作树内容) ----")
for pat in ["DISARM_DELAY", "EK3_SRC1_POSZ", "ReadinessTimeoutSec", "RNGFND1_MIN"]:
    print("== " + pat + " ==")
    print(sh(["git","-C",CLEAN,"grep","-n","-e",pat]).strip() or "(not found)")
    print()

print("################## 2) RUN 产物真相 ##################")
run = sys.argv[1] if len(sys.argv) > 1 else None
if not run:
    runs = sorted(os.listdir(ART)) if os.path.isdir(ART) else []
    run = runs[-1] if runs else None
print("run_id:", run)
D = os.path.join(ART, run) if run else None
if not D or not os.path.isdir(D):
    print("  (no run dir)"); sys.exit(0)
print("artifact dir:", D)
print("dir listing:", sorted(os.listdir(D)))

# summary.json: 走一遍找关键词
sp = os.path.join(D, "summary.json")
if os.path.exists(sp):
    s = json.load(open(sp))
    print("\n---- summary.json 关键字段 ----")
    KEY = ["status","blocker","error","takeoff","altitude","alt","accepted","path_length",
           "goal","ok","ready","climb","motor","pwm","rcou","ctun","dalt","height"]
    def walk(o, p=""):
        if isinstance(o, dict):
            for k,v in o.items(): walk(v, p+"/"+k)
        elif isinstance(o, list):
            print("  " + p + " = [list len " + str(len(o)) + "]")
            for i,v in enumerate(o[:6]): walk(v, p+"[%d]"%i)
        else:
            low = p.lower()
            if any(w in low for w in KEY):
                print("  " + p + " = " + str(o)[:200])
    walk(s)

# 探针
print("\n---- 探针 json (ok / blockers / 每话题 sample ok) ----")
for name in ["frame_contract_probe","exploration_probe","imu_probe"]:
    path = os.path.join(D, "probes", name + ".json")
    print("==========", name)
    if not os.path.exists(path):
        print("  (no file)"); continue
    d = json.load(open(path))
    print("  ok:", d.get("ok"), " blockers:", d.get("blockers"), " optional_blockers:", d.get("optional_blockers"))
    print("  topics:", d.get("topics"))
    for topic, samp in (d.get("samples") or {}).items():
        if isinstance(samp, dict):
            print("   -", topic, "ok=", samp.get("ok"),
                  "method=", samp.get("sample_method",""),
                  "kind=", samp.get("failure_kind",""),
                  "type=", samp.get("type",""))

# BIN / tlog 定位
print("\n---- BIN / tlog 文件 ----")
for pat in ["**/*.BIN","**/*.bin","**/*.tlog","**/*.log"]:
    for f in glob.glob(os.path.join(D, pat), recursive=True):
        try: sz = os.path.getsize(f)
        except OSError: sz = -1
        print("  ", f.replace(D+"/",""), sz, "bytes")
