#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 · aa_cli 正式操作入口门(二次补正令包四 + 三次补正令包五)。

固化 Codex 三轮反例:
  ①aa_launch 无 CLI → aa_cli --help 必须有帮助文本;
  ②run_batch 直通 → 聚合器拒无身份记录;
  ③aggregate 空分母 rc=0 / fixture 审批与测试覆盖 env 可进生产 execute →
    完整分母验收 + 生产/dry-run 硬隔离。
dry-run 经正式 batch_lifecycle(NAVLAB_SIM_CMD stub=官方 dry 机制);不启动
真实仿真/SITL/容器。运行前置:sourced+真实 docker(image inspect 只读)。SKIP 恒=0。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aa_launch as AL  # noqa: E402

FAIL = 0
RAN = 0
CLI = os.path.join(HERE, "aa_cli.py")
WM_REPO = "/home/ai4s/projects/world-model"
TAG = "jazzy-9a1ce95c56e2"


def ck(name, got, want):
    global FAIL, RAN
    RAN += 1
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def cli(args, env_extra=None, env_drop=(), timeout=300):
    env = {k: v for k, v in os.environ.items() if k not in env_drop}
    env.setdefault("BC_LOCK_PATH", os.path.join(tempfile.gettempdir(), "aa_cli_test.lock"))
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, CLI] + args,
                          capture_output=True, text=True, env=env, timeout=timeout)


def fixture_main_repo():
    repo = tempfile.mkdtemp(prefix="aacli_main_")
    subprocess.run(["git", "init", "-q", repo], check=True)
    open(os.path.join(repo, "f.txt"), "w").write("v1\n")
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "x"], check=True)
    return repo


def write_inputs(d):
    cfg = os.path.join(d, "config.json")
    rtp = os.path.join(d, "runtime_plan.json")
    open(cfg, "w").write(json.dumps(
        {"task_id": "hover", "map_id": "iris_maze", "timeout_sec": 1500,
         "ros_domain_id": "7", "telemetry_arms": ["OFF", "OFF", "ON", "ON"]}))
    open(rtp, "w").write(json.dumps(
        {"services": ["gazebo-headless", "ardupilot-sitl", "mavlink-router",
                      "slam-cartographer", "companion"],
         "companion_image": f"navlab/companion:{TAG}"}))
    return cfg, rtp


def base_args(root, cfg, rtp, mainfx):
    return ["--config", cfg, "--runtime-plan", rtp, "--artifact-root", root,
            "--companion-tag", TAG, "--main-repo", mainfx]


def read_plan(root):
    return json.load(open(os.path.join(root, "aa_plan", "aa_frozen_plan.json")))


