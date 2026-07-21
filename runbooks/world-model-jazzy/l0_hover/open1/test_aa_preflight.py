#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 AA-PF-04 · preflight gate 门(硬门条件 + 真实性门 + 不启动证明)。

expected 来源=04.2/04.3/04.5-04.8 规则文本与 2026-07-20 真实性补正令。零真实系统。
运行前置:操作员 shell 已 source /opt/ros/jazzy/setup.bash(04.6 正例是裁决后
当前现实;未 source 时本套件如实红,不伪装通过)。
裁决前"宿主无 rclpy"状态保留为 04.5 历史反例(剥离 ROS 环境的子进程复现,
环境无关);不再作为当前预期。SKIP 恒=0,不存在跳过路径。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import telemetry_contract as C  # noqa: E402
import aa_launch as L  # noqa: E402

FAIL = 0
RAN = 0
EAB = "eab0cc6f0d5460cbd2cf20fe9b83857549a1e6b5"
NEW = "6d412a11f152428b5e08e42e66c1583d4dce4219"
MAIN_REPO = os.path.realpath(os.path.join(HERE, "..", "..", "..", ".."))
WM_REPO = "/home/ai4s/projects/world-model"
# 格式合法的 fixture digest(preflight 层验 schema+一致性;digest 与本机 docker
# 现值的比对属 aa_launch producer guard/E1 正式接线,见 test_aa_launch.py)
DIG = "sha256:" + "ab" * 32
H64 = "cd" * 32  # 合法 sha256 hex 形状的替身(用于"顶层不一致"类反例)


def ck(name, got, want):
    global FAIL, RAN
    RAN += 1
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def run_pf(plan, output=None, env=None, main_repo=None):
    fx = tempfile.mktemp(suffix=".json")
    open(fx, "w").write(json.dumps(plan))
    args = [sys.executable, os.path.join(HERE, "aa_preflight.py"), "--input", fx]
    if output:
        args += ["--output", output]
    if main_repo:
        args += ["--main-repo", main_repo]
    cp = subprocess.run(args, capture_output=True, text=True, timeout=120, env=env)
    try:
        return cp.returncode, json.loads(cp.stdout)
    finally:
        os.unlink(fx)


def main_head():
    return subprocess.run(["git", "-C", MAIN_REPO, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def materialized_plan(**over):
    """真实物化计划:canonical config+runtime plan 原子落盘 → 文件字节独立 hash。
    这是 04.6 正例与全部单变量反例的共同底座(先真后破)。"""
    run_root = tempfile.mkdtemp(prefix="aa_pf_")
    mat = L.materialize(
        run_root,
        {"task_id": "hover", "map_id": "iris_maze", "timeout_sec": 1500,
         "ros_domain_id": "7", "telemetry_arms": ["OFF", "OFF", "ON", "ON"]},
        {"services": ["gazebo-headless", "ardupilot-sitl", "mavlink-router",
                      "slam-cartographer", "companion"],
         "companion_image": f"navlab/companion:jazzy-{NEW[:12]}"})
    import argparse
    import batch_lifecycle as BL
    iw = BL.identity_wait_sec(argparse.Namespace(
        startup_budget=100.0, duration=25.0, per_run_teardown=0.5,
        inter_run_gap=0.25))
    plan = L.build_frozen_plan(
        mat, main_commit=main_head(), world_model_commit=NEW,
        companion_digest=DIG, identity_wait_sec=iw,
        owner_approvals={"ros_env_plan": True, "readiness_topic": True,
                         "container_identity_upstream": True})
    plan.update(over)
    return plan


def fixture_main_repo(dirty):
    """fixture 主仓(环境无关:正例/脏树反例都不依赖真实主仓的瞬时工作树状态;
    真实主仓的 READY 由正式入口 aa_launch 在实际启动时把关)。返回 (path, head)。"""
    repo = tempfile.mkdtemp(prefix="aa_fxmain_")
    subprocess.run(["git", "init", "-q", repo], check=True)
    open(os.path.join(repo, "f.txt"), "w").write("v1\n")
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c",
                    "user.email=t@t", "commit", "-qm", "x"], check=True)
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if dirty:
        open(os.path.join(repo, "f.txt"), "w").write("v2-dirty\n")
    return repo, head


def plan_for_fixture_main(head, **over):
    p = materialized_plan(main_commit=head, **over)
    for pr in p["pair_plan"]:
        pr["off"]["main_commit"] = head
        pr["on"]["main_commit"] = head
    return p


def stripped_ros_env():
    """剥离 ROS 环境的子进程 env:复现裁决前/未 source 的宿主(环境无关)。"""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH",
                        "COLCON_PREFIX_PATH", "LD_LIBRARY_PATH", "ROS_DISTRO",
                        "ROS_VERSION", "ROS_PYTHON_VERSION")
           and not k.startswith("RMW_")}
    env["PATH"] = "/usr/bin:/bin"
    return env


