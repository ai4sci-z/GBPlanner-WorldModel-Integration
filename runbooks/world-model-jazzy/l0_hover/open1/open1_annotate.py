#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E0 · 独立历史回放标注工具(B1-B5 契约)。

独立性(B1/B5):stdlib-only;**不 import open1_tlog / open1_extract**;CRC 用独立
位反射实现(poly 0x8408,与被测 nibble 法不同代码路径);直接读原始 JSON/TOML/tlog;
expected 绝不由被测代码生成,输入不匹配一律 FAIL,不自动更新 expected(B1-17)。

模式(B1-08..13):
  verify(默认)   只验证现有标注:schema 失败关闭 + 逐 run 重算全量对比。
  generate       显式生成:只写 --out 指定的**临时文件**并 fsync(B1-11/12),
                 绝不直接覆盖正式 TSV(B1-10);替换须显式 --replace 执行原子 rename(B1-13)。
不写 world-model artifacts(B1-14);同输入重复执行结果逐字节一致(B1-15,行序=run 起始时戳)。

hash(B2):全部 64 位完整 SHA-256;验证器拒绝 短/长/非十六进制/与当前输入不一致;
比较用完整值,终端显示可缩写。

schema(B3,失败关闭):固定 header;缺列/未知列/字段数不符/重复 run_id/重复 run_dir/
非法布尔/非法或负 target_count/非法 run_id 格式/未知 schema 版本/空文件/仅注释 → 全部 FAIL。

provenance(B4):
  artifact_claimed_run_commit  产物声称的 wm commit(产物内**无**直接记录 → 该值来自外部登记)
  artifact_commit_source       外部证据路径+章节(B4-07/08);无独立来源时值须为 UNVERIFIED(B4-09)
  annotation_tool_commit / annotation_data_commit(B4-10..16 绑定规则,避免自引用死循环 B4-13):
    两者**不内嵌**于 TSV(内嵌自身提交号=死循环),由验证器经 `git log -1 -- <file>` 派生并打印;
    工具内容由引入/最近修改本文件的提交负责(B4-14),标注数据由引入/最近修改 TSV 的提交负责(B4-15),
    manifest 刷新提交绑定其前序 review 提交(两提交闭包协议,B4-16)。文件未入库(无提交)→ FAIL(B3-12/13)。
    header 可选显式 `# tool_commit=<sha>` / `# data_commit=<sha>` 覆盖;显式值不存在于 git → FAIL。
