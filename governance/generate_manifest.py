#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三工作目录全量 tracked-path 五态清单生成器(提交一补正版)。

用法:
  生成:         python3 generate_manifest.py <worktree> <main|feat|wm> <out.tsv>
  绑定门校验:   python3 generate_manifest.py --verify-bound   <worktree> <main|feat|wm> <manifest.tsv>
  工作树门校验: python3 generate_manifest.py --verify-current <worktree> <main|feat|wm> <manifest.tsv>

两个独立机器门(GOV-03):

bound_commit_closure(--verify-bound),对清单头部绑定 commit 校验:
  ①路径集合 == 该 commit 的 git tree(missing/extra/duplicate=0)
  ②每数据行 review_commit == 绑定 commit 前 12 位
  ③lines == 该 commit 中对应对象的行数(普通 blob=内容行数;symlink=链接自身 blob 行数,
    与生成端同一语义,不跳过;gitlink 要求 -1)
  ④category == 分类器重算(classifier 漂移/篡改检测)
  ⑤audit_status == audit_source 注册表重算(wm=R003 种子表;第三方规则;默认 UNVERIFIED)
  ⑥头部统计(files / category 计数 / audit 计数)与数据行重算一致
  ⑦字段数/枚举/重复路径/尾随空白合法

current_worktree_closure(--verify-current),对当前工作树校验:
  当前 HEAD tracked 集合相对清单的 added/removed、untracked、tracked-but-missing、
  冲突、脏改动(含正确解析的 rename/copy)逐类列出;任一非零 → 非零退出(GOV-02)。

生成流程(原地刷新安全):内存计算 → 写前现场检查(工作树须洁净,唯一豁免=受控输出目标
自身及其 .tmp)→ 写临时文件 → 对临时文件过 bound 门 → 原子替换目标。
任一步失败:删除临时文件,**目标文件保持原状**(失败关闭,零半成品)。

退出码类别:0=门通过  2=用法错误  4=绑定门路径集合违规
  5=格式/引用违规(字段/枚举/尾随空白/缺头/lines 非整数/绑定 commit 不可解析/路径含 tab)
  6=绑定门内容事实违规(lines/category/audit 来源/行 review_commit/头部统计)
  7=工作树门违规(added/removed/untracked/missing/conflict/modified)

verifier 能证明 / 不能证明(GOV-04 诚实契约):
  能证明:清单与绑定 commit 的路径集合、逐行行数、分类器输出、头部统计一致;
  audit_status 与 audit_source 注册表(来源存在且格式完整)一致;当前工作树无漂移。
  不能证明:audit_status 所代表的审查结论本身是否正确——机器只验证"未被篡改且可追溯
  到登记来源",不验证审查质量。
