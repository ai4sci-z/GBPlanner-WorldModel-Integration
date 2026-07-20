#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 · aa_cli 正式操作入口门(2026-07-20 二次补正令包四)。

expected 来源=补正令条款。固化 Codex 两个绕过反例:
  ①aa_launch 无 CLI(--help 零输出)——现 aa_cli --help 必须有帮助文本;
  ②run_batch 直通 producer——现 A/A 聚合器必须拒绝无计划身份的记录。
dry-run 全部经**正式 batch_lifecycle.py launch**(NAVLAB_SIM_CMD stub=官方 dry
机制;WP303_TELEMETRY_CMD=官方 fixture/test 覆盖,record 显式标注);
不启动真实仿真/SITL/容器。运行前置:sourced。SKIP 恒=0。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAIL = 0
RAN = 0
CLI = os.path.join(HERE, "aa_cli.py")
WM_REPO = "/home/ai4s/projects/world-model"
TAG = "jazzy-9a1ce95c56e2"   # 真实在盘镜像(docker image inspect 只读,不起容器)


def ck(name, got, want):
    global FAIL, RAN
    RAN += 1
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def cli(args, env_extra=None, timeout=300):
    env = dict(os.environ)
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


def fixture_approval(root, mainfx, **over):
    """fixture 审批样本(显式 fixture_test_only 标记;真实审批只能由负责人产生)。"""
    plan = json.load(open(os.path.join(root, "aa_plan", "aa_frozen_plan.json")))
    head = subprocess.run(["git", "-C", mainfx, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    ap = {"schema_version": "wp304.aa_approval.v1", "approval_purpose": "A_A_OFF2_ON2",
          "approval_state": "APPROVED", "fixture_test_only": True,
          "approved_by": "FIXTURE-test-only", "approved_at": "2026-07-20T00:00:00Z",
          "main_commit": head, "world_model_commit": plan["world_model_commit"],
          "config_hash": plan["config_hash"], "runtime_plan_hash": plan["runtime_plan_hash"],
          "image_digest": plan["image_digests"]["companion"],
          "ros_domain": "7", "sample_plan": "OFF2_ON2"}
    ap.update(over)
    p = os.path.join(root, "fixture_approval.json")
    open(p, "w").write(json.dumps(ap))
    return p


DRY_ENV = {"NAVLAB_SIM_CMD": "exit 0", "WP303_TELEMETRY_CMD": "sleep 0.1"}
DRY_BUDGETS = ["--duration", "0.2", "--startup-budget", "0.5",
               "--per-run-teardown", "0.1", "--inter-run-gap", "0.05",
               "--finalization-budget", "2"]


print("======== 06.0 前置:sourced ========")
ck("测试环境已 source(rclpy 可导入;未 source=如实红)",
   subprocess.run([sys.executable, "-c", "import rclpy"],
                  capture_output=True).returncode, 0)
before_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout

print("======== 06.1 CLI 用法正反例(Codex 反例①:--help 必须有帮助文本)========")
cp = cli(["--help"])
ck("--help rc=0", cp.returncode, 0)
ck("--help 输出含 usage 与三模式",
   ("usage" in cp.stdout and "--validate-only" in cp.stdout
    and "--execute" in cp.stdout and "--aggregate" in cp.stdout), True)
ck("--help 输出非空(旧 aa_launch 零输出反例)", len(cp.stdout) > 200, True)
ck("零参数 rc=2", cli([]).returncode, 2)
ck("未知参数 rc=2", cli(["--validate-only", "--artifact-root", "/tmp/x",
                        "--bogus"]).returncode, 2)
ck("非法枚举 rc=2", cli(["--validate-only", "--artifact-root", "/tmp/x",
                        "--config", "/dev/null", "--runtime-plan", "/dev/null",
                        "--companion-tag", TAG, "--producer-mode", "nope"]).returncode, 2)
ck("缺 --config rc=2", cli(["--validate-only", "--artifact-root", "/tmp/x",
                            "--runtime-plan", "/dev/null",
                            "--companion-tag", TAG]).returncode, 2)
ck("缺 --companion-tag rc=2", cli(["--validate-only", "--artifact-root", "/tmp/x",
                                   "--config", "/dev/null",
                                   "--runtime-plan", "/dev/null"]).returncode, 2)
ck("不存在的镜像 tag → rc=3(环境错误,非静默)",
   cli(["--validate-only", "--artifact-root", tempfile.mkdtemp(),
        "--config", write_inputs(tempfile.mkdtemp())[0],
        "--runtime-plan", write_inputs(tempfile.mkdtemp())[1],
        "--companion-tag", "jazzy-nonexistent000"]).returncode, 3)

print("======== 06.2 validate-only:物化+真hash+真digest+preflight,producer=0 ========")
work = tempfile.mkdtemp(prefix="aacli_v_")
mainfx = fixture_main_repo()
cfg, rtp = write_inputs(work)
root_v = os.path.join(work, "root")
cp = cli(["--validate-only"] + base_args(root_v, cfg, rtp, mainfx))
out = json.loads(cp.stdout)
ck("validate-only rc=0", cp.returncode, 0)
ck("preflight=READY", out["preflight_status"], "READY")
ck("producer_started=0", out["producer_started"], 0)
ck("attempts 目录不存在(producer 未动)",
   os.path.isdir(os.path.join(root_v, "attempts")), False)
plan = json.load(open(os.path.join(root_v, "aa_plan", "aa_frozen_plan.json")))
ck("冻结计划已落盘且 hash=64hex",
   (len(plan["config_hash"]), len(plan["runtime_plan_hash"])), (64, 64))
ck("digest=真实 docker 现值",
   plan["image_digests"]["companion"],
   subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}",
                   f"navlab/companion:{TAG}"], capture_output=True, text=True).stdout.strip())
