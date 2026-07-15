#!/usr/bin/env python3
"""三工作目录全量 tracked-path 五态清单生成器(R003 动作八 / 验收门一;第二阶段补正版)。

用法:
  生成: python3 generate_manifest.py <worktree> <main|feat|wm> <out.tsv>
  校验: python3 generate_manifest.py --verify <worktree> <main|feat|wm> <manifest.tsv>

TSV 行格式(恰好 6 字段,note 为空写 "-",禁止尾随空白):
  path, lines, category, audit_status, review_commit, note

五态 category:CURRENT_AUTHORITY / ACTIVE_REFERENCE / FROZEN_EVIDENCE / ARCHIVE / THIRD_PARTY
audit_status:
  VERIFIED_PASS / VERIFIED_FAIL / PARTIAL   —— R003 代码清单判定(仅 wm 30 文件)
  UNVERIFIED                                 —— 第一方未逐行审查(默认,不得写成通过)
  THIRD_PARTY_LOCKED      —— 第三方且组件记录五要素齐备(upstream+钉版+license+构建角色+恢复法)
  THIRD_PARTY_UNVERIFIED  —— 第三方但锁定证据不完整(默认;2026-07-16 轮 LOCKED=0,
                              缺口:wm 快照未钉 commit 且上游无 LICENSE;feat sources 无 MANIFEST
                              且含遗留损坏 gitlink;wm 子仓缺 per-component license;论文无 license 概念)
路径含制表符/换行 = 失败关闭(退出码 5),不静默接受。
--verify 语义:对清单头部记录的绑定 commit(review_commit)做 ls-tree 集合相等判定(通过条件);
同时报告当前 HEAD 相对绑定 commit 的路径增量(信息项,不判失败)。

生成即自校验(校验失败非零退出,不落盘半成品):
  参数/仓库类型合法、路径无重复、字段数=6、无尾随空白、非 ASCII 路径经 NUL 通道无损、
  wm 的 30 个 R003 种子路径全部命中、写盘后回读集合 == git ls-files 集合(missing/extra/dup=0)。
--verify 对既有清单做同样的集合闭包检查(用于发现"清单已过期"):
  退出码 0=闭包成立;4=集合不等(打印 missing/extra/duplicate);5=格式错误;2=参数错误。
确定性:同一 HEAD 重复生成输出逐字节一致(排序与统计均确定;由 test_generate_manifest.sh 断言)。
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

# 第三方"锁定"判定:只有能映射到完整 pin 记录(来源+SHA+许可证+构建角色)的文件才 LOCKED。
# 现状:main/feat 的 sources/ 由 sources/MANIFEST.yaml 承载四要素 → LOCKED;
# 其余第三方(wm gitlink、feat vendored voxblox 等)缺 per-component 许可证记录 → UNVERIFIED。
def third_party_audit(repo_key: str, p: str) -> str:
    # 2026-07-16 轮判定:没有任何组件同时具备五要素(upstream+钉版+license+build role+恢复法),
    # 故 LOCKED=0,全部 UNVERIFIED。升级条件与缺口清单见 governance/README.md。
    return "THIRD_PARTY_UNVERIFIED"


def classify_main(p: str) -> tuple[str, str]:
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


def classify_feat(p: str) -> tuple[str, str]:
    if p.startswith("sources/"):
        return "THIRD_PARTY", "DUPLICATE 旧态:feat 无 MANIFEST.yaml 且仍含 main 已移除的损坏 gitlink;组件记录缺失;禁入构建;去重处置候选"
    if p.startswith("ros2_port/src/voxblox") or "/voxblox/" in p:
        return "THIRD_PARTY", "vendored voxblox(snt-arg@d08e9d4 基底+维护补丁;per-component license 记录缺,故 UNVERIFIED)"
    if p.startswith("ros2_port/"):
        return "CURRENT_AUTHORITY", "ROS2 迁移施工事实源(M1-M5 代码,R003 未逐行审查)"
    if p.startswith(("archive/", "docs/archive/")):
        return "ARCHIVE", "历史归档(随分支携带,以 main 为准)"
    return "ACTIVE_REFERENCE", "main 分支文件的 feat 分支副本;权威=main@HEAD"


def classify_wm(p: str) -> tuple[str, str]:
    if p.startswith("third_party/") or p == ".gitmodules":
        return "THIRD_PARTY", "冻结外部实现/子仓引用;SHA 见 .gitmodules 与 pins_2026-07-14.yaml;per-component license 记录缺,故 UNVERIFIED"
    if p.startswith(("navlab/", "orchestration/", "docker/")):
        return "CURRENT_AUTHORITY", "B17-B22 实现事实源"
    if p.startswith("docs/"):
        return "ACTIVE_REFERENCE", "-"
    return "ACTIVE_REFERENCE", "-"


CLASSIFIERS = {"main": classify_main, "feat": classify_feat, "wm": classify_wm}
FIELDS = 6


def die(code: int, msg: str) -> None:
    print(f"generate_manifest: {msg}", file=sys.stderr)
    sys.exit(code)


def ls_files(worktree: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", worktree, "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    files = [p for p in out.split("\0") if p]
    dups = {p for p in files if files.count(p) > 1} if len(files) != len(set(files)) else set()
    if dups:
        die(5, f"git ls-files 返回重复路径: {sorted(dups)[:5]}")
    return files


def head_of(worktree: str) -> str:
    return subprocess.run(
        ["git", "-C", worktree, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


VALID_CATEGORIES = {"CURRENT_AUTHORITY", "ACTIVE_REFERENCE", "FROZEN_EVIDENCE", "ARCHIVE", "THIRD_PARTY"}
VALID_AUDITS = {"VERIFIED_PASS", "VERIFIED_FAIL", "PARTIAL", "UNVERIFIED",
                "THIRD_PARTY_LOCKED", "THIRD_PARTY_UNVERIFIED"}


def read_manifest(path: str) -> tuple[str | None, list[str]]:
    """返回 (绑定 commit, 路径列表);同时校验字段数/尾随空白/分类与状态枚举。"""
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
            rows.append(parts[0])
    return bound, rows


def ls_tree_at(worktree: str, commit: str) -> list[str]:
    r = subprocess.run(
        ["git", "-C", worktree, "ls-tree", "-r", "--name-only", "-z", commit],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        die(5, f"绑定 commit 不可解析: {commit}")
    return [p for p in r.stdout.split("\0") if p]


def verify_sets(worktree: str, manifest: str) -> int:
    """通过条件 = 清单集合与其绑定 commit 的 ls-tree 集合严格相等;
    另以信息项报告当前 HEAD 相对绑定 commit 的路径增量(不判失败)。"""
    bound, listed = read_manifest(manifest)
    if not bound:
        die(5, f"{manifest} 头部缺少 HEAD= 绑定 commit")
    tracked = ls_tree_at(worktree, bound)
    dup = sorted({p for p in listed if listed.count(p) > 1}) if len(listed) != len(set(listed)) else []
    tracked_set, listed_set = set(tracked), set(listed)
    missing = sorted(tracked_set - listed_set)
    extra = sorted(listed_set - tracked_set)
    cur_head = head_of(worktree)
    cur_set = set(ls_files(worktree))
    added = sorted(cur_set - tracked_set)
    removed = sorted(tracked_set - cur_set)
    print(
        f"closure: review_commit={bound[:12]} tracked_at_review={len(tracked)} "
        f"manifest_rows={len(listed)} missing={len(missing)} extra={len(extra)} duplicate={len(dup)}"
    )
    print(
        f"delta_vs_current: current_head={cur_head[:12]} added={len(added)} removed={len(removed)}"
        + ("" if cur_head == bound else "(绑定 commit ≠ 当前 HEAD)")
    )
    for tag, items in (("MISSING", missing), ("EXTRA", extra), ("DUPLICATE", dup),
                       ("ADDED_SINCE_REVIEW", added), ("REMOVED_SINCE_REVIEW", removed)):
        for p in items[:10]:
            print(f"  {tag}: {p}")
    return 0 if not missing and not extra and not dup else 4


def generate(worktree: str, repo_key: str, out_path: str) -> int:
    classify = CLASSIFIERS[repo_key]
    head = head_of(worktree)
    files = ls_files(worktree)
    if repo_key == "wm":
        missed = [p for p in R003_CODE_STATUS if p not in set(files)]
        if missed:
            die(5, f"R003 种子路径未命中 {len(missed)} 条(种子表与仓库不符): {missed}")
    for bad in files:
        if "\t" in bad or "\n" in bad:
            die(5, f"tracked 路径含制表符/换行,TSV 无法无损表示,失败关闭: {bad!r}")
    rows = []
    counts: dict[str, int] = {}
    audit_counts: dict[str, int] = {}
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
        if category == "THIRD_PARTY":
            audit = third_party_audit(repo_key, p)
        elif repo_key == "wm" and p in R003_CODE_STATUS:
            audit = R003_CODE_STATUS[p]
        else:
            audit = "UNVERIFIED"
        counts[category] = counts.get(category, 0) + 1
        audit_counts[audit] = audit_counts.get(audit, 0) + 1
        row = f"{p}\t{lines}\t{category}\t{audit}\t{head[:12]}\t{note}"
        if row != row.rstrip():
            die(5, f"行尾随空白: {p}")
        rows.append(row)
    with open(out_path, "w") as f:
        f.write("# R003 动作八 五态清单(第二阶段补正版;--verify 可随时校验闭包)\n")
        f.write(f"# worktree={worktree} HEAD={head} files={len(files)}\n")
        f.write("# category: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n")
        f.write("# audit: " + ", ".join(f"{k}={v}" for k, v in sorted(audit_counts.items())) + "\n")
        f.write("path\tlines\tcategory\taudit_status\treview_commit\tnote\n")
        f.write("\n".join(rows) + "\n")
    # 写盘后立即回读自校验闭包
    rc = verify_sets(worktree, out_path)
    if rc != 0:
        die(4, f"生成后自校验失败: {out_path}")
    print(f"{repo_key}: {len(files)} files -> {out_path} (self-verified)")
    print("  category: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("  audit:    " + ", ".join(f"{k}={v}" for k, v in sorted(audit_counts.items())))
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--verify":
        if len(args) != 4:
            die(2, "用法: --verify <worktree> <main|feat|wm> <manifest.tsv>")
        worktree, repo_key, manifest = args[1], args[2], args[3]
        if repo_key not in CLASSIFIERS:
            die(2, f"未知仓库类型: {repo_key}(合法: {sorted(CLASSIFIERS)})")
        if not Path(manifest).is_file():
            die(2, f"清单不存在: {manifest}")
        return verify_sets(worktree, manifest)
    if len(args) != 3:
        die(2, "用法: generate_manifest.py <worktree> <main|feat|wm> <out.tsv> 或 --verify ...")
    worktree, repo_key, out_path = args
    if repo_key not in CLASSIFIERS:
        die(2, f"未知仓库类型: {repo_key}(合法: {sorted(CLASSIFIERS)})")
    if not Path(worktree).is_dir():
        die(2, f"worktree 不存在: {worktree}")
    return generate(worktree, repo_key, out_path)


if __name__ == "__main__":
    sys.exit(main())
