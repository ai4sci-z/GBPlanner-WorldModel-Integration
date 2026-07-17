#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0:单 run 只读离线提取器(不启动仿真、不改任何产物)。

从既有 hover run 产物抽取**事后可提取子集**。诚实边界:
  - airborne:仅由 mission_summary.airborne_seen **正证据**判定(True→起飞正证据、
    False→明确未起飞、缺失/无字段/无文件→UNKNOWN);不从 blocker 缺失反推。
  - arm 请求/ack/拒绝**时序**:产物无带时间戳序列 → 一律 UNKNOWN,不下任何结论
    (不写"零 arm/从未进入 arm 循环/异源")。
  - STATUSTEXT:经 CRC 校验(open1_tlog);marker 只记"文本出现",不升级为"完整 boot 完成"。
  - canonical_config_hash:解析 TOML → 排除明确的易变字段 → 稳定序列化 → sha256。
运行时才能取的字段(宿主负载、SITL stdout/退出码、连续 readiness、EKF 残差、arm 时序、
companion digest)一律进 evidence_gaps,E1 前须申请扩权,不静默改 world-model。
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_tlog  # noqa: E402

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    tomllib = None

# 配置身份**排除**的易变字段(点分路径,明确列举);未列举的未知字段一律**纳入**身份(保守)。
# 真实 run_config.toml 用 TOML 表:语义在 [inputs]/[run]/[startup_readiness_policy];
# 易变仅 run.run_id、run.artifact_dir、整个 [outputs] 表(全是嵌 run_id 的路径)。
CONFIG_EXCLUDE_PATHS = frozenset({"outputs", "run.run_id", "run.artifact_dir"})

RUNTIME_ONLY_GAPS = [
    "host{loadavg/cpu/freq/mem/io} 时序:需 world-model 运行时埋点",
    "SITL stdout/stderr + 进程退出码/生命周期:需 world-model 直存(no-BIN 死因关键)",
    "heartbeat/dataflash 打开时刻:需运行时捕获",
    "连续 external-nav/readiness 序列:需运行时订阅(现仅采样点)",
    "fcu.arm_request/ack/reject 时序 + EKF/INS 连续残差:需运行时捕获",
    "freeze_ref.companion_digest:历史未捕获",
]


def _sha256_file(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _read_json(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _prune(d, prefix=""):
    """递归删除点分路径在 CONFIG_EXCLUDE_PATHS 内的键(排除易变字段)。"""
    out = {}
    for k, v in d.items():
        path = f"{prefix}{k}"
        if path in CONFIG_EXCLUDE_PATHS:
            continue
        out[k] = _prune(v, path + ".") if isinstance(v, dict) else v
    return out


def canonical_config_hash(run_config_text):
    """解析 TOML → 递归去易变字段 → sort_keys 稳定序列化 → sha256。解析失败返回 None(fail-closed)。
    键顺序/空白/单双引号不影响结果(先解析后规范化);语义变化改变结果;
    run_id 只按点分路径排除,不做全局字符串替换(语义值里的 run_id 子串保留)。"""
    if not run_config_text or tomllib is None:
        return None
    try:
        cfg = tomllib.loads(run_config_text)
    except (tomllib.TOMLDecodeError, ValueError):
        return None
    ser = json.dumps(_prune(cfg), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(ser.encode("utf-8")).hexdigest()


def _dig(cfg, *keys):
    """按嵌套键路径取标量;任一层缺失/非 dict → None。"""
    cur = cfg
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def airborne_verdict(mission_summary):
    """point4:仅正证据。airborne_seen True→True、False→False、缺失/无文件→None(UNKNOWN)。"""
    if not isinstance(mission_summary, dict):
        return None
    v = mission_summary.get("airborne_seen")
    if v is True:
        return True
    if v is False:
        return False
    return None  # 字段缺失/旧版 summary → UNKNOWN


def extract(run_dir):
    run_id = os.path.basename(run_dir.rstrip("/"))
    cfg_path = os.path.join(run_dir, "run_config.toml")
    cfg_text = None
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8", errors="replace") as f:
            cfg_text = f.read()
    cfg = {}
    if cfg_text and tomllib is not None:
        try:
            cfg = tomllib.loads(cfg_text)
        except (tomllib.TOMLDecodeError, ValueError):
            cfg = {}

    manifest = _read_json(os.path.join(run_dir, "manifest.json"))
    summary = _read_json(os.path.join(run_dir, "summary.json"))
    mission = _read_json(os.path.join(run_dir, "mission_summary.json"))

    logs_dir = os.path.join(run_dir, "sitl", "logs")
    bin_present = (os.path.isdir(logs_dir)
                   and any(n.endswith(".BIN") for n in os.listdir(logs_dir))) if os.path.isdir(logs_dir) else False

    tlog = os.path.join(run_dir, "sitl", "mav.tlog")
    tlog_bytes = os.path.getsize(tlog) if os.path.exists(tlog) else 0
    st = open1_tlog.summarize(tlog) if os.path.exists(tlog) else None

    status = summary.get("status") if isinstance(summary, dict) else None
    blockers = []
    abort_reason = None
    if isinstance(summary, dict):
        for b in (summary.get("blockers") or []):
            if isinstance(b, dict):
                code = b.get("code")
                if code and code not in blockers:
                    blockers.append(code)
                if code == "hover_mission_abort" and ":" in b.get("message", ""):
                    abort_reason = b["message"].split(":", 1)[1]

    readiness = _read_json(os.path.join(run_dir, "audits", "startup_readiness_probe.json"))
    imu_probe = _read_json(os.path.join(run_dir, "probes", "imu_probe.txt"))

    return {
        "run_id": run_id,
        "run_dir": os.path.abspath(run_dir),
        "input_hashes": {
            "run_config.toml": _sha256_file(cfg_path),
            "summary.json": _sha256_file(os.path.join(run_dir, "summary.json")),
            "mission_summary.json": _sha256_file(os.path.join(run_dir, "mission_summary.json")),
            "mav.tlog": _sha256_file(tlog),
        },
        "freeze_ref": {
            "simulation_profile": _dig(cfg, "inputs", "simulation_profile"),
            "control_mode": _dig(cfg, "inputs", "control_mode"),
            "canonical_config_hash": canonical_config_hash(cfg_text),
            "created_at": manifest.get("created_at") if isinstance(manifest, dict) else None,
            "companion_digest": None,  # 历史未捕获 → gap
        },
        "outcome": {
            "bin_present": bin_present,
            "tlog_bytes": tlog_bytes,
            "status": status,
            "full_pass": status == "TASK_STATUS_OK",
            "airborne": airborne_verdict(mission),      # True/False/None(UNKNOWN),仅正证据
            "mission_blockers": blockers,
            "abort_reason": abort_reason,
        },
        "fcu_statustext": st,  # 含 protocol_stats(CRC 校验)、markers_seen、accels 计数
        "arm_status": "UNKNOWN",  # 产物无带时间戳 arm 时序 → 不下任何 arm 结论
        "ros2_sampled": {
            "note": "仅采样时点,非整个 pre-arm 窗口连续证据",
            "startup_readiness_ok": bool(readiness.get("ok")) if isinstance(readiness, dict) else None,
            "imu_probe_ok": bool(imu_probe.get("ok")) if isinstance(imu_probe, dict) else None,
        },
        "evidence_gaps": list(RUNTIME_ONLY_GAPS),
    }


if __name__ == "__main__":
    print(json.dumps(extract(sys.argv[1]), ensure_ascii=False, indent=2))
