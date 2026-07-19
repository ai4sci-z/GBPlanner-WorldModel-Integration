#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1 · telemetry 契约(schema/枚举/身份/evidence gate/五层分母)。

契约源 = WP304 §10(D3 字段 22 属性模板、D4 观测集合、D5 旁路契约、D7 五层分母)。
本模块只做验证与判定,零 I/O、零副作用;采集与落盘在 telemetry_sidecar.py。
"""

SCHEMA_VERSION = "wp304.telemetry.v1"

REQUIRED = "required"
OPTIONAL = "optional"

GATE_COMPLETE = "COMPLETE"
GATE_INCOMPLETE = "INCOMPLETE"
GATE_CORRUPT = "CORRUPT"
UNAVAILABLE = "UNAVAILABLE"

# 输入状态(evidence_gate 的入参枚举)
_ARTIFACT_STATES = ("PRESENT_VALID", "MISSING", "CORRUPT", "UNAVAILABLE")

LAYERS = ("launched", "infrastructure_valid", "causal_analysis_eligible",
          "airborne", "full_pass")


class ContractError(ValueError):
    """契约违规:一律失败关闭,不静默降级。"""


# ---- D4 观测集合:字段契约表(required/optional、节奏上限、落盘相对路径)----
FIELD_CONTRACTS = {
    "host.loadavg":   {"source": "/proc/loadavg",   "unit": "load",    "cadence_hz_max": 1.0,
                       "requirement": REQUIRED, "artifact_rel": "telemetry/host.jsonl",
                       "missing_policy": GATE_INCOMPLETE},
    "host.cpu_pct":   {"source": "/proc/stat",      "unit": "percent", "cadence_hz_max": 1.0,
                       "requirement": REQUIRED, "artifact_rel": "telemetry/host.jsonl",
                       "missing_policy": GATE_INCOMPLETE},
    "host.cpu_freq":  {"source": "sysfs cpufreq",   "unit": "kHz",     "cadence_hz_max": 1.0,
                       "requirement": OPTIONAL, "artifact_rel": "telemetry/host.jsonl",
                       "missing_policy": UNAVAILABLE},
    "host.mem":       {"source": "/proc/meminfo",   "unit": "kB",      "cadence_hz_max": 1.0,
                       "requirement": REQUIRED, "artifact_rel": "telemetry/host.jsonl",
                       "missing_policy": GATE_INCOMPLETE},
    "host.io":        {"source": "/proc/diskstats", "unit": "sectors", "cadence_hz_max": 1.0,
                       "requirement": OPTIONAL, "artifact_rel": "telemetry/host.jsonl",
                       "missing_policy": UNAVAILABLE},
    "sitl.proc":      {"source": "docker top",      "unit": "proc",    "cadence_hz_max": 2.0,
                       "requirement": REQUIRED, "artifact_rel": "telemetry/sitl_proc.jsonl",
                       "missing_policy": GATE_INCOMPLETE},
    "sitl.console":   {"source": "docker logs",     "unit": "text",    "cadence_hz_max": 0.0,
                       "requirement": REQUIRED, "artifact_rel": "telemetry/sitl_console.log",
                       "missing_policy": GATE_INCOMPLETE},
    "official_baseline_container_exit_code":
                      {"source": "docker wait",     "unit": "rc",      "cadence_hz_max": 0.0,
                       "requirement": REQUIRED,
                       "artifact_rel": "telemetry/official_baseline_container_exit.json",
                       "missing_policy": GATE_INCOMPLETE},
    "readiness":      {"source": "ros subscribe",   "unit": "status",  "cadence_hz_max": 2.0,
                       "requirement": REQUIRED, "artifact_rel": "telemetry/readiness.jsonl",
                       "missing_policy": GATE_INCOMPLETE},
    "extnav":         {"source": "ros subscribe",   "unit": "status",  "cadence_hz_max": 2.0,
                       "requirement": REQUIRED, "artifact_rel": "telemetry/extnav.jsonl",
                       "missing_policy": GATE_INCOMPLETE},
    "freeze":         {"source": "git/docker inspect/E0 canonical hash", "unit": "identity",
                       "cadence_hz_max": 0.0, "requirement": REQUIRED,
                       "artifact_rel": "telemetry/freeze.json",
                       "missing_policy": GATE_INCOMPLETE},
}

_IDENT_KEYS = ("batch_id", "run_id", "pid", "pid_starttime", "boot_id")


def _need_str(d, key, what):
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ContractError(f"{what} 缺失或为空: {key}")
    return v


def validate_writer_identity(ident, run_dir):
    """writer 身份:batch_id/run_id/pid/pid_starttime/boot_id 全必填;
    run_id 必须等于 run 目录基名(路径与身份绑死,防串写)。"""
    import os
    for k in _IDENT_KEYS:
        if k not in ident:
            raise ContractError(f"writer 身份缺字段: {k}")
    _need_str(ident, "batch_id", "writer 身份")
    run_id = _need_str(ident, "run_id", "writer 身份")
    if not isinstance(ident["pid"], int) or ident["pid"] <= 0:
        raise ContractError("writer pid 必须为正整数")
    _need_str(ident, "pid_starttime", "writer 身份")
    _need_str(ident, "boot_id", "writer 身份")
    base = os.path.basename(os.path.normpath(run_dir))
    if run_id != base:
        raise ContractError(f"run_id 与 run 目录基名不一致: {run_id} != {base}")
    return True


def identity_matches(a, b):
    """同一 writer = pid ∧ pid_starttime ∧ boot_id ∧ batch_id ∧ run_id 全同。
    PID 复用(同 pid 不同 starttime)≠ 同一 writer。"""
    return all(a.get(k) == b.get(k) for k in _IDENT_KEYS)


def validate_record(recd):
    """每条 telemetry 记录:schema_version 已知、身份、双时间戳、字段登记在契约表。"""
    if recd.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"未知 schema_version: {recd.get('schema_version')!r}"
                            f"(期望 {SCHEMA_VERSION})")
    _need_str(recd, "batch_id", "record")
    _need_str(recd, "run_id", "record")
    utc = recd.get("utc_ns")
    if not isinstance(utc, int) or utc <= 0:
        raise ContractError(f"UTC 时间戳缺失或非正: {utc!r}")
    mono = recd.get("mono_ns")
    if not isinstance(mono, int) or mono < 0:
        raise ContractError(f"monotonic 时间戳缺失或非法: {mono!r}")
    field = recd.get("field")
    requirement_of(field)
    return True


def requirement_of(field):
    c = FIELD_CONTRACTS.get(field)
    if c is None:
        raise ContractError(f"字段未登记契约(required/optional 未知): {field!r}")
    return c["requirement"]


def evidence_gate(statuses, business_ok, full_pass=False):
    """D5-08/09:required MISSING→INCOMPLETE;required CORRUPT→CORRUPT(占优);
    optional 不可得→登记 gap 不降门。acceptance_eligible=业务∧证据双确认;
    full_pass 为历史兼容字段,不得单独开门(参数仅为显式证明其无效)。"""
    failed_required = []
    corrupt_required = []
    optional_gaps = []
    for field, state in statuses.items():
        req = requirement_of(field)
        if state not in _ARTIFACT_STATES:
            raise ContractError(f"未知 artifact 状态: {field}={state!r}")
        if req == REQUIRED:
            if state == "MISSING":
                failed_required.append(field)
            elif state == "CORRUPT":
                corrupt_required.append(field)
            elif state == "UNAVAILABLE":
                # required 不允许以 UNAVAILABLE 逃逸:等同缺失
                failed_required.append(field)
        else:
            if state in ("MISSING", "UNAVAILABLE", "CORRUPT"):
                optional_gaps.append(field)
    if corrupt_required:
        status = GATE_CORRUPT
    elif failed_required:
        status = GATE_INCOMPLETE
    else:
        status = GATE_COMPLETE
    acceptance = bool(business_ok) and status == GATE_COMPLETE
    return {"status": status,
            "failed_required": sorted(failed_required + corrupt_required),
            "optional_gaps": sorted(optional_gaps),
            "acceptance_eligible": acceptance,
            "full_pass_compat_ignored": bool(full_pass)}


def derive_bin_dependent(bin_present, decoded):
    """D4-18/19:EKF/INS 只能来自 BIN;no-BIN 时必须 UNAVAILABLE,禁止伪造正常。"""
    if not bin_present:
        return UNAVAILABLE
    return decoded


def airborne_semantics(controller_airborne):
    """D2-13/红案25:controller 侧 airborne 是观察证据,不是 FCU 全知真值。
    False=控制器未观察到(≠FCU 确定未离地);None=UNKNOWN,不得压成 false。"""
    if controller_airborne is True:
        return "observed_airborne"
    if controller_airborne is False:
        return "not_observed_by_controller"
    return "UNKNOWN"


def _layer_set(layers, name):
    lay = layers.get(name)
    if not isinstance(lay, dict):
        raise ContractError(f"缺分母层: {name}")
    ids = lay.get("run_ids")
    cnt = lay.get("count")
    if not isinstance(ids, list):
        raise ContractError(f"{name}.run_ids 必须为列表")
    if len(ids) != len(set(ids)):
        raise ContractError(f"{name} 同一 run 重复计数: {sorted(ids)}")
    if cnt != len(ids):
        raise ContractError(f"{name}.count({cnt}) != len(run_ids)({len(ids)})")
    return set(ids)


def validate_five_layers(attempts, layers, corrupt_runs):
    """D7-13..15 五层并列分母:
    launched ⊇ infrastructure_valid ⊇ causal_analysis_eligible ⊇ airborne ⊇ full_pass;
    launched 必须恰等于权威 attempt 集合(发起过的 attempt 永不消失);
    causal 层不得含 CORRUPT run;逐层排除必须逐 run 登记 exclusion reason。"""
    attempts_set = set(attempts)
    if len(attempts) != len(attempts_set):
        raise ContractError(f"权威 attempts 含重复 run: {sorted(attempts)}")
    sets = {name: _layer_set(layers, name) for name in LAYERS}
    if sets["launched"] != attempts_set:
        missing = sorted(attempts_set - sets["launched"])
        extra = sorted(sets["launched"] - attempts_set)
        raise ContractError(
            f"launched 必须恰等于权威 attempts(发起永不消失):缺={missing} 多={extra}")
    for parent, child in zip(LAYERS, LAYERS[1:]):
        if not sets[child] <= sets[parent]:
            leak = sorted(sets[child] - sets[parent])
            raise ContractError(f"{child} 含 {parent} 外 run_id: {leak}")
        reasons = layers[child].get("exclusion_reasons")
        if not isinstance(reasons, dict):
            raise ContractError(f"{child}.exclusion_reasons 必须为 dict")
        excluded = sets[parent] - sets[child]
        unexplained = sorted(r for r in excluded if not str(reasons.get(r, "")).strip())
        if unexplained:
            raise ContractError(f"{child} 排除的 run 无登记原因: {unexplained}")
    bad = sorted(sets["causal_analysis_eligible"] & set(corrupt_runs))
    if bad:
        raise ContractError(f"causal_analysis_eligible 含 CORRUPT run: {bad}")
    return True
