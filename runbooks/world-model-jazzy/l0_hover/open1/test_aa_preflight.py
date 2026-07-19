#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 AA-PF-04 · preflight gate 门(硬门条件 + 不启动证明 + 当前真实预期)。

expected 来源=04.2/04.3/04.5 规则文本。零真实系统。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import telemetry_contract as C  # noqa: E402

FAIL = 0
EAB = "eab0cc6f0d5460cbd2cf20fe9b83857549a1e6b5"
NEW = "9a1ce95c56e2901aad062e31c9d4a8006474b0fc"


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def run_pf(plan, output=None):
    fx = tempfile.mktemp(suffix=".json")
    open(fx, "w").write(json.dumps(plan))
    args = [sys.executable, os.path.join(HERE, "aa_preflight.py"), "--input", fx]
    if output:
        args += ["--output", output]
    cp = subprocess.run(args, capture_output=True, text=True, timeout=120)
    try:
        return cp.returncode, json.loads(cp.stdout)
    finally:
        os.unlink(fx)


def full_plan(**over):
    main_sha = subprocess.run(["git", "-C", os.path.join(HERE, "..", "..", "..", ".."),
                               "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    def rr(mode, n):
        return {"run_id": f"r{n}", "telemetry_mode": mode,
                "baseline_class": "FUTURE_CANDIDATE", "main_commit": main_sha,
                "world_model_commit": NEW, "image_digests": "sha256:img",
                "config_hash": "cafe", "task_id": "hover", "map_id": "iris_maze",
                "timeout_sec": 1500, "ros_domain_id": "7",
                "container_identity_source": "runtime/service_handles.json",
                "evidence_state": "COMPLETE"}
    plan = {"main_commit": main_sha, "baseline_class": "FUTURE_CANDIDATE",
            "sidecar_backend": "real",
            "ros_readiness_topic": "/mavlink_external_nav/status",
            "ros_extnav_topic": "/external_nav/status",
            "sidecar_ros_domain": "7", "system_ros_domain": "7",
            "container_identity_source": "runtime/service_handles.json",
            "image_digests": {"companion": "sha256:img"},
            "runtime_plan_hash": "deadbeefcafe",
            "identity_wait_sec": 135.75,
            "evidence_contract_version": C.SCHEMA_VERSION,
            "pair_plan": [{"off": rr("OFF", 1), "on": rr("ON", 2)},
                          {"off": rr("OFF", 3), "on": rr("ON", 4)}],
            "real_validation_claims": {"real_ros_graph": False, "real_docker_chain": False},
            "owner_approvals": {"ros_env_plan": True, "readiness_topic": True,
                                "container_identity_upstream": True}}
    plan.update(over)
    return plan


print("======== 04.5 当前真实预期:禁止 READY ========")
rc, out = run_pf(full_plan())
ck("状态∈四枚举", out["preflight_status"] in ("READY", "BLOCKED", "CORRUPT",
                                              "OWNER_DECISION_REQUIRED"), True)
ck("当前现场禁止 READY(宿主无 rclpy)", out["preflight_status"] != "READY", True)
ck("acceptance_eligible=false", out["acceptance_eligible"], False)
ck("rc=1(非 READY)", rc, 1)
failed = set(out["failed_checks"])
ck("AA-PF-01 在列(rclpy)", "host_rclpy_available" in failed, True)
ck("必备输出字段齐", all(k in out for k in
   ("preflight_status", "checks", "failed_checks", "owner_decisions_required",
    "warnings", "main_commit", "world_model_commit", "generated_at",
    "acceptance_eligible")), True)
ck("owner_decisions 列出 ros_env_plan",
   any(d["decision"] == "ros_env_plan" for d in out["owner_decisions_required"]), True)

print("======== 04.3 硬门逐项(单变量打断)========")
rc, out = run_pf(full_plan(main_commit="0" * 40))
ck("main SHA 不符 → 非 READY + 在列",
   ("main_sha_match" in out["failed_checks"]), True)
rc, out = run_pf(full_plan(baseline_class="HISTORICAL_REPRODUCTION"))
ck("baseline_class 与现场 wm SHA 不符 → 打断",
   "wm_sha_matches_baseline_class" in out["failed_checks"], True)
rc, out = run_pf(full_plan(ros_readiness_topic="/navlab/startup_readiness/status"))
ck("未验证 readiness topic → 打断", "readiness_topic_decided_and_verified" in out["failed_checks"], True)
rc, out = run_pf(full_plan(system_ros_domain=None))
ck("system domain 未知 → 打断", "ros_domains_configured" in out["failed_checks"], True)
rc, out = run_pf(full_plan(sidecar_ros_domain="8"))
ck("双域不一致 → 打断", "ros_domains_equal" in out["failed_checks"], True)
rc, out = run_pf(full_plan(container_identity_source="docker_ps_guess"))
ck("容器身份非权威来源 → 打断", "container_identity_live_pipeline" in out["failed_checks"], True)
rc, out = run_pf(full_plan(owner_approvals={"ros_env_plan": True, "readiness_topic": True,
                                            "container_identity_upstream": False}))
ck("上游契约未批 → OWNER_DECISION_REQUIRED 在列",
   any(d["decision"] == "container_identity_upstream" for d in out["owner_decisions_required"]), True)
rc, out = run_pf(full_plan(image_digests=None))
ck("镜像 digest 缺失 → 打断", "image_digests_present" in out["failed_checks"], True)
rc, out = run_pf(full_plan(evidence_contract_version="old.v0"))
ck("evidence contract 版本不符 → 打断", "evidence_contract_current" in out["failed_checks"], True)
p = full_plan()
p["pair_plan"] = p["pair_plan"][:1]
rc, out = run_pf(p)
ck("样本≠OFF×2+ON×2 → 打断", "sample_plan_off2_on2" in out["failed_checks"], True)
p = full_plan()
p["pair_plan"][0]["on"]["config_hash"] = "beef"
rc, out = run_pf(p)
ck("配对冻结字段不符 → 打断", "pair_plan_frozen_fields_match" in out["failed_checks"], True)
rc, out = run_pf(full_plan(real_validation_claims={"real_ros_graph": True}))
ck("真实验证被冒称完成 → 打断", "no_fake_real_validation_claims" in out["failed_checks"], True)
rc, out = run_pf({"broken": True})
ck("残缺计划 → 非 READY", out["preflight_status"] != "READY", True)

print("======== 04.4 门不启动任何东西 ========")
src = open(os.path.join(HERE, "aa_preflight.py")).read()
for pat in ("docker start", "docker stop", "docker restart", "docker exec",
            "rclpy.init", "navlab-sim", "telemetry_sidecar.py"):
    ck(f"源码零调用: {pat!r}", pat in src, False)
before_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout
tmpout = tempfile.mkdtemp()
outfile = os.path.join(tmpout, "pf.json")
before_files = set(os.listdir(tmpout))
mdirty = subprocess.run(["git", "-C", os.path.join(HERE, "..", "..", "..", ".."),
                         "status", "--porcelain"], capture_output=True, text=True).stdout
rc, out = run_pf(full_plan(), output=outfile)
after_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout
ck("运行中容器集合不变", after_docker, before_docker)
ck("仅生成指定输出文件", sorted(set(os.listdir(tmpout)) - before_files), ["pf.json"])
mdirty2 = subprocess.run(["git", "-C", os.path.join(HERE, "..", "..", "..", ".."),
                          "status", "--porcelain"], capture_output=True, text=True).stdout
ck("不改仓库", mdirty2, mdirty)
wdirty = subprocess.run(["git", "-C", "/home/ai4s/projects/world-model",
                         "status", "--porcelain"], capture_output=True, text=True).stdout
ck("不写 world-model", wdirty, "")

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
