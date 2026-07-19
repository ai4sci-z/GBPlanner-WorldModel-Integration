#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 · A/A 唯一正式启动入口:计划物化 → 真实 hash → 冻结计划 → preflight → producer guard。

顺序铁律(2026-07-20 真实性补正令):
  1. materialize():canonical config + runtime plan 原子落盘(tmp+rename,canonical JSON 字节);
  2. 独立计算 sha256(文件精确字节)——hash 的输入来源=落盘文件,不是内存对象;
  3. build_frozen_plan():生成 OFF×2+ON×2 冻结计划,pair 成员逐字段继承顶层冻结值;
  4. launch_aa() 调用唯一 preflight(aa_preflight.run_preflight);
  5. 仅 preflight_status=READY 且 acceptance_eligible=true 才进入启动分支;
  6. producer 调用前重算 config/runtime plan hash 并复核镜像 digest 现值——
     preflight 之后任何改动 → 拒绝启动(producer 调用次数=0)并给出原因;
  7. 任一冻结字段变化后必须重新物化计划并重新走完整入口(不存在"部分重跑");
  8. 本模块自身绝不启动容器/ROS node/仿真/编排器——producer 由调用方注入:
     E1 正式接线时注入 batch_lifecycle 启动链,测试注入计数 fixture。
禁止路径:先用占位符拿 READY、实验启动时再补真实值——占位符在 preflight 的
schema 门直接非 READY,producer 不会被调用。
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aa_preflight as PF  # noqa: E402

DEFAULT_MAIN_REPO = os.path.realpath(os.path.join(HERE, "..", "..", "..", ".."))
DEFAULT_WM_REPO = "/home/ai4s/projects/world-model"


def canonical_json_bytes(obj):
    """canonical 序列化:排序键+紧凑分隔符,同一对象恒同字节 → 同 hash。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    """tmp+rename 原子落盘;失败不留半写文件在目标路径。"""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def materialize(run_root, canonical_config, runtime_plan):
    """物化计划:先落盘,后由文件字节独立计算真实 hash(顺序不可倒)。"""
    os.makedirs(run_root, exist_ok=True)
    config_path = os.path.join(run_root, "aa_config.json")
    plan_path = os.path.join(run_root, "aa_runtime_plan.json")
    atomic_write(config_path, canonical_json_bytes(canonical_config))
    atomic_write(plan_path, canonical_json_bytes(runtime_plan))
    return {"config_path": config_path,
            "config_hash": PF._sha256_file(config_path),
            "runtime_plan_path": plan_path,
            "runtime_plan_hash": PF._sha256_file(plan_path)}


def build_frozen_plan(mat, *, main_commit, world_model_commit, companion_digest,
                      identity_wait_sec, identity_wait_budgets=None,
                      task_id="hover", map_id="iris_maze", timeout_sec=1500,
                      ros_domain="7",
                      ros_readiness_topic="/mavlink_external_nav/status",
                      ros_extnav_topic="/external_nav/status",
                      evidence_contract_version=None,
                      owner_approvals=None, run_id_prefix="aa"):
    """由物化产物+现场冻结值组装 OFF×2+ON×2 计划;pair 成员逐字段继承顶层。"""
    import telemetry_contract as C

    def rr(mode, n):
        return {"run_id": f"{run_id_prefix}-r{n}", "telemetry_mode": mode,
                "baseline_class": "FUTURE_CANDIDATE", "main_commit": main_commit,
                "world_model_commit": world_model_commit,
                "image_digests": companion_digest,
                "config_hash": mat["config_hash"], "task_id": task_id,
                "map_id": map_id, "timeout_sec": timeout_sec,
                "ros_domain_id": str(ros_domain),
                "container_identity_source": "runtime/service_handles.json",
                "evidence_state": "COMPLETE"}

    plan = {"main_commit": main_commit, "baseline_class": "FUTURE_CANDIDATE",
            "sidecar_backend": "real",
            "ros_readiness_topic": ros_readiness_topic,
            "ros_extnav_topic": ros_extnav_topic,
            "sidecar_ros_domain": str(ros_domain),
            "system_ros_domain": str(ros_domain),
            "container_identity_source": "runtime/service_handles.json",
            "image_digests": {"companion": companion_digest},
            "config_path": mat["config_path"], "config_hash": mat["config_hash"],
            "runtime_plan_path": mat["runtime_plan_path"],
            "runtime_plan_hash": mat["runtime_plan_hash"],
            "identity_wait_sec": identity_wait_sec,
            "evidence_contract_version": (evidence_contract_version
                                          if evidence_contract_version is not None
                                          else C.SCHEMA_VERSION),
            "pair_plan": [{"off": rr("OFF", 1), "on": rr("ON", 2)},
                          {"off": rr("OFF", 3), "on": rr("ON", 4)}],
            "real_validation_claims": {"real_ros_graph": False,
                                       "real_docker_chain": False},
            "owner_approvals": dict(owner_approvals or {})}
    if identity_wait_budgets:
        plan["identity_wait_budgets"] = dict(identity_wait_budgets)
    return plan


def _guard_refusals(plan, digest_provider):
    """producer 启动前的最后复核:独立重算物化文件 hash + 镜像 digest 现值比对。
    preflight 之后的任何改动在此拒绝——返回非空即禁止启动。"""
    refusals = []
    for path_key, hash_key in (("config_path", "config_hash"),
                               ("runtime_plan_path", "runtime_plan_hash")):
        p = plan.get(path_key)
        actual = PF._sha256_file(p) if isinstance(p, str) and os.path.isfile(p) else None
        if actual != plan.get(hash_key):
            refusals.append(f"{hash_key}_changed_after_preflight")
    current = digest_provider("companion")
    if current != plan.get("image_digests", {}).get("companion"):
        refusals.append("image_digest_changed_after_preflight")
    return refusals


def launch_aa(plan, producer, digest_provider,
              main_repo=DEFAULT_MAIN_REPO, wm_repo=DEFAULT_WM_REPO,
              output=None, _post_preflight_hook=None):
    """唯一启动分支。producer:仅 READY+guard 全过才被调用(注入,本模块零启动)。
    digest_provider(name)->当前真实镜像 digest(E1 正式接线=docker image inspect;
    测试=fixture)。_post_preflight_hook 仅供测试注入 preflight 后突变,生产=None。"""
    pf = PF.run_preflight(plan, main_repo, wm_repo)
    record = {"preflight_status": pf["preflight_status"],
              "acceptance_eligible": pf["acceptance_eligible"],
              "failed_checks": pf["failed_checks"],
              "owner_decisions_required": pf["owner_decisions_required"],
              "producer_started": 0, "refusal_reasons": []}
    if output:
        atomic_write(output, json.dumps(pf, ensure_ascii=False, sort_keys=True,
                                        indent=1).encode("utf-8"))
    if not (pf["preflight_status"] == "READY" and pf["acceptance_eligible"]):
        record["refusal_reasons"] = ["preflight_not_ready"] + pf["failed_checks"]
        return record
    if _post_preflight_hook is not None:
        _post_preflight_hook()
    refusals = _guard_refusals(plan, digest_provider)
    if refusals:
        record["refusal_reasons"] = refusals
        return record
    producer(plan)
    record["producer_started"] = 1
    return record
