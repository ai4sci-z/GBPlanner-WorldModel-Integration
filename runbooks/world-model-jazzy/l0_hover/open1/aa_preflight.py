#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 AA-PF-04 · A/A preflight gate(唯一预检入口;只检查,绝不启动任何东西)。

不调用任何容器启停/exec 命令、不建 ROS node、不启动仿真编排器或 sidecar、
不改仓库、不写 world-model;除 --output 指定文件外零产物。
状态枚举:READY / BLOCKED / CORRUPT / OWNER_DECISION_REQUIRED(禁布尔吞原因)。"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aa_pair_contract as P  # noqa: E402
import telemetry_contract as C  # noqa: E402
import telemetry_sidecar as S  # noqa: E402

STATUSES = ("READY", "BLOCKED", "CORRUPT", "OWNER_DECISION_REQUIRED")

OWNER_DECISIONS = {
    "ros_env_plan": "AA-PF-01:批准受控宿主 ROS2 环境方案(A/B/C,见 WP304 §11.1)",
    "readiness_topic": "AA-PF-01:裁决 readiness 连续订阅目标 topic",
    "container_identity_upstream": "AA-PF-02:批准 world-model 输出本次 run 的容器身份"
                                   "(runtime/service_handles.json 契约,见 §11.3)",
}


def _git_head(path):
    try:
        return subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return "UNVERIFIED"


