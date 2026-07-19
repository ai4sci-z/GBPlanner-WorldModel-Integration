#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1 · telemetry 契约反例门(E1-01.4 红案 1-10/24/25 + evidence gate + 五层分母)。

expected 来源:WP304 §10 契约(D3/D5/D7 条款)与 Linux /proc 语义;
不由被测函数生成 expected。环境无关,不触 Docker/ROS/仿真。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telemetry_contract as C  # noqa: E402

FAIL = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def rejects(name, fn):
    global FAIL
    try:
        fn()
        print(f"FAIL: {name} expected=ContractError actual=被放行")
        FAIL += 1
    except C.ContractError as e:
        print(f"PASS: {name} expected=ContractError actual=ContractError")
        print(f"    ↳ {e}")
    except Exception as e:  # 其它异常类型不算正确的失败关闭
        print(f"FAIL: {name} expected=ContractError actual={type(e).__name__}: {e}")
        FAIL += 1


IDENT = {"batch_id": "b1", "run_id": "20260715T204428.255001623Z",
         "pid": 1234, "pid_starttime": "5566", "boot_id": "aaaa-bbbb"}
REC = {"schema_version": C.SCHEMA_VERSION, "batch_id": "b1",
       "run_id": "20260715T204428.255001623Z", "utc_ns": 1_800_000_000_000_000_000,
       "mono_ns": 123_456_789, "field": "host.loadavg", "value": {"l1": 0.5}}


def with_run_dir(run_id):
    d = tempfile.mkdtemp()
    p = os.path.join(d, run_id)
    os.makedirs(p, exist_ok=True)
    return p


print("======== E1-01.4 红案 1-9:身份/记录 schema 失败关闭 ========")
run_dir = with_run_dir(IDENT["run_id"])
C.validate_writer_identity(dict(IDENT), run_dir)  # 合法基准必须通过
print("PASS: 合法身份基准通过")
i = dict(IDENT); i.pop("batch_id")
rejects("红案1 缺 batch_id", lambda: C.validate_writer_identity(i, run_dir))
i2 = dict(IDENT); i2["batch_id"] = ""
rejects("红案1b 空 batch_id", lambda: C.validate_writer_identity(i2, run_dir))
i3 = dict(IDENT); i3.pop("run_id")
rejects("红案2 缺 run_id", lambda: C.validate_writer_identity(i3, run_dir))
i4 = dict(IDENT); i4["run_id"] = "OTHER_RUN"
rejects("红案3 run_id≠run 目录基名", lambda: C.validate_writer_identity(i4, run_dir))
ck("红案4 PID 相同 starttime 不同 ≠ 同一 writer",
   C.identity_matches(IDENT, {**IDENT, "pid_starttime": "9999"}), False)
ck("红案4b 同 PID 同 starttime 同 boot = 同一 writer",
   C.identity_matches(IDENT, dict(IDENT)), True)
i5 = dict(IDENT); i5.pop("boot_id")
rejects("红案5 缺 boot_id", lambda: C.validate_writer_identity(i5, run_dir))
r = dict(REC); r.pop("utc_ns")
rejects("红案6 缺 UTC 时间戳", lambda: C.validate_record(r))
r = dict(REC); r.pop("mono_ns")
rejects("红案7 缺 monotonic 时间戳", lambda: C.validate_record(r))
r = dict(REC); r["schema_version"] = "unknown.v9"
rejects("红案8 未知 schema_version", lambda: C.validate_record(r))
rejects("红案9 未知 required/optional(未登记字段)",
        lambda: C.requirement_of("mystery.field"))
r = dict(REC); r["utc_ns"] = -1
rejects("红案6b 非正 UTC", lambda: C.validate_record(r))

print("======== E1-01.4 红案10 + evidence gate(D5-08/09,D7)========")
# required 缺失仍判 COMPLETE 必须被拒:gate 必须 INCOMPLETE
g = C.evidence_gate({"host.loadavg": "MISSING"}, business_ok=True)
ck("红案10 required 缺失 → INCOMPLETE(非 COMPLETE)", g["status"], C.GATE_INCOMPLETE)
ck("红案10b required 缺失 → acceptance_eligible=False", g["acceptance_eligible"], False)
g = C.evidence_gate({"host.loadavg": "CORRUPT"}, business_ok=True)
ck("gate required 损坏 → CORRUPT", g["status"], C.GATE_CORRUPT)
g = C.evidence_gate({"host.cpu_freq": "UNAVAILABLE"}, business_ok=True)
ck("gate optional 不可得 → COMPLETE + gap 登记", g["status"], C.GATE_COMPLETE)
ck("gate optional gap 登记", g["optional_gaps"], ["host.cpu_freq"])
g = C.evidence_gate({}, business_ok=False)
ck("业务失败 ∧ 证据全齐 → 不可验收(业务≠证据)", g["acceptance_eligible"], False)
# full_pass 兼容字段不得单独开门
g = C.evidence_gate({"host.loadavg": "MISSING"}, business_ok=True, full_pass=True)
ck("full_pass=True 不得单独打开验收门", g["acceptance_eligible"], False)

