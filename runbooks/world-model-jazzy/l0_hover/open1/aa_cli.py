#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 · A/A 具名正式操作入口(唯一;2026-07-20 二次补正令包一/包二)。

固定顺序(execute):
  真实 config/runtime plan 物化(原子落盘)→ 独立算 sha256 → docker 查询真实镜像
  digest → OFF×2+ON×2 冻结计划落盘 → 唯一 preflight(aa_preflight)→ 最后一次
  hash/digest/HEAD/dirty 复核 + 负责人本次启动授权机器门(aa_launch.launch_aa)→
  依次经**正式 batch_lifecycle.py launch** 发起 4 个 attempt(OFF,OFF,ON,ON,
  每 attempt 独立 artifact root + 不可伪造共同计划身份 aa_identity.json)→
  任一 attempt 失败立即停止后续,已发起分母保留。

--validate-only:只物化+真实 hash+真实 digest+preflight,绝不启动 producer。
--aggregate:A/A 专用聚合,只接受带本冻结计划身份的 attempt;直接 run_batch
  产生的记录(无 aa_identity.json 或 hash 不符)一律拒绝,不入 A/A 分母。

退出码:0=成功(validate=READY;execute=4/4 全过;aggregate=聚合成功且无拒绝项)
        1=门拒绝/非 READY/attempt 失败/聚合含拒绝项
        2=用法错误(未知参数/缺参/非法枚举;argparse 语义)
        3=环境错误(docker/git/输入文件不可用)
真实审批文件只能在负责人明确下达 A/A 启动指令后由负责人产生;本 CLI 绝不生成。
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


def _run(argv, timeout=30):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def real_image_digest(companion_tag):
    """docker image inspect 真实 digest(只读查询,不启动容器)。失败=环境错误。"""
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
        description="A/A(OFF×2+ON×2)唯一正式操作入口:物化→真实 hash→真实 digest→"
                    "preflight→授权机器门→正式 batch_lifecycle producer 链。"
                    "直接调用 run_batch.sh 的结果不得计入 A/A 分母。")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true",
                      help="只物化计划+算真实 hash+读真实 digest+跑 preflight;绝不启动 producer")
    mode.add_argument("--execute", action="store_true",
                      help="完整启动链;必须提供 --owner-approval(负责人本次启动授权 artifact)")
    mode.add_argument("--aggregate", action="store_true",
                      help="聚合 --artifact-root 下的 A/A attempts(拒绝无计划身份的记录)")
    ap.add_argument("--config", help="canonical config 输入 JSON(validate/execute 必填)")
    ap.add_argument("--runtime-plan", help="runtime plan 输入 JSON(validate/execute 必填)")
    ap.add_argument("--artifact-root", required=True, help="A/A 根目录")
    ap.add_argument("--companion-tag", help="companion 镜像 tag(如 jazzy-9a1ce95c56e2;"
                                            "validate/execute 必填,CLI 用 docker 查真实 digest)")
    ap.add_argument("--main-repo", default=L.DEFAULT_MAIN_REPO)
    ap.add_argument("--wm-repo", default=L.DEFAULT_WM_REPO)
    ap.add_argument("--ros-domain", default="7")
    ap.add_argument("--readiness-topic", default="/mavlink_external_nav/status")
    ap.add_argument("--extnav-topic", default="/external_nav/status")
    ap.add_argument("--producer-mode", choices=sorted(PRODUCER_SCRIPTS), default="l2",
                    help="leaf producer(正式脚本,经 batch_lifecycle 启动)")
    ap.add_argument("--task-id", default="hover")
    ap.add_argument("--map-id", default="iris_maze")
    ap.add_argument("--timeout-sec", type=int, default=1500)
    ap.add_argument("--duration", type=float, default=1500.0)
    ap.add_argument("--startup-budget", type=float, default=120.0)
    ap.add_argument("--per-run-teardown", type=float, default=30.0)
    ap.add_argument("--inter-run-gap", type=float, default=10.0)
    ap.add_argument("--finalization-budget", type=float, default=180.0)
    ap.add_argument("--owner-approval", help="负责人本次 A/A 启动授权 artifact 路径(execute 必需)")
    ap.add_argument("--allow-fixture-approval", action="store_true",
                    help="仅测试:接受 fixture_test_only 审批样本(launch record 显式标注)")
    ap.add_argument("--preflight-out", help="preflight 输出路径(默认 <root>/aa_plan/preflight.json)")
    ap.add_argument("--launch-record-out",
                    help="launch record 输出路径(默认 <root>/aa_plan/launch_record.json)")
    return ap


def derive_identity_wait(a):
    import batch_lifecycle as BL
    ns = argparse.Namespace(startup_budget=a.startup_budget, duration=a.duration,
                            per_run_teardown=a.per_run_teardown, inter_run_gap=a.inter_run_gap)
    return BL.identity_wait_sec(ns)


def materialize_and_plan(a):
    """物化输入→真实 hash→真实 digest→冻结计划(含 execution_order=OFF,OFF,ON,ON)。"""
    for path, name in ((a.config, "--config"), (a.runtime_plan, "--runtime-plan")):
        if not path:
            raise UsageError(f"{name} 为 validate/execute 必填")
    if not a.companion_tag:
        raise UsageError("--companion-tag 为 validate/execute 必填")
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


class UsageError(Exception):
    pass