print("======== 04.0 套件前置:sourced 环境(裁决后现实)========")
rc_rclpy = subprocess.run([sys.executable, "-c", "import rclpy"],
                          capture_output=True).returncode
ck("测试环境已 source(rclpy 可导入;未 source=如实红)", rc_rclpy, 0)

print("======== 04.5 历史反例(裁决前:未 source → 失败关闭)========")
rc, out = run_pf(materialized_plan(), env=stripped_ros_env())
ck("状态∈四枚举", out["preflight_status"] in ("READY", "BLOCKED", "CORRUPT",
                                              "OWNER_DECISION_REQUIRED"), True)
ck("未 source 禁止 READY(失败关闭)", out["preflight_status"] != "READY", True)
ck("未 source:acceptance_eligible=false", out["acceptance_eligible"], False)
ck("未 source:rc=1(非 READY)", rc, 1)
ck("AA-PF-01 在列(rclpy)", "host_rclpy_available" in set(out["failed_checks"]), True)
ck("owner_decisions 列出 ros_env_plan",
   any(d["decision"] == "ros_env_plan" for d in out["owner_decisions_required"]), True)

print("======== 04.6 当前正例(裁决后 sourced+真实物化计划 → READY)========")
fx_clean, fx_clean_head = fixture_main_repo(dirty=False)
rc, out = run_pf(plan_for_fixture_main(fx_clean_head), main_repo=fx_clean)
ck("裁决后+真实冻结字段 → READY", out["preflight_status"], "READY")
ck("acceptance_eligible=true", out["acceptance_eligible"], True)
ck("rc=0", rc, 0)
ck("failed_checks 空", out["failed_checks"], [])
ck("owner_decisions_required 空", out["owner_decisions_required"], [])
ck("必备输出字段齐", all(k in out for k in
   ("preflight_status", "checks", "failed_checks", "owner_decisions_required",
    "warnings", "main_commit", "world_model_commit", "generated_at",
    "acceptance_eligible")), True)

print("======== 04.7 真实性硬门(占位符/schema/物化/一致性 → 非 READY)========")
for bad in ("", "PLAN_PENDING", "PLAN_PENDING_REAL_RUN", "UNKNOWN", "TODO",
            "deadbeefcafe", "AB" * 32, "cd" * 31 + "c", None):
    rc, out = run_pf(materialized_plan(runtime_plan_hash=bad))
    ck(f"runtime_plan_hash={bad!r:.24} → schema 拒绝+非 READY",
       ("runtime_plan_hash_schema_valid" in out["failed_checks"],
        out["preflight_status"] != "READY", rc), (True, True, 1))
for bad in ("", "PLAN_PENDING_REAL_RUN", "cafe", None):
    rc, out = run_pf(materialized_plan(config_hash=bad))
    ck(f"config_hash={bad!r:.24} → schema 拒绝+非 READY",
       ("config_hash_schema_valid" in out["failed_checks"],
        out["preflight_status"] != "READY"), (True, True))
for bad_digs in ({"companion": "sha256:img"}, {"companion": "ab" * 32},
                 {"companion": "sha256:" + "AB" * 32}, {}, None,
                 {"companion": "sha256:" + "ab" * 32, "extra": "TODO"}):
    rc, out = run_pf(materialized_plan(image_digests=bad_digs))
    ck(f"image_digests={str(bad_digs)[:38]!r} → 拒绝",
       "image_digests_valid" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(runtime_plan_path="/nonexistent/rp.json"))
ck("runtime plan 未物化(文件不存在) → 打断",
   "runtime_plan_materialized" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(config_path=None))
ck("config 未物化(路径缺失) → 打断",
   "config_materialized" in out["failed_checks"], True)
p = materialized_plan()
with open(p["runtime_plan_path"], "ab") as f:
    f.write(b" tampered")
rc, out = run_pf(p)
ck("物化文件在 hash 之后被改动 → 独立重算击穿",
   ("runtime_plan_hash_matches_file" in out["failed_checks"],
    out["preflight_status"] != "READY"), (True, True))
p = materialized_plan()
for pr in p["pair_plan"]:
    pr["off"]["config_hash"] = H64
    pr["on"]["config_hash"] = H64
rc, out = run_pf(p)
ck("四 run 内部一致但 config_hash≠顶层 → 拒绝",
   "pair_hashes_consistent_with_plan" in out["failed_checks"], True)
p = materialized_plan()
for pr in p["pair_plan"]:
    pr["off"]["image_digests"] = "sha256:" + "ee" * 32
    pr["on"]["image_digests"] = "sha256:" + "ee" * 32
