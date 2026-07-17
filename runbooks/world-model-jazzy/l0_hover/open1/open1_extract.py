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


# A1 统一输入质量状态(全集):
#   PRESENT_VALID    文件存在、可读、格式符合契约(A1-10)
#   MISSING          路径不存在(A1-11)
#   EMPTY            文件存在但为空且空不合法(A1-12)
#   MALFORMED        文件存在但语法/协议损坏(A1-13)
#   READ_ERROR       文件存在但读取失败(A1-14)
#   UNSUPPORTED      格式有效但当前实现不支持(A1-15)
#   PRESENT_NO_MATCH 容器/目录存在但没有目标文件(A1-16)
# 铁律:不得只因路径存在就标 PRESENT_VALID(A1-17);MALFORMED≠MISSING(A1-18);
#       READ_ERROR≠UNKNOWN(A1-19);证据损坏≠业务失败(A1-20)。


# A-02/A-03 schema 契约:语法合法≠契约合格。语法错=MALFORMED;
# 语法合法但结构/字段/类型违约 = **UNSUPPORTED_SCHEMA**(全局唯一选择,corrupt 类,入 failed_inputs)。
KNOWN_SUMMARY_STATUSES = ("TASK_STATUS_OK", "TASK_STATUS_ERROR", "TASK_STATUS_BLOCKED")


def _schema_manifest(v):
    """manifest.json:对象;身份/产物字段存在且类型正确。"""
    return (isinstance(v, dict)
            and isinstance(v.get("run_id"), str)
            and isinstance(v.get("created_at"), str)
            and isinstance(v.get("artifacts"), list))


def _schema_summary(v):
    """summary.json:对象;status 属已知集合;ok 布尔;blockers 列表。"""
    return (isinstance(v, dict)
            and v.get("status") in KNOWN_SUMMARY_STATUSES
            and isinstance(v.get("ok"), bool)
            and isinstance(v.get("blockers"), list))


def _schema_mission(v):
    """mission_summary.json:对象;airborne_seen 若存在必须为布尔(缺失→UNKNOWN 由上层映射)。"""
    if not isinstance(v, dict):
        return False
    if "airborne_seen" in v and not isinstance(v["airborne_seen"], bool):
        return False
    return True


def _schema_probe(v):
    """readiness/imu probe:对象;ok 若存在必须为布尔。"""
    if not isinstance(v, dict):
        return False
    if "ok" in v and not isinstance(v["ok"], bool):
        return False
    return True


def _read_json_q(p, schema=None):
    """返回 (value, quality)。缺失/空/语法损坏/读错/schema 违约分立,不压成单一 None。"""
    if not os.path.exists(p):
        return None, "MISSING"
    try:
        if os.path.getsize(p) == 0:
            return None, "EMPTY"
        with open(p, encoding="utf-8", errors="replace") as f:
            v = json.load(f)
    except ValueError:
        return None, "MALFORMED"
    except OSError:
        return None, "READ_ERROR"
    if schema is not None and not schema(v):
        return None, "UNSUPPORTED_SCHEMA"     # A-03:语法合法但违约 → 不得 PRESENT_VALID
    return v, "PRESENT_VALID"


def _read_json(p):
    return _read_json_q(p)[0]


def tlog_quality(path, st):
    """A4:tlog 质量判定,与"目标文本是否出现"完全分离(A4-10)。
    MISSING(A4-01)/EMPTY(A4-02)/MALFORMED(A4-03 随机垃圾:无任何可解析 record,
    重同步字节占绝对多数)/UNSUPPORTED(A4-04 结构可解析但零个已知 CRC 帧)/
    PRESENT_VALID(A4-06 至少一个 CRC-valid 支持帧)。CRC 错误在协议计数中如实记录(A4-05);
    随机垃圾绝不标 PRESENT_VALID(A4-11),也不静默输出"正常零消息"(A4-12)。"""
    if not os.path.exists(path):
        return "MISSING"                # A4-01
    try:
        if os.path.getsize(path) == 0:
            return "EMPTY"              # A4-02(存在但空:先于 st 判定)
    except OSError:
        return "READ_ERROR"
    if st is None:
        return "READ_ERROR"             # 存在非空却无解析结果 → 读取层失败
    ps = st["protocol_stats"]
    if ps["valid_crc_frames"] >= 1:
        return "PRESENT_VALID"          # A4-06:≥1 已知帧 CRC 通过
    consumed = ps["candidate_records"] + ps["unsupported_message_frames"] + ps["unsupported_incompat_flags"]
    noise = ps["resync_bytes"] + ps["truncated_tail"] + ps["truncated_candidates"]
    if consumed == 0 or (noise > 0 and consumed == 0):
        return "MALFORMED"              # A4-03:纯噪声,无一个结构可解析 record
    if ps["unsupported_message_frames"] >= 1 and ps["crc_failed_frames"] == 0 and noise <= consumed:
        return "UNSUPPORTED"            # A4-04:只有未知 msgid 的结构合法帧
    if ps["crc_failed_frames"] >= 1 and ps["valid_crc_frames"] == 0:
        return "MALFORMED"              # 已知帧全部 CRC 失败
    return "MALFORMED" if noise > consumed else "UNSUPPORTED"