def make_official_producer(a, root, plan, aa_batch_id, approval_path, record):
    """正式 producer 链:每 attempt 一次 batch_lifecycle.py launch(不复制第二套
    生命周期);OFF/ON 经 WP303_TELEMETRY 注入;attempt 根先盖 aa_identity 身份。"""
    modes = {r["run_id"]: r["telemetry_mode"]
             for p in plan["pair_plan"] for r in (p["off"], p["on"])}
    approval_sha = PF._sha256_file(approval_path)
    script = os.path.join(L0_HOVER, PRODUCER_SCRIPTS[a.producer_mode])

    def producer(_plan):
        for run_id in plan["execution_order"]:
            mode = modes[run_id]
            att_root = os.path.join(root, "attempts", f"{run_id}_{mode}")
            os.makedirs(os.path.join(att_root, "runs"), exist_ok=True)
            L.atomic_write(os.path.join(att_root, "aa_identity.json"), L.canonical_json_bytes({
                "schema_version": IDENTITY_SCHEMA, "aa_batch_id": aa_batch_id,
                "run_id": run_id, "telemetry_mode": mode,
                "config_hash": plan["config_hash"],
                "runtime_plan_hash": plan["runtime_plan_hash"],
                "approval_sha256": approval_sha, "cli": "aa_cli"}))
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
                      "producer_started": 0}, ensure_ascii=False, sort_keys=True, indent=1))
    return 0 if pf["preflight_status"] == "READY" else 1


def cmd_execute(a):
    root, plan_dir, plan, digest = materialize_and_plan(a)
    aa_batch_id = f"aa_{time.time_ns()}_{uuid.uuid4().hex[:8]}"
    record = {"mode": "execute", "aa_batch_id": aa_batch_id, "attempts": [],
              "stopped_on_failure": None}
    rec_out = a.launch_record_out or os.path.join(plan_dir, "launch_record.json")
    pf_out = a.preflight_out or os.path.join(plan_dir, "preflight.json")
    # 主机 SITL 互斥(与 run_batch 同一把锁,execute 全程持有)
    lfd = os.open(os.environ.get("BC_LOCK_PATH", DEFAULT_LOCK), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("aa_cli: another SITL batch holds the host lock", file=sys.stderr)
        return 3
    producer = (make_official_producer(a, root, plan, aa_batch_id, a.owner_approval, record)
                if a.owner_approval else None)
    lrec = L.launch_aa(
        plan,
        producer if producer else (lambda _p: None),
        lambda name: real_image_digest(a.companion_tag),
        approval_path=a.owner_approval,
        repo_state=lambda: {"main_head": repo_head(a.main_repo),
                            "wm_head": repo_head(a.wm_repo),
                            "main_dirty": repo_dirty(a.main_repo),
                            "wm_dirty": repo_dirty(a.wm_repo)},
        main_repo=a.main_repo, wm_repo=a.wm_repo, output=pf_out,
        allow_fixture_approval=a.allow_fixture_approval)
    record.update({"gate": lrec, "producer_started": lrec["producer_started"]})
    L.atomic_write(rec_out, json.dumps(record, ensure_ascii=False, sort_keys=True,
                                       indent=1).encode())
    print(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=1))
    if lrec["producer_started"] != 1:
        return 1
    bad = [x for x in record["attempts"] if x["rc"] != 0]
    return 1 if bad else 0


def cmd_aggregate(a):
    root = os.path.realpath(a.artifact_root)
    plan_path = os.path.join(root, "aa_plan", "aa_frozen_plan.json")
    try:
        plan = json.load(open(plan_path, encoding="utf-8"))
    except (OSError, ValueError):
        print(json.dumps({"error": "aa_frozen_plan_missing", "root": root}))
        return 3
    att_dir = os.path.join(root, "attempts")
    eligible, rejected = [], []
    names = sorted(os.listdir(att_dir)) if os.path.isdir(att_dir) else []
    for name in names:
        d = os.path.join(att_dir, name)
        ident_p = os.path.join(d, "aa_identity.json")
        if not os.path.isfile(ident_p):
            rejected.append({"dir": name, "reason": "no_aa_identity(直接 run_batch 类记录,不入 A/A 分母)"})
            continue
        try:
            ident = json.load(open(ident_p, encoding="utf-8"))
        except (OSError, ValueError):
            rejected.append({"dir": name, "reason": "identity_unparsable"})
            continue
        if (ident.get("schema_version") != IDENTITY_SCHEMA
                or ident.get("config_hash") != plan.get("config_hash")
                or ident.get("runtime_plan_hash") != plan.get("runtime_plan_hash")):
            rejected.append({"dir": name, "reason": "identity_plan_mismatch"})
            continue
        if not os.path.isfile(os.path.join(d, "task_record.json")):
            rejected.append({"dir": name, "reason": "no_batch_lifecycle_task_record"})
            continue
        eligible.append({"dir": name, "run_id": ident["run_id"],
                         "telemetry_mode": ident["telemetry_mode"]})
    out = {"mode": "aggregate", "plan_runtime_plan_hash": plan.get("runtime_plan_hash"),
           "eligible": eligible, "rejected": rejected,
           "eligible_modes_in_execution_order":
               [e["telemetry_mode"] for e in
                sorted(eligible, key=lambda e: plan.get("execution_order", []).index(e["run_id"])
                       if e["run_id"] in plan.get("execution_order", []) else 99)]}
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1))
    return 1 if rejected else 0


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        if a.validate_only:
            return cmd_validate(a)
        if a.execute:
            return cmd_execute(a)
        return cmd_aggregate(a)
    except UsageError as e:
        ap.error(str(e))          # argparse 语义:rc=2
    except EnvironmentError as e:
        print(f"aa_cli: 环境错误: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
