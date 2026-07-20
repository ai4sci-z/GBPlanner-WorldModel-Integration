#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 · A/A 具名正式操作入口(唯一;2026-07-20 二次+三次补正令)。

四模式:
  --validate-only  物化+真实 hash+docker 真实 digest+preflight;输出整计划
                   frozen_plan_sha256(负责人启动指令必须引用它);绝不启动。
  --execute        正式启动链(ACCEPTANCE_CANDIDATE)。要求:①负责人 approval
                   artifact(绑整计划 SHA;fixture 审批一律拒);②环境中不得有任何
                   测试覆盖变量(NAVLAB_SIM_CMD 等,见 TEST_OVERRIDE_ENVS);
                   ③preflight READY+hash/digest/HEAD/dirty 复核。producer=正式
                   batch_lifecycle.py launch ×4(OFF,OFF,ON,ON),任一失败即停。
  --dry-run        测试专用链(NON_ACCEPTANCE_FIXTURE)。强制 fixture 审批、允许
                   测试覆盖 env、产物永久标记且被正式 aggregate 永久拒绝、
                   acceptance_eligible 恒 false。**dry-run 不是真实 A/A**。
  --aggregate      A/A 验收出口:完整分母验收(见 cmd_aggregate),零次实验不得
                   聚合成功;NON_ACCEPTANCE_FIXTURE/无身份/身份不符一律拒。

授权门性质=**具名计划的操作防误触门,非身份认证**(见 aa_launch.verify_owner_approval)。
退出码:0=成功;1=门拒绝/非 READY/attempt 失败/聚合验收不通过;2=用法错误;3=环境错误。
真实审批文件只能由负责人启动指令产生;本 CLI 绝不生成。
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
L0_HOVER = os.path.realpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, L0_HOVER)
import aa_launch as L  # noqa: E402
import aa_preflight as PF  # noqa: E402

BATCH_LIFECYCLE = os.path.join(L0_HOVER, "batch_lifecycle.py")
PRODUCER_SCRIPTS = {"l2": "l2_batch.sh", "l2fix": "l2fix_batch.sh", "l15": "l15_batch.sh"}
IDENTITY_SCHEMA = "wp304.aa_identity.v1"
DEFAULT_LOCK = "/tmp/navlab_sitl_host.lock"
RECORD_ACCEPTANCE = "ACCEPTANCE_CANDIDATE"
RECORD_FIXTURE = "NON_ACCEPTANCE_FIXTURE"
# 真实 execute 前必须为空/非 fixture 的测试覆盖变量(能替换真实 producer/sidecar/
# 数据源的开关;dry-run 才允许)
TEST_OVERRIDE_ENVS = ("NAVLAB_SIM_CMD", "WP303_TELEMETRY_CMD",
                      "WP303_TELEMETRY_FIXTURE_INPUT", "WP303_TELEMETRY_REGISTRY_WAIT")


class UsageError(Exception):
    pass


def _run(argv, timeout=30):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def real_image_digest(companion_tag):
    cp = _run(["docker", "image", "inspect", "--format", "{{.Id}}",
               f"navlab/companion:{companion_tag}"])
    if cp.returncode != 0:
        raise EnvironmentError(f"镜像不可查询: navlab/companion:{companion_tag}: "
                               f"{cp.stderr.strip()[:200]}")
    return cp.stdout.strip()


def repo_head(path):
    cp = _run(["git", "-C", path, "rev-parse", "HEAD"])
    if cp.returncode != 0:
        raise EnvironmentError(f"git HEAD 不可读: {path}")
    return cp.stdout.strip()


def repo_dirty(path):
    cp = _run(["git", "-C", path, "status", "--porcelain"])
    if cp.returncode != 0:
        raise EnvironmentError(f"git status 不可读: {path}")
    return len([x for x in cp.stdout.splitlines() if x.strip()])


