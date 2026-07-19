#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 AA-PF-03 · 双基线 A/A 判读契约(schema + validator;实验前锁死分母与因果规则)。

只提供 schema/validator/fixture/dry-run 能力;不生成任何真实 A/A 结果。
基线红线:HISTORICAL_REPRODUCTION(eab0cc6)与 FUTURE_CANDIDATE(750032a)
永不合并统计;现场 SHA 不符=失败关闭,禁止自动改写配置。"""

BASELINE_CLASSES = {
    "HISTORICAL_REPRODUCTION": {
        "world_model_commit": "eab0cc6f0d5460cbd2cf20fe9b83857549a1e6b5",
        "purpose": "历史 OPEN-1/E1 复现",
        "known_baseline_defects": ["B23"],   # runner 探针完即掐 mission(该基线自带)
        "note": "不得与未来材料合并统计",
    },
    "FUTURE_CANDIDATE": {
        "world_model_commit": "750032a3aad8b62b0c8ef2b00f740ee125fdb382",
        "purpose": "B23/B22/OPEN-2 修复后的候选材料",
        "known_baseline_defects": [],
        "note": "仅 fixture/单测层;未经真实仿真不得称'已验证新基线'",
    },
}

TELEMETRY_MODES = ("OFF", "ON")

B23_CLASSES = ("COMMON_BASELINE_DEFECT", "ON_ONLY_DIVERGENCE", "OFF_ONLY_DIVERGENCE",
               "TIMING_DIVERGENCE_REQUIRES_CAUSAL_REVIEW", "NO_B23_SIGNATURE", "INELIGIBLE")

PAIR_FROZEN_FIELDS = ("main_commit", "world_model_commit", "baseline_class",
                      "image_digests", "config_hash", "task_id", "map_id",
                      "timeout_sec", "ros_domain_id", "container_identity_source")

PAIR_SCHEMA_FIELDS = ("pair_id", "baseline_class", "main_commit", "world_model_commit",
                      "telemetry_mode", "image_digests", "config_hash", "ros_domain_id",
                      "container_identity", "known_baseline_defects", "b23_signature",
                      "b23_timing", "freeze_match", "evidence_state",
                      "comparison_eligibility", "exclusion_reasons")

# B23 时序判读阈值:当前无独立依据 → UNKNOWN(禁止事后看结果定阈;须人工因果复核)
B23_TIMING_THRESHOLD_SEC = "UNKNOWN"


class PairContractError(ValueError):
    pass


def validate_baseline(world_model_commit, declared_class):
    """现场 SHA 与声明基线类不符 → 失败关闭(禁止自动改写)。"""
    cls = BASELINE_CLASSES.get(declared_class)
    if cls is None:
        raise PairContractError(f"未知 baseline_class: {declared_class!r}")
    want = cls["world_model_commit"]
    if world_model_commit != want:
        raise PairContractError(
            f"现场 wm SHA 与 baseline_class 不符: {declared_class} 要求 {want[:12]},"
            f"实得 {str(world_model_commit)[:12]}(失败关闭,禁止改写配置)")
    return dict(cls)


def _need(run, key):
    v = run.get(key)
    if v in (None, "", []):
        raise PairContractError(f"run {run.get('run_id', '?')} 缺 {key}")
    return v


def validate_pair(off_run, on_run):
    """A/A 配对:全部冻结字段一致 + 唯一差异=telemetry OFF/ON + 证据 COMPLETE。
    任一不满足 → comparison_eligibility=false + exclusion reason(不进分母)。"""
    reasons = []
    for run, expect_mode in ((off_run, "OFF"), (on_run, "ON")):
        if run.get("telemetry_mode") != expect_mode:
            reasons.append(f"{run.get('run_id')}: telemetry_mode={run.get('telemetry_mode')}"
                           f" 应为 {expect_mode}")
    for f in PAIR_FROZEN_FIELDS:
        a, b = off_run.get(f), on_run.get(f)
        if a in (None, "") or b in (None, ""):
            reasons.append(f"冻结字段缺失: {f}(OFF={a!r} ON={b!r})")
        elif a != b:
            reasons.append(f"冻结字段不一致: {f}(OFF={a!r} ON={b!r})")
    try:
        validate_baseline(off_run.get("world_model_commit"), off_run.get("baseline_class"))
    except PairContractError as e:
        reasons.append(str(e))
    for run in (off_run, on_run):
        ev = run.get("evidence_state")
        if ev != "COMPLETE":
            reasons.append(f"{run.get('run_id')}: evidence={ev}(非 COMPLETE 不入比较)")
    eligible = not reasons
    return {"comparison_eligibility": eligible, "exclusion_reasons": reasons,
            "baseline_class": off_run.get("baseline_class"),
            "pair_id": f"{off_run.get('run_id')}__{on_run.get('run_id')}"}


def classify_b23(off_signature, on_signature, off_timing=None, on_timing=None,
                 evidence_ok=True):
    """B23 签名判读(机器枚举)。阈值无独立依据 → 共同出现一律
    TIMING_DIVERGENCE_REQUIRES_CAUSAL_REVIEW(人工因果复核),不得编造阈值。"""
    if not evidence_ok:
        return {"class": "INELIGIBLE", "reason": "证据不完整"}
    if off_signature and on_signature:
        if B23_TIMING_THRESHOLD_SEC == "UNKNOWN":
            return {"class": "TIMING_DIVERGENCE_REQUIRES_CAUSAL_REVIEW",
                    "reason": "共同 B23 签名;时序阈值无独立依据(UNKNOWN),须人工因果复核",
                    "b23_timing": {"off": off_timing, "on": on_timing,
                                   "threshold": "UNKNOWN"}}
        # (阈值一旦由独立依据确立,在此实现界内判 COMMON_BASELINE_DEFECT)
        return {"class": "COMMON_BASELINE_DEFECT", "reason": "共同签名且时序在预定界内"}
    if on_signature and not off_signature:
        return {"class": "ON_ONLY_DIVERGENCE",
                "reason": "仅 ON 出现 B23 签名:禁止判无扰动通过"}
    if off_signature and not on_signature:
        return {"class": "OFF_ONLY_DIVERGENCE", "reason": "仅 OFF 出现 B23 签名"}
    return {"class": "NO_B23_SIGNATURE", "reason": "两侧均无签名"}


def aggregate_guard(runs):
    """统计合并守卫:跨 baseline_class 合并/未配对凑分母 → 失败关闭。"""
    classes = {r.get("baseline_class") for r in runs}
    if len(classes) > 1:
        raise PairContractError(
            f"禁止跨基线合并统计: {sorted(str(c) for c in classes)}")
    unpaired = [r.get("run_id") for r in runs if not r.get("pair_id")]
    if unpaired:
        raise PairContractError(f"未配对 run 不得入比较分母: {unpaired}")
    ineligible = [r.get("run_id") for r in runs
                  if not r.get("comparison_eligibility", False)]
    if ineligible:
        raise PairContractError(f"不合格 pair 成员不得入分母: {ineligible}")
    return True