def _worktree_dirty(path):
    try:
        out = subprocess.run(["git", "-C", path, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=30).stdout
        return len([x for x in out.splitlines() if x.strip()])
    except Exception:
        return -1


def _can_import(mod):
    cp = subprocess.run([sys.executable, "-c", f"import {mod}"],
                        capture_output=True, text=True, timeout=30)
    return cp.returncode == 0, (cp.stderr.strip().splitlines() or [""])[-1]


def run_preflight(plan, main_repo, wm_repo):
    checks = []
    owner_required = []

    def add(name, ok, detail, corrupt=False, owner=None):
        checks.append({"name": name,
                       "status": ("CORRUPT" if corrupt else ("PASS" if ok else "FAIL")),
                       "detail": detail})
        if owner and not ok and not any(d["decision"] == owner for d in owner_required):
            owner_required.append({"decision": owner, "description": OWNER_DECISIONS[owner]})

    main_sha = _git_head(main_repo)
    wm_sha = _git_head(wm_repo)
    add("main_sha_match", main_sha == plan.get("main_commit"),
        f"actual={main_sha[:12]} plan={str(plan.get('main_commit'))[:12]}")
    try:
        cls = P.validate_baseline(wm_sha, plan.get("baseline_class"))
        add("wm_sha_matches_baseline_class", True,
            f"{plan.get('baseline_class')}={wm_sha[:12]};known_defects={cls['known_baseline_defects']}")
    except P.PairContractError as e:
        add("wm_sha_matches_baseline_class", False, str(e))
    add("main_worktree_clean", _worktree_dirty(main_repo) == 0,
        f"dirty={_worktree_dirty(main_repo)}")
    add("wm_worktree_clean", _worktree_dirty(wm_repo) == 0,
        f"dirty={_worktree_dirty(wm_repo)}")
    ok_rclpy, err1 = _can_import("rclpy")
    ok_std, err2 = _can_import("std_msgs.msg")
    add("host_rclpy_available", ok_rclpy, err1 or "importable", owner="ros_env_plan")
    add("host_std_msgs_available", ok_std, err2 or "importable",
        owner=None if ok_rclpy else "ros_env_plan")
    # topic/类型契约
    rt = plan.get("ros_readiness_topic")
    add("readiness_topic_decided_and_verified",
        bool(rt) and rt in S.AUTHORITATIVE_TOPIC_TYPES,
        f"readiness_topic={rt!r}(权威登记表={sorted(S.AUTHORITATIVE_TOPIC_TYPES)})",
        owner="readiness_topic")
    et = plan.get("ros_extnav_topic", "/external_nav/status")
    add("extnav_topic_verified", et in S.AUTHORITATIVE_TOPIC_TYPES, f"extnav_topic={et}")
    sd = plan.get("sidecar_ros_domain")
    yd = plan.get("system_ros_domain")
    add("ros_domains_configured", bool(sd) and bool(yd),
        f"sidecar={sd!r} system={yd!r}(双独立来源,缺任一 fail)")
    add("ros_domains_equal", bool(sd) and bool(yd) and str(sd) == str(yd),
        f"sidecar={sd!r} system={yd!r}")
    # 容器身份(live 路径须上游契约;post-run 不满足 A/A 运行期采集要求)
    cis = plan.get("container_identity_source")
    add("container_identity_live_pipeline",
        cis == "runtime/service_handles.json"
        and plan.get("owner_approvals", {}).get("container_identity_upstream") is True,
        f"source={cis!r};live 权威管道须上游契约+负责人批准(§11.3)",
        owner="container_identity_upstream")
    add("image_digests_present", bool(plan.get("image_digests")),
        f"digests={str(plan.get('image_digests'))[:60]}")
    add("runtime_plan_hash_present", bool(plan.get("runtime_plan_hash")),
        f"hash={str(plan.get('runtime_plan_hash'))[:16]}")
    add("identity_wait_budget_derived",
        isinstance(plan.get("identity_wait_sec"), (int, float)) and plan.get("identity_wait_sec", 0) > 0,
        f"identity_wait_sec={plan.get('identity_wait_sec')}")
    add("evidence_contract_current",
        plan.get("evidence_contract_version") == C.SCHEMA_VERSION,
        f"plan={plan.get('evidence_contract_version')!r} current={C.SCHEMA_VERSION!r}")
    # OFF×2+ON×2 同基线配对
    pairs = plan.get("pair_plan", [])
    modes = [r.get("telemetry_mode") for p in pairs for r in (p.get("off", {}), p.get("on", {}))]
    add("sample_plan_off2_on2",
        len(pairs) == 2 and modes.count("OFF") == 2 and modes.count("ON") == 2,
        f"pairs={len(pairs)} modes={modes}")
    pair_ok = True
    reasons = []
    for pr in pairs:
        v = P.validate_pair(pr.get("off", {}), pr.get("on", {}))
        if not v["comparison_eligibility"]:
            pair_ok = False
            reasons += v["exclusion_reasons"]
    add("pair_plan_frozen_fields_match", bool(pairs) and pair_ok,
        "; ".join(reasons[:4]) if reasons else "全冻结字段一致")
    fake_done = [k for k, v in plan.get("real_validation_claims", {}).items() if v]
    add("no_fake_real_validation_claims", not fake_done,
        f"被声称已完成的真实验证={fake_done}(必须全为 false)")

    failed = [c for c in checks if c["status"] != "PASS"]
    corrupt = [c for c in checks if c["status"] == "CORRUPT"]
    if corrupt:
        status = "CORRUPT"
    elif owner_required:
        status = "OWNER_DECISION_REQUIRED"
    elif failed:
        status = "BLOCKED"
    else:
        status = "READY"
    return {"preflight_status": status,
            "checks": checks,
            "failed_checks": [c["name"] for c in failed],
            "owner_decisions_required": owner_required,
            "warnings": [],
            "main_commit": main_sha,
            "world_model_commit": wm_sha,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "acceptance_eligible": status == "READY"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aa_preflight",
                                 description="A/A preflight gate(只检查,不启动)")
    ap.add_argument("--input", required=True, help="A/A 计划 JSON")
    ap.add_argument("--main-repo", default=os.path.realpath(os.path.join(HERE, "..", "..", "..", "..")))
    ap.add_argument("--wm-repo", default="/home/ai4s/projects/world-model")
    ap.add_argument("--output", default=None)
    a = ap.parse_args(argv)
    try:
        plan = json.load(open(a.input, encoding="utf-8"))
    except (OSError, ValueError) as e:
        out = {"preflight_status": "CORRUPT", "checks": [],
               "failed_checks": ["plan_input"], "owner_decisions_required": [],
               "warnings": [f"输入不可解析: {e}"], "acceptance_eligible": False}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 3
    out = run_preflight(plan, a.main_repo, a.wm_repo)
    text = json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    return 0 if out["preflight_status"] == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