ck("execution_order=OFF,OFF,ON,ON 对应 r1,r3,r2,r4",
   plan["execution_order"], ["aa-r1", "aa-r3", "aa-r2", "aa-r4"])

print("======== 06.3 execute 授权门反例(producer 恒=0)========")
def exec_and_record(root, extra_args, env_extra=None):
    cp = cli(["--execute"] + base_args(root, cfg, rtp, mainfx) + DRY_BUDGETS + extra_args,
             env_extra=env_extra)
    rec = json.load(open(os.path.join(root, "aa_plan", "launch_record.json")))
    return cp, rec

root_e = os.path.join(work, "root_noap")
cp, rec = exec_and_record(root_e, [])
ck("无 owner approval → rc=1", cp.returncode, 1)
ck("无 approval:producer_started=0", rec["producer_started"], 0)
ck("原因=approval_missing", "approval_missing" in rec["gate"]["refusal_reasons"], True)
ck("无 approval:attempts 未发起", rec["attempts"], [])

root_e2 = os.path.join(work, "root_badhash")
cli(["--validate-only"] + base_args(root_e2, cfg, rtp, mainfx))
ap_bad = fixture_approval(root_e2, mainfx, config_hash="ee" * 32)
cp, rec = exec_and_record(root_e2, ["--owner-approval", ap_bad, "--allow-fixture-approval"])
ck("approval config_hash 不符 → producer=0",
   (cp.returncode, rec["producer_started"]), (1, 0))
ck("原因含 approval_config_hash_mismatch",
   "approval_config_hash_mismatch" in rec["gate"]["refusal_reasons"], True)

root_e3 = os.path.join(work, "root_nofix")
cli(["--validate-only"] + base_args(root_e3, cfg, rtp, mainfx))
ap3 = fixture_approval(root_e3, mainfx)
cp, rec = exec_and_record(root_e3, ["--owner-approval", ap3])   # 无 --allow-fixture-approval
ck("fixture 审批未显式放行 → producer=0",
   (cp.returncode, rec["producer_started"]), (1, 0))
ck("原因=fixture_approval_not_allowed",
   "fixture_approval_not_allowed" in rec["gate"]["refusal_reasons"], True)

root_e4 = os.path.join(work, "root_state")
cli(["--validate-only"] + base_args(root_e4, cfg, rtp, mainfx))
ap4 = fixture_approval(root_e4, mainfx, approval_state="DRAFT")
cp, rec = exec_and_record(root_e4, ["--owner-approval", ap4, "--allow-fixture-approval"])
ck("approval_state=DRAFT → producer=0",
   (cp.returncode, rec["producer_started"]), (1, 0))

print("======== 06.4 dry-run execute:必须实际经 batch_lifecycle 正式入口 ========")
root_x = os.path.join(work, "root_exec")
cli(["--validate-only"] + base_args(root_x, cfg, rtp, mainfx))
ap = fixture_approval(root_x, mainfx)
cp, rec = exec_and_record(root_x, ["--owner-approval", ap, "--allow-fixture-approval"],
                          env_extra=DRY_ENV)
ck("dry-run execute rc=0", cp.returncode, 0)
ck("producer_started=1(gate 全过)", rec["producer_started"], 1)
ck("fixture 审批在 record 显式标注", rec["gate"]["approval_fixture_test_only"], True)
atts = rec["attempts"]
ck("四 attempt 全发起且 rc=0", [(x["run_id"], x["rc"]) for x in atts],
   [("aa-r1", 0), ("aa-r3", 0), ("aa-r2", 0), ("aa-r4", 0)])
ck("模式序=OFF,OFF,ON,ON", [x["telemetry_mode"] for x in atts],
   ["OFF", "OFF", "ON", "ON"])
