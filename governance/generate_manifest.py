#!/usr/bin/env python3
"""三工作目录全量 tracked-path 五态清单生成器(R003 动作八 / 验收门一·G12)。

对每个 worktree 的每个 tracked path 输出 TSV:
  path, lines, category, audit_status, review_commit, note

五态 category(唯一):
  CURRENT_AUTHORITY  当前唯一权威源
  ACTIVE_REFERENCE   活跃参考资料
  FROZEN_EVIDENCE    冻结原始证据(只读,不改写)
  ARCHIVE            历史归档
  THIRD_PARTY        第三方资产(锁 SHA/来源/边界,不做逐行人审)

audit_status:
  VERIFIED_PASS / VERIFIED_FAIL / PARTIAL(来自 R003 代码清单)
  UNVERIFIED(第一方未逐行审查——默认,不得写成通过)
  THIRD_PARTY_LOCKED(第三方:只锁来源不人审)

用法: python3 generate_manifest.py <worktree> <repo_key> <out.tsv>
repo_key ∈ {main, feat, wm}
"""
import subprocess
import sys
from pathlib import Path

# R003 CODE_REVIEW_MANIFEST(30 文件)审查状态,review_commit=eab0cc6 快照
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
    "orchestration/sim/internal/tasks/templates/parm/navlab_gps_baseline.parm.tmpl": "PARTIAL",
    "orchestration/sim/internal/tasks/templates/fcu_controller_runtime.py.tmpl": "PARTIAL",
    "orchestration/sim/internal/tasks/hover_slo_policy.go": "VERIFIED_PASS",
    "orchestration/sim/internal/tasks/runtime_artifacts.go": "VERIFIED_PASS",
    "orchestration/sim/internal/tasks/runtime_artifacts_test.go": "PARTIAL",
    "orchestration/sim/internal/tasks/simulation_profiles.go": "VERIFIED_FAIL",
    "orchestration/sim/internal/tasks/simulation_profiles_test.go": "PARTIAL",
    "orchestration/sim/internal/tasks/types.go": "PARTIAL",
    "orchestration/sim/internal/tasks/workflow_summaries.go": "VERIFIED_FAIL",
    "orchestration/sim/internal/tasks/workflow_summaries_test.go": "PARTIAL",
}


def classify_main(p: str) -> tuple[str, str]:
    if p.startswith("sources/"):
        return "THIRD_PARTY", "外部源码快照(gbplanner_ros@7301b535/adaptive_obb@7dc24c9,见 sources/MANIFEST.yaml);禁入当前构建;与 gbp-feat sources/ 重复=DUPLICATE"
    if p.startswith(("archive/", "docs/archive/")):
        return "ARCHIVE", "历史归档,只读"
    if p == "CURRENT_STATUS.md":
        return "CURRENT_AUTHORITY", "唯一当前状态入口(2026-07-16 治理令)"
    if p == "docs/world-model端到端Bug台账_给作者PR.md":
        return "ACTIVE_REFERENCE", "唯一问题台账(专项事实源)"
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
    if p.startswith(("integration/", "gui/", "images/", "governance/")):
        return "ACTIVE_REFERENCE", ""
    return "ACTIVE_REFERENCE", ""


def classify_feat(p: str) -> tuple[str, str]:
    if p.startswith("sources/"):
        return "THIRD_PARTY", "DUPLICATE:与 main sources/ 同源快照;禁入构建;治理处置候选(去重)"
    if p.startswith("ros2_port/src/voxblox") or "/voxblox/" in p:
        return "THIRD_PARTY", "vendored voxblox(snt-arg@d08e9d4 基底+维护补丁);第一方补丁部分见 ros2_port/README"
    if p.startswith("ros2_port/"):
        return "CURRENT_AUTHORITY", "ROS2 迁移施工事实源(M1-M5 代码,R003 未逐行审查)"
    if p.startswith(("archive/", "docs/archive/")):
        return "ARCHIVE", "历史归档(随分支携带,以 main 为准)"
    return "ACTIVE_REFERENCE", "main 分支文件的 feat 分支副本;权威=main@HEAD"


def classify_wm(p: str) -> tuple[str, str]:
    if p.startswith("third_party/") or p in (".gitmodules",):
        return "THIRD_PARTY", "冻结外部实现/子仓引用;锁 SHA 见 .gitmodules 与 pins_2026-07-14.yaml"
    if p.startswith(("navlab/", "orchestration/", "docker/")):
        return "CURRENT_AUTHORITY", "B17-B22 实现事实源"
    if p.startswith("docs/"):
        return "ACTIVE_REFERENCE", ""
    return "ACTIVE_REFERENCE", ""


CLASSIFIERS = {"main": classify_main, "feat": classify_feat, "wm": classify_wm}


def main() -> int:
    worktree, repo_key, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    classify = CLASSIFIERS[repo_key]
    head = subprocess.run(
        ["git", "-C", worktree, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    # -z:NUL 分隔,避免非 ASCII 路径被 git 引号转义导致分类失败
    files = [
        p
        for p in subprocess.run(
            ["git", "-C", worktree, "ls-files", "-z"], capture_output=True, text=True, check=True
        ).stdout.split("\0")
        if p
    ]
    rows = []
    counts: dict[str, int] = {}
    for p in files:
        category, note = classify(p)
        full = Path(worktree) / p
        try:
            lines = sum(1 for _ in open(full, "rb"))
        except OSError:
            lines = -1  # gitlink / missing
            if lines == -1 and category != "THIRD_PARTY":
                note = (note + ";" if note else "") + "gitlink/不可读"
        if category == "THIRD_PARTY":
            audit = "THIRD_PARTY_LOCKED"
        elif repo_key == "wm" and p in R003_CODE_STATUS:
            audit = R003_CODE_STATUS[p]
        else:
            audit = "UNVERIFIED"
        counts[category] = counts.get(category, 0) + 1
        rows.append(f"{p}\t{lines}\t{category}\t{audit}\t{head[:12]}\t{note}")
    with open(out_path, "w") as f:
        f.write("# R003 动作八 五态清单\n")
        f.write(f"# worktree={worktree} HEAD={head} files={len(files)}\n")
        f.write("# 分类计数: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n")
        f.write("path\tlines\tcategory\taudit_status\treview_commit\tnote\n")
        f.write("\n".join(rows) + "\n")
    print(f"{repo_key}: {len(files)} files -> {out_path}")
    print("  " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