print("======== E1-01.4 红案24/25:UNAVAILABLE/airborne 语义 ========")
ck("红案24 no-BIN 时 EKF 派生必须 UNAVAILABLE(禁伪造正常)",
   C.derive_bin_dependent(bin_present=False, decoded={"ekf": "OK"}), C.UNAVAILABLE)
ck("红案24b BIN 在时按解码结果", C.derive_bin_dependent(True, {"ekf": "OK"}), {"ekf": "OK"})
ck("红案25 controller 未观察到 airborne = not_observed(非'FCU 确定未离地')",
   C.airborne_semantics(False), "not_observed_by_controller")
ck("红案25b UNKNOWN 不压成 false", C.airborne_semantics(None), "UNKNOWN")
ck("红案25c 观察到 airborne", C.airborne_semantics(True), "observed_airborne")

print("======== 五层分母(D7-13..15;E1-04.3 反例 1-9)========")
RUNS = ["r1", "r2", "r3", "r4", "r5"]


def layers(launched, infra, causal, airborne, full):
    def lay(ids, parent):
        return {"count": len(ids), "run_ids": list(ids),
                "exclusion_reasons": {x: "登记原因" for x in parent if x not in ids}}
    return {"launched": lay(launched, launched),
            "infrastructure_valid": lay(infra, launched),
            "causal_analysis_eligible": lay(causal, infra),
            "airborne": lay(airborne, causal),
            "full_pass": lay(full, airborne)}


ok_layers = layers(RUNS, RUNS[:4], RUNS[:3], RUNS[:2], RUNS[:1])
C.validate_five_layers(RUNS, ok_layers, corrupt_runs=set())
print("PASS: 五层 5/4/3/2/1 合法基准通过")
bad = layers(RUNS, RUNS[:4] + ["ghost"], RUNS[:3], RUNS[:2], RUNS[:1])
rejects("五层2 infrastructure 含 launched 外 run_id",
        lambda: C.validate_five_layers(RUNS, bad, corrupt_runs=set()))
rejects("五层3 causal 含 CORRUPT run",
        lambda: C.validate_five_layers(RUNS, ok_layers, corrupt_runs={"r3"}))
bad = layers(RUNS, RUNS[:4], RUNS[:3], RUNS[:2], ["r5"])
rejects("五层4 full_pass 不属于 airborne",
        lambda: C.validate_five_layers(RUNS, bad, corrupt_runs=set()))
# 五层5:删除失败 attempt 使成功率变高 → launched 必须与权威 attempt 集合相等
shrunk = layers(RUNS[:4], RUNS[:4], RUNS[:3], RUNS[:2], RUNS[:1])
rejects("五层5 删除失败 attempt(launched≠权威 attempts)",
        lambda: C.validate_five_layers(RUNS, shrunk, corrupt_runs=set()))
# 五层6:infrastructure 失败仍留在 launched(排除必须有登记原因)
noreason = layers(RUNS, RUNS[:4], RUNS[:3], RUNS[:2], RUNS[:1])
noreason["infrastructure_valid"]["exclusion_reasons"] = {}
rejects("五层6 被排除 run 无 exclusion reason",
        lambda: C.validate_five_layers(RUNS, noreason, corrupt_runs=set()))
dup = layers(RUNS, RUNS[:4], RUNS[:3], RUNS[:2], RUNS[:1])
dup["launched"]["run_ids"] = RUNS + ["r1"]
dup["launched"]["count"] = 6
rejects("五层9 同一 run 重复计数",
        lambda: C.validate_five_layers(RUNS + ["r1"], dup, corrupt_runs=set()))
mis = layers(RUNS, RUNS[:4], RUNS[:3], RUNS[:2], RUNS[:1])
mis["airborne"]["count"] = 99
rejects("五层附 count≠len(run_ids)",
        lambda: C.validate_five_layers(RUNS, mis, corrupt_runs=set()))

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
