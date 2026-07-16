#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三工作目录全量 tracked-path 五态清单生成器(R003 治理真实性补正版·阶段 B)。

用法:
  生成:         python3 generate_manifest.py <worktree> <main|feat|wm> <out.tsv>
  绑定门校验:   python3 generate_manifest.py --verify-bound   <worktree> <main|feat|wm> <manifest.tsv>
  工作树门校验: python3 generate_manifest.py --verify-current <worktree> <main|feat|wm> <manifest.tsv>

两个独立机器门(GOV-03,不再用一个 rc 混写两个结论):

bound_commit_closure(--verify-bound),对清单头部绑定 commit 校验:
  ①路径集合 == 该 commit 的 git tree(missing/extra/duplicate=0)
  ②每数据行 review_commit == 绑定 commit 前 12 位
  ③lines == 该 commit 中对应 blob 的行数(gitlink 行要求 -1;symlink 行跳过行数比对并计数报告)
  ④category == 分类器对该路径的重算结果(classifier 漂移/篡改检测)
  ⑤audit_status == 登记来源的重算结果(wm=R003 种子表;第三方=third_party_audit;其余=UNVERIFIED)
  ⑥字段数/枚举/重复路径/尾随空白合法

current_worktree_closure(--verify-current),对当前工作树校验:
  当前 HEAD tracked 集合相对清单的 added/removed、untracked、tracked-but-missing、
  冲突、脏改动逐类列出;任一非零 → 非零退出(GOV-02)。

退出码类别(GOV-05,每反例断言精确码):
  0=门通过  2=用法错误
  4=绑定门路径集合违规
  5=格式/引用违规(字段数/枚举/尾随空白/缺绑定头/lines 非整数/绑定 commit 不可解析/路径含 tab)
  6=绑定门行事实违规(lines/category/audit 来源/行 review_commit)
  7=工作树门违规(added/removed/untracked/missing/conflict/modified)

verifier 能证明什么 / 不能证明什么(GOV-04 诚实契约):
  能证明:清单与绑定 commit 的路径集合一致、逐行 lines 与 blob 一致、category 与分类器一致、
  audit_status 与**登记来源**(R003 种子表/第三方规则/默认 UNVERIFIED)一致、工作树无漂移。
  不能证明:audit_status 所代表的**审查结论本身**是否正确——那是人工审查的产物;
  verifier 只验证"值未被篡改且可追溯到登记来源",不验证审查质量。

