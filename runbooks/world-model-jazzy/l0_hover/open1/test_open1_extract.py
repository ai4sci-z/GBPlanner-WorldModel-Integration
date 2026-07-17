#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0 · G2 提取语义门 + G3 历史回放门。

G2(环境无关合成):airborne 仅正证据、缺证据 UNKNOWN;canonical TOML 等价/不等价;
  不从 STATUSTEXT 缺失反推 arm。
G3(真实回放):五个指定 run 实际执行,断言引用**实际提取值**(无恒真),
  每结果绑 run_id/目录/输入 hash;产物不在盘则整段 SKIP/UNVERIFIED(不冒充全绿)。
单元与回放**分开报告**。
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_extract as E  # noqa: E402

G2_FAIL = 0
G3_FAIL = 0
G3_RAN = 0


def ck(name, got, want):
    global G2_FAIL
    if got == want:
        print(f"PASS: {name} [{got!r}]")
    else:
        print(f"FAIL: {name} 期望[{want!r}] 实得[{got!r}]")
        G2_FAIL += 1


def ckr(name, cond):
    global G3_FAIL
    if cond:
        print(f"PASS(replay): {name}")
    else:
        print(f"FAIL(replay): {name}")
        G3_FAIL += 1


print("======== G2 提取语义门(环境无关) ========")

# --- C1 airborne = mission controller 侧结构化,非 FCU 真值 ---
av = E.airborne_verdict({"airborne_seen": True})
ck("airborne True→controller seen True", av["mission_controller_airborne_seen"], True)
ck("airborne 标注 controller 侧来源", "controller" in av["source"], True)
ck("airborne epistemic:False≠证明未离地", "FCU 从未离地" in av["epistemic_scope"], True)
ck("airborne False→controller seen False", E.airborne_verdict({"airborne_seen": False})["mission_controller_airborne_seen"], False)
ck("airborne 缺字段→UNKNOWN(None)", E.airborne_verdict({"other": 1})["mission_controller_airborne_seen"], None)
ck("airborne 无 mission_summary→UNKNOWN", E.airborne_verdict(None)["mission_controller_airborne_seen"], None)
ck("airborne 旧版summary(无字段)→UNKNOWN", E.airborne_verdict({"status": "ok"})["mission_controller_airborne_seen"], None)
ck("airborne 不看blocker(空dict)→UNKNOWN", E.airborne_verdict({})["mission_controller_airborne_seen"], None)
# controller=False 但其它来源声称 airborne → conflict
ck("airborne controller=False+他源=True→conflict", E.airborne_verdict({"airborne_seen": False}, other_airborne_claim=True)["conflict"], True)
ck("airborne 无他源→无 conflict", E.airborne_verdict({"airborne_seen": False})["conflict"], False)

# --- canonical_config_hash:精确叶子排除(不排整表);未知字段默认进身份 ---
base = ("[inputs]\n"
        "simulation_profile = 'slam-direct-no-odom-prior'\n"
        "control_mode = 'hover_slam-direct-no-odom-prior'\n"
        "[run]\n"
        "run_id = 'R1'\n"
        "artifact_dir = '/a/R1'\n"
        "duration_sec = 1500\n"
        "note = 'keep'\n"
        "[outputs]\n"
        "manifest = '/a/R1/manifest.json'\n"
        "format = 'raw'\n"
        "retain_truth = false\n"
        "sensors = ['imu', 'lidar']\n")
CH = E.canonical_config_hash
# 表序 + 键序 + 空白 + 引号 + 注释变化 → 同 hash
equiv = ("# comment line\n[run]\n"
         'duration_sec=1500\n'
         "run_id = 'R1'\n"
         'note   =   "keep"   # inline\n'
         "artifact_dir = '/a/R1'\n"
         "[outputs]\n"
         'retain_truth = false\n'
         'manifest = "/a/R1/manifest.json"\n'
         "format = 'raw'\n"
         "sensors = ['imu', 'lidar']\n"
         "[inputs]\n"
         'control_mode = "hover_slam-direct-no-odom-prior"\n'
         "simulation_profile = 'slam-direct-no-odom-prior'\n")
