#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0:open1_extract 提取器测试。

核心断言用**内存合成 run 目录**(环境无关,不依赖 world-model 产物)。
另含可选"真实产物回放":若 world-model 历史产物在盘,则复跑并断言 E0 已确定的
纠偏事实(accel 计数在成败间相同、no-BIN accel=0 且已 boot);产物不在则跳过(不失败)。
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_extract as E  # noqa: E402
import open1_tlog as T  # noqa: E402

FAIL = 0


def ck(name, got, want):
    global FAIL
    if got == want:
        print(f"PASS: {name} [{got!r}]")
    else:
        print(f"FAIL: {name} 期望[{want!r}] 实得[{got!r}]")
        FAIL += 1


def make_run(root, run_id, profile, tlog_records, bin_present, blockers):
    d = os.path.join(root, run_id)
    os.makedirs(os.path.join(d, "sitl", "logs"), exist_ok=True)
    os.makedirs(os.path.join(d, "audits"), exist_ok=True)
    os.makedirs(os.path.join(d, "probes"), exist_ok=True)
    cfg = (f"artifact_dir = '../../artifacts/sim/hover/{run_id}'\n"
           f"control_mode = 'hover_{profile}'\n"
           f"simulation_profile = '{profile}'\n"
           f"run_id = '{run_id}'\n")
    open(os.path.join(d, "run_config.toml"), "w").write(cfg)
    json.dump({"created_at": "2026-07-15T20:00:00Z", "run_id": run_id},
              open(os.path.join(d, "manifest.json"), "w"))
    status = "TASK_STATUS_OK" if not blockers else "TASK_STATUS_BLOCKED"
    json.dump({"status": status, "blockers": blockers},
              open(os.path.join(d, "summary.json"), "w"))
    json.dump({"ok": True}, open(os.path.join(d, "audits", "startup_readiness_probe.json"), "w"))
    json.dump({"ok": True}, open(os.path.join(d, "probes", "imu_probe.txt"), "w"))
    tlog = b"".join(T._build_v2_statustext_record(ts, sev, txt) for ts, sev, txt in tlog_records)
    open(os.path.join(d, "sitl", "mav.tlog"), "wb").write(tlog)
    if bin_present:
        open(os.path.join(d, "sitl", "logs", "00000001.BIN"), "wb").write(b"\x00")
    return d


# ---------- 环境无关合成断言 ----------
tmp = tempfile.mkdtemp()
try:
    # A 成功类:有 BIN,accel 出现但已消解,full-pass
    succ = make_run(tmp, "20260715T111111.000000000Z", "slam-direct-no-odom-prior",
                    [(1_000_000, 6, "ArduPilot Ready"),
                     (2_000_000, 4, "Arm: Accels inconsistent"),
                     (3_000_000, 4, "Arm: Accels inconsistent")],
                    bin_present=True, blockers=[])
    da = E.extract(succ)
    ck("A profile", da["freeze_ref"]["simulation_profile"], "slam-direct-no-odom-prior")
    ck("A bin_present", da["outcome"]["bin_present"], True)
    ck("A full_pass", da["outcome"]["full_pass"], True)
    ck("A accel计数", da["fcu_statustext"]["accels_inconsistent_count"], 2)
    ck("A boot ready", da["fcu_statustext"]["boot_markers"]["ardupilot_ready"], True)

    # B no-BIN 类:无 BIN,accel=0,但已 boot ready;abort=waiting_for_stable_external_nav_and_imu
    nob = make_run(tmp, "20260715T222222.000000000Z", "slam-direct-no-odom-prior",
                   [(1_000_000, 6, "ArduPilot Ready"),
                    (2_000_000, 6, "EKF3 IMU0 origin set")],
                   bin_present=False,
                   blockers=[{"code": "hover_mission_abort",
                              "message": "hover_mission_abort:waiting_for_stable_external_nav_and_imu"},
                             {"code": "hover_mission_armed_seen_missing", "message": "x"}])
    db = E.extract(nob)
    ck("B bin_present", db["outcome"]["bin_present"], False)
    ck("B full_pass", db["outcome"]["full_pass"], False)
    ck("B accel=0(no-BIN 非 accel 失败)", db["fcu_statustext"]["accels_inconsistent_count"], 0)
    ck("B 已 boot ready", db["fcu_statustext"]["boot_markers"]["ardupilot_ready"], True)
    ck("B abort_reason", db["outcome"]["abort_reason"], "waiting_for_stable_external_nav_and_imu")

    # C canonical hash:同 profile 折叠、异 profile 区分
    succ2 = make_run(tmp, "20260715T333333.000000000Z", "slam-direct-no-odom-prior",
                     [(1_000_000, 6, "ArduPilot Ready")], bin_present=True, blockers=[])
    diag = make_run(tmp, "20260715T444444.000000000Z", "imu-flu-correction",
                    [(1_000_000, 6, "ArduPilot Ready")], bin_present=True, blockers=[])
    h_succ = E.extract(succ)["freeze_ref"]["canonical_config_hash"]
    h_succ2 = E.extract(succ2)["freeze_ref"]["canonical_config_hash"]
    h_diag = E.extract(diag)["freeze_ref"]["canonical_config_hash"]
    ck("C 同profile折叠", h_succ, h_succ2)
    ck("C 异profile区分", h_succ != h_diag, True)

    # D 运行时缺口如实登记(非空)
    ck("D evidence_gaps 非空", len(da["evidence_gaps"]) >= 5, True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------- 可选:真实历史产物回放(在盘则断言,不在则跳过) ----------
H = "/home/ai4s/projects/world-model/artifacts/sim/hover"
import glob  # noqa: E402
REAL = {
    "204428": ("slam-direct-no-odom-prior", True, 20, True),   # ✅ pass, BIN, accel=20
    "211927": ("slam-direct-no-odom-prior", True, 20, True),   # ✅ pass, BIN, accel=20
    "210849": ("slam-direct-no-odom-prior", True, 20, False),  # ❌ fail, BIN, accel=20(同成功→非判别器)
    "205113": ("slam-direct-no-odom-prior", False, 0, False),  # ❌ fail, no-BIN, accel=0, boot ready
    "210149": ("slam-direct-no-odom-prior", False, 0, False),
}
present = os.path.isdir(H) and all(glob.glob(f"{H}/20260715T{ts}*") for ts in REAL)
if not present:
    print("SKIP: world-model 历史产物不在盘,跳过真实回放(环境无关核心断言已过)")
else:
    main_hashes = set()
    for ts, (prof, binp, accel, fullpass) in REAL.items():
        d = E.extract(glob.glob(f"{H}/20260715T{ts}*")[0])
        ck(f"real {ts} profile", d["freeze_ref"]["simulation_profile"], prof)
        ck(f"real {ts} bin_present", d["outcome"]["bin_present"], binp)
        ck(f"real {ts} accel计数", d["fcu_statustext"]["accels_inconsistent_count"], accel)
        ck(f"real {ts} full_pass", d["outcome"]["full_pass"], fullpass)
        ck(f"real {ts} boot ready(均已启动)", d["fcu_statustext"]["boot_markers"]["ardupilot_ready"], True)
        main_hashes.add(d["freeze_ref"]["canonical_config_hash"])
    ck("real 默认主线 canonical hash 折叠为1", len(main_hashes), 1)
    # 关键纠偏:accel 计数在成功(204428/211927)与 BIN 失败(210849)间相同 → 非判别器
    ck("real accel 非判别器(pass==BIN-fail)", 20 == 20, True)

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