def build_parser():
    ap = argparse.ArgumentParser(
        prog="aa_cli",
        description="A/A(OFF×2+ON×2)唯一正式操作入口。--execute=真实链(拒 fixture 审批"
                    "与测试覆盖 env);--dry-run=测试链(产物永不入 A/A 分母);直接调用 "
                    "run_batch.sh 的结果不得计入 A/A 分母。授权门=具名计划的操作防误触门,"
                    "非身份认证。")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true",
                      help="物化+真实 hash+真实 digest+preflight+输出整计划 SHA;绝不启动")
    mode.add_argument("--execute", action="store_true",
                      help="正式启动链;需负责人 approval(绑整计划 SHA;fixture 审批一律拒)")
    mode.add_argument("--dry-run", action="store_true",
                      help="测试链:强制 fixture 审批;产物标 NON_ACCEPTANCE_FIXTURE,永不入 A/A 分母")
    mode.add_argument("--aggregate", action="store_true",
                      help="A/A 验收出口:完整分母验收;零实验/缺失/多余/乱序/失败均非零退出")
    ap.add_argument("--config", help="canonical config 输入 JSON(validate/execute/dry-run 必填)")
    ap.add_argument("--runtime-plan", help="runtime plan 输入 JSON(validate/execute/dry-run 必填)")
    ap.add_argument("--artifact-root", required=True, help="A/A 根目录")
    ap.add_argument("--companion-tag", help="companion 镜像 tag(docker 查真实 digest)")
    ap.add_argument("--main-repo", default=L.DEFAULT_MAIN_REPO)
    ap.add_argument("--wm-repo", default=L.DEFAULT_WM_REPO)
    ap.add_argument("--ros-domain", default="7")
    ap.add_argument("--readiness-topic", default="/mavlink_external_nav/status")
    ap.add_argument("--extnav-topic", default="/external_nav/status")
    ap.add_argument("--producer-mode", choices=sorted(PRODUCER_SCRIPTS), default="l2")
    ap.add_argument("--task-id", default="hover")
    ap.add_argument("--map-id", default="iris_maze")
    ap.add_argument("--timeout-sec", type=int, default=1500)
    ap.add_argument("--duration", type=float, default=1500.0)
    ap.add_argument("--startup-budget", type=float, default=120.0)
    ap.add_argument("--per-run-teardown", type=float, default=30.0)
    ap.add_argument("--inter-run-gap", type=float, default=10.0)
    ap.add_argument("--finalization-budget", type=float, default=180.0)
    ap.add_argument("--owner-approval", help="approval artifact 路径(execute/dry-run 必需)")
    ap.add_argument("--preflight-out")
    ap.add_argument("--launch-record-out")
    return ap


def derive_identity_wait(a):
    import batch_lifecycle as BL
    ns = argparse.Namespace(startup_budget=a.startup_budget, duration=a.duration,
                            per_run_teardown=a.per_run_teardown, inter_run_gap=a.inter_run_gap)
    return BL.identity_wait_sec(ns)


