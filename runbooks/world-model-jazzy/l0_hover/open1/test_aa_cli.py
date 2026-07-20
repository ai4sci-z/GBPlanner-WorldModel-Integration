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


def fabricate_acceptance_root():
    """构造完整合规的 ACCEPTANCE_CANDIDATE 现场(聚合器黑盒正例底座)。"""
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
        d = os.path.join(root, "attempts", f"{r}_{modes[r]}")
        os.makedirs(os.path.join(d, "runs"))
        open(os.path.join(d, "aa_identity.json"), "w").write(json.dumps(
            {"schema_version": "wp304.aa_identity.v1", "aa_batch_id": bid,
             "run_id": r, "telemetry_mode": modes[r],
             "config_hash": plan["config_hash"],
             "runtime_plan_hash": plan["runtime_plan_hash"],
             "approval_sha256": apsha, "cli": "aa_cli",
             "non_acceptance_fixture": False}))
        open(os.path.join(d, "task_record.json"), "w").write(json.dumps(
            {"batch_id": f"{bid}.{r}.{modes[r]}",
             "telemetry": {"enabled": modes[r] == "ON"}}))
        open(os.path.join(d, "monitor_status.json"), "w").write("{}")
        open(os.path.join(d, "batch_final.json"), "w").write(
            json.dumps({"final": "done", "run_rc_map": {"1": 0}}))
        open(os.path.join(d, "runs", "run_1.json"), "w").write(json.dumps({"rc": 0}))
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

print("======== 06.7 生产代码调用链断言 ========")
cli_src = open(CLI).read()
ck("aa_cli 调用 launch_aa+batch_lifecycle+preflight",
   all(s in cli_src for s in ("L.launch_aa(", "BATCH_LIFECYCLE", "PF.run_preflight(")), True)
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