ck("canon 表序/键序/空白/引号/注释 等价", CH(base), CH(equiv))
# Codex 反例:[outputs].format 语义变化 → 不同 hash
ck("canon [outputs].format 变→不同hash", CH(base) != CH(base.replace("format = 'raw'", "format = 'semantic-change'")), True)
# Codex 反例:[outputs].retain_truth 语义变化 → 不同 hash
ck("canon [outputs].retain_truth 变→不同hash", CH(base) != CH(base.replace("retain_truth = false", "retain_truth = true")), True)
# [outputs] 新增未知字段 → 不同 hash
ck("canon [outputs] 新增未知字段→不同hash", CH(base) != CH(base.replace("format = 'raw'", "format = 'raw'\nnew_unknown = 42")), True)
# 只改批准的 artifact 路径(outputs.manifest)→ 同 hash
ck("canon 仅批准路径变→同hash", CH(base), CH(base.replace("/a/R1/manifest.json", "/a/OTHER/manifest.json")))
# 只改批准的 run_id → 同 hash(run.run_id + run.artifact_dir 精确排除)
diff_runid = base.replace("run_id = 'R1'", "run_id = 'R2'").replace("artifact_dir = '/a/R1'", "artifact_dir = '/a/R2'")
ck("canon 仅run_id变→同hash", CH(base), CH(diff_runid))
# 语义变化(profile / control_mode)→ 不同 hash
ck("canon profile变→不同hash", CH(base) != CH(base.replace("slam-direct-no-odom-prior", "imu-flu-correction")), True)
# run.note 含 run_id 子串,改 run_id 不动 note(非全局替换)
a = base.replace("note = 'keep'", "note = 'tag-R1'")
b = a.replace("run_id = 'R1'", "run_id = 'R2'").replace("artifact_dir = '/a/R1'", "artifact_dir = '/a/R2'")
ck("canon run_id子串在语义值中不被误替换(a==b)", CH(a), CH(b))
ck("canon 语义note不同→不同hash", CH(a) != CH(base.replace("note = 'keep'", "note = 'tag-R2'")), True)
# 列表顺序变化 → 不同 hash
ck("canon 列表顺序变→不同hash", CH(base) != CH(base.replace("['imu', 'lidar']", "['lidar', 'imu']")), True)
# 嵌套未知字段默认进入 hash
n1 = base + "[extra]\nnested = { deep = 1 }\n"
n2 = base + "[extra]\nnested = { deep = 2 }\n"
ck("canon 嵌套未知字段进身份→不同hash", CH(n1) != CH(n2), True)
# run_id 作为嵌套同名键默认进入 hash(非全局排除)
ck("canon 嵌套同名run_id进身份→不同hash", CH(base + "[meta]\nrun_id = 'X'\n") != CH(base + "[meta]\nrun_id = 'Y'\n"), True)
# 解析失败 → None(fail-closed)
ck("canon 非法TOML→None", CH("this is = = not toml ]["), None)