def fixture_approval(root, mainfx, **over):
    plan = read_plan(root)
    head = subprocess.run(["git", "-C", mainfx, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    ap = {"schema_version": "wp304.aa_approval.v1", "approval_purpose": "A_A_OFF2_ON2",
          "approval_state": "APPROVED", "fixture_test_only": True,
          "approved_by": "FIXTURE-test-only", "approved_at": "2026-07-20T00:00:00Z",
          "main_commit": head, "world_model_commit": plan["world_model_commit"],
          "config_hash": plan["config_hash"], "runtime_plan_hash": plan["runtime_plan_hash"],
          "image_digest": plan["image_digests"]["companion"],
          "ros_domain": "7", "sample_plan": "OFF2_ON2",
          "frozen_plan_sha256": AL.frozen_plan_sha256(plan)}
    ap.update(over)
    p = os.path.join(root, "fixture_approval.json")
    open(p, "w").write(json.dumps(ap))
    return p


DRY_ENV = {"NAVLAB_SIM_CMD": "exit 0", "WP303_TELEMETRY_CMD": "sleep 0.1"}
CLEAN_DROP = ("NAVLAB_SIM_CMD", "WP303_TELEMETRY_CMD", "WP303_TELEMETRY_BACKEND",
              "WP303_TELEMETRY_FIXTURE_INPUT", "WP303_TELEMETRY_REGISTRY_WAIT")
DRY_BUDGETS = ["--duration", "0.2", "--startup-budget", "0.5",
               "--per-run-teardown", "0.1", "--inter-run-gap", "0.05",
               "--finalization-budget", "2"]


print("======== 06.0 前置:sourced+docker ========")
ck("测试环境已 source(rclpy 可导入;未 source=如实红)",
   subprocess.run([sys.executable, "-c", "import rclpy"],
                  capture_output=True).returncode, 0)
before_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout

print("======== 06.1 CLI 用法正反例 ========")
cp = cli(["--help"])
ck("--help rc=0 且含四模式",
   (cp.returncode, all(m in cp.stdout for m in
                       ("--validate-only", "--execute", "--dry-run", "--aggregate"))),
   (0, True))
ck("零参数 rc=2", cli([]).returncode, 2)
ck("未知参数 rc=2", cli(["--validate-only", "--artifact-root", "/tmp/x",
                        "--bogus"]).returncode, 2)
ck("已删除的 --allow-fixture-approval → rc=2(生产后门不存在)",
   cli(["--execute", "--artifact-root", "/tmp/x",
        "--allow-fixture-approval"]).returncode, 2)
ck("非法枚举 rc=2", cli(["--validate-only", "--artifact-root", "/tmp/x",
                        "--config", "/dev/null", "--runtime-plan", "/dev/null",
                        "--companion-tag", TAG, "--producer-mode", "nope"]).returncode, 2)
ck("缺 --config rc=2", cli(["--validate-only", "--artifact-root", "/tmp/x",
                            "--runtime-plan", "/dev/null",
                            "--companion-tag", TAG]).returncode, 2)
ck("不存在镜像 tag → rc=3",
   cli(["--validate-only", "--artifact-root", tempfile.mkdtemp(),
        "--config", write_inputs(tempfile.mkdtemp())[0],
        "--runtime-plan", write_inputs(tempfile.mkdtemp())[1],
        "--companion-tag", "jazzy-nonexistent000"]).returncode, 3)

print("======== 06.2 validate-only:输出整计划 SHA,producer=0 ========")
work = tempfile.mkdtemp(prefix="aacli_")
mainfx = fixture_main_repo()
cfg, rtp = write_inputs(work)
root_v = os.path.join(work, "root_v")
cp = cli(["--validate-only"] + base_args(root_v, cfg, rtp, mainfx))
out = json.loads(cp.stdout)
ck("validate-only rc=0 READY producer=0",
   (cp.returncode, out["preflight_status"], out["producer_started"]), (0, "READY", 0))
ck("attempts 不存在", os.path.isdir(os.path.join(root_v, "attempts")), False)
ck("输出整计划 frozen_plan_sha256(负责人指令引用点)",
   out["frozen_plan_sha256"], AL.frozen_plan_sha256(read_plan(root_v)))

print("======== 06.3 生产 execute 硬门(fixture 审批/测试覆盖 env 一律拒)========")
def run_mode(mode_flag, root, extra, env_extra=None, env_drop=CLEAN_DROP):
    cp = cli([mode_flag] + base_args(root, cfg, rtp, mainfx) + DRY_BUDGETS + extra,
             env_extra=env_extra, env_drop=env_drop)
    rec_p = os.path.join(root, "aa_plan", "launch_record.json")
    rec = json.load(open(rec_p)) if os.path.isfile(rec_p) else None
    return cp, rec

root_e = os.path.join(work, "root_noap")
cp, rec = run_mode("--execute", root_e, [])
ck("无 approval → rc=1 producer=0 approval_missing",
   (cp.returncode, rec["producer_started"],
    "approval_missing" in rec["gate"]["refusal_reasons"]), (1, 0, True))
ck("record_class=ACCEPTANCE_CANDIDATE(真实链状态类)",
   rec["record_class"], "ACCEPTANCE_CANDIDATE")

root_e2 = os.path.join(work, "root_fixap")
cli(["--validate-only"] + base_args(root_e2, cfg, rtp, mainfx) + DRY_BUDGETS)
apx = fixture_approval(root_e2, mainfx)
cp, rec = run_mode("--execute", root_e2, ["--owner-approval", apx])
ck("生产 execute + fixture 审批 → producer=0(后门已死)",
   (cp.returncode, rec["producer_started"],
    "fixture_approval_not_allowed" in rec["gate"]["refusal_reasons"]), (1, 0, True))
ck("生产 execute 拒后 attempts 未发起", rec["attempts"], [])

for env_name, env_val in (("NAVLAB_SIM_CMD", "exit 0"),
                          ("WP303_TELEMETRY_CMD", "sleep 0.1"),
                          ("WP303_TELEMETRY_FIXTURE_INPUT", "/tmp/fx.json"),
                          ("WP303_TELEMETRY_REGISTRY_WAIT", "5"),
                          ("WP303_TELEMETRY_BACKEND", "fixture")):
    root_env = os.path.join(work, f"root_env_{env_name}")
    cp, rec = run_mode("--execute", root_env, [], env_extra={env_name: env_val})
    ck(f"生产 execute + {env_name} → producer=0 且拒绝原因点名",
       (cp.returncode, rec["producer_started"],
        any(env_name in r for r in rec["gate"]["refusal_reasons"])), (1, 0, True))

root_e3 = os.path.join(work, "root_plansha")
cli(["--validate-only"] + base_args(root_e3, cfg, rtp, mainfx) + DRY_BUDGETS)
ap3 = fixture_approval(root_e3, mainfx, fixture_test_only=False,
                       frozen_plan_sha256="ff" * 32)
cp, rec = run_mode("--execute", root_e3, ["--owner-approval", ap3])
ck("approval 整计划 SHA 不符 → producer=0",
   (cp.returncode, rec["producer_started"],
    "approval_frozen_plan_sha_mismatch" in rec["gate"]["refusal_reasons"]), (1, 0, True))

print("======== 06.4 dry-run:独立测试链(强制 fixture 审批;产物永久标记)========")
root_d = os.path.join(work, "root_dry")
cli(["--validate-only"] + base_args(root_d, cfg, rtp, mainfx) + DRY_BUDGETS)
apd_real = fixture_approval(root_d, mainfx, fixture_test_only=False)
cp, rec = run_mode("--dry-run", root_d, ["--owner-approval", apd_real],
                   env_extra=DRY_ENV, env_drop=())
ck("dry-run + 非 fixture 审批 → 拒(真实审批不得被 dry-run 冒用)",
   (cp.returncode, rec["producer_started"],
    "dry_run_requires_fixture_approval" in rec["gate"]["refusal_reasons"]), (1, 0, True))
apd = fixture_approval(root_d, mainfx)
cp, rec = run_mode("--dry-run", root_d, ["--owner-approval", apd],
                   env_extra=DRY_ENV, env_drop=())
ck("dry-run 链 rc=0(经正式 batch_lifecycle)", cp.returncode, 0)
ck("record_class=NON_ACCEPTANCE_FIXTURE 且 acceptance_eligible=false",
   (rec["record_class"], rec["acceptance_eligible"], rec["non_acceptance_fixture"]),
   ("NON_ACCEPTANCE_FIXTURE", False, True))
atts = rec["attempts"]
ck("dry-run 四 attempt=OFF,OFF,ON,ON 全 rc=0",
   [(x["run_id"], x["telemetry_mode"], x["rc"]) for x in atts],
   [("aa-r1", "OFF", 0), ("aa-r3", "OFF", 0), ("aa-r2", "ON", 0), ("aa-r4", "ON", 0)])
for x in atts:
    ck(f"{x['run_id']}:task_record 存在(batch_lifecycle 正式链)",
       os.path.isfile(os.path.join(x["artifact_root"], "task_record.json")), True)
    ident = json.load(open(os.path.join(x["artifact_root"], "aa_identity.json")))
    ck(f"{x['run_id']}:身份永久标记 non_acceptance_fixture",
       ident["non_acceptance_fixture"], True)

print("======== 06.5 dry-run 失败即停,分母保留 ========")
root_f = os.path.join(work, "root_fail")
cli(["--validate-only"] + base_args(root_f, cfg, rtp, mainfx) + DRY_BUDGETS)
apf = fixture_approval(root_f, mainfx)
cp, rec = run_mode("--dry-run", root_f, ["--owner-approval", apf],
                   env_extra={"NAVLAB_SIM_CMD": "exit 7", "WP303_TELEMETRY_CMD": "sleep 0.1"},
                   env_drop=())
started = [x for x in rec["attempts"] if x.get("rc") is not None]
not_started = [x for x in rec["attempts"] if x.get("state") == "NOT_STARTED_PRIOR_FAILURE"]
ck("失败链 rc=1;仅 1 发起且 rc≠0;3 个显式 NOT_STARTED",
   (cp.returncode, len(started), started[0]["rc"] != 0, len(not_started)), (1, 1, True, 3))

print("======== 06.6 aggregate 完整分母验收(Codex 反例:空分母必须非零)========")
def agg(root):
    cp = cli(["--aggregate", "--artifact-root", root])
    return cp.returncode, json.loads(cp.stdout)

root_z = os.path.join(work, "root_zero")
os.makedirs(os.path.join(root_z, "aa_plan"))
shutil.copy(os.path.join(root_v, "aa_plan", "aa_frozen_plan.json"),
            os.path.join(root_z, "aa_plan", "aa_frozen_plan.json"))
rc, a = agg(root_z)
ck("零 attempt(无 launch_record) → rc=1,acceptance_eligible=false",
   (rc, a["acceptance_eligible"], a["eligible_count"]), (1, False, 0))
ck("聚合输出含完整分母字段",
   all(k in a for k in ("attempts_expected", "attempts_observed", "attempts_terminal",
                        "off_observed", "on_observed", "eligible_count",
                        "rejected_count", "acceptance_eligible")), True)
rc, a = agg(root_d)
ck("dry-run 产物进正式 aggregate → rc=1(NON_ACCEPTANCE_FIXTURE 永久拒)",
   (rc, a["acceptance_eligible"],
    any("NON_ACCEPTANCE_FIXTURE" in f for f in a["acceptance_failures"])), (1, False, True))


def real_monitor(bid_full, mode):
    """按 batch_lifecycle 真实写出契约构造 monitor(源码 L547-556+finalize_telemetry;
    expected 来源=生产者写入点,非被测 aggregate)。B 包后:ON 臂 telemetry 分录须
    COMPLETE/WRITTEN(旧 UNKNOWN/MISSING 现为 S 系列负例);OFF 臂=真实 OFF 形状。"""
    if mode == "ON":
        ts = {"enabled": True, "process_state": "EXITED_ZERO", "sidecar_rc": 0,
              "evidence_state": "COMPLETE", "finalization_state": "WRITTEN"}
    else:
        ts = {"enabled": False, "process_state": "OFF", "sidecar_rc": None,
              "evidence_state": "OFF", "finalization_state": "OFF"}
    return {"schema_version": 1, "batch_id": bid_full, "readonly": False,
            "producer_outcome": "SUCCEEDED", "evidence_status": "COMPLETE",
            "evidence_missing": None, "cleanup_status": "CLEAN",
            "container_cleanup": "NOT_ATTEMPTED", "run_rc_map": {"1": 0},
            "telemetry_status": ts}


def real_sidecar_final(bid_full, rid):
    """按 telemetry_sidecar write_batch_final 真实契约构造(schema=wp304.telemetry.v1)。"""
    return {"schema_version": "wp304.telemetry.v1", "batch_id": bid_full,
            "run_ids_processed": [rid], "process_rc": 0,
            "evidence_state": "COMPLETE", "finalization_state": "WRITTEN",
            "failure_reasons": [], "attempts": [], "truncated": {},
            "dropped_records": {}, "telemetry_overrun": False,
            "business_outcome": "OK", "evidence_gate": {"status": "COMPLETE"}}


def fabricate_acceptance_root():
    """契约级正例底座(P04.2):按 §8.2 权威终态契约构造 ACCEPTANCE_CANDIDATE 现场。
    (五验补正:旧版在此写 monitor=`{}` 并称"完整合规"——已删除;该现场现为正式负例。)"""
    root = os.path.join(work, f"root_fab_{len(os.listdir(work))}")
    os.makedirs(os.path.join(root, "aa_plan"))
    shutil.copy(os.path.join(root_v, "aa_plan", "aa_frozen_plan.json"),
                os.path.join(root, "aa_plan", "aa_frozen_plan.json"))
    plan = read_plan(root)
    modes = {r["run_id"]: r["telemetry_mode"]
             for p in plan["pair_plan"] for r in (p["off"], p["on"])}
    bid, apsha = "aa_fab_1", "ab" * 32
    lrec = {"mode": "execute", "record_class": "ACCEPTANCE_CANDIDATE",
            "non_acceptance_fixture": False, "acceptance_eligible": False,
            "aa_batch_id": bid, "frozen_plan_sha256": AL.frozen_plan_sha256(plan),
            "producer_started": 1, "stopped_on_failure": None,
            "attempts": [{"run_id": r, "telemetry_mode": modes[r],
                          "artifact_root": os.path.join(root, "attempts", f"{r}_{modes[r]}"),
                          "rc": 0} for r in plan["execution_order"]],
            "gate": {"approval_fixture_test_only": False, "approval_sha256": apsha,
                     "refusal_reasons": [], "preflight_status": "READY",
                     "producer_started": 1}}
    open(os.path.join(root, "aa_plan", "launch_record.json"), "w").write(json.dumps(lrec))
    for r in plan["execution_order"]:
        mode = modes[r]
        bidf = f"{bid}.{r}.{mode}"
        d = os.path.join(root, "attempts", f"{r}_{mode}")
        os.makedirs(os.path.join(d, "runs"))
        open(os.path.join(d, "aa_identity.json"), "w").write(json.dumps(
            {"schema_version": "wp304.aa_identity.v1", "aa_batch_id": bid,
             "run_id": r, "telemetry_mode": mode,
             "config_hash": plan["config_hash"],
             "runtime_plan_hash": plan["runtime_plan_hash"],
             "approval_sha256": apsha, "cli": "aa_cli",
             "non_acceptance_fixture": False}))
        open(os.path.join(d, "task_record.json"), "w").write(json.dumps(
            {"schema_version": 1, "batch_id": bidf,
             "telemetry": {"enabled": mode == "ON"}}))
        open(os.path.join(d, "runs", "run_1.json"), "w").write(json.dumps(
            {"schema_version": 1, "batch_id": bidf, "run_index": 1,
             "start": "2026-07-20T03:00:00Z", "end": "2026-07-20T03:01:00Z", "rc": 0}))
        open(os.path.join(d, "batch_final.json"), "w").write(json.dumps(
            {"schema_version": 1, "batch_id": bidf, "final": "done",
             "run_rc_map": {"1": 0}}))
        open(os.path.join(d, "monitor_status.json"), "w").write(
            json.dumps(real_monitor(bidf, mode)))
        if mode == "ON":
            os.makedirs(os.path.join(d, "telemetry"))
            open(os.path.join(d, "telemetry", "sidecar_final_status.json"), "w").write(
                json.dumps(real_sidecar_final(bidf, r)))
    return root, plan, modes

root_ok, plan_ok, modes_ok = fabricate_acceptance_root()
rc, a = agg(root_ok)
ck("完整合规现场 → rc=0,acceptance_eligible=true",
   (rc, a["acceptance_eligible"]), (0, True))
ck("分母字段:4/4 终态,OFF=2 ON=2,eligible=4 rejected=0",
   (a["attempts_observed"], a["attempts_terminal"], a["off_observed"],
    a["on_observed"], a["eligible_count"], a["rejected_count"]), (4, 4, 2, 2, 4, 0))

def mutated(mutator):
    root, plan, modes = fabricate_acceptance_root()
    mutator(root, plan, modes)
    rc, a = agg(root)
    return rc, a

rc, a = mutated(lambda r, p, m: shutil.rmtree(os.path.join(r, "attempts", "aa-r4_ON")))
ck("3 个 attempt → rc=1", (rc, a["acceptance_eligible"]), (1, False))
rc, a = mutated(lambda r, p, m: [shutil.rmtree(os.path.join(r, "attempts", d))
                                 for d in ("aa-r2_ON", "aa-r3_OFF", "aa-r4_ON")])
ck("1 个 attempt → rc=1", rc, 1)
def add_extra(r, p, m):
    d = os.path.join(r, "attempts", "aa-r9_EXTRA")
    os.makedirs(d)
    open(os.path.join(d, "task_record.json"), "w").write("{}")
rc, a = mutated(add_extra)
ck("5 个 attempt(计划外 run) → rc=1 且 rejected 点名 unplanned",
   (rc, any("unplanned" in x["reason"] for x in a["rejected"])), (1, True))
def wrong_mode(r, p, m):
    ip = os.path.join(r, "attempts", "aa-r2_ON", "aa_identity.json")
    i = json.load(open(ip)); i["telemetry_mode"] = "OFF"; open(ip, "w").write(json.dumps(i))
rc, a = mutated(wrong_mode)
ck("模式与计划不符(OFF/ON 数错) → rc=1", rc, 1)
def dup_rid(r, p, m):
    ip = os.path.join(r, "attempts", "aa-r3_OFF", "aa_identity.json")
    i = json.load(open(ip)); i["run_id"] = "aa-r1"; open(ip, "w").write(json.dumps(i))
rc, a = mutated(dup_rid)
ck("重复/错位 run_id → rc=1", rc, 1)
def not_started(r, p, m):
    lp = os.path.join(r, "aa_plan", "launch_record.json")
    l = json.load(open(lp))
    l["attempts"][3] = {"run_id": "aa-r4", "telemetry_mode": "ON", "artifact_root": None,
                        "rc": None, "state": "NOT_STARTED_PRIOR_FAILURE"}
    l["stopped_on_failure"] = "aa-r2"
    open(lp, "w").write(json.dumps(l))
rc, a = mutated(not_started)
ck("NOT_STARTED 在档 → rc=1 且失败原因点名",
   (rc, any("not_started" in f or "stopped_on_failure" in f
            for f in a["acceptance_failures"])), (1, True))
rc, a = mutated(lambda r, p, m: os.unlink(
    os.path.join(r, "attempts", "aa-r1_OFF", "task_record.json")))
ck("task_record 缺失 → rc=1", rc, 1)
rc, a = mutated(lambda r, p, m: os.unlink(
    os.path.join(r, "attempts", "aa-r1_OFF", "monitor_status.json")))
ck("monitor_status 缺失(非终态) → rc=1", rc, 1)
rc, a = mutated(lambda r, p, m: os.unlink(
    os.path.join(r, "attempts", "aa-r1_OFF", "batch_final.json")))
ck("batch_final 缺失 → rc=1", rc, 1)
def bad_batch(r, p, m):
    tp = os.path.join(r, "attempts", "aa-r1_OFF", "task_record.json")
    open(tp, "w").write(json.dumps({"batch_id": "someone_else.b.OFF"}))
rc, a = mutated(bad_batch)
ck("identity 与 task_record batch_id 不一致 → rc=1", rc, 1)
def bad_apsha(r, p, m):
    ip = os.path.join(r, "attempts", "aa-r1_OFF", "aa_identity.json")
    i = json.load(open(ip)); i["approval_sha256"] = "ee" * 32; open(ip, "w").write(json.dumps(i))
rc, a = mutated(bad_apsha)
ck("approval hash 不一致 → rc=1", rc, 1)
def fixture_flag(r, p, m):
    ip = os.path.join(r, "attempts", "aa-r1_OFF", "aa_identity.json")
    i = json.load(open(ip)); i["non_acceptance_fixture"] = True; open(ip, "w").write(json.dumps(i))
rc, a = mutated(fixture_flag)
ck("fixture attempt 混入 → rc=1(永久拒)", rc, 1)
def fixture_lrec(r, p, m):
    lp = os.path.join(r, "aa_plan", "launch_record.json")
    l = json.load(open(lp)); l["gate"]["approval_fixture_test_only"] = True
    open(lp, "w").write(json.dumps(l))
rc, a = mutated(fixture_lrec)
ck("fixture approval 的 launch record → rc=1(永久拒)", rc, 1)

print("======== 06.6b 缺口补正反例(2026-07-20 树状令 P01.4.4/P01.5.4/P01.5.10/P01.3.7)========")
def tel_mismatch(r, p, m):
    tp = os.path.join(r, "attempts", "aa-r2_ON", "task_record.json")
    t = json.load(open(tp)); t["telemetry"]["enabled"] = False
    open(tp, "w").write(json.dumps(t))
rc, a = mutated(tel_mismatch)
ck("task_record telemetry 证据与 identity(ON) 不符 → rc=1(曾红:旧 rc=0)",
   (rc, any("telemetry_mismatch" in x["reason"] for x in a["rejected"])), (1, True))
def tel_missing(r, p, m):
    tp = os.path.join(r, "attempts", "aa-r1_OFF", "task_record.json")
    t = json.load(open(tp)); del t["telemetry"]
    open(tp, "w").write(json.dumps(t))
rc, a = mutated(tel_missing)
ck("task_record telemetry 证据缺失 → rc=1", rc, 1)
rc, a = mutated(lambda r, p, m: open(
    os.path.join(r, "attempts", "aa-r1_OFF", "batch_final.json"), "w").write("{corrupt"))
ck("batch_final 损坏 → rc=1(曾红:旧 rc=0)",
   (rc, any("batch_final" in x["reason"] for x in a["rejected"])), (1, True))
rc, a = mutated(lambda r, p, m: open(
    os.path.join(r, "attempts", "aa-r1_OFF", "batch_final.json"), "w").write(
        json.dumps({"final": "done", "run_rc_map": {"1": 7}})))
ck("batch_final run_rc_map 非零 → rc=1(曾红:旧 rc=0)", rc, 1)
rc, a = mutated(lambda r, p, m: open(
    os.path.join(r, "attempts", "aa-r1_OFF", "monitor_status.json"), "w").write("{corrupt"))
ck("monitor_status 损坏 → rc=1", rc, 1)
rc, a = mutated(lambda r, p, m: open(
    os.path.join(r, "attempts", "aa-r1_OFF", "runs", "run_1.json"), "w").write(
        json.dumps({"rc": 5})))
ck("run 记录 rc≠0 → rc=1", rc, 1)
def dir_swap(r, p, m):
    a1, a3 = (os.path.join(r, "attempts", d) for d in ("aa-r1_OFF", "aa-r3_OFF"))
    shutil.move(a1, a1 + "_t"); shutil.move(a3, a1); shutil.move(a1 + "_t", a3)
rc, a = mutated(dir_swap)
ck("目录互换名(目录名≠身份) → rc=1(身份为准,目录名非唯一依据)", rc, 1)

print("======== 06.6c dry-run 缺 stub → 拒(不得跑真实仿真)========")
root_ns = os.path.join(work, "root_nostub")
cli(["--validate-only"] + base_args(root_ns, cfg, rtp, mainfx) + DRY_BUDGETS)
apns = fixture_approval(root_ns, mainfx)
cp, rec = run_mode("--dry-run", root_ns, ["--owner-approval", apns],
                   env_extra=None, env_drop=CLEAN_DROP)   # 无 NAVLAB_SIM_CMD
ck("dry-run 无 NAVLAB_SIM_CMD → producer=0(fail-closed,防真实仿真)",
   (cp.returncode, rec["producer_started"],
    any("dry_run_requires_sim_stub" in r for r in rec["gate"]["refusal_reasons"])),
   (1, 0, True))

print("======== 06.6d 终态语义门(五验红案入册;{} 现为正式负例)========")
def mon_path(r, rid="aa-r1", mode="OFF"):
    return os.path.join(r, "attempts", f"{rid}_{mode}", "monitor_status.json")

def set_mon(root, content, rid="aa-r1", mode="OFF"):
    p = mon_path(root, rid, mode)
    open(p, "w").write(content if isinstance(content, str) else json.dumps(content))

def mon_mut(**over):
    def m(r, p, mods):
        mon = json.load(open(mon_path(r)))
        mon.update(over)
        set_mon(r, mon)
    return m

rc, a = mutated(lambda r, p, m: [set_mon(r, "{}", rid, m[rid])
                                 for rid in p["execution_order"]])
ck("R01 {} monitor ×4(Codex 五验原反例;旧正例已删) → rc=1(曾红:旧 rc=0)",
   (rc, a["acceptance_eligible"]), (1, False))
ck("R01b 拒绝原因具体(非泛化不可解析)",
   any("monitor_not_object_or_empty" in x["reason"] for x in a["rejected"]), True)
rc, a = mutated(lambda r, p, m: set_mon(r, "[]"))
ck("R02 monitor=[](合法 JSON 非对象) → rc=1(曾红)", rc, 1)
rc, a = mutated(lambda r, p, m: set_mon(r, '{"status":"done"}'))
ck("R03 仅 status 字段 → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(producer_outcome=0))
ck("R04 producer_outcome 类型错 → rc=1(曾红)", rc, 1)
def drop_keys(*keys):
    def m(r, p, mods):
        mon = json.load(open(mon_path(r)))
        for k in keys:
            mon.pop(k, None)
        set_mon(r, mon)
    return m
rc, a = mutated(drop_keys("schema_version"))
ck("R05 缺 schema_version → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(schema_version=99))
ck("R06 未知 schema_version → rc=1(曾红)", rc, 1)
rc, a = mutated(drop_keys("producer_outcome", "evidence_status", "cleanup_status"))
ck("R07 缺三轴字段 → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(evidence_status="INCOMPLETE", evidence_missing="x.json"))
ck("R08 SUCCEEDED+evidence INCOMPLETE → rc=1(曾红,轴不互覆盖)", rc, 1)
rc, a = mutated(mon_mut(evidence_status="CORRUPT"))
ck("R09 evidence 非法枚举 → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(producer_outcome="FAILED", run_rc_map={"1": 7}))
ck("R10 producer=FAILED(evidence 仍 COMPLETE) → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(cleanup_status="RESIDUAL"))
ck("R11 cleanup=RESIDUAL → rc=1(曾红,finalization 轴独立)", rc, 1)
rc, a = mutated(mon_mut(run_rc_map={"1": 0, "2": 0}))
ck("R12 monitor 与 final run_rc_map 不一致 → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(producer_outcome="CANCELLED"))
ck("R13 CANCELLED 但 final=done → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(batch_id="other_batch.r.OFF"))
ck("R14 monitor batch_id 错(陈旧复制) → rc=1(曾红)", rc, 1)
def tel_flip(r, p, m):
    mon = json.load(open(mon_path(r)))
    mon["telemetry_status"]["enabled"] = True   # OFF 臂被标 enabled
    set_mon(r, mon)
rc, a = mutated(tel_flip)
ck("R15 monitor telemetry.enabled 与 mode 矛盾 → rc=1(曾红)", rc, 1)
rc, a = mutated(mon_mut(readonly=True))
ck("R16 readonly monitor → rc=1(曾红)", rc, 1)
rc, a = mutated(lambda r, p, m: open(
    os.path.join(r, "attempts", "aa-r1_OFF", "monitor_status.json.tmp"), "w").write("x"))
ck("R17 .tmp 残留(半写) → rc=1(曾红)", rc, 1)
def sidecar_killed(r, p, m):
    mon = json.load(open(mon_path(r, "aa-r2", "ON")))
    mon["telemetry_status"]["process_state"] = "KILLED"
    set_mon(r, mon, "aa-r2", "ON")
rc, a = mutated(sidecar_killed)
ck("R18 ON 臂 sidecar 非正常退出 → rc=1(曾红)", rc, 1)
rc, a = mutated(lambda r, p, m: [os.utime(mon_path(r, rid, m[rid]), (1, 1))
                                 for rid in p["execution_order"]])
ck("R19 monitor 终态早于 run 结束(mtime) → rc=1(曾红)", rc, 1)
def bad_run_index(r, p, m):
    rp = os.path.join(r, "attempts", "aa-r1_OFF", "runs", "run_1.json")
    d = json.load(open(rp)); d["run_index"] = 2; open(rp, "w").write(json.dumps(d))
rc, a = mutated(bad_run_index)
ck("R20 run_index 错 → rc=1(曾红)", rc, 1)
rc, a = agg(fabricate_acceptance_root()[0])
ck("契约级正例(真实 schema)仍 rc=0(判别性:仅上述单变量翻红)",
   (rc, a["acceptance_eligible"], a["eligible_count"]), (0, True, 4))
ck("正例逐 attempt 输出三轴",
   all(e.get("axes") == {"process": "SUCCEEDED", "evidence": "COMPLETE",
                         "finalization": "CLEAN"} for e in a["eligible"]), True)

print("======== 06.6f B 包:ON 臂 sidecar deep evidence 联动(先红后绿)========")
def sf_path(r, rid="aa-r2"):
    return os.path.join(r, "attempts", f"{rid}_ON", "telemetry", "sidecar_final_status.json")

def mon_tel(r, rid="aa-r2", **over):
    p = mon_path(r, rid, "ON")
    mon = json.load(open(p)); mon["telemetry_status"].update(over)
    open(p, "w").write(json.dumps(mon))

def sf_mut(r, rid="aa-r2", **over):
    p = sf_path(r, rid)
    sf = json.load(open(p)); sf.update(over); open(p, "w").write(json.dumps(sf))

rc, a = mutated(lambda r, p, m: [
    os.unlink(sf_path(r, rid)) or mon_tel(r, rid, evidence_state="UNKNOWN",
                                          finalization_state="MISSING")
    for rid in ("aa-r2", "aa-r4")])
ck("S1 ON 开了但无 sidecar 证据(UNKNOWN/MISSING+无 final 文件) → rc=1(曾红:旧 rc=0)",
   (rc, a["acceptance_eligible"],
    any("sidecar_evidence_not_complete" in x["reason"] for x in a["rejected"])), (1, False, True))
rc, a = mutated(lambda r, p, m: os.unlink(sf_path(r)))
ck("S2 monitor 称 COMPLETE 但 final 文件缺失 → rc=1(交叉联动)",
   (rc, any("sidecar_final_missing" in x["reason"] for x in a["rejected"])), (1, True))
rc, a = mutated(lambda r, p, m: (sf_mut(r, evidence_state="INCOMPLETE"),
                                 mon_tel(r, evidence_state="INCOMPLETE")))
ck("S3 evidence_state=INCOMPLETE → rc=1", rc, 1)
rc, a = mutated(lambda r, p, m: (sf_mut(r, finalization_state="MISSING"),
                                 mon_tel(r, finalization_state="MISSING")))
ck("S4 finalization_state≠WRITTEN → rc=1", rc, 1)
rc, a = mutated(lambda r, p, m: open(sf_path(r), "w").write("{corrupt"))
ck("S5 sidecar final 损坏 → rc=1",
   (rc, any("sidecar_final_corrupt" in x["reason"] for x in a["rejected"])), (1, True))
rc, a = mutated(lambda r, p, m: sf_mut(r, batch_id="aa_fab_1.aa-r4.ON"))
ck("S6 sidecar final 绑定到另一 attempt → rc=1",
   (rc, any("sidecar_final_batch_id_mismatch" in x["reason"] for x in a["rejected"])), (1, True))
rc, a = mutated(lambda r, p, m: sf_mut(r, evidence_state="INCOMPLETE"))
ck("S7 monitor 分录与 final 文件不一致 → rc=1",
   (rc, any("inconsistent" in x["reason"] or "not_complete" in x["reason"]
            for x in a["rejected"])), (1, True))
rc, a = agg(fabricate_acceptance_root()[0])
ck("S8 正例:ON 臂带完整 deep evidence、OFF 臂不要求 sidecar → rc=0",
   (rc, a["acceptance_eligible"], a["eligible_count"]), (0, True, 4))

print("======== 06.6e 正式生命周期正例(生产者-消费者同契约;P04.3)========")
# 复制真实 dry-run 产物,仅去除 fixture 隔离标记(identity.non_acceptance_fixture/
# record_class/approval_fixture 标志——只为证明"正式 batch_lifecycle 真实写出的
# 产物能过 validator",其余全部字节不动;真实 A/A 记录只能来自真实 execute)
root_lc = os.path.join(work, "root_lifecycle")
shutil.copytree(root_d, root_lc)
lp = os.path.join(root_lc, "aa_plan", "launch_record.json")
l = json.load(open(lp))
l["record_class"] = "ACCEPTANCE_CANDIDATE"
l["gate"]["approval_fixture_test_only"] = False
open(lp, "w").write(json.dumps(l))
for x in l["attempts"]:
    d_lc = os.path.join(root_lc, "attempts", f"{x['run_id']}_{x['telemetry_mode']}")
    ip = os.path.join(d_lc, "aa_identity.json")
    i = json.load(open(ip)); i["non_acceptance_fixture"] = False
    open(ip, "w").write(json.dumps(i))
    if x["telemetry_mode"] == "ON":
        # B 包注记:dry-run 的 WP303_TELEMETRY_CMD 官方覆盖不产 sidecar final
        # (真实分录=UNKNOWN/MISSING,正确地不可判读)。此处嫁接契约级 ON 臂
        # deep evidence(schema=telemetry_sidecar 写入点)仅为验证消费端契约;
        # 真实 A/A 的该证据只能由真实 sidecar 产生。
        bidf = json.load(open(os.path.join(d_lc, "task_record.json")))["batch_id"]
        os.makedirs(os.path.join(d_lc, "telemetry"), exist_ok=True)
        open(os.path.join(d_lc, "telemetry", "sidecar_final_status.json"), "w").write(
            json.dumps(real_sidecar_final(bidf, x["run_id"])))
        mp = os.path.join(d_lc, "monitor_status.json")
        mon = json.load(open(mp))
        mon["telemetry_status"].update({"evidence_state": "COMPLETE",
                                        "finalization_state": "WRITTEN"})
        open(mp, "w").write(json.dumps(mon))
rc, a = agg(root_lc)
ck("正式 batch_lifecycle 真实产物(仅去隔离标记)过 validator → rc=0",
   (rc, a["acceptance_eligible"], a["attempts_terminal"]), (0, True, 4))
ck("真实产物三轴=SUCCEEDED/COMPLETE/CLEAN",
   all(e["axes"] == {"process": "SUCCEEDED", "evidence": "COMPLETE",
                     "finalization": "CLEAN"} for e in a["eligible"]), True)

print("======== 06.7 生产代码调用链断言 ========")
cli_src = open(CLI).read()
ck("aa_cli 调用 launch_aa+batch_lifecycle+preflight",
   all(s in cli_src for s in ("L.launch_aa(", "BATCH_LIFECYCLE", "PF.run_preflight(")), True)
ck("aggregate 正式链内含终态语义验证器(非测试旁路)",
   "validate_monitor_terminal(" in cli_src
   and cli_src.index("def validate_monitor_terminal") < cli_src.index("def cmd_aggregate"), True)
ck("生产 execute 恒 allow_fixture=False(源码断言)",
   "allow_fixture_approval=dry_run" in cli_src, True)
ck("run_batch 声明 A/A 红线",
   "不得计入 A/A 分母" in open(os.path.join(HERE, "..", "run_batch.sh")).read(), True)

print("======== 06.8 零真实容器 ========")
after_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout
ck("运行中容器集合不变", after_docker, before_docker)

print("================================")
print(f"结果: RAN={RAN} PASS={RAN - FAIL} FAIL={FAIL} SKIP=0(无跳过路径)")
sys.exit(1 if FAIL else 0)