"""
import os
import subprocess
import sys
from pathlib import Path

R003_CODE_STATUS = {
    "docker/images/runtime/official-baseline.Dockerfile": "PARTIAL",
    "docker/profiles/navlab-sitl-gps-baseline.parm": "PARTIAL",
    "navlab/common/slam/ros/bridges/navlab_external_nav_bridge/src/navlab_external_nav_bridge_node.cpp": "PARTIAL",
    "navlab/real/companion/nodes/external_nav.py": "VERIFIED_FAIL",
    "navlab/sim/companion/nodes/imu_frame_corrector.py": "VERIFIED_FAIL",
    "navlab/sim/gazebo_sensor/benewake_tfmini_serial.py": "UNVERIFIED",
    "navlab/sim/gazebo_sensor/range_projection.py": "UNVERIFIED",
    "navlab/tests/companion/test_external_nav_sender.py": "PARTIAL",
    "navlab/tests/companion/test_imu_frame_corrector.py": "VERIFIED_FAIL",
    "navlab/tests/gazebo_sensor/x2/test_sensor_ownership.py": "UNVERIFIED",
    "navlab/tests/slam/test_runtime_config.py": "PARTIAL",
    "navlab/tests/slam/test_sitl_external_nav_params.py": "PARTIAL",
    "orchestration/sim/cmd/navlab-sim/main.go": "PARTIAL",
    "orchestration/sim/internal/config/defaults.go": "PARTIAL",
    "orchestration/sim/internal/config/task_runtime.go": "PARTIAL",
    "orchestration/sim/internal/config/types.go": "VERIFIED_FAIL",
    "orchestration/sim/internal/tasks/helpers/execution_plan.go": "PARTIAL",
    "orchestration/sim/internal/tasks/helpers/navlab_models.go": "UNVERIFIED",
    "orchestration/sim/internal/tasks/helpers/runtime_specs.go": "PARTIAL",
    "orchestration/sim/internal/tasks/helpers/slam.go": "PARTIAL",
    "orchestration/sim/internal/tasks/helpers/templates/parm/navlab_gps_baseline.parm.tmpl": "PARTIAL",
    "orchestration/sim/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl": "PARTIAL",
    "orchestration/sim/internal/tasks/hover_slo_policy.go": "VERIFIED_PASS",
    "orchestration/sim/internal/tasks/runtime_artifacts.go": "VERIFIED_PASS",
    "orchestration/sim/internal/tasks/runtime_artifacts_test.go": "PARTIAL",
    "orchestration/sim/internal/tasks/simulation_profiles.go": "VERIFIED_FAIL",
    "orchestration/sim/internal/tasks/simulation_profiles_test.go": "PARTIAL",
    "orchestration/sim/internal/tasks/types.go": "PARTIAL",
    "orchestration/sim/internal/tasks/workflow_summaries.go": "VERIFIED_FAIL",
    "orchestration/sim/internal/tasks/workflow_summaries_test.go": "PARTIAL",
}


def third_party_audit(repo_key, p):
    # 2026-07-16 轮判定:没有组件同时具备五要素 → LOCKED=0,全部 UNVERIFIED(见 README §2)。
    return "THIRD_PARTY_UNVERIFIED"


def classify_main(p):
    if p in ("sources/MANIFEST.yaml", "sources/README.md") or p.startswith("sources/mentor"):
        return "ACTIVE_REFERENCE", "sources 组件锁定记录/内部文档(第一方治理资产)"
    if p.startswith("sources/"):
        return "THIRD_PARTY", "外部快照/文献(组件记录=sources/MANIFEST.yaml;wm 快照未钉 commit、上游无 LICENSE → 不可 LOCKED);禁入构建"
    if p.startswith(("archive/", "docs/archive/")):
        return "ARCHIVE", "历史归档,只读"
    if p == "CURRENT_STATUS.md":
        return "CURRENT_AUTHORITY", "唯一当前状态入口(2026-07-16 治理令)"
    if p == "docs/world-model端到端Bug台账_给作者PR.md":
        return "ACTIVE_REFERENCE", "唯一问题台账(专项事实源;编号不携带状态,四维状态字段为准)"
    if p == "TASKS.md":
        return "ACTIVE_REFERENCE", "任务队列专项事实源,状态以 CURRENT_STATUS 为准"
    if p == "接力棒_当前值班.md":
        return "ACTIVE_REFERENCE", "交接锁,只保留单一当前块"
    if p in ("README.md", "文档索引.md"):
        return "ACTIVE_REFERENCE", "入口指针,不承载状态"
    if p == "HANDOVER_LINUX.md":
        return "ACTIVE_REFERENCE", "环境重建参考;其执行状态段=历史,已标 SUPERSEDED"
    if p.startswith("runbooks/"):
        if p.endswith((".md", ".txt", ".yaml", ".json", ".png")):
            return "FROZEN_EVIDENCE", "原始实验证据,只读;结论以 CURRENT_STATUS 指针为准"
        return "ACTIVE_REFERENCE", "实验/治理工具脚本"
    if p.startswith("docs/"):
        return "ACTIVE_REFERENCE", "设计/审计文档;dated 快照以标注日期为界"
    return "ACTIVE_REFERENCE", "-"


def classify_feat(p):
    if p.startswith("sources/"):
        return "THIRD_PARTY", "DUPLICATE 旧态:feat 无 MANIFEST.yaml 且仍含 main 已移除的损坏 gitlink;组件记录缺失;禁入构建;去重处置候选"
    if p.startswith("ros2_port/src/voxblox") or "/voxblox/" in p:
        return "THIRD_PARTY", "vendored voxblox(snt-arg@d08e9d4 基底+维护补丁;per-component license 记录缺,故 UNVERIFIED)"
    if p.startswith("ros2_port/"):
        return "CURRENT_AUTHORITY", "ROS2 迁移施工事实源(M1-M5 代码,R003 未逐行审查)"
    if p.startswith(("archive/", "docs/archive/")):
        return "ARCHIVE", "历史归档(随分支携带,以 main 为准)"
    return "ACTIVE_REFERENCE", "main 分支文件的 feat 分支副本;权威=main@HEAD"


def classify_wm(p):
    if p.startswith("third_party/") or p == ".gitmodules":
        return "THIRD_PARTY", "冻结外部实现/子仓引用;SHA 见 .gitmodules 与 pins_2026-07-14.yaml;per-component license 记录缺,故 UNVERIFIED"
    if p.startswith(("navlab/", "orchestration/", "docker/")):
        return "CURRENT_AUTHORITY", "B17-B22 实现事实源"
    if p.startswith("docs/"):
        return "ACTIVE_REFERENCE", "-"
    return "ACTIVE_REFERENCE", "-"


CLASSIFIERS = {"main": classify_main, "feat": classify_feat, "wm": classify_wm}
FIELDS = 6
VALID_CATEGORIES = {"CURRENT_AUTHORITY", "ACTIVE_REFERENCE", "FROZEN_EVIDENCE", "ARCHIVE", "THIRD_PARTY"}
VALID_AUDITS = {"VERIFIED_PASS", "VERIFIED_FAIL", "PARTIAL", "UNVERIFIED",
                "THIRD_PARTY_LOCKED", "THIRD_PARTY_UNVERIFIED"}


def die(code, msg):
    print(f"generate_manifest: {msg}", file=sys.stderr)
    sys.exit(code)


def ls_files(worktree):
    out = subprocess.run(
        ["git", "-C", worktree, "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    files = [p for p in out.split("\0") if p]
    if len(files) != len(set(files)):
        dups = sorted({p for p in files if files.count(p) > 1})
        die(5, f"git ls-files 返回重复路径: {dups[:5]}")
    return files


def head_of(worktree):
    return subprocess.run(
        ["git", "-C", worktree, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def expected_audit(repo_key, path, category):
    """audit_source 注册表重算(诚实边界:验证来源一致性,不验证审查结论本身)。"""
    if category == "THIRD_PARTY":
        return third_party_audit(repo_key, path)
    if repo_key == "wm" and path in R003_CODE_STATUS:
        return R003_CODE_STATUS[path]
    return "UNVERIFIED"


def read_manifest(path):
    """返回 (bound_commit, rows, header);header={'files','category','audit'}。格式违规 die(5)。"""
    bound = None
    header = {"files": None, "category": None, "audit": None}
    rows = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            if line.startswith("#"):
                if " HEAD=" in line:
                    bound = line.split(" HEAD=")[1].split()[0].strip()
                if " files=" in line:
                    try:
                        header["files"] = int(line.split(" files=")[1].split()[0])
                    except ValueError:
                        die(5, f"{path}:{lineno} files 统计非整数")
                for key in ("category", "audit"):
                    tag = f"# {key}: "
                    if line.startswith(tag):
                        try:
                            header[key] = {
                                kv.split("=")[0]: int(kv.split("=")[1])
                                for kv in line[len(tag):].strip().split(", ") if "=" in kv
                            }
                        except ValueError:
                            die(5, f"{path}:{lineno} {key} 统计格式错误")
                continue
            if line.startswith("path\t"):
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != FIELDS:
                die(5, f"{path}:{lineno} 字段数 {len(parts)} != {FIELDS}")
            if line != line.rstrip():
                die(5, f"{path}:{lineno} 存在尾随空白")
            if parts[2] not in VALID_CATEGORIES:
                die(5, f"{path}:{lineno} 非法 category: {parts[2]}")
            if parts[3] not in VALID_AUDITS:
                die(5, f"{path}:{lineno} 非法 audit_status: {parts[3]}")
            try:
                n = int(parts[1])
            except ValueError:
                die(5, f"{path}:{lineno} lines 非整数: {parts[1]}")
            rows.append((parts[0], n, parts[2], parts[3], parts[4]))
    if not bound:
        die(5, f"{path} 头部缺少 HEAD= 绑定 commit")
    return bound, rows, header


def ls_tree_entries(worktree, commit):
    """{path: (mode, object_sha)};commit 不可解析 die(5)。"""
    r = subprocess.run(
        ["git", "-C", worktree, "ls-tree", "-r", "-z", commit],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        die(5, f"绑定 commit 不可解析: {commit}")
    entries = {}
    for rec in r.stdout.split("\0"):
        if not rec:
            continue
        meta, pathname = rec.split("\t", 1)
        mode, _typ, sha = meta.split()
        entries[pathname] = (mode, sha)
    return entries


def blob_lines(worktree, shas):
    """批量取 blob 行数;行数语义与生成端一致(末行无换行也计 1 行)。"""
    out = {}
    uniq = list(dict.fromkeys(shas))
    if not uniq:
        return out
    proc = subprocess.run(
        ["git", "-C", worktree, "cat-file", "--batch"],
        input=("\n".join(uniq) + "\n").encode(), capture_output=True,
    )
    data = proc.stdout
    i = 0
    for sha in uniq:
        j = data.index(b"\n", i)
        header = data[i:j].decode()
        parts = header.split()
        if len(parts) < 3 or parts[1] == "missing":
            out[sha] = None
            i = j + 1
            continue
        size = int(parts[2])
        content = data[j + 1: j + 1 + size]
        n = content.count(b"\n")
        if content and not content.endswith(b"\n"):
            n += 1
        out[sha] = n
        i = j + 1 + size + 1
    return out


def verify_bound(worktree, repo_key, manifest):
    bound, rows, header = read_manifest(manifest)
    entries = ls_tree_entries(worktree, bound)
    listed = [r[0] for r in rows]
    dup = sorted({p for p in listed if listed.count(p) > 1}) if len(listed) != len(set(listed)) else []
    missing = sorted(set(entries) - set(listed))
    extra = sorted(set(listed) - set(entries))
    print(f"bound_gate: review_commit={bound[:12]} tracked_at_review={len(entries)} "
          f"manifest_rows={len(listed)} missing={len(missing)} extra={len(extra)} duplicate={len(dup)}")
    for tag, items in (("MISSING", missing), ("EXTRA", extra), ("DUPLICATE", dup)):
        for p in items[:10]:
            print(f"  {tag}: {p}")
    if missing or extra or dup:
        return 4
    classify = CLASSIFIERS[repo_key]
    facts_bad = []
    # symlink 与普通文件同语义:lines = 该路径对象 blob 的行数(symlink blob=链接目标字符串)
    blob_of = {p: entries[p][1] for (p, _n, _c, _a, _rc) in rows if entries[p][0] != "160000"}
    lines_map = blob_lines(worktree, list(blob_of.values()))
    cat_counts = {}
    aud_counts = {}
    for p, n, cat, aud, rowc in rows:
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        aud_counts[aud] = aud_counts.get(aud, 0) + 1
        if rowc != bound[:12]:
            facts_bad.append(f"row_commit {p}: {rowc} != {bound[:12]}")
        exp_cat, _note = classify(p)
        if cat != exp_cat:
            facts_bad.append(f"category {p}: {cat} != 分类器 {exp_cat}")
        exp_aud = expected_audit(repo_key, p, exp_cat)
        if aud != exp_aud:
            facts_bad.append(f"audit_source {p}: {aud} != 登记来源 {exp_aud}")
        mode = entries[p][0]
        if mode == "160000":
            if n != -1:
                facts_bad.append(f"lines {p}: gitlink 应为 -1,实为 {n}")
        else:
            want = lines_map.get(blob_of.get(p))
            if want is None or n != want:
                facts_bad.append(f"lines {p}: {n} != blob {want}")
    # 头部统计是清单公开事实:必须与数据行重算一致(防篡改)
    if header.get("files") != len(rows):
        facts_bad.append(f"header files={header.get('files')} != 数据行 {len(rows)}")
    if header.get("category") != cat_counts:
        facts_bad.append(f"header category 统计与数据行不一致")
    if header.get("audit") != aud_counts:
        facts_bad.append(f"header audit 统计与数据行不一致")
    print(f"bound_gate_facts: row_fact_violations={len(facts_bad)}")
    for msg in facts_bad[:10]:
        print(f"  FACT: {msg}")
    return 6 if facts_bad else 0


def worktree_status(worktree, exclude=frozenset()):
    """porcelain-v2 -z 解析;type-2(rename/copy)正确消费第二个 NUL 段,score 不混入路径。"""
    st = subprocess.run(["git", "-C", worktree, "status", "--porcelain=v2", "-z"],
                        capture_output=True, text=True, check=True).stdout
    toks = st.split("\0")
    untracked, missing_wt, conflict, modified = [], [], [], []
    i = 0
    while i < len(toks):
        rec = toks[i]
        i += 1
        if not rec:
            continue
        if rec.startswith("? "):
            p = rec[2:]
            if p not in exclude:
                untracked.append(p)
        elif rec.startswith("u "):
            p = rec.split(" ", 10)[10]
            if p not in exclude:
                conflict.append(p)
        elif rec.startswith("1 "):
            fields = rec.split(" ", 8)
            xy, p = fields[1], fields[8]
            if p in exclude:
                continue
            (missing_wt if "D" in xy else modified).append(p)
        elif rec.startswith("2 "):
            # 2 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <X><score> <path> NUL <origPath> NUL
            fields = rec.split(" ", 9)
            xy, p = fields[1], fields[9]
            orig = toks[i] if i < len(toks) else ""
            i += 1
            if p in exclude and orig in exclude:
                continue
            (missing_wt if "D" in xy else modified).append(f"{p} (原 {orig})")
    return untracked, missing_wt, conflict, modified


def verify_current(worktree, manifest):
    _bound, rows, _header = read_manifest(manifest)
    listed = {r[0] for r in rows}
    cur_head = head_of(worktree)
    untracked, missing_wt, conflict, modified = worktree_status(worktree)
    if conflict:
        # merge 冲突态下 ls-files 会按 stage 重复输出未合并路径,集合比较无意义:直接判 7
        print(f"current_gate: current_head={cur_head[:12]} conflict={len(conflict)}(冲突态,集合比较跳过)")
        for p2 in conflict[:10]:
            print(f"  CONFLICT: {p2}")
        return 7
    tracked = set(ls_files(worktree))
    added = sorted(tracked - listed)
    removed = sorted(listed - tracked)
    print(f"current_gate: current_head={cur_head[:12]} tracked={len(tracked)} manifest_rows={len(listed)} "
          f"added={len(added)} removed={len(removed)} untracked={len(untracked)} "
          f"missing_in_worktree={len(missing_wt)} conflict={len(conflict)} modified={len(modified)}")
    for tag, items in (("ADDED", added), ("REMOVED", removed), ("UNTRACKED", untracked),
                       ("MISSING_WT", missing_wt), ("CONFLICT", conflict), ("MODIFIED", modified)):
        for p in items[:10]:
            print(f"  {tag}: {p}")
    bad = added or removed or untracked or missing_wt or conflict or modified
    return 7 if bad else 0


def generate(worktree, repo_key, out_path):
    classify = CLASSIFIERS[repo_key]
    head = head_of(worktree)
    files = ls_files(worktree)
    for bad in files:
        if "\t" in bad or "\n" in bad:
            die(5, f"tracked 路径含制表符/换行,TSV 无法无损表示,失败关闭: {bad!r}")
    if repo_key == "wm":
        missed = [p for p in R003_CODE_STATUS if p not in set(files)]
        if missed:
            die(5, f"R003 种子路径未命中 {len(missed)} 条(种子表与仓库不符): {missed}")
    # 写前现场检查:工作树须洁净;唯一豁免 = 受控输出目标自身及其 .tmp(支持原地刷新)
    out_abs = os.path.abspath(out_path)
    wt_abs = os.path.abspath(worktree)
    exclude = set()
    if out_abs.startswith(wt_abs + os.sep):
        rel = os.path.relpath(out_abs, wt_abs)
        exclude = {rel, rel + ".tmp"}
    untracked_l, missing_l, conflict_l, modified_l = worktree_status(worktree, exclude=frozenset(exclude))
    if untracked_l or missing_l or conflict_l or modified_l:
        print(f"pre_write_check: untracked={len(untracked_l)} missing={len(missing_l)} "
              f"conflict={len(conflict_l)} modified={len(modified_l)}")
        for tag, items in (("UNTRACKED", untracked_l), ("MISSING_WT", missing_l),
                           ("CONFLICT", conflict_l), ("MODIFIED", modified_l)):
            for q in items[:10]:
                print(f"  {tag}: {q}")
        die(7, f"生成前现场不洁(受控输出目标已豁免),目标文件未被改动: {out_path}")
    rows = []
    counts = {}
    audit_counts = {}
    for p in sorted(files):
        category, note = classify(p)
        note = (note or "-").strip() or "-"
        if "\t" in note or "\n" in note:
            die(5, f"note 含制表符/换行: {p}")
        full = Path(worktree) / p
        try:
            if full.is_symlink():
                # 与验证端同一语义:计链接自身 blob(=目标路径字符串)的行数,不跟随
                content = os.readlink(full).encode()
                lines = content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0)
            else:
                lines = sum(1 for _ in open(full, "rb"))
        except OSError:
            lines = -1  # gitlink / 不可读
            note = note + ";gitlink/不可读" if note != "-" else "gitlink/不可读"
        audit = expected_audit(repo_key, p, category)
        counts[category] = counts.get(category, 0) + 1
        audit_counts[audit] = audit_counts.get(audit, 0) + 1
        row = f"{p}\t{lines}\t{category}\t{audit}\t{head[:12]}\t{note}"
        if row != row.rstrip():
            die(5, f"行尾随空白: {p}")
        rows.append(row)
    # 写临时文件 → bound 门 → 原子替换;失败零残留,目标原状
    tmp_path = out_abs + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            f.write("# R003 动作八 五态清单(提交一补正版;--verify-bound / --verify-current)\n")
            f.write(f"# worktree={worktree} HEAD={head} files={len(files)}\n")
            f.write("# category: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n")
            f.write("# audit: " + ", ".join(f"{k}={v}" for k, v in sorted(audit_counts.items())) + "\n")
            f.write("path\tlines\tcategory\taudit_status\treview_commit\tnote\n")
            f.write("\n".join(rows) + "\n")
        rc = verify_bound(worktree, repo_key, tmp_path)
        if rc != 0:
            die(rc, f"生成物未过 bound 门,临时文件已丢弃,目标未被改动: {out_path}")
        os.replace(tmp_path, out_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    print(f"{repo_key}: {len(files)} files -> {out_path} (bound 门自检通过;原子替换完成)")
    print("  category: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("  audit:    " + ", ".join(f"{k}={v}" for k, v in sorted(audit_counts.items())))
    return 0


def main():
    args = sys.argv[1:]
    if args and args[0] in ("--verify-bound", "--verify-current"):
        if len(args) != 4:
            die(2, f"用法: {args[0]} <worktree> <main|feat|wm> <manifest.tsv>")
        mode, worktree, repo_key, manifest = args
        if repo_key not in CLASSIFIERS:
            die(2, f"未知仓库类型: {repo_key}(合法: {sorted(CLASSIFIERS)})")
        if not Path(worktree).is_dir():
            die(2, f"worktree 不存在: {worktree}")
        if not Path(manifest).is_file():
            die(2, f"清单不存在: {manifest}")
        if mode == "--verify-bound":
            return verify_bound(worktree, repo_key, manifest)
        return verify_current(worktree, manifest)
    if args and args[0] == "--verify":
        die(2, "--verify 已拆分:请显式使用 --verify-bound 或 --verify-current(GOV-03)")
    if len(args) != 3:
        die(2, "用法: generate_manifest.py <worktree> <main|feat|wm> <out.tsv> 或 --verify-bound/--verify-current …")
    worktree, repo_key, out_path = args
    if repo_key not in CLASSIFIERS:
        die(2, f"未知仓库类型: {repo_key}(合法: {sorted(CLASSIFIERS)})")
    if not Path(worktree).is_dir():
        die(2, f"worktree 不存在: {worktree}")
    return generate(worktree, repo_key, out_path)


if __name__ == "__main__":
    sys.exit(main())
