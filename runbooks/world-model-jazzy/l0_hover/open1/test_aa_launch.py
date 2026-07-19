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

print("======== 05.2 完整真实计划 → READY → producer 恰好启动一次 ========")
repo, head = fixture_main_repo()
prod = Producer()
rec = L.launch_aa(real_plan(head), prod, lambda name: DIG,
                  main_repo=repo, wm_repo=WM_REPO)
ck("preflight=READY", rec["preflight_status"], "READY")
ck("producer 启动次数=1", prod.calls, 1)
ck("record.producer_started=1", rec["producer_started"], 1)
ck("无拒绝原因", rec["refusal_reasons"], [])

print("======== 05.3 占位符计划 → producer 启动次数=0 ========")
for bad_key, bad_val in (("runtime_plan_hash", "PLAN_PENDING_REAL_RUN"),
                         ("config_hash", "PLAN_PENDING"),
                         ("runtime_plan_hash", ""),
                         ("config_hash", "TODO")):
    prod = Producer()
    rec = L.launch_aa(real_plan(head, **{bad_key: bad_val}), prod,
                      lambda name: DIG, main_repo=repo, wm_repo=WM_REPO)
    ck(f"{bad_key}={bad_val!r:.20} → 非 READY 且 producer=0",
       (rec["preflight_status"] != "READY", prod.calls,
        rec["producer_started"]), (True, 0, 0))
    ck(f"{bad_key} 占位:拒绝原因含 preflight_not_ready",
       "preflight_not_ready" in rec["refusal_reasons"], True)

print("======== 05.4 preflight 后突变 → producer 启动次数=0 ========")
prod = Producer()
p = real_plan(head)
rec = L.launch_aa(p, prod, lambda name: DIG, main_repo=repo, wm_repo=WM_REPO,
                  _post_preflight_hook=lambda: open(p["config_path"], "ab").write(b"x"))
ck("preflight 后改 config → producer=0", prod.calls, 0)
ck("原因=config_hash_changed_after_preflight",
   "config_hash_changed_after_preflight" in rec["refusal_reasons"], True)
prod = Producer()
p = real_plan(head)
rec = L.launch_aa(p, prod, lambda name: DIG, main_repo=repo, wm_repo=WM_REPO,
                  _post_preflight_hook=lambda: open(p["runtime_plan_path"], "ab").write(b"x"))
ck("preflight 后改 runtime plan → producer=0", prod.calls, 0)
ck("原因=runtime_plan_hash_changed_after_preflight",
   "runtime_plan_hash_changed_after_preflight" in rec["refusal_reasons"], True)
prod = Producer()
p = real_plan(head)
rec = L.launch_aa(p, prod, lambda name: "sha256:" + "ee" * 32,
                  main_repo=repo, wm_repo=WM_REPO)
ck("preflight 后镜像 digest 现值不符 → producer=0", prod.calls, 0)
ck("原因=image_digest_changed_after_preflight",
   "image_digest_changed_after_preflight" in rec["refusal_reasons"], True)
prod = Producer()
p = real_plan(head)
rec = L.launch_aa(p, prod, lambda name: DIG, main_repo=repo, wm_repo=WM_REPO,
                  _post_preflight_hook=lambda: os.unlink(p["runtime_plan_path"]))
ck("preflight 后计划文件被删 → producer=0", prod.calls, 0)

print("======== 05.5 入口自身零启动+零污染 ========")
src = open(os.path.join(HERE, "aa_launch.py")).read()
for pat in ("docker start", "docker stop", "docker restart", "docker exec",
            "docker run", "rclpy.init", "navlab-sim", "telemetry_sidecar.py",
            "subprocess"):
    ck(f"aa_launch 源码零调用: {pat!r}", pat in src, False)
before_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True,
                               text=True).stdout
prod = Producer()
L.launch_aa(real_plan(head), prod, lambda name: DIG,
            main_repo=repo, wm_repo=WM_REPO)
after_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True,
                              text=True).stdout
ck("运行中容器集合不变(producer=fixture)", after_docker, before_docker)
wdirty = subprocess.run(["git", "-C", WM_REPO, "status", "--porcelain"],
                        capture_output=True, text=True).stdout
ck("不写 world-model", wdirty, "")

print("================================")
print(f"结果: RAN={RAN} PASS={RAN - FAIL} FAIL={FAIL} SKIP=0(无跳过路径)")
sys.exit(1 if FAIL else 0)