rc, out = run_pf(p)
ck("四 run digest≠顶层 companion → 拒绝",
   "pair_hashes_consistent_with_plan" in out["failed_checks"], True)
p = materialized_plan()
p["pair_plan"][1]["on"]["run_id"] = p["pair_plan"][0]["off"]["run_id"]
rc, out = run_pf(p)
ck("run_id 重复 → 拒绝", "run_ids_unique_nonempty" in out["failed_checks"], True)

print("======== 04.8 脏工作树 → BLOCKED(fixture 仓,不碰真实仓)========")
fxrepo, fx_head = fixture_main_repo(dirty=True)
rc, out = run_pf(plan_for_fixture_main(fx_head), main_repo=fxrepo)
ck("脏树 → BLOCKED", out["preflight_status"], "BLOCKED")
ck("main_worktree_clean 在列", "main_worktree_clean" in out["failed_checks"], True)
ck("脏树:rc=1", rc, 1)

print("======== 04.3 硬门逐项(单变量打断)========")
rc, out = run_pf(materialized_plan(main_commit="0" * 40))
ck("main SHA 不符 → 非 READY + 在列",
   ("main_sha_match" in out["failed_checks"]), True)
rc, out = run_pf(materialized_plan(baseline_class="HISTORICAL_REPRODUCTION"))
ck("baseline_class 与现场 wm SHA 不符 → 打断",
   "wm_sha_matches_baseline_class" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(ros_readiness_topic="/navlab/startup_readiness/status"))
ck("未验证 readiness topic → 打断",
   "readiness_topic_decided_and_verified" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(system_ros_domain=None))
ck("system domain 未知 → 打断", "ros_domains_configured" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(sidecar_ros_domain="8"))
ck("双域不一致 → 打断", "ros_domains_equal" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(container_identity_source="docker_ps_guess"))
ck("容器身份非权威来源 → 打断",
   "container_identity_live_pipeline" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(owner_approvals={
    "ros_env_plan": True, "readiness_topic": True,
    "container_identity_upstream": False}))
ck("上游契约未批 → OWNER_DECISION_REQUIRED 在列",
   any(d["decision"] == "container_identity_upstream"
       for d in out["owner_decisions_required"]), True)
rc, out = run_pf(materialized_plan(evidence_contract_version="old.v0"))
ck("evidence contract 版本不符 → 打断",
   "evidence_contract_current" in out["failed_checks"], True)
p = materialized_plan()
p["pair_plan"] = p["pair_plan"][:1]
rc, out = run_pf(p)
ck("样本≠OFF×2+ON×2 → 打断", "sample_plan_off2_on2" in out["failed_checks"], True)
p = materialized_plan()
p["pair_plan"][0]["on"]["config_hash"] = "beef"
rc, out = run_pf(p)
ck("配对冻结字段不符 → 打断",
   "pair_plan_frozen_fields_match" in out["failed_checks"], True)
rc, out = run_pf(materialized_plan(real_validation_claims={"real_ros_graph": True}))
ck("真实验证被冒称完成 → 打断",
   "no_fake_real_validation_claims" in out["failed_checks"], True)
rc, out = run_pf({"broken": True})
ck("残缺计划 → 非 READY", out["preflight_status"] != "READY", True)

print("======== 04.4 门不启动任何东西 ========")
src = open(os.path.join(HERE, "aa_preflight.py")).read()
for pat in ("docker start", "docker stop", "docker restart", "docker exec",
            "docker run", "rclpy.init", "navlab-sim", "telemetry_sidecar.py"):
    ck(f"源码零调用: {pat!r}", pat in src, False)
before_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout
tmpout = tempfile.mkdtemp()
outfile = os.path.join(tmpout, "pf.json")
before_files = set(os.listdir(tmpout))
mdirty = subprocess.run(["git", "-C", MAIN_REPO, "status", "--porcelain"],
                        capture_output=True, text=True).stdout
rc, out = run_pf(materialized_plan(), output=outfile)
after_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout
ck("运行中容器集合不变", after_docker, before_docker)
ck("仅生成指定输出文件", sorted(set(os.listdir(tmpout)) - before_files), ["pf.json"])
mdirty2 = subprocess.run(["git", "-C", MAIN_REPO, "status", "--porcelain"],
                         capture_output=True, text=True).stdout
ck("不改仓库", mdirty2, mdirty)
wdirty = subprocess.run(["git", "-C", WM_REPO, "status", "--porcelain"],
                        capture_output=True, text=True).stdout
ck("不写 world-model", wdirty, "")

print("================================")
print(f"结果: RAN={RAN} PASS={RAN - FAIL} FAIL={FAIL} SKIP=0(无跳过路径)")
sys.exit(1 if FAIL else 0)
