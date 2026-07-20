#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 · aa_launch 正式入口门:物化→真实 hash→preflight→producer guard。

expected 来源=2026-07-20 真实性补正令第三包条款。零真实系统:producer=计数
fixture,digest_provider=fixture;本套件证明"占位符/preflight 后突变 → producer
启动次数恒为 0","完整真实计划 → 恰好启动一次"。
运行前置:sourced(READY 正分支需要宿主 rclpy;未 source 如实红)。SKIP 恒=0。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import aa_launch as L  # noqa: E402
import aa_preflight as PF  # noqa: E402

FAIL = 0
RAN = 0
NEW = "9a1ce95c56e2901aad062e31c9d4a8006474b0fc"
WM_REPO = "/home/ai4s/projects/world-model"
DIG = "sha256:" + "ab" * 32


def ck(name, got, want):
    global FAIL, RAN
    RAN += 1
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def fixture_main_repo():
    repo = tempfile.mkdtemp(prefix="aa_l_main_")
    subprocess.run(["git", "init", "-q", repo], check=True)
    open(os.path.join(repo, "f.txt"), "w").write("v1\n")
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c",
                    "user.email=t@t", "commit", "-qm", "x"], check=True)
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    return repo, head


class Producer:
    def __init__(self):
        self.calls = 0

    def __call__(self, plan):
        self.calls += 1


def fixture_approval_file(plan, digest=DIG, **over):
    """fixture 审批(显式 fixture_test_only;真实审批只能由负责人产生,本测试不生成)。"""
    ap = {"schema_version": L.APPROVAL_SCHEMA_VERSION,
          "approval_purpose": L.APPROVAL_PURPOSE, "approval_state": "APPROVED",
          "fixture_test_only": True, "approved_by": "FIXTURE-test-only",
          "approved_at": "2026-07-20T00:00:00Z",
          "main_commit": plan["main_commit"],
          "world_model_commit": plan["world_model_commit"],
          "config_hash": plan["config_hash"],
          "runtime_plan_hash": plan["runtime_plan_hash"],
          "image_digest": digest, "ros_domain": plan["sidecar_ros_domain"],
          "sample_plan": "OFF2_ON2"}
    ap.update(over)
    p = tempfile.mktemp(suffix="_approval.json")
    open(p, "w").write(json.dumps(ap))
    return p


def repo_state_for(head, wm=NEW, main_dirty=0, wm_dirty=0):
    return lambda: {"main_head": head, "wm_head": wm,
                    "main_dirty": main_dirty, "wm_dirty": wm_dirty}


def launch(plan, prod, head, digest_fn=lambda name: DIG, approval=None,
           allow_fixture=True, repo_state=None, repo=None, hook=None):
    return L.launch_aa(plan, prod, digest_fn,
                       approval_path=(approval if approval is not None
                                      else fixture_approval_file(plan)),
                       repo_state=repo_state or repo_state_for(head),
                       main_repo=repo, wm_repo=WM_REPO,
                       allow_fixture_approval=allow_fixture,
                       _post_preflight_hook=hook)


def real_plan(repo_head, **over):
    run_root = tempfile.mkdtemp(prefix="aa_l_run_")
    mat = L.materialize(
        run_root,
        {"task_id": "hover", "map_id": "iris_maze", "timeout_sec": 1500,
         "ros_domain_id": "7", "telemetry_arms": ["OFF", "OFF", "ON", "ON"]},
        {"services": ["gazebo-headless", "ardupilot-sitl", "mavlink-router",
                      "slam-cartographer", "companion"],
         "companion_image": f"navlab/companion:jazzy-{NEW[:12]}"})
    plan = L.build_frozen_plan(
        mat, main_commit=repo_head, world_model_commit=NEW,
        companion_digest=DIG, identity_wait_sec=135.75,
        owner_approvals={"ros_env_plan": True, "readiness_topic": True,
                         "container_identity_upstream": True})
    for pr in plan["pair_plan"]:
        pr["off"]["main_commit"] = repo_head
        pr["on"]["main_commit"] = repo_head
    plan.update(over)
    return plan