# A2 证据门契约:必需/可选输入集合(当前 hover 任务离线证据契约)。
# 必需 = 判定业务结果与配置身份不可缺的最小集;可选 = 缺失可由失败模式解释(入 optional_gaps),
# 但**损坏永远是损坏**(任何输入 MALFORMED/READ_ERROR → failed_inputs,门 CORRUPT)。
REQUIRED_INPUTS = ("run_config.toml", "manifest.json", "summary.json",
                   "mission_summary.json", "mav.tlog")
OPTIONAL_INPUTS = ("startup_readiness_probe.json", "imu_probe.txt",
                   "sitl/logs(dir)", "BIN(set)")
_CORRUPT_STATES = ("MALFORMED", "READ_ERROR", "UNSUPPORTED", "UNSUPPORTED_SCHEMA")


def build_evidence_gate(quality):
    """A2:由逐输入质量构建 evidence_errors + evidence_gate。
    status ∈ {COMPLETE, INCOMPLETE, CORRUPT}(A2-16):
      任一输入(必需或可选)损坏/读错/不支持 → CORRUPT(A2-18;损坏永远是证据问题);
      必需输入 MISSING/EMPTY → INCOMPLETE(A2-17);全部满足契约 → COMPLETE(A2-19)。
    可选输入缺失 → optional_gaps,不误报为业务失败(A2-10)。"""
    failed, gaps, reasons, errors = [], [], [], []
    for name in REQUIRED_INPUTS + OPTIONAL_INPUTS:
        q = quality[name]
        if q in _CORRUPT_STATES:
            failed.append(name)
            errors.append(f"{name}:{q}")
            reasons.append(f"{name} 证据损坏({q})")
        elif name in REQUIRED_INPUTS and q in ("MISSING", "EMPTY"):
            failed.append(name)
            errors.append(f"{name}:{q}")
            reasons.append(f"{name} 必需证据缺失({q})")
        elif name in OPTIONAL_INPUTS and q in ("MISSING", "EMPTY", "PRESENT_NO_MATCH"):
            gaps.append(f"{name}:{q}")
    if any(quality[n] in _CORRUPT_STATES for n in failed):
        status = "CORRUPT"
    elif failed:
        status = "INCOMPLETE"
    else:
        status = "COMPLETE"
    gate = {
        "required_inputs": list(REQUIRED_INPUTS),   # A2-11
        "failed_inputs": failed,                    # A2-12
        "optional_gaps": gaps,                      # A2-13
        "reasons": reasons,                         # A2-14
        "status": status,                           # A2-15
    }
    return errors, gate


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
    # A1-01 run_config 质量
    cfg = {}
    if not os.path.exists(cfg_path):
        cfg_quality = "MISSING"
    elif tomllib is None:
        cfg_quality = "UNSUPPORTED"                       # A1-15
    elif os.path.getsize(cfg_path) == 0:
        cfg_quality = "EMPTY"                             # A1-12
    else:
        try:
            cfg = tomllib.loads(cfg_text)
            inp = cfg.get("inputs")
            if (isinstance(cfg, dict) and isinstance(inp, dict)
                    and isinstance(inp.get("simulation_profile"), str)
                    and isinstance(inp.get("control_mode"), str)):
                cfg_quality = "PRESENT_VALID"
            else:
                cfg, cfg_quality = {}, "UNSUPPORTED_SCHEMA"   # A-02:结构/类型违约
        except (tomllib.TOMLDecodeError, ValueError):
            cfg_quality = "MALFORMED"

    manifest, q_manifest = _read_json_q(os.path.join(run_dir, "manifest.json"), _schema_manifest)   # A1-02
    summary, q_summary = _read_json_q(os.path.join(run_dir, "summary.json"), _schema_summary)       # A1-03
    mission, q_mission = _read_json_q(os.path.join(run_dir, "mission_summary.json"), _schema_mission)  # A1-04
    readiness, q_readiness = _read_json_q(os.path.join(run_dir, "audits", "startup_readiness_probe.json"), _schema_probe)  # A1-06
    imu_probe, q_imu = _read_json_q(os.path.join(run_dir, "probes", "imu_probe.txt"), _schema_probe)    # A1-07

    # A1-08 sitl/logs 目录质量 + A1-09 BIN 文件集合质量(目录在≠有 BIN,A1-16/17)
    logs_dir = os.path.join(run_dir, "sitl", "logs")
    if not os.path.isdir(logs_dir):
        bin_present, q_logsdir, q_binset = False, "MISSING", "MISSING"
    else:
        try:
            names = os.listdir(logs_dir)
            q_logsdir = "PRESENT_VALID"
            bin_present = any(n.endswith(".BIN") for n in names)
            q_binset = "PRESENT_VALID" if bin_present else "PRESENT_NO_MATCH"
        except OSError:
            bin_present, q_logsdir, q_binset = False, "READ_ERROR", "READ_ERROR"  # A1-14/A2-08

    # A1-05/A4 tlog 质量:存在≠有效,须经协议解析判定(A4-11 垃圾不得 PRESENT_VALID)
    tlog = os.path.join(run_dir, "sitl", "mav.tlog")
    if not os.path.exists(tlog):
        tlog_bytes, st, q_tlog = 0, None, "MISSING"
    else:
        try:
            tlog_bytes = os.path.getsize(tlog)
            st = open1_tlog.summarize(tlog) if tlog_bytes else None
            q_tlog = tlog_quality(tlog, st)
        except OSError:
            tlog_bytes, st, q_tlog = 0, None, "READ_ERROR"

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

    # A1 完整逐输入质量矩阵
    quality = {
        "run_config.toml": cfg_quality,
        "manifest.json": q_manifest,
        "summary.json": q_summary,
        "mission_summary.json": q_mission,
        "mav.tlog": q_tlog,
        "startup_readiness_probe.json": q_readiness,
        "imu_probe.txt": q_imu,
        "sitl/logs(dir)": q_logsdir,
        "BIN(set)": q_binset,
    }
    # A2:evidence_errors 覆盖全部输入的损坏/读错/不支持 + 必需缺失;可选缺失入 optional_gaps
    evidence_errors, evidence_gate = build_evidence_gate(quality)

    # A3:业务结果与证据验收彻底拆分
    reported_task_status = status                                   # A3-01 只记录 summary 原始状态
    reported_task_ok = (status == "TASK_STATUS_OK")                 # A3-02 summary 是否声称 OK
    evidence_complete = (evidence_gate["status"] == "COMPLETE")     # A3-03 证据门
    acceptance_eligible = reported_task_ok and evidence_complete    # A3-04..07 同时满足才可验收

    return {
        "run_id": run_id,
        "run_dir": os.path.abspath(run_dir),
        "input_hashes": {
            "run_config.toml": _sha256_file(cfg_path),
            "summary.json": _sha256_file(os.path.join(run_dir, "summary.json")),
            "mission_summary.json": _sha256_file(os.path.join(run_dir, "mission_summary.json")),
            "mav.tlog": _sha256_file(tlog),
        },
        "evidence_quality": quality,          # A1 九输入独立质量
        "evidence_errors": evidence_errors,   # A2 非空 = 有损坏/必缺证据,绝不静默
        "evidence_gate": evidence_gate,       # A2-11..16 required/failed/optional/reasons/status
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
            "reported_task_status": reported_task_status,   # A3-01
            "reported_task_ok": reported_task_ok,           # A3-02
            "evidence_complete": evidence_complete,         # A3-03
            "acceptance_eligible": acceptance_eligible,     # A3-04(新验收唯一依据,A3-16)
            "status": status,  # 兼容别名 = reported_task_status
            # A3-14/15 兼容字段:full_pass **只表示历史 summary 主张**(=reported_task_ok),
            # 不代表证据完整,**不得作为 R003 gate**;R003 验收一律用 acceptance_eligible。
            "full_pass": reported_task_ok,
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
