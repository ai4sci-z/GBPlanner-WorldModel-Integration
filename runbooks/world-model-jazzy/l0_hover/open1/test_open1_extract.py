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

# --- airborne 仅正证据 ---
ck("airborne True(正证据)", E.airborne_verdict({"airborne_seen": True}), True)
ck("airborne False(明确未起飞/pre-arm 失败)", E.airborne_verdict({"airborne_seen": False}), False)
ck("airborne 缺字段→UNKNOWN", E.airborne_verdict({"other": 1}), None)
ck("airborne 无 mission_summary→UNKNOWN", E.airborne_verdict(None), None)
ck("airborne 旧版summary(无字段)→UNKNOWN", E.airborne_verdict({"status": "ok"}), None)
# 不得从"无 airborne_seen_missing blocker"反推起飞:airborne_verdict 根本不看 blocker
ck("airborne 不看blocker(空dict)→UNKNOWN", E.airborne_verdict({}), None)

# --- canonical_config_hash 等价/不等价(真实嵌套表结构:[inputs]/[run]/[outputs]) ---
base = ("[inputs]\n"
        "simulation_profile = 'slam-direct-no-odom-prior'\n"
        "control_mode = 'hover_slam-direct-no-odom-prior'\n"
        "[run]\n"
        "run_id = 'R1'\n"
        "artifact_dir = '/a/R1'\n"
        "duration_sec = 1500\n"
        "note = 'keep'\n"
        "[outputs]\n"
        "manifest = '/a/R1/manifest.json'\n")
# 表序 + 键序 + 空白 + 单双引号变化 → 同 hash
equiv = ("[run]\n"
         'duration_sec=1500\n'
         "run_id = 'R1'\n"
         'note   =   "keep"\n'
         "artifact_dir = '/a/R1'\n"
         "[outputs]\n"
         'manifest = "/a/R1/manifest.json"\n'
         "[inputs]\n"
         'control_mode = "hover_slam-direct-no-odom-prior"\n'
         "simulation_profile = 'slam-direct-no-odom-prior'\n")
