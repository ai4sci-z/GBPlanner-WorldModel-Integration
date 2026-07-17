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

# 配置身份**排除**的易变字段 = 精确叶子路径白名单(不排整表、不用前缀/模糊名/全局替换)。
# 只排"已证纯易变"字段;未知字段(含 [outputs] 内新字段)、嵌套未知、列表顺序一律**默认进入** hash。
# 每个排除路径的理由/示例/失效检测见 CONFIG_EXCLUDE_REGISTRY。
CONFIG_EXCLUDE_PATHS = frozenset({
    "run.run_id",
    "run.artifact_dir",
    "outputs.manifest",
    "outputs.rosbag",
    "outputs.summary_json",
    "outputs.summary_md",
    "outputs.task_plan",
})
# 排除登记:路径 → (为何不改变实验语义, 历史样本示例, 若含义变化如何使测试失败)
CONFIG_EXCLUDE_REGISTRY = {
    "run.run_id": ("每次运行的时戳型唯一 id,不改变被测配置",
                   "20260715T204428.255001623Z",
                   "test_canon_runid_only_change_same_hash 会因它进入身份而变红"),
    "run.artifact_dir": ("产物落盘目录,仅嵌 run_id 路径,不改变被测配置",
                         "../../artifacts/sim/hover/20260715T204428.255001623Z",
                         "同上,路径变化本应折叠,进入身份即变红"),
    "outputs.manifest": ("产物 manifest 路径,仅嵌 run_id", ".../<run_id>/manifest.json",
                         "test_canon_approved_artifact_path_same_hash 变红"),
    "outputs.rosbag": ("产物 rosbag 路径,仅嵌 run_id", ".../<run_id>/rosbag/rosbag_0.mcap", "同上"),
    "outputs.summary_json": ("产物 summary 路径,仅嵌 run_id", ".../<run_id>/summary.json", "同上"),
    "outputs.summary_md": ("产物 summary.md 路径,仅嵌 run_id", ".../<run_id>/summary.md", "同上"),
    "outputs.task_plan": ("产物 task_plan 路径,仅嵌 run_id", ".../<run_id>/task_plan.json", "同上"),
}

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


def _read_json_q(p):
    """返回 (value, quality)。区分缺失/损坏/读错,不压成单一 None(C2)。"""
    if not os.path.exists(p):
        return None, "MISSING"
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return json.load(f), "PRESENT_VALID"
    except ValueError:
        return None, "MALFORMED"
    except OSError:
        return None, "READ_ERROR"


def _read_json(p):
    return _read_json_q(p)[0]


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


def airborne_verdict(mission_summary, other_airborne_claim=None):
    """C1:mission_summary.airborne_seen 是 **mission controller 侧**汇总,非 FCU 内部真值。
    返回结构化对象:
      mission_controller_airborne_seen ∈ {True, False, None(UNKNOWN)}
      True  = controller 记录到 airborne;
      False = controller **未记录**到 airborne(**≠证明 FCU 从未离地**);
      None  = 字段缺失/无 mission_summary → UNKNOWN。
    other_airborne_claim 为其它来源的 airborne 主张(如有);与 controller=False 冲突时 conflict=True。"""
    seen = None
    if isinstance(mission_summary, dict):
        v = mission_summary.get("airborne_seen")
        seen = v if isinstance(v, bool) else None
    conflict = (seen is False and other_airborne_claim is True)
    return {
        "mission_controller_airborne_seen": seen,
        "source": "mission_summary.json (mission controller 侧观测)",
        "epistemic_scope": "controller 观测,非 FCU 地面真值;False≠证明 FCU 从未离地",
        "conflict": conflict,
    }


def extract(run_dir):
    run_id = os.path.basename(run_dir.rstrip("/"))
    cfg_path = os.path.join(run_dir, "run_config.toml")
    cfg_text = None
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8", errors="replace") as f:
            cfg_text = f.read()
    # run_config 质量:MISSING/MALFORMED/PRESENT_VALID(C2)
    cfg = {}
    if not os.path.exists(cfg_path):
        cfg_quality = "MISSING"
    elif tomllib is None:
        cfg_quality = "UNSUPPORTED"
    else:
        try:
            cfg = tomllib.loads(cfg_text)
            cfg_quality = "PRESENT_VALID"
        except (tomllib.TOMLDecodeError, ValueError):
            cfg_quality = "MALFORMED"

    manifest, q_manifest = _read_json_q(os.path.join(run_dir, "manifest.json"))
    summary, q_summary = _read_json_q(os.path.join(run_dir, "summary.json"))
    mission, q_mission = _read_json_q(os.path.join(run_dir, "mission_summary.json"))
    readiness, q_readiness = _read_json_q(os.path.join(run_dir, "audits", "startup_readiness_probe.json"))
    imu_probe, q_imu = _read_json_q(os.path.join(run_dir, "probes", "imu_probe.txt"))

    logs_dir = os.path.join(run_dir, "sitl", "logs")
    if not os.path.isdir(logs_dir):
        bin_present, q_bindir = False, "MISSING"
    else:
        bin_present = any(n.endswith(".BIN") for n in os.listdir(logs_dir))
        q_bindir = "PRESENT_VALID"

    tlog = os.path.join(run_dir, "sitl", "mav.tlog")
    if not os.path.exists(tlog):
        tlog_bytes, st, q_tlog = 0, None, "MISSING"
    else:
        tlog_bytes = os.path.getsize(tlog)
        st = open1_tlog.summarize(tlog)  # protocol_stats 承载 tlog 协议质量(crc_failed 等)
        q_tlog = "PRESENT_VALID"

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

    # 证据错误(损坏≠缺失≠正常业务失败):有文件但 MALFORMED 时显式登记
    evidence_errors = [name for name, q in (
        ("run_config.toml", cfg_quality), ("summary.json", q_summary),
        ("mission_summary.json", q_mission)) if q == "MALFORMED"]

    return {
        "run_id": run_id,
        "run_dir": os.path.abspath(run_dir),
        "input_hashes": {
            "run_config.toml": _sha256_file(cfg_path),
            "summary.json": _sha256_file(os.path.join(run_dir, "summary.json")),
            "mission_summary.json": _sha256_file(os.path.join(run_dir, "mission_summary.json")),
            "mav.tlog": _sha256_file(tlog),
        },
        "evidence_quality": {   # C2:每输入区分 PRESENT_VALID/MISSING/MALFORMED/READ_ERROR/UNSUPPORTED
            "run_config.toml": cfg_quality,
            "manifest.json": q_manifest,
            "summary.json": q_summary,
            "mission_summary.json": q_mission,
            "mav.tlog": q_tlog,
            "startup_readiness_probe.json": q_readiness,
            "imu_probe.txt": q_imu,
            "sitl/logs(BIN dir)": q_bindir,
        },
        "evidence_errors": evidence_errors,   # 非空 = 有损坏证据,不得当普通业务失败静默
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
            "airborne": airborne_verdict(mission),   # C1:结构化 controller 侧,非 FCU 真值
            "mission_blockers": blockers,
            "abort_reason": abort_reason,
        },
        "fcu_statustext": st,  # None(tlog MISSING) 或 含 protocol_stats(CRC 校验)/markers/accels
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