"""
import hashlib
import json
import math  # noqa: F401  (保留:字段派生如需)
import os
import re
import subprocess
import sys

SCHEMA_VERSION = "open1_replay_annotations.v2"
COLUMNS = [
    "run_id", "run_dir", "artifact_claimed_run_commit", "artifact_commit_source",
    "profile", "control_mode",
    "config_sha256", "tlog_sha256", "summary_sha256", "mission_summary_sha256", "manifest_sha256",
    "bin_exists", "summary_status", "controller_airborne_seen",
    "target_statustext", "target_count",
    "provable", "not_provable", "annotation_method", "annotation_source",
]
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}\.\d{9}Z$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HERE = os.path.dirname(os.path.abspath(__file__))
# B-02 冻结 registry:验收门要求恰为这五个 run,RAN=5/PASS=5/FAIL=0/SKIP=0,否则非零(失败关闭)
FROZEN_RUN_IDS = frozenset({
    "20260715T204428.255001623Z", "20260715T211927.641462689Z", "20260715T210849.272170331Z",
    "20260715T205113.276955543Z", "20260715T210149.482334513Z",
})
# B-05 外部 registry(相对管理主仓根):含五 run_id 短式、profile、claimed commit 前缀
REGISTRY_REL = "governance/WP304_OPEN-1因果时间线与实验设计_2026-07-17.md"
REGISTRY_SECTION = "## 1. 样本分层"   # 节锚;绑定检查限定在该节到下一 "## " 之间的区域
WM_REPO = "/home/ai4s/projects/world-model"   # 只读解析 claimed commit
DEFAULT_TSV = os.path.join(HERE, "open1_replay_annotations.tsv")


# ---------- 独立解码(不依赖 open1_tlog) ----------
def indep_crc(buf, extra):
    """位反射 CRC-16/MCRF4XX(poly 0x8408)——与被测 nibble 实现不同代码路径(B5-03)。"""
    crc = 0xFFFF
    for b in bytes(buf) + bytes([extra]):
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return crc


def indep_count_statustext(path, target: bytes):
    """独立最小 MAVLink v2 走查:统计 CRC 有效且文本==target 的 STATUSTEXT。"""
    data = open(path, "rb").read()
    n = len(data)
    i = 0
    cnt = 0
    recovery = False
    while i < n:
        if n - i < 16:
            break
        if data[i + 8] == 0xFD and i + 18 <= n:
            ln = data[i + 9]
            inc = data[i + 10]
            sig = 13 if inc & 1 else 0
            total = 8 + 10 + ln + 2 + sig
            if i + total <= n and not (inc & ~0x01):
                msgid = data[i + 15] | (data[i + 16] << 8) | (data[i + 17] << 16)
                if msgid == 253:
                    body = data[i + 9: i + 18 + ln]
                    crc_in = data[i + 18 + ln] | (data[i + 18 + ln + 1] << 8)
                    if indep_crc(body, 83) == crc_in:
                        txt = data[i + 19: i + 19 + min(ln - 1, 50)].split(b"\x00")[0]
                        if txt == target:
                            cnt += 1
                        i += total
                        recovery = False
                        continue
                    recovery = True
                    i += 1
                    continue
                if recovery:
                    i += 1
                    continue
                i += total
                continue
            recovery = True
            i += 1
            continue
        i += 1
    return cnt


def sha256_full(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    except OSError:
        return ""


def _toml_inputs(p):
    """极简只读:取 [inputs] 的 simulation_profile / control_mode(不 import 被测 TOML 逻辑)。"""
    prof = mode = ""
    section = ""
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "inputs" and "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k == "simulation_profile":
                prof = v
            elif k == "control_mode":
                mode = v
    return prof, mode


def derive_row(run_dir):
    """从原始产物独立派生一行标注(B1-05..07;确定性 B1-15)。"""
    d = run_dir.rstrip("/")
    cfg = os.path.join(d, "run_config.toml")
    prof, mode = _toml_inputs(cfg)
    summ = json.load(open(os.path.join(d, "summary.json")))
    miss = json.load(open(os.path.join(d, "mission_summary.json")))
    logs = os.path.join(d, "sitl", "logs")
    binx = os.path.isdir(logs) and any(x.endswith(".BIN") for x in os.listdir(logs))
    tlog = os.path.join(d, "sitl", "mav.tlog")
    cnt = indep_count_statustext(tlog, b"Arm: Accels inconsistent")
    return {
        "run_id": os.path.basename(d),
        "run_dir": d,
        "artifact_claimed_run_commit": _resolve_claimed_commit(),
        "artifact_commit_source": f"EXTERNAL_REGISTRY:{REGISTRY_REL}#{REGISTRY_SECTION}",
        "profile": prof,
        "control_mode": mode,
        "config_sha256": sha256_full(cfg),
        "tlog_sha256": sha256_full(tlog),
        "summary_sha256": sha256_full(os.path.join(d, "summary.json")),
        "mission_summary_sha256": sha256_full(os.path.join(d, "mission_summary.json")),
        "manifest_sha256": sha256_full(os.path.join(d, "manifest.json")),
        "bin_exists": str(bool(binx)).lower(),
        "summary_status": str(summ.get("status")),
        "controller_airborne_seen": str(miss.get("airborne_seen")).lower(),
        "target_statustext": "Arm: Accels inconsistent",
        "target_count": str(cnt),
        "provable": "controller-side airborne_seen; BIN existence; CRC-valid target STATUSTEXT count; summary status",
        "not_provable": "FCU 是否离地; arm 请求/拒绝时序; no-BIN 直接死因; 两类是否同源",
        "annotation_method": "独立最小MAVLink-v2解码(位反射CRC-16/MCRF4XX,非open1_tlog)+直接读原始JSON/TOML+sha256全量",
        "annotation_source": "open1_annotate.py(独立工具,不import open1_tlog/open1_extract)",
    }


def _resolve_claimed_commit():
    """由外部 registry 记载的前缀(eab0cc6)经 wm 仓只读解析为完整 40 位 SHA。
    独立于被测 extractor(B5);解析失败返回 UNVERIFIED(B4-09)。"""
    r = _git(["rev-parse", "eab0cc6"], WM_REPO)
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else "UNVERIFIED"


def check_provenance_row(r, repo):
    """B-05 真绑定。返回缺陷列表(空=通过)。不做字符串前缀糊弄:
    ① claimed commit = 40 位 hex 且能在 wm 仓解析为 commit;
    ② source 必须解析到实际存在的 registry 文件 + 明确 section;
    ③ registry 中必须存在该 run_id(短式)、claimed commit 前缀、该行 profile;
    ④ 结构一致:run_dir 基名 == run_id(artifact path 绑定)。"""
    bad = []
    sha = r["artifact_claimed_run_commit"]
    if sha == "UNVERIFIED":
        pass  # B4-09 显式未验证,允许但不算绑定通过 → 视作缺陷以失败关闭
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        bad.append(f"claimed_commit 非40位hex: {sha}")
    else:
        g = _git(["cat-file", "-t", sha], WM_REPO)
        if g.returncode != 0 or g.stdout.strip() != "commit":
            bad.append(f"claimed_commit 无法在 wm 仓解析: {sha[:12]}…")
    src = r["artifact_commit_source"]
    if not src.startswith("EXTERNAL_REGISTRY:"):
        bad.append("source 非 EXTERNAL_REGISTRY")
        return bad
    body = src[len("EXTERNAL_REGISTRY:"):]
    if "#" not in body:
        bad.append("source 缺 section 锚")
        return bad
    rel, section = body.split("#", 1)
    reg_path = os.path.join(repo, rel) if repo else rel
    if not os.path.isfile(reg_path):
        bad.append(f"registry 文件不存在: {rel}")
        return bad
    text = open(reg_path, encoding="utf-8", errors="replace").read()
    if section not in text:
        bad.append(f"registry 无该 section: {section}")
        return bad
    # 区域绑定:仅在锚定节内查(防止前缀在文档他处出现造成假绑定)
    i = text.index(section)
    j = text.find("\n## ", i + len(section))
    region = text[i:j] if j != -1 else text[i:]
    short = r["run_id"][:15]
    if short not in region:
        bad.append(f"registry 节内无该 run_id: {short}")
    if re.fullmatch(r"[0-9a-f]{40}", sha) and sha[:7] not in region:
        bad.append(f"registry 节内未记载该 commit 前缀: {sha[:7]}")
    if r["profile"] and r["profile"] not in region:
        bad.append(f"registry 节内未记载该 profile: {r['profile']}")
    if os.path.basename(r["run_dir"].rstrip("/")) != r["run_id"]:
        bad.append("run_dir 基名 != run_id(artifact path 不一致)")
    return bad


# ---------- schema 校验(B3,失败关闭) ----------
def parse_tsv(path):
    """返回 (meta, rows)。任何违规 raise ValueError(失败关闭)。"""
    if not os.path.exists(path):
        raise ValueError(f"标注文件不存在: {path}")
    if os.path.getsize(path) == 0:
        raise ValueError("空标注文件(B3-15)")
    meta = {}
    header = None
    rows = []
    for ln, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line:
            continue
        if line.startswith("#"):
            m = re.match(r"#\s*(schema|tool_commit|data_commit)\s*=\s*(\S+)", line)
            if m:
                meta[m.group(1)] = m.group(2)
            continue
        parts = line.split("\t")
        if header is None:
            header = parts
            continue
        rows.append((ln, parts))
    if meta.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"schema 版本未知/缺失: {meta.get('schema')!r}(要求 {SCHEMA_VERSION},B3-14)")
    if header is None:
        raise ValueError("只有注释没有 header/数据(B3-16)")
    missing = [c for c in COLUMNS if c not in header]
    extra = [c for c in header if c not in COLUMNS]
    if missing:
        raise ValueError(f"缺少必需列: {missing}(B3-02)")
    if extra:
        raise ValueError(f"未知额外列: {extra}(B3-03)")
    if header != COLUMNS:
        raise ValueError("列顺序与 schema 不符")
    if not rows:
        raise ValueError("没有数据行(B3-16)")
    seen_id, seen_dir = set(), set()
    out = []
    for ln, parts in rows:
        if len(parts) != len(COLUMNS):
            raise ValueError(f"行 {ln} 字段数 {len(parts)} != {len(COLUMNS)}(B3-04/05)")
        r = dict(zip(COLUMNS, parts))
        if not RUN_ID_RE.match(r["run_id"]):
            raise ValueError(f"行 {ln} 非法 run_id 格式: {r['run_id']}(B3-11)")
        if r["run_id"] in seen_id:
            raise ValueError(f"行 {ln} 重复 run_id(B3-06)")
        if r["run_dir"] in seen_dir:
            raise ValueError(f"行 {ln} 重复 run_dir(B3-07)")
        seen_id.add(r["run_id"])
        seen_dir.add(r["run_dir"])
        for bcol in ("bin_exists",):
            if r[bcol] not in ("true", "false"):
                raise ValueError(f"行 {ln} 非法布尔 {bcol}={r[bcol]}(B3-08)")
        if r["controller_airborne_seen"] not in ("true", "false", "none"):
            raise ValueError(f"行 {ln} 非法布尔 controller_airborne_seen(B3-08)")
        if not r["target_count"].isdigit():
            raise ValueError(f"行 {ln} 非法 target_count={r['target_count']}(B3-09/10 含负数)")
        for hcol in ("config_sha256", "tlog_sha256", "summary_sha256", "mission_summary_sha256", "manifest_sha256"):
            if not SHA256_RE.match(r[hcol]):
                raise ValueError(f"行 {ln} {hcol} 非完整 64 位十六进制 SHA-256(B2-06/07/08)")
        out.append(r)
    return meta, out


# ---------- git provenance(B4) ----------
def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def repo_root():
    r = _git(["rev-parse", "--show-toplevel"], HERE)
    return r.stdout.strip() if r.returncode == 0 else None


def file_commit(path):
    """派生该文件的最近提交(B4 绑定规则);未入库或**工作树内容未提交(脏)** → None
    (脏文件的 git-log 提交并不描述当前内容,放行即假 provenance)。"""
    root = repo_root()
    if not root:
        return None
    rel = os.path.relpath(path, root)
    dirty = _git(["status", "--porcelain", "--", rel], root).stdout.strip()
    if dirty:
        return None
    r = _git(["log", "-1", "--format=%H", "--", rel], root)
    sha = r.stdout.strip()
    return sha or None


def commit_exists(sha):
    root = repo_root()
    if not root or not sha:
        return False
    return _git(["cat-file", "-t", sha], root).returncode == 0


# ---------- verify / generate ----------
def cmd_verify(tsv, gate=True):
    """gate=True(默认 verify)= **冻结验收门,失败关闭**(B-02/B-03):
      行集必须恰为 FROZEN_RUN_IDS 五个 run;RAN=5、PASS=5、FAIL=0、SKIP=0;
      任一不满足 → 非零(INCOMPLETE/FAIL),SKIP 绝不计入 PASS,FAIL=0 也不足以 rc=0。
    gate=False(replay 子命令)= 观察性回放,非验收门:如实报 PASS/FAIL/SKIP,rc 仅随 FAIL。"""
    mode = "GATE" if gate else "REPLAY(非验收门)"
    try:
        meta, rows = parse_tsv(tsv)
    except ValueError as e:
        print(f"SCHEMA-FAIL: {e}")
        print(f"[{mode}] 结果: PASS=0 FAIL=1 SKIP=0 status=FAIL")
        return 1
    repo = repo_root()
    npass = nfail = nskip = 0
    tool_sha = meta.get("tool_commit") or file_commit(os.path.abspath(__file__))
    data_sha = meta.get("data_commit") or file_commit(tsv)
    for label, sha in (("annotation_tool_commit", tool_sha), ("annotation_data_commit", data_sha)):
        if sha is None or not commit_exists(sha):
            print(f"FAIL: {label} 不存在于 git/内容未提交(B3-12/13): {sha}")
            nfail += 1
        else:
            print(f"PROVENANCE: {label}={sha}")
    # B-02 冻结行集:恰为五个冻结 run(gate 模式)
    row_ids = {r["run_id"] for r in rows}
    if gate and row_ids != FROZEN_RUN_IDS:
        print(f"FAIL: 行集≠冻结五 run(expected 5,got {len(rows)};缺={sorted(FROZEN_RUN_IDS-row_ids)} 多={sorted(row_ids-FROZEN_RUN_IDS)})")
        nfail += 1
    for r in rows:
        d = r["run_dir"]
        if not os.path.isdir(d):
            print(f"SKIP: {r['run_id']}(产物不在盘;SKIP≠PASS)")
            nskip += 1
            continue
        try:
            cur = derive_row(d)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL: {r['run_id']} 重算失败: {e!r}")
            nfail += 1
            continue
        diffs = [c for c in ("config_sha256", "tlog_sha256", "summary_sha256",
                             "mission_summary_sha256", "manifest_sha256",
                             "profile", "control_mode", "bin_exists", "summary_status",
                             "controller_airborne_seen", "target_count")
                 if cur[c] != r[c]]
        diffs += check_provenance_row(r, repo)          # B-05 真绑定
        if diffs:
            print(f"FAIL: {r['run_id']} 不匹配/绑定失败={diffs}(不自动更新 expected,B1-17)")
            nfail += 1
        else:
            print(f"PASS: {r['run_id']} 全列匹配+provenance 绑定通过(tlog={r['tlog_sha256'][:12]}…)")
            npass += 1
    if gate:
        ok = (nfail == 0 and nskip == 0 and npass == len(FROZEN_RUN_IDS) and row_ids == FROZEN_RUN_IDS)
        status = "COMPLETE" if ok else ("INCOMPLETE" if (nskip or row_ids != FROZEN_RUN_IDS) and nfail == 0 else "FAIL")
        print(f"[GATE] 结果: RAN={npass+nfail} PASS={npass} FAIL={nfail} SKIP={nskip} status={status}")
        return 0 if ok else 1
    print(f"[REPLAY(非验收门)] 结果: PASS={npass} FAIL={nfail} SKIP={nskip}")
    return 1 if nfail else 0


def write_tsv(rows, out_path):
    body = [f"# schema={SCHEMA_VERSION}",
            "# WP304 E0 独立历史回放标注(v2):expected 由本独立工具派生,非 extractor 自产;",
            "# annotation_tool_commit/annotation_data_commit 由验证器经 git log 派生(避免自引用死循环,B4-13)。",
            "\t".join(COLUMNS)]
    for r in sorted(rows, key=lambda x: x["run_id"]):
        body.append("\t".join(r[c] for c in COLUMNS))
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
        f.flush()
        os.fsync(f.fileno())            # B1-12
    return tmp


def cmd_generate(run_dirs, out_path, replace):
    for d in run_dirs:
        real = os.path.realpath(d)
        if "/world-model/" in real + "/" and not real.startswith(os.path.realpath(repo_root() or "/nonexistent")):
            pass  # 只读来源;写目标另检
    rows = [derive_row(d) for d in sorted(run_dirs)]
    real_out = os.path.realpath(out_path)
    if "/world-model/" in real_out:
        print("拒绝:输出位于 world-model(B1-14)")
        return 1
    tmp = write_tsv(rows, real_out)
    print(f"已写临时文件(fsync 完成): {tmp}")
    if replace:
        os.replace(tmp, real_out)       # B1-13 显式原子 rename
        dfd = os.open(os.path.dirname(real_out), os.O_RDONLY)
        os.fsync(dfd)
        os.close(dfd)
        print(f"已原子替换: {real_out}")
    else:
        print("未替换正式文件(需显式 --replace,B1-10)")
    return 0


def main(argv):
    if not argv or argv[0] in ("verify", "replay"):
        gate = (not argv) or argv[0] == "verify"
        rest = argv[1:] if argv else []
        tsv = DEFAULT_TSV
        if len(rest) >= 2 and rest[0] == "--tsv":
            tsv = rest[1]
        return cmd_verify(tsv, gate=gate)
    if argv[0] == "generate":
        dirs = []
        out = DEFAULT_TSV
        replace = False
        i = 1
        while i < len(argv):
            if argv[i] == "--run-dir":
                dirs.append(argv[i + 1])
                i += 2
            elif argv[i] == "--out":
                out = argv[i + 1]
                i += 2
            elif argv[i] == "--replace":
                replace = True
                i += 1
            else:
                print(f"未知参数 {argv[i]}")
                return 2
        if not dirs:
            print("generate 需要至少一个 --run-dir(B1-09 显式参数)")
            return 2
        return cmd_generate(dirs, out, replace)
    print("用法: open1_annotate.py [verify(冻结验收门)|replay(观察) [--tsv PATH] | generate --run-dir D [...] [--out PATH] [--replace]]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
