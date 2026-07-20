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

2026-07-20 二次补正(Codex 复验:正式入口绕过):
  - launch_aa 增加**负责人本次启动授权机器门**(approval artifact,必填):缺失/损坏/
    用途错/SHA-hash-digest 不匹配/未批准 → producer 恒不被调用。文档停点≠机器停点,
    本参数即机器停点。validate 路径(仅 preflight)不需要授权,execute 必须。
  - guard 增加 HEAD/dirty 最后复核(repo_state 注入,本模块保持零子进程调用)。
  - 本模块是库层;操作者入口=同目录 aa_cli.py(argparse CLI,producer=正式
    batch_lifecycle 链)。直接调用本库也过不了授权门。
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

APPROVAL_SCHEMA_VERSION = "wp304.aa_approval.v1"
APPROVAL_PURPOSE = "A_A_OFF2_ON2"


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

    plan = {"main_commit": main_commit, "world_model_commit": world_model_commit,
            "baseline_class": "FUTURE_CANDIDATE",
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
    plan["execution_order"] = ["%s-r1" % run_id_prefix, "%s-r3" % run_id_prefix,
                               "%s-r2" % run_id_prefix, "%s-r4" % run_id_prefix]
    if identity_wait_budgets:
        plan["identity_wait_budgets"] = dict(identity_wait_budgets)
    return plan


def frozen_plan_sha256(plan):
    """整份冻结计划的 canonical 字节 sha256(与 aa_frozen_plan.json 落盘字节一致)。
    approval 绑定此值 → 计划任何字节变化后旧 approval 立即失效。"""
    return sha256_bytes(canonical_json_bytes(plan))


def verify_owner_approval(approval_path, plan, current_digest, allow_fixture=False):
    """负责人本次 A/A 启动授权 artifact 的机器校验。返回 (ok, reasons, approval)。

    **性质=具名计划的操作防误触门,不是身份认证**:它证明"有人拿到 validate 输出的
    整计划 SHA 并显式写进了审批文件",能防误触发/防拿旧计划启动,**不能抵抗恶意
    伪造**(JSON 里的 approved_by 任何人都能写;若需审批者身份验证须另行引入可信
    签名或外部批准源)。
    缺失/损坏/用途错/状态非 APPROVED/任何绑定字段(含整计划 frozen_plan_sha256)
    与冻结计划或镜像现值不符 → 拒绝。fixture_test_only=true 的样本仅
    allow_fixture=True(测试/dry-run)时可过,且由调用方在 launch record 里显式
    标注;真实审批文件只能由负责人启动指令产生,本代码不生成。"""
    if not approval_path or not (isinstance(approval_path, str) and os.path.isfile(approval_path)):
        return False, ["approval_missing"], None
    try:
        with open(approval_path, encoding="utf-8") as f:
            ap = json.load(f)
    except (OSError, ValueError):
        return False, ["approval_unparsable"], None
    reasons = []
    if ap.get("schema_version") != APPROVAL_SCHEMA_VERSION:
        reasons.append("approval_schema_version_mismatch")
    if ap.get("approval_purpose") != APPROVAL_PURPOSE:
        reasons.append("approval_purpose_mismatch")
    if ap.get("approval_state") != "APPROVED":
        reasons.append("approval_state_not_approved")
    if ap.get("fixture_test_only") and not allow_fixture:
        reasons.append("fixture_approval_not_allowed")
    if not ap.get("approved_by") or not ap.get("approved_at"):
        reasons.append("approval_actor_or_time_missing")
    wm_commit = (plan.get("world_model_commit")
                 or (plan.get("pair_plan") or [{}])[0].get("off", {}).get("world_model_commit"))
    for key, want in (("main_commit", plan.get("main_commit")),
                      ("world_model_commit", wm_commit),
                      ("config_hash", plan.get("config_hash")),
                      ("runtime_plan_hash", plan.get("runtime_plan_hash")),
                      ("ros_domain", plan.get("sidecar_ros_domain")),
                      ("sample_plan", "OFF2_ON2")):
        if ap.get(key) != want:
            reasons.append(f"approval_{key}_mismatch")
    plan_digest = plan.get("image_digests", {}).get("companion")
    if ap.get("image_digest") != plan_digest:
        reasons.append("approval_image_digest_mismatch_plan")
    if ap.get("image_digest") != current_digest:
        reasons.append("approval_image_digest_mismatch_current")
    if ap.get("frozen_plan_sha256") != frozen_plan_sha256(plan):
        reasons.append("approval_frozen_plan_sha_mismatch")
    return (not reasons), reasons, ap


def _guard_refusals(plan, digest_provider, repo_state):
    """producer 启动前的最后复核:独立重算物化文件 hash + 镜像 digest 现值 +
    HEAD/dirty 现值(repo_state 注入,保持本模块零子进程调用)。
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
    if repo_state is None:
        refusals.append("repo_state_provider_missing")
    else:
        st = repo_state()
        wm_commit = (plan.get("world_model_commit")
                     or (plan.get("pair_plan") or [{}])[0].get("off", {}).get("world_model_commit"))
        if st.get("main_head") != plan.get("main_commit"):
            refusals.append("main_head_changed_after_preflight")
        if st.get("wm_head") != wm_commit:
            refusals.append("wm_head_changed_after_preflight")
        if st.get("main_dirty") != 0:
            refusals.append("main_worktree_dirty_at_launch")
        if st.get("wm_dirty") != 0:
            refusals.append("wm_worktree_dirty_at_launch")
    return refusals


def launch_aa(plan, producer, digest_provider, *, approval_path, repo_state,
              main_repo=DEFAULT_MAIN_REPO, wm_repo=DEFAULT_WM_REPO,
              output=None, allow_fixture_approval=False, _post_preflight_hook=None):
    """唯一启动分支。producer:仅 READY+授权+guard 全过才被调用(注入,本模块零启动)。
    digest_provider(name)->当前真实镜像 digest;repo_state()->{main_head,wm_head,
    main_dirty,wm_dirty} 现值(CLI=git 实查;测试=fixture)。
    approval_path=负责人本次启动授权 artifact(机器门,keyword-only 必填——库层直接
    调用也绕不过);validate 路径请直接用 PF.run_preflight,不要带 producer 调本函数。
    _post_preflight_hook 仅供测试注入 preflight 后突变,生产=None。"""
    pf = PF.run_preflight(plan, main_repo, wm_repo)
    record = {"preflight_status": pf["preflight_status"],
              "acceptance_eligible": pf["acceptance_eligible"],
              "failed_checks": pf["failed_checks"],
              "owner_decisions_required": pf["owner_decisions_required"],
              "producer_started": 0, "refusal_reasons": [],
              "approval_fixture_test_only": False}
    if output:
        atomic_write(output, json.dumps(pf, ensure_ascii=False, sort_keys=True,
                                        indent=1).encode("utf-8"))
    if not (pf["preflight_status"] == "READY" and pf["acceptance_eligible"]):
        record["refusal_reasons"] = ["preflight_not_ready"] + pf["failed_checks"]
        return record
    if _post_preflight_hook is not None:
        _post_preflight_hook()
    ok, why, ap = verify_owner_approval(approval_path, plan, digest_provider("companion"),
                                        allow_fixture=allow_fixture_approval)
    if not ok:
        record["refusal_reasons"] = why
        return record
    record["approval_fixture_test_only"] = bool(ap.get("fixture_test_only"))
    record["approval_sha256"] = PF._sha256_file(approval_path)
    refusals = _guard_refusals(plan, digest_provider, repo_state)
    if refusals:
        record["refusal_reasons"] = refusals
        return record
    producer(plan)
    record["producer_started"] = 1
    return record