# --- 不从 STATUSTEXT 缺失反推 arm ---
import tempfile
import shutil
tmp = tempfile.mkdtemp()
try:
    d = os.path.join(tmp, "20260715T000000.000000000Z")
    os.makedirs(os.path.join(d, "sitl", "logs"))
    open(os.path.join(d, "run_config.toml"), "w").write(base)
    json.dump({"status": "TASK_STATUS_BLOCKED", "blockers": []}, open(os.path.join(d, "summary.json"), "w"))
    # 无 mission_summary、无 BIN、空 tlog
    open(os.path.join(d, "sitl", "mav.tlog"), "wb").write(b"")
    ex = E.extract(d)
    ck("arm 恒为 UNKNOWN(不反推)", ex["arm_status"], "UNKNOWN")
    ck("无mission_summary→airborne UNKNOWN", ex["outcome"]["airborne"]["mission_controller_airborne_seen"], None)
    ck("空tlog→质量 EMPTY 且 statustext=None", (ex["evidence_quality"]["mav.tlog"], ex["fcu_statustext"]), ("EMPTY", None))

    # --- C2 证据质量:损坏≠缺失≠正常业务失败 ---
    d2 = os.path.join(tmp, "20260715T111111.000000000Z")
    os.makedirs(os.path.join(d2, "sitl", "logs"))
    open(os.path.join(d2, "run_config.toml"), "w").write(base)
    open(os.path.join(d2, "summary.json"), "w").write("{bad json ]")          # MALFORMED
    open(os.path.join(d2, "mission_summary.json"), "w").write('{"airborne_seen": true}')  # valid
    # manifest.json 缺失;tlog 缺失
    ex2 = E.extract(d2)
    ck("C2 summary MALFORMED(非MISSING)", ex2["evidence_quality"]["summary.json"], "MALFORMED")
    ck("C2 manifest MISSING", ex2["evidence_quality"]["manifest.json"], "MISSING")
    ck("C2 mission PRESENT_VALID", ex2["evidence_quality"]["mission_summary.json"], "PRESENT_VALID")
    ck("C2 tlog MISSING", ex2["evidence_quality"]["mav.tlog"], "MISSING")
    ck("C2 损坏证据入 evidence_errors(不静默)", "summary.json:MALFORMED" in ex2["evidence_errors"], True)
    d3 = os.path.join(tmp, "20260715T222222.000000000Z")
    os.makedirs(d3)
    open(os.path.join(d3, "run_config.toml"), "w").write("not = = toml ][")   # MALFORMED TOML
    ex3 = E.extract(d3)
    ck("C2 run_config MALFORMED", ex3["evidence_quality"]["run_config.toml"], "MALFORMED")
    ck("C2 run_config损坏入 evidence_errors", "run_config.toml:MALFORMED" in ex3["evidence_errors"], True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("======== 包A evidence gate(A5 反例;先红已由 /tmp/A0_oldproof.py 记录) ========")
import open1_tlog as T2


def make_valid_run(root, name, *, tlog_bytes=None, with_bin=True, mut=None):
    """构造九输入全 PRESENT_VALID 的基准 run;mut(d) 注入单变量破坏(控制变量)。"""
    d = os.path.join(root, name)
    os.makedirs(os.path.join(d, "sitl", "logs"), exist_ok=True)
    os.makedirs(os.path.join(d, "audits"), exist_ok=True)
    os.makedirs(os.path.join(d, "probes"), exist_ok=True)
    open(os.path.join(d, "run_config.toml"), "w").write(base)
    json.dump({"created_at": "2026-07-15T20:00:00Z"}, open(os.path.join(d, "manifest.json"), "w"))
    json.dump({"status": "TASK_STATUS_OK", "blockers": []}, open(os.path.join(d, "summary.json"), "w"))
    json.dump({"airborne_seen": True}, open(os.path.join(d, "mission_summary.json"), "w"))
    json.dump({"ok": True}, open(os.path.join(d, "audits", "startup_readiness_probe.json"), "w"))
    json.dump({"ok": True}, open(os.path.join(d, "probes", "imu_probe.txt"), "w"))
    tl = tlog_bytes if tlog_bytes is not None else T2.build_statustext_record(1_000_000, 6, "ArduPilot Ready")
    open(os.path.join(d, "sitl", "mav.tlog"), "wb").write(tl)
    if with_bin:
        open(os.path.join(d, "sitl", "logs", "00000001.BIN"), "wb").write(b"\x00")
    if mut:
        mut(d)
    return d


tmp = tempfile.mkdtemp()
try:
    # 基准:全 PRESENT_VALID → COMPLETE + acceptance_eligible=True
    d0 = make_valid_run(tmp, "base")
    x0 = E.extract(d0)
    ck("A5基准 gate=COMPLETE", x0["evidence_gate"]["status"], "COMPLETE")
    ck("A5基准 acceptance_eligible=True", x0["outcome"]["acceptance_eligible"], True)
    ck("A5基准 evidence_errors=[]", x0["evidence_errors"], [])

    # A5-04/A6:Codex 复合反例(summary OK + manifest/readiness/imu 损坏 + 垃圾 tlog)
    def codex_mut(d):
        open(os.path.join(d, "manifest.json"), "w").write("{broken json ]")
        open(os.path.join(d, "audits", "startup_readiness_probe.json"), "w").write("{also broken")
        open(os.path.join(d, "probes", "imu_probe.txt"), "w").write("not json }{")
    xc = E.extract(make_valid_run(tmp, "codex", tlog_bytes=bytes(range(256)) * 16, mut=codex_mut))
    ck("A6-01 reported_task_ok=True", xc["outcome"]["reported_task_ok"], True)
    ck("A6-02 evidence_complete=False", xc["outcome"]["evidence_complete"], False)
    ck("A6-03 acceptance_eligible=False", xc["outcome"]["acceptance_eligible"], False)
    ck("A6-04 gate.status=CORRUPT", xc["evidence_gate"]["status"], "CORRUPT")
    ck("A6-05 manifest/readiness/imu/tlog 逐项入 failed_inputs",
       all(n in xc["evidence_gate"]["failed_inputs"] for n in
           ("manifest.json", "startup_readiness_probe.json", "imu_probe.txt", "mav.tlog")), True)
    ck("A5-13 业务主张保留(airborne=True 不被改写)",
       xc["outcome"]["airborne"]["mission_controller_airborne_seen"], True)

    # A5-01/02/03 单变量损坏(逐个,控制变量)
    x = E.extract(make_valid_run(tmp, "m1", mut=lambda d: open(os.path.join(d, "manifest.json"), "w").write("{]")))
    ck("A5-01 manifest MALFORMED→CORRUPT+failed", (x["evidence_gate"]["status"], "manifest.json" in x["evidence_gate"]["failed_inputs"]), ("CORRUPT", True))
    x = E.extract(make_valid_run(tmp, "m2", mut=lambda d: open(os.path.join(d, "audits", "startup_readiness_probe.json"), "w").write("{]")))
    ck("A5-02 readiness MALFORMED→CORRUPT", x["evidence_gate"]["status"], "CORRUPT")
    x = E.extract(make_valid_run(tmp, "m3", mut=lambda d: open(os.path.join(d, "probes", "imu_probe.txt"), "w").write("{]")))
    ck("A5-03 imu MALFORMED→CORRUPT", x["evidence_gate"]["status"], "CORRUPT")

    # A5-05 空 tlog / A5-06 随机垃圾 / A5-07 不存在 / A5-08 只有 unsupported 消息
    x = E.extract(make_valid_run(tmp, "t1", tlog_bytes=b""))
    ck("A5-05 空tlog→EMPTY+INCOMPLETE", (x["evidence_quality"]["mav.tlog"], x["evidence_gate"]["status"]), ("EMPTY", "INCOMPLETE"))
    x = E.extract(make_valid_run(tmp, "t2", tlog_bytes=bytes(range(256)) * 16))
    ck("A5-06 垃圾tlog→MALFORMED(A4-11)", x["evidence_quality"]["mav.tlog"], "MALFORMED")
    ck("A5-06 垃圾tlog→acceptance=False", x["outcome"]["acceptance_eligible"], False)
    x = E.extract(make_valid_run(tmp, "t3", mut=lambda d: os.unlink(os.path.join(d, "sitl", "mav.tlog"))))
    ck("A5-07 无tlog→MISSING+INCOMPLETE", (x["evidence_quality"]["mav.tlog"], x["evidence_gate"]["status"]), ("MISSING", "INCOMPLETE"))
    only_unsup = T2.build_record(2_000_000, T2.build_frame(30, b"\x00" * 8, crc_extra=None)) * 3
    x = E.extract(make_valid_run(tmp, "t4", tlog_bytes=only_unsup))
    ck("A5-08 仅unsupported消息→UNSUPPORTED+CORRUPT", (x["evidence_quality"]["mav.tlog"], x["evidence_gate"]["status"]), ("UNSUPPORTED", "CORRUPT"))

    # A5-09 READ_ERROR 注入(chmod 000;root 下跳过)
    if os.geteuid() != 0:
        d9 = make_valid_run(tmp, "r1")
        os.chmod(os.path.join(d9, "summary.json"), 0)
        x = E.extract(d9)
        os.chmod(os.path.join(d9, "summary.json"), 0o644)
        ck("A5-09 summary READ_ERROR→CORRUPT", (x["evidence_quality"]["summary.json"], x["evidence_gate"]["status"]), ("READ_ERROR", "CORRUPT"))
        # A5-10 sitl/logs 不可枚举
        d10 = make_valid_run(tmp, "r2")
        os.chmod(os.path.join(d10, "sitl", "logs"), 0)
        x = E.extract(d10)
        os.chmod(os.path.join(d10, "sitl", "logs"), 0o755)
        ck("A5-10 logs目录READ_ERROR→CORRUPT", (x["evidence_quality"]["sitl/logs(dir)"], x["evidence_gate"]["status"]), ("READ_ERROR", "CORRUPT"))
    else:
        print("SKIP: A5-09/A5-10(euid=0,chmod 注入无效)")

    # A5-11 BIN 目录在但无 BIN → PRESENT_NO_MATCH → optional_gaps,不判损坏(A5-16)
    x = E.extract(make_valid_run(tmp, "b1", with_bin=False))
    ck("A5-11 无BIN→PRESENT_NO_MATCH 入 optional_gaps", "BIN(set):PRESENT_NO_MATCH" in x["evidence_gate"]["optional_gaps"], True)
    ck("A5-16 optional gap 不判 CORRUPT(gate=COMPLETE)", x["evidence_gate"]["status"], "COMPLETE")

    # A5-12 controller airborne=True 但 gate CORRUPT
    x = E.extract(make_valid_run(tmp, "a1", mut=lambda d: open(os.path.join(d, "manifest.json"), "w").write("{]")))
    ck("A5-12 airborne=True 保留 + A5-14 gate 拒绝验收",
       (x["outcome"]["airborne"]["mission_controller_airborne_seen"], x["outcome"]["acceptance_eligible"]), (True, False))
    ck("A5-15 损坏输入逐项入 failed_inputs", x["evidence_gate"]["failed_inputs"], ["manifest.json"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("======== G3 历史回放门(独立标注驱动;不在盘则 SKIP/UNVERIFIED) ========")
H = "/home/ai4s/projects/world-model/artifacts/sim/hover"
ANN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "open1_replay_annotations.tsv")


def _load_annotations(path):
    """读独立标注 TSV(expected 非 extractor 自产)。返回 {run_id6: rowdict}。"""
    rows = {}
    with open(path, encoding="utf-8") as f:
        header = None
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#") or not line:
                continue
            parts = line.split("\t")
            if header is None:
                header = parts
                continue
            r = dict(zip(header, parts))
            rows[r["run_id"][9:15]] = r
    return rows


import hashlib


def _sha_full(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    except OSError:
        return None


ann = _load_annotations(ANN) if os.path.exists(ANN) else {}
dirs = {ts: (glob.glob(f"{H}/20260715T{ts}*") or [None])[0] for ts in ann}
if not ann or not all(dirs.values()):
    print("SKIP/UNVERIFIED: 标注缺失或部分历史 run 不在盘,G3 未执行(不计 PASS)(G2 已独立通过)")
else:
    extracted = {}
    for ts, a in ann.items():
        dpath = dirs[ts]
        # 回放前:校验当前输入 hash 与标注绑定一致,不一致则 FAIL(不继续回放)
        cur_tlog = _sha_full(os.path.join(dpath, "sitl", "mav.tlog"))
        cur_cfg = _sha_full(os.path.join(dpath, "run_config.toml"))
        cur_summ = _sha_full(os.path.join(dpath, "summary.json"))
        cur_miss = _sha_full(os.path.join(dpath, "mission_summary.json"))
        hash_ok = (cur_tlog == a["tlog_sha256"] and cur_cfg == a["config_sha256"]
                   and cur_summ == a["summary_sha256"] and cur_miss == a["mission_summary_sha256"])
        ckr(f"{ts} 输入hash与标注一致(否则不回放)", hash_ok)
        if not hash_ok:
            continue
        d = E.extract(dpath)
        extracted[ts] = d
        G3_RAN += 1
        print(f"  --- run {d['run_id']} dir={d['run_dir']} tlog_sha={cur_tlog[:12]}… 标注方法={a['annotation_method'][:28]}… ---")
        # extractor 输出 vs 独立标注(非自产 expected)
        ckr(f"{ts} profile == 标注", d["freeze_ref"]["simulation_profile"] == a["profile"])
        ckr(f"{ts} bin_present == 标注", str(d["outcome"]["bin_present"]).lower() == a["bin_exists"])
        ckr(f"{ts} summary_status == 标注", str(d["outcome"]["status"]) == a["summary_status"])
        ckr(f"{ts} controller_airborne == 标注",
            str(d["outcome"]["airborne"]["mission_controller_airborne_seen"]).lower() == a["controller_airborne_seen"])
        ckr(f"{ts} accel(CRC) == 独立标注计数 {a['target_count']}",
            d["fcu_statustext"]["accels_inconsistent_count"] == int(a["target_count"]))
        ckr(f"{ts} arm_status=UNKNOWN", d["arm_status"] == "UNKNOWN")
        ckr(f"{ts} bad_crc=0", d["fcu_statustext"]["protocol_stats"]["statustext_bad_crc"] == 0)
        ckr(f"{ts} 每结果绑 run_id/dir/hash", bool(d["run_id"] and d["run_dir"] and cur_tlog))
    # 当前样本观察(明确标注为观察,非解析器普适不变量;引用标注计数)
    if extracted:
        accels = {ts: extracted[ts]["fcu_statustext"]["accels_inconsistent_count"] for ts in extracted}
        cfhash = {extracted[ts]["freeze_ref"]["canonical_config_hash"] for ts in extracted}
        print(f"  [观察·非不变量] accel 计数(引用标注)= {accels};默认主线 canonical hash 唯一集大小 = {len(cfhash)}")
        print("  [观察·非不变量] 'accel 非成败判别器'与'no-BIN<有BIN'仅为当前 5 样本观察,不作解析器普适断言")

print("================================")
print(f"G2 单元: FAIL={G2_FAIL}")
print(f"G3 回放: RAN={G3_RAN} FAIL={G3_FAIL}" + ("" if G3_RAN else " (SKIP/UNVERIFIED)"))
sys.exit(1 if (G2_FAIL or G3_FAIL) else 0)