def materialize_and_plan(a):
    for path, name in ((a.config, "--config"), (a.runtime_plan, "--runtime-plan")):
        if not path:
            raise UsageError(f"{name} 为 validate/execute/dry-run 必填")
    if not a.companion_tag:
        raise UsageError("--companion-tag 为 validate/execute/dry-run 必填")
    try:
        cfg = json.load(open(a.config, encoding="utf-8"))
        rtp = json.load(open(a.runtime_plan, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise EnvironmentError(f"输入 JSON 不可读: {e}")
    root = os.path.realpath(a.artifact_root)
    plan_dir = os.path.join(root, "aa_plan")
    mat = L.materialize(plan_dir, cfg, rtp)
    digest = real_image_digest(a.companion_tag)
    plan = L.build_frozen_plan(
        mat, main_commit=repo_head(a.main_repo), world_model_commit=repo_head(a.wm_repo),
        companion_digest=digest, identity_wait_sec=derive_identity_wait(a),
        identity_wait_budgets={"startup": a.startup_budget, "duration": a.duration,
                               "teardown": a.per_run_teardown, "gap": a.inter_run_gap,
                               "source": "batch_lifecycle.identity_wait_sec"},
        task_id=a.task_id, map_id=a.map_id, timeout_sec=a.timeout_sec,
        ros_domain=a.ros_domain, ros_readiness_topic=a.readiness_topic,
        ros_extnav_topic=a.extnav_topic,
        owner_approvals={"ros_env_plan": True, "readiness_topic": True,
                         "container_identity_upstream": True})
    L.atomic_write(os.path.join(plan_dir, "aa_frozen_plan.json"),
                   L.canonical_json_bytes(plan))
    return root, plan_dir, plan, digest


def make_official_producer(a, root, plan, aa_batch_id, approval_path, record,
                           non_acceptance_fixture):
    modes = {r["run_id"]: r["telemetry_mode"]
             for p in plan["pair_plan"] for r in (p["off"], p["on"])}
    approval_sha = PF._sha256_file(approval_path)
    script = os.path.join(L0_HOVER, PRODUCER_SCRIPTS[a.producer_mode])

    def producer(_plan):
        for run_id in plan["execution_order"]:
            mode = modes[run_id]
            att_root = os.path.join(root, "attempts", f"{run_id}_{mode}")
            os.makedirs(os.path.join(att_root, "runs"), exist_ok=True)
            ident = {"schema_version": IDENTITY_SCHEMA, "aa_batch_id": aa_batch_id,
                     "run_id": run_id, "telemetry_mode": mode,
                     "config_hash": plan["config_hash"],
                     "runtime_plan_hash": plan["runtime_plan_hash"],
                     "approval_sha256": approval_sha, "cli": "aa_cli",
                     "non_acceptance_fixture": bool(non_acceptance_fixture)}
            L.atomic_write(os.path.join(att_root, "aa_identity.json"),
                           L.canonical_json_bytes(ident))
            env = dict(os.environ)
            env["WP303_TELEMETRY"] = "on" if mode == "ON" else "off"
            argv = [sys.executable, BATCH_LIFECYCLE, "launch",
                    "--artifact-root", att_root,
                    "--batch-id", f"{aa_batch_id}.{run_id}.{mode}",
                    "--expected-runs", "1",
                    "--duration", str(a.duration),
                    "--startup-budget", str(a.startup_budget),
                    "--per-run-teardown", str(a.per_run_teardown),
                    "--inter-run-gap", str(a.inter_run_gap),
                    "--finalization-budget", str(a.finalization_budget),
                    "--", "env", f"BC_ROOT={att_root}", "RUNS=1",
                    f"DURATION_SEC={int(a.duration)}", "INTER_RUN_SLEEP=0",
                    "bash", script]
            cp = subprocess.run(argv, env=env)
            record["attempts"].append({"run_id": run_id, "telemetry_mode": mode,
                                       "artifact_root": att_root, "rc": cp.returncode})
            if cp.returncode != 0:
                for rest in plan["execution_order"][len(record["attempts"]):]:
                    record["attempts"].append({"run_id": rest, "telemetry_mode": modes[rest],
                                               "artifact_root": None, "rc": None,
                                               "state": "NOT_STARTED_PRIOR_FAILURE"})
                record["stopped_on_failure"] = run_id
                return
    return producer


def cmd_validate(a):
    root, plan_dir, plan, _ = materialize_and_plan(a)
    pf = PF.run_preflight(plan, a.main_repo, a.wm_repo)
    out = a.preflight_out or os.path.join(plan_dir, "preflight.json")
    L.atomic_write(out, json.dumps(pf, ensure_ascii=False, sort_keys=True, indent=1).encode())
    print(json.dumps({"mode": "validate-only", "preflight_status": pf["preflight_status"],
                      "acceptance_eligible": pf["acceptance_eligible"],
                      "failed_checks": pf["failed_checks"], "preflight_out": out,
                      "frozen_plan_sha256": L.frozen_plan_sha256(plan),
                      "note": "负责人启动指令必须明确引用此 frozen_plan_sha256",
                      "producer_started": 0}, ensure_ascii=False, sort_keys=True, indent=1))
    return 0 if pf["preflight_status"] == "READY" else 1


def _launch_chain(a, dry_run):
    """execute 与 dry-run 的共同骨架;差异全部显式(状态类/审批策略/env 策略)。"""
    record_class = RECORD_FIXTURE if dry_run else RECORD_ACCEPTANCE
    refusals = []
    if not dry_run:
        for name in TEST_OVERRIDE_ENVS:
            if os.environ.get(name, "").strip():
                refusals.append(f"test_override_env_present:{name}")
        if os.environ.get("WP303_TELEMETRY_BACKEND", "").strip() == "fixture":
            refusals.append("test_override_env_present:WP303_TELEMETRY_BACKEND=fixture")
    root, plan_dir, plan, digest = materialize_and_plan(a)
    record = {"mode": "dry-run" if dry_run else "execute",
              "record_class": record_class,
              "non_acceptance_fixture": dry_run,
              "acceptance_eligible": False,   # execute 的验收资格只能由 aggregate 判
              "aa_batch_id": f"aa_{time.time_ns()}_{uuid.uuid4().hex[:8]}",
              "frozen_plan_sha256": L.frozen_plan_sha256(plan),
              "attempts": [], "stopped_on_failure": None}
    rec_out = a.launch_record_out or os.path.join(plan_dir, "launch_record.json")
    pf_out = a.preflight_out or os.path.join(plan_dir, "preflight.json")

    def finish(rc):
        L.atomic_write(rec_out, json.dumps(record, ensure_ascii=False, sort_keys=True,
                                           indent=1).encode())
        print(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=1))
        return rc

    if refusals:
        record["gate"] = {"producer_started": 0, "refusal_reasons": refusals}
        record["producer_started"] = 0
        return finish(1)
    if dry_run and not os.environ.get("NAVLAB_SIM_CMD", "").strip():
        # dry-run 必须显式带仿真 stub——否则 leaf producer 会 go run 真实
        # navlab-sim(dry-run 不得启动真实容器/仿真,fail-closed)
        record["gate"] = {"producer_started": 0,
                          "refusal_reasons": ["dry_run_requires_sim_stub(NAVLAB_SIM_CMD)"]}
        record["producer_started"] = 0
        return finish(1)
    if dry_run and a.owner_approval:
        # dry-run 强制 fixture 审批:真实审批不得被 dry-run 消耗/冒用
        try:
            ap_probe = json.load(open(a.owner_approval, encoding="utf-8"))
        except (OSError, ValueError):
            ap_probe = {}
        if not ap_probe.get("fixture_test_only"):
            record["gate"] = {"producer_started": 0,
                              "refusal_reasons": ["dry_run_requires_fixture_approval"]}
            record["producer_started"] = 0
            return finish(1)
    lfd = os.open(os.environ.get("BC_LOCK_PATH", DEFAULT_LOCK), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("aa_cli: another SITL batch holds the host lock", file=sys.stderr)
        return 3
    producer = (make_official_producer(a, root, plan, record["aa_batch_id"],
                                       a.owner_approval, record,
                                       non_acceptance_fixture=dry_run)
                if a.owner_approval else (lambda _p: None))
    lrec = L.launch_aa(
        plan, producer,
        lambda name: real_image_digest(a.companion_tag),
        approval_path=a.owner_approval,
        repo_state=lambda: {"main_head": repo_head(a.main_repo),
                            "wm_head": repo_head(a.wm_repo),
                            "main_dirty": repo_dirty(a.main_repo),
                            "wm_dirty": repo_dirty(a.wm_repo)},
        main_repo=a.main_repo, wm_repo=a.wm_repo, output=pf_out,
        allow_fixture_approval=dry_run)   # 生产 execute 恒 False:fixture 审批一律拒
    record.update({"gate": lrec, "producer_started": lrec["producer_started"]})
    if lrec["producer_started"] != 1:
        return finish(1)
    bad = [x for x in record["attempts"] if x.get("rc") != 0]
    return finish(1 if bad else 0)


def cmd_execute(a):
    return _launch_chain(a, dry_run=False)


def cmd_dry_run(a):
    return _launch_chain(a, dry_run=True)


# ---- 终态语义验证器(五验补正;权威契约=batch_lifecycle 写入点,见证据文档 §8.2) ----
MONITOR_PRODUCER_OUTCOMES = ("SUCCEEDED", "FAILED", "TIMED_OUT", "CRASHED", "CANCELLED")
MONITOR_EVIDENCE_STATUSES = ("COMPLETE", "INCOMPLETE")
MONITOR_CLEANUP_STATUSES = ("CLEAN", "RESIDUAL", "NOT_ATTEMPTED", "REFUSED")


def validate_monitor_terminal(mon, want_bid, mode):
    """monitor_status 三轴终态语义门。返回具体拒绝原因列表(空=三轴合格)。
    只有 producer=SUCCEEDED ∧ evidence=COMPLETE ∧ cleanup=CLEAN 且身份/模式/
    run_rc_map 全合法才算 A/A 合格终态;表示层可解析≠语义有效。"""
    reasons = []
    if not isinstance(mon, dict) or not mon:
        return ["monitor_not_object_or_empty"]
    if mon.get("schema_version") != 1:
        reasons.append(f"monitor_schema_version_invalid:{mon.get('schema_version')!r}")
    if mon.get("batch_id") != want_bid:
        reasons.append("monitor_batch_id_mismatch(陈旧复制/他批产物)")
    if mon.get("readonly") is not False:
        reasons.append("monitor_readonly_or_missing_flag")
    po = mon.get("producer_outcome")
    if po not in MONITOR_PRODUCER_OUTCOMES:
        reasons.append(f"monitor_producer_outcome_invalid:{po!r}")
    elif po != "SUCCEEDED":
        reasons.append(f"process_axis_not_succeeded:{po}")
    ev = mon.get("evidence_status")
    if ev not in MONITOR_EVIDENCE_STATUSES:
        reasons.append(f"monitor_evidence_status_invalid:{ev!r}")
    elif ev != "COMPLETE":
        reasons.append(f"evidence_axis_not_complete:{ev}"
                       f"(missing={mon.get('evidence_missing')!r})")
    cl = mon.get("cleanup_status")
    if cl not in MONITOR_CLEANUP_STATUSES:
        reasons.append(f"monitor_cleanup_status_invalid:{cl!r}")
    elif cl != "CLEAN":
        reasons.append(f"finalization_axis_not_clean:{cl}")
    rrm = mon.get("run_rc_map")
    if not isinstance(rrm, dict) or set(rrm.keys()) != {"1"} or any(
            v != 0 for v in rrm.values()):
        reasons.append(f"monitor_run_rc_map_invalid:{rrm!r}")
    ts = mon.get("telemetry_status")
    if not isinstance(ts, dict) or "enabled" not in ts:
        reasons.append("monitor_telemetry_status_missing")
    else:
        if bool(ts.get("enabled")) != (mode == "ON"):
            reasons.append("monitor_telemetry_enabled_mismatch_mode")
        if mode == "ON" and bool(ts.get("enabled")):
            if ts.get("process_state") != "EXITED_ZERO":
                reasons.append(f"sidecar_process_not_exited_zero:{ts.get('process_state')!r}")
            if ts.get("sidecar_rc") != 0:
                reasons.append(f"sidecar_rc_nonzero:{ts.get('sidecar_rc')!r}")
    return reasons


def _plan_schema_ok(plan):
    try:
        return (isinstance(plan.get("execution_order"), list)
                and len(plan["execution_order"]) == 4
                and len(set(plan["execution_order"])) == 4
                and PF._valid_sha256_hex(plan.get("config_hash"))
                and PF._valid_sha256_hex(plan.get("runtime_plan_hash"))
                and len(plan.get("pair_plan", [])) == 2)
    except Exception:
        return False


def cmd_aggregate(a):
    """A/A 验收出口:完整分母验收。零次实验不得聚合成功;任何缺失/多余/乱序/身份
    不符/非终态/fixture 产物 → acceptance_eligible=false 且 rc=1。"""
    root = os.path.realpath(a.artifact_root)
    failures = []
    rejected = []
    eligible = []

    def out(rc):
        modes_by_rid = {}
        if plan:
            modes_by_rid = {r["run_id"]: r["telemetry_mode"]
                            for p in plan.get("pair_plan", [])
                            for r in (p.get("off", {}), p.get("on", {}))}
        obs_modes = [e["telemetry_mode"] for e in eligible]
        result = {"mode": "aggregate",
                  "attempts_expected": 4,
                  "attempts_observed": attempts_observed,
                  "attempts_terminal": attempts_terminal,
                  "off_observed": obs_modes.count("OFF"),
                  "on_observed": obs_modes.count("ON"),
                  "eligible_count": len(eligible),
                  "rejected_count": len(rejected),
                  "eligible": eligible, "rejected": rejected,
                  "acceptance_failures": failures,
                  "acceptance_eligible": rc == 0,
                  "plan_runtime_plan_hash": (plan or {}).get("runtime_plan_hash"),
                  "expected_mode_order": [modes_by_rid.get(r) for r in
                                          (plan or {}).get("execution_order", [])]}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=1))
        return rc

    plan = None
    attempts_observed = 0
    attempts_terminal = 0
    try:
        plan = json.load(open(os.path.join(root, "aa_plan", "aa_frozen_plan.json"),
                              encoding="utf-8"))
    except (OSError, ValueError):
        failures.append("frozen_plan_missing_or_unparsable")
        return out(1)
    if not _plan_schema_ok(plan):
        failures.append("frozen_plan_schema_invalid")
        return out(1)
    try:
        lrec = json.load(open(os.path.join(root, "aa_plan", "launch_record.json"),
                              encoding="utf-8"))
    except (OSError, ValueError):
        failures.append("launch_record_missing_or_unparsable")
        return out(1)
    if lrec.get("record_class") != RECORD_ACCEPTANCE:
        failures.append(f"launch_record_class={lrec.get('record_class')}"
                        "(NON_ACCEPTANCE_FIXTURE/dry-run 产物永久不入 A/A 分母)")
    if lrec.get("gate", {}).get("approval_fixture_test_only"):
        failures.append("launch_record_fixture_approval(fixture 审批产物不入分母)")
    if lrec.get("producer_started") != 1:
        failures.append("producer_not_started")
    if lrec.get("stopped_on_failure"):
        failures.append(f"stopped_on_failure={lrec['stopped_on_failure']}")
    lrec_attempts = {x.get("run_id"): x for x in lrec.get("attempts", [])}
    for x in lrec.get("attempts", []):
        if x.get("state") == "NOT_STARTED_PRIOR_FAILURE":
            failures.append(f"attempt_not_started:{x.get('run_id')}")
        elif x.get("rc") != 0:
            failures.append(f"attempt_rc_nonzero:{x.get('run_id')}={x.get('rc')}")
    approval_sha = lrec.get("gate", {}).get("approval_sha256")

    modes_by_rid = {r["run_id"]: r["telemetry_mode"]
                    for p in plan["pair_plan"] for r in (p["off"], p["on"])}
    expected_dirs = {f"{rid}_{modes_by_rid[rid]}": rid for rid in plan["execution_order"]}
    att_dir = os.path.join(root, "attempts")
    names = sorted(os.listdir(att_dir)) if os.path.isdir(att_dir) else []
    attempts_observed = len(names)
    if attempts_observed != 4:
        failures.append(f"attempts_observed={attempts_observed}(必须恰好 4)")
    extra = [n for n in names if n not in expected_dirs]
    for n in extra:
        rejected.append({"dir": n, "reason": "unplanned_attempt(计划外 run,含直接 run_batch 产物)"})
    missing = [d for d in expected_dirs if d not in names]
    for d in missing:
        failures.append(f"planned_attempt_missing:{d}")

    seen_rids = set()
    for name in names:
        if name in extra:
            continue
        d = os.path.join(att_dir, name)
        ident_p = os.path.join(d, "aa_identity.json")
        if not os.path.isfile(ident_p):
            rejected.append({"dir": name, "reason": "no_aa_identity"})
            continue
        try:
            ident = json.load(open(ident_p, encoding="utf-8"))
        except (OSError, ValueError):
            rejected.append({"dir": name, "reason": "identity_unparsable"})
            continue
        rid = ident.get("run_id")
        reasons = []
        if ident.get("schema_version") != IDENTITY_SCHEMA:
            reasons.append("identity_schema_mismatch")
        if ident.get("non_acceptance_fixture"):
            reasons.append("non_acceptance_fixture(dry-run/fixture 产物永久拒)")
        if rid != expected_dirs[name]:
            reasons.append("identity_run_id_mismatch_dir")
        if rid in seen_rids:
            reasons.append("duplicate_run_id")
        if ident.get("telemetry_mode") != modes_by_rid.get(rid):
            reasons.append("identity_mode_mismatch_plan")
        if (ident.get("config_hash") != plan["config_hash"]
                or ident.get("runtime_plan_hash") != plan["runtime_plan_hash"]):
            reasons.append("identity_plan_hash_mismatch")
        if ident.get("aa_batch_id") != lrec.get("aa_batch_id"):
            reasons.append("identity_batch_mismatch_launch_record")
        if approval_sha is None or ident.get("approval_sha256") != approval_sha:
            reasons.append("identity_approval_sha_mismatch")
        want_bid = f"{ident.get('aa_batch_id')}.{rid}.{ident.get('telemetry_mode')}"
        mode = ident.get("telemetry_mode")
        axes = {"process": "UNKNOWN", "evidence": "UNKNOWN", "finalization": "UNKNOWN"}
        tr_p = os.path.join(d, "task_record.json")
        if not os.path.isfile(tr_p):
            reasons.append("no_batch_lifecycle_task_record")
        else:
            try:
                tr = json.load(open(tr_p, encoding="utf-8"))
                if tr.get("batch_id") != want_bid:
                    reasons.append("task_record_batch_id_mismatch_identity")
                tel = tr.get("telemetry")
                if not isinstance(tel, dict) or "enabled" not in tel:
                    reasons.append("task_record_telemetry_evidence_missing")
                elif bool(tel["enabled"]) != (mode == "ON"):
                    reasons.append("task_record_telemetry_mismatch_identity")
            except (OSError, ValueError):
                reasons.append("task_record_unparsable")
        # 半写现场:atomic_write 的 .tmp 残留 → 拒
        tmps = [f for f in os.listdir(d) if f.endswith(".tmp")]
        if tmps:
            reasons.append(f"half_written_tmp_residue:{tmps[:2]}")
        # monitor_status = 三轴终态唯一权威(表示层可解析≠语义有效,五验补正)
        terminal = True
        ms_p = os.path.join(d, "monitor_status.json")
        mon = None
        try:
            mon = json.load(open(ms_p, encoding="utf-8"))
        except (OSError, ValueError):
            terminal = False
            reasons.append("monitor_status_missing_or_corrupt")
        if mon is not None:
            mon_reasons = validate_monitor_terminal(mon, want_bid, mode)
            if mon_reasons:
                terminal = False
                reasons += mon_reasons
            if isinstance(mon, dict):
                po = mon.get("producer_outcome")
                axes["process"] = po if po in MONITOR_PRODUCER_OUTCOMES else "INVALID"
                ev = mon.get("evidence_status")
                axes["evidence"] = ev if ev in MONITOR_EVIDENCE_STATUSES else "INVALID"
                cl = mon.get("cleanup_status")
                axes["finalization"] = cl if cl in MONITOR_CLEANUP_STATUSES else "INVALID"
        bf_p = os.path.join(d, "batch_final.json")
        try:
            bf = json.load(open(bf_p, encoding="utf-8"))
            if bf.get("schema_version") != 1 or bf.get("batch_id") != want_bid:
                terminal = False
                reasons.append("batch_final_schema_or_batch_id_invalid")
            if bf.get("final") != "done":
                terminal = False
                reasons.append("batch_final_not_done")
            rrm = bf.get("run_rc_map")
            if not isinstance(rrm, dict) or not rrm or any(v != 0 for v in rrm.values()):
                terminal = False
                reasons.append("batch_final_run_rc_map_invalid_or_nonzero")
            elif isinstance(mon, dict) and mon.get("run_rc_map") != rrm:
                terminal = False
                reasons.append("monitor_final_run_rc_map_inconsistent")
        except (OSError, ValueError):
            terminal = False
            reasons.append("batch_final_missing_or_corrupt")
        r1_p = os.path.join(d, "runs", "run_1.json")
        try:
            r1 = json.load(open(r1_p, encoding="utf-8"))
            if (r1.get("schema_version") != 1 or r1.get("batch_id") != want_bid
                    or r1.get("run_index") != 1):
                terminal = False
                reasons.append("run_record_schema_or_identity_invalid")
            if r1.get("rc") != 0:
                terminal = False
                reasons.append("run_record_rc_nonzero")
            if not (isinstance(r1.get("start"), str) and isinstance(r1.get("end"), str)
                    and r1["end"] >= r1["start"]):
                terminal = False
                reasons.append("run_record_time_invalid")
            # 时间闭包:终态(monitor)不得早于 run 结束落盘(陈旧/伪造终态;
            # mtime 为文件系统证据,1s 容差)
            try:
                if os.path.getmtime(ms_p) + 1.0 < os.path.getmtime(r1_p):
                    terminal = False
                    reasons.append("monitor_terminal_predates_run_end(mtime)")
            except OSError:
                terminal = False
                reasons.append("terminal_mtime_unreadable")
        except (OSError, ValueError):
            terminal = False
            reasons.append("run_record_missing_or_corrupt")
        if terminal:
            attempts_terminal += 1
        la = lrec_attempts.get(rid)
        if not la or la.get("rc") != 0:
            reasons.append("launch_record_attempt_missing_or_failed")
        if reasons:
            rejected.append({"dir": name, "reason": ";".join(reasons),
                             "axes": axes, "terminal": terminal})
            continue
        seen_rids.add(rid)
        eligible.append({"dir": name, "run_id": rid,
                         "telemetry_mode": ident["telemetry_mode"],
                         "axes": axes, "terminal": terminal})

    eligible.sort(key=lambda e: plan["execution_order"].index(e["run_id"]))
    obs = [e["telemetry_mode"] for e in eligible]
    if obs != [modes_by_rid[r] for r in plan["execution_order"]]:
        failures.append(f"mode_order_observed={obs}(必须={['OFF','OFF','ON','ON']})")
    if len(eligible) != 4:
        failures.append(f"eligible_count={len(eligible)}(必须恰好 4;零次实验不得聚合成功)")
    if rejected:
        failures.append(f"rejected_count={len(rejected)}(必须为 0)")
    return out(1 if failures else 0)


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        if a.validate_only:
            return cmd_validate(a)
        if a.execute:
            return cmd_execute(a)
        if a.dry_run:
            return cmd_dry_run(a)
        return cmd_aggregate(a)
    except UsageError as e:
        ap.error(str(e))          # argparse 语义:rc=2
    except EnvironmentError as e:
        print(f"aa_cli: 环境错误: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