生成即自检:生成后立即跑两门,任一不过则以对应退出码失败(生成要求 HEAD==绑定点且工作树干净)。
确定性:同一 HEAD 重复生成逐字节一致。tracked 路径含 tab/换行 = 失败关闭(5)。
"""
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


def third_party_audit(repo_key: str, p: str) -> str:
    # 2026-07-16 轮判定:没有任何组件同时具备五要素(upstream+钉版+license+build role+恢复法),
    # 故 LOCKED=0,全部 UNVERIFIED。升级条件与缺口清单见 governance/README.md §2。
    return "THIRD_PARTY_UNVERIFIED"


def classify_main(p: str):
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


def classify_feat(p: str):
    if p.startswith("sources/"):
        return "THIRD_PARTY", "DUPLICATE 旧态:feat 无 MANIFEST.yaml 且仍含 main 已移除的损坏 gitlink;组件记录缺失;禁入构建;去重处置候选"
    if p.startswith("ros2_port/src/voxblox") or "/voxblox/" in p:
        return "THIRD_PARTY", "vendored voxblox(snt-arg@d08e9d4 基底+维护补丁;per-component license 记录缺,故 UNVERIFIED)"
    if p.startswith("ros2_port/"):
        return "CURRENT_AUTHORITY", "ROS2 迁移施工事实源(M1-M5 代码,R003 未逐行审查)"
    if p.startswith(("archive/", "docs/archive/")):
        return "ARCHIVE", "历史归档(随分支携带,以 main 为准)"
    return "ACTIVE_REFERENCE", "main 分支文件的 feat 分支副本;权威=main@HEAD"


def classify_wm(p: str):
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


def die(code: int, msg: str):
    print(f"generate_manifest: {msg}", file=sys.stderr)
    sys.exit(code)


def ls_files(worktree: str):
    out = subprocess.run(
        ["git", "-C", worktree, "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    files = [p for p in out.split("\0") if p]
    if len(files) != len(set(files)):
        dups = sorted({p for p in files if files.count(p) > 1})
        die(5, f"git ls-files 返回重复路径: {dups[:5]}")
    return files


def head_of(worktree: str) -> str:
    return subprocess.run(
        ["git", "-C", worktree, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def expected_audit(repo_key: str, path: str, category: str) -> str:
    """audit_status 的登记来源重算(诚实边界:验证来源一致性,不验证审查结论本身)。"""
    if category == "THIRD_PARTY":
        return third_party_audit(repo_key, path)
    if repo_key == "wm" and path in R003_CODE_STATUS:
        return R003_CODE_STATUS[path]
    return "UNVERIFIED"


def read_manifest(path: str):
    """返回 (bound_commit, rows);rows=[(path,lines,category,audit,row_commit)]。格式违规 die(5)。"""
    bound = None
    rows = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            if line.startswith("#"):
                if " HEAD=" in line:
                    bound = line.split(" HEAD=")[1].split()[0].strip()
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
    return bound, rows


def ls_tree_entries(worktree: str, commit: str):
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


def blob_lines(worktree: str, shas):
    """批量取 blob 行数;行数语义与生成端 open() 逐行迭代一致。"""
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


def verify_bound(worktree: str, repo_key: str, manifest: str) -> int:
    bound, rows = read_manifest(manifest)
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
    symlink_skipped = 0
    blob_of = {p: entries[p][1] for (p, _n, _c, _a, _rc) in rows
               if entries[p][0] not in ("120000", "160000")}
    lines_map = blob_lines(worktree, list(blob_of.values()))
    for p, n, cat, aud, rowc in rows:
        if rowc != bound[:12]:
            facts_bad.append(f"row_commit {p}: {rowc} != {bound[:12]}")
        exp_cat, _note = classify(p)
        if cat != exp_cat:
            facts_bad.append(f"category {p}: {cat} != 分类器 {exp_cat}")
        exp_aud = expected_audit(repo_key, p, exp_cat)
        if aud != exp_aud:
            facts_bad.append(f"audit_source {p}: {aud} != 登记来源 {exp_aud}")
        mode = entries[p][0]
        if mode == "120000":
            symlink_skipped += 1
        elif mode == "160000":
            if n != -1:
                facts_bad.append(f"lines {p}: gitlink 应为 -1,实为 {n}")
        else:
            want = lines_map.get(blob_of.get(p))
            if want is None or n != want:
                facts_bad.append(f"lines {p}: {n} != blob {want}")
    print(f"bound_gate_facts: row_fact_violations={len(facts_bad)} symlink_lines_skipped={symlink_skipped}")
    for msg in facts_bad[:10]:
        print(f"  FACT: {msg}")
    return 6 if facts_bad else 0


def verify_current(worktree: str, manifest: str) -> int:
    _bound, rows = read_manifest(manifest)
    listed = {r[0] for r in rows}
    cur_head = head_of(worktree)
    tracked = set(ls_files(worktree))
    added = sorted(tracked - listed)
    removed = sorted(listed - tracked)
    st = subprocess.run(["git", "-C", worktree, "status", "--porcelain=v2", "-z"],
                        capture_output=True, text=True, check=True).stdout
    untracked, missing_wt, conflict, modified = [], [], [], []
    for rec in st.split("\0"):
        if not rec:
            continue
        if rec.startswith("? "):
            untracked.append(rec[2:])
        elif rec.startswith("u "):
            conflict.append(rec.rsplit("\t", 1)[-1] if "\t" in rec else rec)
        elif rec.startswith(("1 ", "2 ")):
            fields = rec.split(" ", 8)
            xy = fields[1]
            pathname = fields[8]
            if "D" in xy:
                missing_wt.append(pathname)
            else:
                modified.append(pathname)
    print(f"current_gate: current_head={cur_head[:12]} tracked={len(tracked)} manifest_rows={len(listed)} "
          f"added={len(added)} removed={len(removed)} untracked={len(untracked)} "
          f"missing_in_worktree={len(missing_wt)} conflict={len(conflict)} modified={len(modified)}")
    for tag, items in (("ADDED", added), ("REMOVED", removed), ("UNTRACKED", untracked),
                       ("MISSING_WT", missing_wt), ("CONFLICT", conflict), ("MODIFIED", modified)):
        for p in items[:10]:
            print(f"  {tag}: {p}")
    bad = added or removed or untracked or missing_wt or conflict or modified
    return 7 if bad else 0


def generate(worktree: str, repo_key: str, out_path: str) -> int:
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
    with open(out_path, "w") as f:
        f.write("# R003 动作八 五态清单(阶段 B 两门版;--verify-bound / --verify-current)\n")
        f.write(f"# worktree={worktree} HEAD={head} files={len(files)}\n")
        f.write("# category: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n")
        f.write("# audit: " + ", ".join(f"{k}={v}" for k, v in sorted(audit_counts.items())) + "\n")
        f.write("path\tlines\tcategory\taudit_status\treview_commit\tnote\n")
        f.write("\n".join(rows) + "\n")
    # 生成即自检:先 current 门(工作树必须洁净,归因清晰),再 bound 门
    rc = verify_current(worktree, out_path)
    if rc != 0:
        die(rc, f"生成后 current 门失败(工作树不洁): {out_path}")
    rc = verify_bound(worktree, repo_key, out_path)
    if rc != 0:
        die(rc, f"生成后 bound 门失败: {out_path}")
    print(f"{repo_key}: {len(files)} files -> {out_path} (两门自检通过)")
    print("  category: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("  audit:    " + ", ".join(f"{k}={v}" for k, v in sorted(audit_counts.items())))
    return 0


def main() -> int:
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