ck("canon 表序/键序/空白/引号 等价", E.canonical_config_hash(base), E.canonical_config_hash(equiv))
# run.run_id + run.artifact_dir + [outputs] 变化(易变字段)→ 同 hash
diff_runid = base.replace("R1", "R2")
ck("canon 仅run_id/路径变→同hash", E.canonical_config_hash(base), E.canonical_config_hash(diff_runid))
# 语义变化(inputs.simulation_profile)→ 不同 hash
diff_sem = base.replace("slam-direct-no-odom-prior", "imu-flu-correction")
ck("canon 语义变→不同hash", E.canonical_config_hash(base) != E.canonical_config_hash(diff_sem), True)
# run_id 出现在语义值(run.note)中不被"全局替换":改 run_id 不应改 note
a = base.replace("note = 'keep'", "note = 'tag-R1'")
b = a.replace("run_id = 'R1'", "run_id = 'R2'").replace("artifact_dir = '/a/R1'", "artifact_dir = '/a/R2'")
ck("canon run_id子串在语义值中不被误替换(a==b)", E.canonical_config_hash(a), E.canonical_config_hash(b))
c = base.replace("note = 'keep'", "note = 'tag-R2'")
ck("canon 语义note不同→不同hash", E.canonical_config_hash(a) != E.canonical_config_hash(c), True)
# 解析失败 → None(fail-closed)
ck("canon 非法TOML→None", E.canonical_config_hash("this is = = not toml ]["), None)

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
    ck("无mission_summary→airborne UNKNOWN", ex["outcome"]["airborne"], None)
    ck("空tlog→accel 0 且不误报", ex["fcu_statustext"]["accels_inconsistent_count"], 0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("======== G3 历史回放门(五个指定 run;不在盘则 SKIP/UNVERIFIED) ========")
H = "/home/ai4s/projects/world-model/artifacts/sim/hover"
# 期望值 = 现场观测事实(profile, bin, accel(CRC后), airborne, full_pass)
EXPECT = {
    "204428": dict(profile="slam-direct-no-odom-prior", bin=True, accel=20, airborne=True, full_pass=True),
    "211927": dict(profile="slam-direct-no-odom-prior", bin=True, accel=20, airborne=True, full_pass=True),
    "210849": dict(profile="slam-direct-no-odom-prior", bin=True, accel=20, airborne=False, full_pass=False),
    "205113": dict(profile="slam-direct-no-odom-prior", bin=False, accel=0, airborne=False, full_pass=False),
    "210149": dict(profile="slam-direct-no-odom-prior", bin=False, accel=0, airborne=False, full_pass=False),
}
dirs = {ts: (glob.glob(f"{H}/20260715T{ts}*") or [None])[0] for ts in EXPECT}
if not all(dirs.values()):
    print("SKIP/UNVERIFIED: 部分历史 run 不在盘,G3 未执行(G2 已独立通过)")
else:
    extracted = {}
    for ts, exp in EXPECT.items():
        d = E.extract(dirs[ts])
        extracted[ts] = d
        G3_RAN += 1
        ih = d["input_hashes"]["mav.tlog"]
        print(f"  --- run {d['run_id']} dir={d['run_dir']} tlog_sha={ih[:12] if ih else None} ---")
        ckr(f"{ts} profile={exp['profile']}", d["freeze_ref"]["simulation_profile"] == exp["profile"])
        ckr(f"{ts} bin_present={exp['bin']}", d["outcome"]["bin_present"] == exp["bin"])
        ckr(f"{ts} accel(CRC后)={exp['accel']}", d["fcu_statustext"]["accels_inconsistent_count"] == exp["accel"])
        ckr(f"{ts} airborne(正证据)={exp['airborne']}", d["outcome"]["airborne"] == exp["airborne"])
        ckr(f"{ts} full_pass={exp['full_pass']}", d["outcome"]["full_pass"] == exp["full_pass"])
        ckr(f"{ts} arm_status=UNKNOWN", d["arm_status"] == "UNKNOWN")
        ckr(f"{ts} bad_crc=0", d["fcu_statustext"]["protocol_stats"]["statustext_bad_crc"] == 0)
        ckr(f"{ts} 每结果绑 run_id/dir/hash", bool(d["run_id"] and d["run_dir"] and ih))
    # 关系断言引用**实际提取值**(非恒真):accel 计数在成功与 BIN-present 失败间相同 → 非判别器
    a204 = extracted["204428"]["fcu_statustext"]["accels_inconsistent_count"]
    a211 = extracted["211927"]["fcu_statustext"]["accels_inconsistent_count"]
    a210 = extracted["210849"]["fcu_statustext"]["accels_inconsistent_count"]
    n205 = extracted["205113"]["fcu_statustext"]["accels_inconsistent_count"]
    n210 = extracted["210149"]["fcu_statustext"]["accels_inconsistent_count"]
    ckr("accel 计数:两成功==BIN失败(引用实际值,非判别器)", a204 == a211 == a210)
    ckr("accel 计数:两 no-BIN 均为 0(引用实际值)", n205 == n210 == 0)
    ckr("no-BIN accel 严格小于 有BIN(引用实际值)", n205 < a210)
    # canonical hash:五个默认主线 run 折叠为 1(引用实际提取值)
    hashes = {extracted[ts]["freeze_ref"]["canonical_config_hash"] for ts in EXPECT}
    ckr("五默认主线 canonical hash 折叠为1", len(hashes) == 1)

print("================================")
print(f"G2 单元: FAIL={G2_FAIL}")
print(f"G3 回放: RAN={G3_RAN} FAIL={G3_FAIL}" + ("" if G3_RAN else " (SKIP/UNVERIFIED)"))
sys.exit(1 if (G2_FAIL or G3_FAIL) else 0)
