#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 AA-PF-03 · 双基线 A/A 配对契约门(03.5 十五案)。

expected 来源=03.2/03.3 规则文本;不生成任何真实 A/A 结果。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aa_pair_contract as P  # noqa: E402

FAIL = 0
EAB = "eab0cc6f0d5460cbd2cf20fe9b83857549a1e6b5"
NEW = "6d412a11f152428b5e08e42e66c1583d4dce4219"


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
        print(f"FAIL: {name} expected=PairContractError actual=被放行")
        FAIL += 1
    except P.PairContractError as e:
        print(f"PASS: {name}")
        print(f"    ↳ {e}")


def run(mode, **kw):
    base = {"run_id": f"r_{mode}_{kw.get('n', 0)}", "baseline_class": "HISTORICAL_REPRODUCTION",
            "main_commit": "m1", "world_model_commit": EAB, "telemetry_mode": mode,
            "image_digests": "sha256:img", "config_hash": "cafe", "task_id": "hover",
            "map_id": "iris_maze", "timeout_sec": 1500, "ros_domain_id": "7",
            "container_identity_source": "summary.json#service_handles",
            "evidence_state": "COMPLETE"}
    base.update(kw)
    return base


print("======== 基线分类(03.1)========")
ck("HISTORICAL=eab0cc6 且带 B23", P.validate_baseline(EAB, "HISTORICAL_REPRODUCTION")["known_baseline_defects"], ["B23"])
ck("FUTURE=750032a 无已知基线缺陷", P.validate_baseline(NEW, "FUTURE_CANDIDATE")["known_baseline_defects"], [])
rejects("现场 SHA 不符 → 失败关闭(禁改写)",
        lambda: P.validate_baseline(NEW, "HISTORICAL_REPRODUCTION"))
rejects("未知 baseline_class 拒绝", lambda: P.validate_baseline(EAB, "MYSTERY"))

print("======== 合法配对基准 ========")
v = P.validate_pair(run("OFF"), run("ON", n=1))
ck("合法 OFF/ON 配对合格", v["comparison_eligibility"], True)

print("======== 03.5 反例 1-9:冻结字段 ========")
for field, bad in (("main_commit", "m2"), ("world_model_commit", NEW),
                   ("baseline_class", "FUTURE_CANDIDATE"), ("image_digests", "sha256:other"),
                   ("config_hash", "beef"), ("ros_domain_id", "8"),
                   ("container_identity_source", "docker_ps_guess")):
    v = P.validate_pair(run("OFF"), run("ON", n=1, **{field: bad}))
    ck(f"反例 {field} 不一致 → 不合格", v["comparison_eligibility"], False)
    ck(f"反例 {field} 排除原因在档", any(field in r for r in v["exclusion_reasons"]), True)
v = P.validate_pair(run("OFF", baseline_class=None), run("ON", n=1, baseline_class=None))
ck("反例 baseline_class 缺失 → 不合格", v["comparison_eligibility"], False)

print("======== 反例 evidence ========")
v = P.validate_pair(run("OFF", evidence_state="INCOMPLETE"), run("ON", n=1))
ck("evidence INCOMPLETE → 不合格", v["comparison_eligibility"], False)
v = P.validate_pair(run("OFF"), run("ON", n=1, evidence_state="CORRUPT"))
ck("evidence CORRUPT → 不合格", v["comparison_eligibility"], False)

print("======== B23 分类(03.3)========")
ck("ON-only → ON_ONLY_DIVERGENCE(禁判无扰动)",
   P.classify_b23(False, True)["class"], "ON_ONLY_DIVERGENCE")
ck("OFF-only → OFF_ONLY_DIVERGENCE",
   P.classify_b23(True, False)["class"], "OFF_ONLY_DIVERGENCE")
ck("双侧无 → NO_B23_SIGNATURE", P.classify_b23(False, False)["class"], "NO_B23_SIGNATURE")
r = P.classify_b23(True, True, off_timing=12.0, on_timing=14.0)
ck("共同签名+阈值无独立依据 → REQUIRES_CAUSAL_REVIEW(不编阈值)",
   r["class"], "TIMING_DIVERGENCE_REQUIRES_CAUSAL_REVIEW")
ck("阈值字段=UNKNOWN", r["b23_timing"]["threshold"], "UNKNOWN")
ck("证据不完整 → INELIGIBLE", P.classify_b23(True, True, evidence_ok=False)["class"], "INELIGIBLE")

print("======== 合并守卫(禁跨基线/未配对凑分母)========")
h = run("OFF"); h["pair_id"] = "p1"; h["comparison_eligibility"] = True
f = run("ON", n=1, baseline_class="FUTURE_CANDIDATE", world_model_commit=NEW)
f["pair_id"] = "p2"; f["comparison_eligibility"] = True
rejects("历史与未来样本合并 → 拒绝", lambda: P.aggregate_guard([h, f]))
u = run("ON", n=2); u["comparison_eligibility"] = True   # 无 pair_id
rejects("未配对 run 凑分母 → 拒绝", lambda: P.aggregate_guard([h, u]))
bad = run("ON", n=3); bad["pair_id"] = "p1"; bad["comparison_eligibility"] = False
rejects("不合格成员入分母 → 拒绝", lambda: P.aggregate_guard([h, bad]))
h2 = run("ON", n=1); h2["pair_id"] = "p1"; h2["comparison_eligibility"] = True
ck("同基线合格配对 → 放行", P.aggregate_guard([h, h2]), True)

print("======== schema 字段齐全(03.4)========")
missing = [f for f in P.PAIR_SCHEMA_FIELDS if f not in
           {"pair_id", "baseline_class", "main_commit", "world_model_commit",
            "telemetry_mode", "image_digests", "config_hash", "ros_domain_id",
            "container_identity", "known_baseline_defects", "b23_signature",
            "b23_timing", "freeze_match", "evidence_state",
            "comparison_eligibility", "exclusion_reasons"}]
ck("最小机器字段 16 项全在 schema", missing, [])

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
