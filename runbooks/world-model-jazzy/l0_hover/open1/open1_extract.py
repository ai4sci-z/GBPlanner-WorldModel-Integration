#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0 埋点:单 run 只读提取器。

从一个已存在的 hover run 产物目录抽取 per_attempt schema 的**事后可提取子集**,
不启动仿真、不改任何产物、纯读。需运行时埋点才能拿的字段(宿主负载、SITL 控制台、
EKF/INS 残差时序、arm 请求/拒绝时刻、companion digest)一律进 evidence_gaps,
标注"需 world-model 运行时埋点(E1 前须申请扩权)"。

canonical_config_hash:把 run_config.toml 中的 run_id 令牌(及其嵌入路径)红act 为
<RUN_ID> 后 sha256 —— 同 profile 同配置的 run 应折叠到同一 hash(易变字段=仅路径时戳)。
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import open1_tlog  # noqa: E402

# 运行时埋点才能获取、事后产物拿不到的 schema 字段(E0 只登记为缺口)
RUNTIME_ONLY_GAPS = [
    "host{loadavg/cpu/freq/mem/io} 时序:需 world-model 运行时埋点",
    "SITL 控制台/进程退出码:需 world-model 直存(no-BIN 死因关键)",
    "fcu.ekf_status_report[]/ins_accel_residual[] 时序:需运行时订阅",
    "fcu.arm_request[]/arm_reject_reason[] 时刻:需运行时捕获",
    "freeze_ref.companion_digest:历史未捕获",
]


def _read_text(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _read_json(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _toml_scalar(text, key):
    """极简:取 `key = '...'` 或 `key = "..."` 的标量值(run_config 是平铺 kv)。"""
    if not text:
        return None
    m = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*['\"]([^'\"]*)['\"]", text)
    return m.group(1) if m else None


def canonical_config_hash(run_config_text, run_id):
    """红act run_id 令牌后 sha256;同配置折叠。run_id 未知则整体 hash(降级)。"""
    if not run_config_text:
        return None
    redacted = run_config_text.replace(run_id, "<RUN_ID>") if run_id else run_config_text
    return hashlib.sha256(redacted.encode("utf-8")).hexdigest()


def extract(run_dir):
    run_id = os.path.basename(run_dir.rstrip("/"))
    cfg_text = _read_text(os.path.join(run_dir, "run_config.toml"))
    manifest = _read_json(os.path.join(run_dir, "manifest.json"))
    summary = _read_json(os.path.join(run_dir, "summary.json"))

    # BIN 是否存在
    logs_dir = os.path.join(run_dir, "sitl", "logs")
    bin_present = os.path.isdir(logs_dir) and any(
        n.endswith(".BIN") for n in os.listdir(logs_dir)
    ) if os.path.isdir(logs_dir) else False

    # tlog 字节 + STATUSTEXT 确定性汇总
    tlog = os.path.join(run_dir, "sitl", "mav.tlog")
    tlog_bytes = os.path.getsize(tlog) if os.path.exists(tlog) else 0
    st = open1_tlog.summarize(tlog) if os.path.exists(tlog) else {
        "statustext_total": 0, "window_sec": 0.0, "accels_inconsistent_count": 0,
        "boot_markers": {"ardupilot_ready": False, "ekf_origin_set": False, "baro_calibrated": False},
        "distinct_texts": 0,
    }

    # mission blockers + abort 原因(去重取 code / abort message 尾段)
    blockers = []
    abort_reason = None
    status = None
    if isinstance(summary, dict):
        status = summary.get("status")
        for b in (summary.get("blockers") or summary.get("gate_blockers") or []):
            if isinstance(b, dict):
                code = b.get("code")
                if code and code not in blockers:
                    blockers.append(code)
                msg = b.get("message", "")
                if code == "hover_mission_abort" and ":" in msg:
                    abort_reason = msg.split(":", 1)[1]

    full_pass = status == "TASK_STATUS_OK"
    airborne = not any("airborne_seen_missing" in b for b in blockers) if blockers else full_pass

    # ROS2 侧采样点健康(仅采样点,非连续窗口)
    readiness = _read_json(os.path.join(run_dir, "audits", "startup_readiness_probe.json"))
    ext_nav_sampled_ok = bool(readiness.get("ok")) if isinstance(readiness, dict) else None
    imu_probe = _read_json(os.path.join(run_dir, "probes", "imu_probe.txt"))
    imu_sampled_ok = bool(imu_probe.get("ok")) if isinstance(imu_probe, dict) else None

    return {
        "run_id": run_id,
        "freeze_ref": {
            "simulation_profile": _toml_scalar(cfg_text, "simulation_profile"),
            "control_mode": _toml_scalar(cfg_text, "control_mode"),
            "canonical_config_hash": canonical_config_hash(cfg_text, run_id),
            "created_at": manifest.get("created_at") if isinstance(manifest, dict) else None,
            "companion_digest": None,  # 历史未捕获 → gap
        },
        "outcome": {
            "bin_present": bin_present,
            "tlog_bytes": tlog_bytes,
            "status": status,
            "full_pass": full_pass,
            "airborne": airborne,
            "mission_blockers": blockers,
            "abort_reason": abort_reason,
        },
        "fcu_statustext": st,
        "ros2_sampled": {
            "note": "仅采样时点,非整个 pre-arm 窗口连续证据",
            "startup_readiness_ok": ext_nav_sampled_ok,
            "imu_probe_ok": imu_sampled_ok,
        },
        "evidence_gaps": list(RUNTIME_ONLY_GAPS),
    }


if __name__ == "__main__":
    print(json.dumps(extract(sys.argv[1]), ensure_ascii=False, indent=2))