print("======== 05.0 前置:sourced ========")
ck("测试环境已 source(rclpy 可导入;未 source=如实红)",
   subprocess.run([sys.executable, "-c", "import rclpy"],
                  capture_output=True).returncode, 0)

print("======== 05.1 物化:原子落盘+独立 hash ========")
root = tempfile.mkdtemp(prefix="aa_l_mat_")
cfg = {"b": 2, "a": 1}
rtp = {"services": ["x"], "n": 1}
mat = L.materialize(root, cfg, rtp)
ck("config hash=64 位小写 hex", bool(PF.SHA256_HEX.match(mat["config_hash"])), True)
ck("runtime plan hash=64 位小写 hex",
   bool(PF.SHA256_HEX.match(mat["runtime_plan_hash"])), True)
ck("hash=文件字节独立重算", PF._sha256_file(mat["config_path"]), mat["config_hash"])
ck("canonical 字节确定性(重物化同 hash)",
   L.materialize(tempfile.mkdtemp(prefix="aa_l_mat2_"), cfg, rtp)["config_hash"],
   mat["config_hash"])
ck("键序无关(canonical 排序)",
   L.sha256_bytes(L.canonical_json_bytes({"a": 1, "b": 2})),
   L.sha256_bytes(L.canonical_json_bytes({"b": 2, "a": 1})))
ck("无 .tmp 残留", [f for f in os.listdir(root) if f.endswith(".tmp")], [])
ck("落盘内容可回读一致", json.load(open(mat["config_path"])), cfg)

print("======== 05.2 完整真实计划+有效授权 → READY → producer 恰好启动一次 ========")
repo, head = fixture_main_repo()
prod = Producer()
rec = launch(real_plan(head), prod, head, repo=repo)
ck("preflight=READY", rec["preflight_status"], "READY")
ck("producer 启动次数=1", prod.calls, 1)
ck("record.producer_started=1", rec["producer_started"], 1)
ck("无拒绝原因", rec["refusal_reasons"], [])
ck("fixture 审批在 record 显式标注", rec["approval_fixture_test_only"], True)
ck("approval_sha256 入档(64hex)", len(rec.get("approval_sha256", "")), 64)

print("======== 05.3 占位符计划 → producer 启动次数=0 ========")
for bad_key, bad_val in (("runtime_plan_hash", "PLAN_PENDING_REAL_RUN"),
                         ("config_hash", "PLAN_PENDING"),
                         ("runtime_plan_hash", ""),
                         ("config_hash", "TODO")):
    prod = Producer()
    rec = launch(real_plan(head, **{bad_key: bad_val}), prod, head, repo=repo)
    ck(f"{bad_key}={bad_val!r:.20} → 非 READY 且 producer=0",
       (rec["preflight_status"] != "READY", prod.calls,
        rec["producer_started"]), (True, 0, 0))
    ck(f"{bad_key} 占位:拒绝原因含 preflight_not_ready",
       "preflight_not_ready" in rec["refusal_reasons"], True)

print("======== 05.3b 授权机器门(库层;直接调用库也绕不过)========")
prod = Producer()
rec = launch(real_plan(head), prod, head, repo=repo, approval="/nonexistent/ap.json")
ck("approval 缺失 → producer=0",
   (prod.calls, "approval_missing" in rec["refusal_reasons"]), (0, True))
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo,
             approval=fixture_approval_file(p, runtime_plan_hash="ee" * 32))
ck("approval runtime_plan_hash 不符 → producer=0",
   (prod.calls, "approval_runtime_plan_hash_mismatch" in rec["refusal_reasons"]), (0, True))
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo,
             approval=fixture_approval_file(p, approval_state="REVOKED"))
ck("approval_state=REVOKED → producer=0",
   (prod.calls, "approval_state_not_approved" in rec["refusal_reasons"]), (0, True))
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo,
             approval=fixture_approval_file(p, approval_purpose="SOMETHING_ELSE"))
ck("approval 用途错 → producer=0",
   (prod.calls, "approval_purpose_mismatch" in rec["refusal_reasons"]), (0, True))
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo, allow_fixture=False)
ck("fixture 审批未显式放行 → producer=0",
   (prod.calls, "fixture_approval_not_allowed" in rec["refusal_reasons"]), (0, True))