for x in atts:
    tr = os.path.join(x["artifact_root"], "task_record.json")
    ck(f"{x['run_id']}:batch_lifecycle task_record 存在(正式链证明)",
       os.path.isfile(tr), True)
    t = json.load(open(tr))
    ck(f"{x['run_id']}:telemetry.enabled 与模式一致",
       t["telemetry"]["enabled"], x["telemetry_mode"] == "ON")
    ident = json.load(open(os.path.join(x["artifact_root"], "aa_identity.json")))
    ck(f"{x['run_id']}:身份绑定同一冻结计划 hash",
       (ident["config_hash"], ident["runtime_plan_hash"]),
       (json.load(open(os.path.join(root_x, "aa_plan", "aa_frozen_plan.json")))["config_hash"],
        json.load(open(os.path.join(root_x, "aa_plan", "aa_frozen_plan.json")))["runtime_plan_hash"]))
    ck(f"{x['run_id']}:batch_id 由 CLI 具名生成(aa_ 前缀)",
       t["batch_id"].startswith(rec["aa_batch_id"]), True)

print("======== 06.5 任一 attempt 失败 → 立即停止后续,分母保留 ========")
root_f = os.path.join(work, "root_fail")
cli(["--validate-only"] + base_args(root_f, cfg, rtp, mainfx))
apf = fixture_approval(root_f, mainfx)
cp, rec = exec_and_record(root_f, ["--owner-approval", apf, "--allow-fixture-approval"],
                          env_extra={"NAVLAB_SIM_CMD": "exit 7",
                                     "WP303_TELEMETRY_CMD": "sleep 0.1"})
ck("失败链 rc=1", cp.returncode, 1)
started = [x for x in rec["attempts"] if x.get("rc") is not None]
not_started = [x for x in rec["attempts"] if x.get("state") == "NOT_STARTED_PRIOR_FAILURE"]
ck("仅第 1 个 attempt 发起且 rc≠0",
   (len(started), started[0]["run_id"], started[0]["rc"] != 0), (1, "aa-r1", True))
ck("其余 3 个显式 NOT_STARTED(分母保留,不消失)", len(not_started), 3)
ck("stopped_on_failure=aa-r1", rec["stopped_on_failure"], "aa-r1")

print("======== 06.6 聚合器(Codex 反例②:run_batch 直通记录必须被拒)========")
cp = cli(["--aggregate", "--artifact-root", root_x])
agg = json.loads(cp.stdout)
ck("干净 A/A root 聚合 rc=0", cp.returncode, 0)
ck("eligible=4", len(agg["eligible"]), 4)
ck("聚合模式序=OFF,OFF,ON,ON", agg["eligible_modes_in_execution_order"],
   ["OFF", "OFF", "ON", "ON"])
rogue = os.path.join(root_x, "attempts", "rogue_runbatch")
os.makedirs(os.path.join(rogue, "runs"), exist_ok=True)
open(os.path.join(rogue, "task_record.json"), "w").write('{"batch_id":"rogue"}')
cp = cli(["--aggregate", "--artifact-root", root_x])
agg = json.loads(cp.stdout)
ck("混入 run_batch 式记录 → 聚合 rc=1", cp.returncode, 1)
ck("rogue 被拒且 eligible 仍=4",
   (len(agg["rejected"]), len(agg["eligible"])), (1, 4))
ck("拒绝原因=no_aa_identity",
   "no_aa_identity" in agg["rejected"][0]["reason"], True)
ident_p = os.path.join(root_x, "attempts", "aa-r1_OFF", "aa_identity.json")
ident = json.load(open(ident_p))
ident["config_hash"] = "ee" * 32
open(ident_p, "w").write(json.dumps(ident))
cp = cli(["--aggregate", "--artifact-root", root_x])
agg = json.loads(cp.stdout)
ck("身份 hash 被篡改 → 该 attempt 被拒(identity_plan_mismatch)",
   any(r["reason"] == "identity_plan_mismatch" for r in agg["rejected"]), True)
ck("篡改后 eligible=3", len(agg["eligible"]), 3)

print("======== 06.7 生产代码调用链断言(禁止 README 代替调用证据)========")
cli_src = open(CLI).read()
ck("aa_cli 调用 launch_aa", "L.launch_aa(" in cli_src, True)
ck("aa_cli 调用正式 batch_lifecycle.py", "batch_lifecycle.py" in cli_src
   and "BATCH_LIFECYCLE" in cli_src, True)
ck("aa_cli validate 走唯一 preflight", "PF.run_preflight(" in cli_src, True)
launch_src = open(os.path.join(HERE, "aa_launch.py")).read()
ck("launch_aa 内含 preflight 调用", "PF.run_preflight(" in launch_src, True)
ck("launch_aa 内含授权机器门", "verify_owner_approval(" in launch_src, True)
rb_src = open(os.path.join(HERE, "..", "run_batch.sh")).read()
ck("run_batch 声明 A/A 红线(结果不入 A/A 分母)", "不得计入 A/A 分母" in rb_src, True)

print("======== 06.8 零真实容器 ========")
after_docker = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout
ck("运行中容器集合不变(全程 stub dry-run)", after_docker, before_docker)

print("================================")
print(f"结果: RAN={RAN} PASS={RAN - FAIL} FAIL={FAIL} SKIP=0(无跳过路径)")
sys.exit(1 if FAIL else 0)