badp = tempfile.mktemp(suffix=".json")
open(badp, "w").write("{corrupt")
prod = Producer()
rec = launch(real_plan(head), prod, head, repo=repo, approval=badp)
ck("approval 损坏 → producer=0",
   (prod.calls, "approval_unparsable" in rec["refusal_reasons"]), (0, True))
try:
    L.launch_aa(real_plan(head), Producer(), lambda name: DIG)
    got = "被放行"
except TypeError:
    got = "TypeError(keyword-only 必填)"
ck("不带 approval/repo_state 调 launch_aa → TypeError(库层强制)",
   got, "TypeError(keyword-only 必填)")

print("======== 05.4 preflight 后突变 → producer 启动次数=0 ========")
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo,
             hook=lambda: open(p["config_path"], "ab").write(b"x"))
ck("preflight 后改 config → producer=0", prod.calls, 0)
ck("原因=config_hash_changed_after_preflight",
   "config_hash_changed_after_preflight" in rec["refusal_reasons"], True)
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo,
             hook=lambda: open(p["runtime_plan_path"], "ab").write(b"x"))
ck("preflight 后改 runtime plan → producer=0", prod.calls, 0)
ck("原因=runtime_plan_hash_changed_after_preflight",
   "runtime_plan_hash_changed_after_preflight" in rec["refusal_reasons"], True)
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo, digest_fn=lambda name: "sha256:" + "ee" * 32,
             approval=fixture_approval_file(p, image_digest="sha256:" + "ee" * 32))
ck("preflight 后镜像 digest 现值不符 → producer=0", prod.calls, 0)
ck("digest 伪造被拒(approval 绑计划 digest 先拒;伪造 approval+现值也过不了防御纵深)",
   ("approval_image_digest_mismatch_plan" in rec["refusal_reasons"]
    or "image_digest_changed_after_preflight" in rec["refusal_reasons"]), True)
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo,
             hook=lambda: os.unlink(p["runtime_plan_path"]))
ck("preflight 后计划文件被删 → producer=0", prod.calls, 0)
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo, repo_state=repo_state_for("0" * 40))
ck("HEAD 现值≠计划 → producer=0",
   (prod.calls, "main_head_changed_after_preflight" in rec["refusal_reasons"]), (0, True))
prod = Producer()
p = real_plan(head)
rec = launch(p, prod, head, repo=repo, repo_state=repo_state_for(head, wm_dirty=2))
ck("wm 树 launch 时刻脏 → producer=0",
   (prod.calls, "wm_worktree_dirty_at_launch" in rec["refusal_reasons"]), (0, True))
prod = Producer()
p = real_plan(head)
rec = L.launch_aa(p, prod, lambda name: DIG,
                  approval_path=fixture_approval_file(p), repo_state=None,
                  main_repo=repo, wm_repo=WM_REPO, allow_fixture_approval=True)
ck("repo_state 缺失 → producer=0(fail-closed,非默认放行)",
   (prod.calls, "repo_state_provider_missing" in rec["refusal_reasons"]), (0, True))

print("======== 05.5 入口自身零启动+零污染 ========")
src = open(os.path.join(HERE, "aa_launch.py")).read()
for pat in ("docker start", "docker stop", "docker restart", "docker exec",
            "docker run", "rclpy.init", "navlab-sim", "telemetry_sidecar.py",
            "subprocess"):
    ck(f"aa_launch 源码零调用: {pat!r}", pat in src, False)
before_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True,
                               text=True).stdout
prod = Producer()
launch(real_plan(head), prod, head, repo=repo)
after_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True,
                              text=True).stdout
ck("运行中容器集合不变(producer=fixture)", after_docker, before_docker)
wdirty = subprocess.run(["git", "-C", WM_REPO, "status", "--porcelain"],
                        capture_output=True, text=True).stdout
ck("不写 world-model", wdirty, "")

print("================================")
print(f"结果: RAN={RAN} PASS={RAN - FAIL} FAIL={FAIL} SKIP=0(无跳过路径)")
sys.exit(1 if FAIL else 0)
