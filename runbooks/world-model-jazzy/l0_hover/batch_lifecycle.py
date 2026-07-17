#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP303 批任务生命周期:managed launcher + monitor + 结构化 task record。

只跑 fixture,不跑真实仿真。设计契约(修订自 WP303 方案,修正其已知缺陷):

身份契约(不靠日志文本/锁文件存在性/tail 进程当生命真值):
  producer 运行于独立 session(os.setsid),task record 落盘含
  schema_version/batch_id(UUID)/script/PID/PGID/SID/pid_starttime(/proc/pid/stat 22)/
  boot_id(/proc/sys/kernel/random/boot_id)/artifact_root/log/expected_runs/deadline_params/created_at。
  存活判定 = PID 存在 ∧ starttime 匹配 ∧ boot_id 匹配。
  清理前额外要求 = PGID==leader PID ∧ SID==leader PID ∧ monitor 自身不在目标 PGID。
  任一不符只登记 CLEANUP: REFUSED/NOT_ATTEMPTED,禁止发信号。

安全边界:record 路径经 realpath 必须位于 artifact_root 内;拒绝 symlink record、
  错误 owner/权限、陈旧 boot_id、未知 schema_version(失败关闭 rc=5)。

多 monitor 排他:record 同目录 flock(fcntl,真实内核锁)。第二 monitor 拿不到锁 →
  进入只读观察模式(不发信号/不清理),不出现两个 writer。

deadline(批级,非单 run;单调时钟):
  startup_budget + expected_runs*(duration + per_run_teardown + inter_run_gap) + finalization_budget

三轴状态(不吞成单一布尔):
  producer_outcome ∈ {SUCCEEDED, FAILED, TIMED_OUT, CRASHED, CANCELLED}
  evidence_status  ∈ {COMPLETE, INCOMPLETE}
  cleanup_status   ∈ {CLEAN, RESIDUAL, NOT_ATTEMPTED, REFUSED}

终态优先级(单次观察快照):
  1 已观察 producer 终止 → 按真实退出状态(全 run rc=0 且完成→SUCCEEDED;有 rc≠0→FAILED)
  2 producer 仍活 ∧ cancel 已执行 → CANCELLED
  3 producer 仍活 ∧ deadline 到期 → TIMED_OUT
  4 身份匹配但异常消失且无正常终态记录 → CRASHED
  cancel 与自然完成同时:以已观察到的自然终态为准,cancel 记为 no-op。

producer 结构化真值(不 grep 散文):
  producer 每 run 写 <artifact>/runs/run_<i>.json {run_index,start,end,rc};
  批完成写 <artifact>/batch_final.json {schema_version, final, run_rc_map}。
  文本日志(<log>)仅供人读,不是状态权威。

monitor 退出码(精确):
  0=SUCCEEDED+COMPLETE+CLEAN  10=FAILED  20=CRASHED  30=TIMED_OUT  40=CANCELLED
  50=evidence INCOMPLETE(叠加于终态,取最高上报)  60=cleanup RESIDUAL
  2=用法  5=record/身份/schema/security 违规  70=内部错误

容器:当前无法从 runtime event 可靠得到容器 ID → 不自动删容器,登记
  container_cleanup=NOT_ATTEMPTED(理由 UNVERIFIED)。
"""
import argparse
import errno
import fcntl
import json
import os
import shlex
import signal
import stat
import subprocess
import sys
import time

SCHEMA_VERSION = 1

RC_SUCCESS = 0
RC_FAILED = 10
RC_CRASHED = 20
RC_TIMED_OUT = 30
RC_CANCELLED = 40
RC_EVIDENCE_INCOMPLETE = 50
RC_CLEANUP_RESIDUAL = 60
RC_USAGE = 2
RC_SECURITY = 5
RC_INTERNAL = 70
RC_READONLY_DEFER = 75   # 第二 monitor 让位(观察,非批次成功;调用者不得计入 gate)

POLL_SEC = float(os.environ.get("WP303_POLL_SEC", "0.1"))
TERM_GRACE_SEC = float(os.environ.get("WP303_TERM_GRACE_SEC", "0.5"))


# ---------- 身份原语 ----------
def boot_id():
    with open("/proc/sys/kernel/random/boot_id") as f:
        return f.read().strip()


def _stat_fields(pid):
    """/proc/<pid>/stat 末括号后字段表(index0=state)。进程不存在返回 None。"""
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except (FileNotFoundError, ProcessLookupError):
        return None
    rparen = data.rfind(")")
    if rparen < 0:
        return None
    return data[rparen + 2:].split()


def pid_starttime(pid):
    """starttime = 全表第 22 字段 = 末括号后 index 19。进程不存在返回 None。"""
    f = _stat_fields(pid)
    if f is None or len(f) < 20:
        return None
    return f[19]


def pid_is_zombie(pid):
    f = _stat_fields(pid)
    return bool(f) and f[0] == "Z"


def pid_pgrp(pid):
    """process group id = 全表第 5 字段 = 末括号后 index 2。"""
    f = _stat_fields(pid)
    if f is None or len(f) < 3:
        return None
    return int(f[2])


def identity_alive(rec):
    """PID 存在且非僵尸 ∧ starttime 匹配 ∧ boot_id 匹配(僵尸=已终止,判死)。"""
    if boot_id() != rec["boot_id"]:
        return False
    st = pid_starttime(rec["pid"])
    if st is None or st != rec["pid_starttime"]:
        return False
    return not pid_is_zombie(rec["pid"])


def live_group_members(pgid):
    """PGID 下所有存活(非僵尸)进程 PID,排除 monitor 自身。用于残留检测。"""
    me = os.getpid()
    out = []
    try:
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            pid = int(name)
            if pid == me:
                continue
            g = pid_pgrp(pid)
            if g == pgid and not pid_is_zombie(pid):
                out.append(pid)
    except OSError:
        pass
    return out


def cleanup_allowed(rec):
    """清理前置:身份存活 ∧ PGID==leader ∧ SID==leader ∧ monitor 不在目标组。"""
    if not identity_alive(rec):
        return False, "identity_dead"
    pid = rec["pid"]
    try:
        if os.getpgid(pid) != pid:
            return False, "pgid_not_leader"
        if os.getsid(pid) != pid:
            return False, "sid_not_leader"
    except ProcessLookupError:
        return False, "gone"
    if os.getpgid(0) == pid:
        return False, "monitor_in_target_group"
    return True, "ok"


# ---------- 原子 JSON ----------
def write_json_atomic(path, obj):
    d = os.path.dirname(path)
    fd, tmp = _mkstemp_in(d)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _mkstemp_in(d):
    import tempfile
    return tempfile.mkstemp(prefix=".bl.", suffix=".tmp", dir=d)


def read_json_safe(path):
    """半写/损坏 JSON → 返回 None(失败关闭,不抛)。"""
    try:
        if os.path.islink(path):
            return None
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return None


# ---------- record 安全校验 ----------
def validate_record_path(record, artifact_root):
    real_root = os.path.realpath(artifact_root)
    real_rec = os.path.realpath(record)
    if os.path.islink(record):
        die(RC_SECURITY, f"record 是符号链接,拒绝: {record}")
    if not (real_rec == real_root or real_rec.startswith(real_root + os.sep)):
        die(RC_SECURITY, f"record 越出 artifact_root: {real_rec} !⊂ {real_root}")
    if os.path.lexists(record):
        stt = os.lstat(record)
        if not stat.S_ISREG(stt.st_mode):
            die(RC_SECURITY, f"record 非普通文件: {record}")
        if stt.st_uid != os.getuid():
            die(RC_SECURITY, f"record owner 不符: uid={stt.st_uid}")
        if stt.st_mode & 0o077:
            die(RC_SECURITY, f"record 权限过宽(要求 0600): {oct(stt.st_mode & 0o777)}")


def load_record(record, artifact_root):
    validate_record_path(record, artifact_root)
    rec = read_json_safe(record)
    if rec is None:
        die(RC_SECURITY, f"record 不可读/损坏 JSON: {record}")
    if rec.get("schema_version") != SCHEMA_VERSION:
        die(RC_SECURITY, f"未知 schema_version={rec.get('schema_version')}(期望 {SCHEMA_VERSION})")
    required_keys = ("pid", "pgid", "sid", "pid_starttime", "boot_id", "expected_runs",
                     "deadline_monotonic", "artifact_root")
    missing = [k for k in required_keys if k not in rec]
    if missing:
        die(RC_SECURITY, f"record 缺必需字段: {missing}")
    return rec


def die(code, msg):
    print(f"batch_lifecycle: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------- deadline ----------
def batch_deadline(rec):
    p = rec["deadline_params"]
    return (p["startup_budget"]
            + rec["expected_runs"] * (p["duration"] + p["per_run_teardown"] + p["inter_run_gap"])
            + p["finalization_budget"])


# ---------- 观察快照 + 判定 ----------
def observe(rec, artifact_root, t0, cancel_path):
    now = time.monotonic() - t0
    final = read_json_safe(os.path.join(artifact_root, "batch_final.json"))
    run_rc_map = {}
    runs_dir = os.path.join(artifact_root, "runs")
    if os.path.isdir(runs_dir):
        for fn in sorted(os.listdir(runs_dir)):
            if fn.startswith("run_") and fn.endswith(".json"):
                r = read_json_safe(os.path.join(runs_dir, fn))
                if r and "run_index" in r and "rc" in r:
                    run_rc_map[str(r["run_index"])] = r["rc"]
    return {
        "monotonic_now": now,
        "producer_identity_alive": identity_alive(rec),
        "producer_exit_observed": final is not None,
        "final": final,
        "run_rc_map": run_rc_map,
        # deadline 跨 monitor 重启不变:用 record 里存的绝对 monotonic 值 + boot_id 守卫
        # (CLOCK_MONOTONIC 同 boot 内全系统一致;boot 不符则 record 陈旧,identity 亦判死)
        "deadline_expired": (boot_id() == rec["boot_id"]) and (time.monotonic() >= rec["deadline_monotonic"]),
        "cancel_requested": os.path.exists(cancel_path),
    }


def decide(snap, rec):
    """返回 (producer_outcome, terminal:bool)。纯函数,便于测边界竞态。"""
    if snap["producer_exit_observed"]:
        # 1 真实终态优先(即使 cancel/deadline 同时;自然终态胜)
        rcs = list(snap["run_rc_map"].values())
        expected = rec["expected_runs"]
        if len(rcs) >= expected and all(rc == 0 for rc in rcs):
            return "SUCCEEDED", True
        return "FAILED", True
    if not snap["producer_identity_alive"]:
        # 4 身份消失且无终态记录 → 崩溃
        return "CRASHED", True
    if snap["cancel_requested"]:
        return "CANCELLED", True   # 需先执行终止,见 monitor
    if snap["deadline_expired"]:
        return "TIMED_OUT", True
    return None, False


# ---------- 清理 ----------
def do_cleanup(rec, force_fail=False):
    """返回 cleanup_status。
    leader 存活且组领导匹配 → 可安全 SIGTERM/SIGKILL 整组;
    leader 已死(僵尸/reaped)→ pgid 可能被复用,禁止盲杀,只查真实存活组员:
      无 → CLEAN;有 → RESIDUAL(如实登记,不冒险杀他人)。
    其它身份不符 → REFUSED。"""
    if force_fail:
        return "RESIDUAL"
    pgid = rec["pgid"]
    ok, why = cleanup_allowed(rec)
    if ok:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return "CLEAN"
        deadline = time.monotonic() + TERM_GRACE_SEC
        while time.monotonic() < deadline and live_group_members(pgid):
            time.sleep(POLL_SEC)
        if live_group_members(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            time.sleep(POLL_SEC)
        return "CLEAN" if not live_group_members(pgid) else "RESIDUAL"
    if why == "identity_dead":
        # 区分"我的进程真的没了"vs"PID 被复用":
        #   pid 完全不在 /proc(gone)或为僵尸 → 是我们的进程终止了 → pgid 可信,查真实残留
        #   pid 在但 starttime 不符 → PID 已被复用,pgid 不可信 → NOT_ATTEMPTED,不赖在他人头上
        st = pid_starttime(rec["pid"])
        recycled = (st is not None) and (st != rec["pid_starttime"]) and (not pid_is_zombie(rec["pid"]))
        if recycled:
            return "NOT_ATTEMPTED"
        return "CLEAN" if not live_group_members(pgid) else "RESIDUAL"
    return "REFUSED"


def evidence_status(rec, artifact_root):
    required = rec.get("required_artifacts", [])
    for rel in required:
        if not os.path.exists(os.path.join(artifact_root, rel)):
            return "INCOMPLETE", rel
    return "COMPLETE", None


def write_partial_index(artifact_root, rec, snap, outcome):
    idx = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": rec["batch_id"],
        "producer_outcome": outcome,
        "run_rc_map": snap["run_rc_map"],
        "monotonic_at_partial": snap["monotonic_now"],
        "note": "partial evidence saved before cleanup",
    }
    write_json_atomic(os.path.join(artifact_root, "partial_index.json"), idx)


def final_rc(outcome, ev, cleanup):
    """固定优先级(cleanup 未完成 > evidence 缺失 > producer outcome):
      cleanup ∈ {RESIDUAL, REFUSED, NOT_ATTEMPTED}(需要清理但未完成)→ 60;
      evidence == INCOMPLETE(无论 outcome)→ 50;
      否则按 producer outcome → 0/10/20/30/40。
    cleanup != CLEAN 时绝不返回 0;evidence 缺失不因 FAILED/CRASHED 被隐藏。"""
    if cleanup in ("RESIDUAL", "REFUSED", "NOT_ATTEMPTED"):
        return RC_CLEANUP_RESIDUAL
    if ev == "INCOMPLETE":
        return RC_EVIDENCE_INCOMPLETE
    return {"SUCCEEDED": RC_SUCCESS, "FAILED": RC_FAILED, "CRASHED": RC_CRASHED,
            "TIMED_OUT": RC_TIMED_OUT, "CANCELLED": RC_CANCELLED}[outcome]


# ---------- monitor 主循环 ----------
def run_monitor(rec, record, artifact_root, cancel_path, readonly=False, child=None):
    t0 = time.monotonic()
    outcome, terminal = None, False
    while not terminal:
        if child is not None:
            child.poll()  # 及时 reap 自己的直接子进程,清掉 leader 僵尸,残留检测才准
        snap = observe(rec, artifact_root, t0, cancel_path)
        outcome, terminal = decide(snap, rec)
        if terminal:
            break
        time.sleep(POLL_SEC)
    if child is not None:
        # 终态后:若是 CANCELLED/TIMED_OUT 需先杀组(见下),但正常/崩溃终态先 reap leader 僵尸
        if outcome in ("SUCCEEDED", "FAILED", "CRASHED"):
            try:
                child.wait(timeout=TERM_GRACE_SEC)
            except Exception:
                pass

    # CANCELLED / TIMED_OUT:先执行终止(除非只读),再定 cleanup
    force_fail = os.environ.get("WP303_FORCE_CLEANUP_FAIL") == "1"
    if readonly:
        cleanup = "NOT_ATTEMPTED"
    elif outcome in ("CANCELLED", "TIMED_OUT", "CRASHED"):
        write_partial_index(artifact_root, rec, snap, outcome)
        cleanup = do_cleanup(rec, force_fail=force_fail)
    else:
        cleanup = do_cleanup(rec, force_fail=force_fail)  # 正常终态也确认无残留

    ev, missing = evidence_status(rec, artifact_root)
    status = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": rec["batch_id"],
        "producer_outcome": outcome,
        "evidence_status": ev,
        "evidence_missing": missing,
        "cleanup_status": cleanup,
        "container_cleanup": "NOT_ATTEMPTED",  # 容器归属不可核验
        "run_rc_map": snap["run_rc_map"],
        "readonly": readonly,
    }
    write_json_atomic(os.path.join(artifact_root, "monitor_status.json"), status)
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return final_rc(outcome, ev, cleanup)


# ---------- 子命令 ----------
def cmd_launch(args):
    artifact_root = os.path.realpath(args.artifact_root)
    if not os.path.isdir(artifact_root):
        die(RC_USAGE, f"artifact_root 不存在: {artifact_root}")
    os.makedirs(os.path.join(artifact_root, "runs"), exist_ok=True)
    record = os.path.join(artifact_root, "task_record.json")
    cancel_path = os.path.join(artifact_root, "CANCEL")
    lock_path = os.path.join(artifact_root, ".monitor.lock")

    # 独占 monitor 锁
    lfd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        die(RC_SECURITY, "另一个 monitor 已持锁")

    # 启动 producer 于独立 session
    producer = args.producer
    child = subprocess.Popen(producer, preexec_fn=os.setsid, cwd=artifact_root)
    pid = child.pid
    # 等 setsid 生效
    for _ in range(50):
        try:
            if os.getpgid(pid) == pid and os.getsid(pid) == pid:
                break
        except ProcessLookupError:
            break
        time.sleep(0.01)
    st = pid_starttime(pid)
    rec = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": args.batch_id,
        "script": " ".join(producer),
        "pid": pid,
        "pgid": (os.getpgid(pid) if pid_starttime(pid) else pid),
        "sid": (os.getsid(pid) if pid_starttime(pid) else pid),
        "pid_starttime": st if st is not None else "gone",
        "boot_id": boot_id(),
        "artifact_root": artifact_root,
        "log": args.log or os.path.join(artifact_root, "batch.log"),
        "expected_runs": args.expected_runs,
        "deadline_params": {
            "startup_budget": args.startup_budget,
            "duration": args.duration,
            "per_run_teardown": args.per_run_teardown,
            "inter_run_gap": args.inter_run_gap,
            "finalization_budget": args.finalization_budget,
        },
        "required_artifacts": args.required or [],
        "created_at_monotonic": time.monotonic(),
    }
    # 绝对 monotonic deadline 存盘:monitor 重启从 record 恢复,不重置预算(boot_id 守卫)
    rec["deadline_monotonic"] = time.monotonic() + batch_deadline(rec)
    # record 落盘(0600)必须在 monitor 接管前完整
    old = os.umask(0o077)
    try:
        write_json_atomic(record, rec)
    finally:
        os.umask(old)
    validate_record_path(record, artifact_root)
    rc = run_monitor(rec, record, artifact_root, cancel_path, readonly=False, child=child)
    try:
        child.wait(timeout=1)
    except Exception:
        pass
    return rc


def cmd_monitor(args):
    artifact_root = os.path.realpath(args.artifact_root)
    record = os.path.join(artifact_root, "task_record.json")
    cancel_path = os.path.join(artifact_root, "CANCEL")
    lock_path = os.path.join(artifact_root, ".monitor.lock")
    rec = load_record(record, artifact_root)
    lfd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # 第二 monitor:主 monitor 在场,立即让位(只读声明);不写 monitor_status、不清理、
        # 不改主 monitor;返回专用退出码(非 0,调用者不得当批次成功计入 gate)
        print(json.dumps({"readonly": True, "batch_id": rec.get("batch_id"),
                          "note": "another monitor holds the lock; deferring", "rc": RC_READONLY_DEFER},
                         ensure_ascii=False, sort_keys=True))
        return RC_READONLY_DEFER
    return run_monitor(rec, record, artifact_root, cancel_path, readonly=False)


def main():
    ap = argparse.ArgumentParser(prog="batch_lifecycle")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument("--artifact-root", required=True)
        p.add_argument("--expected-runs", type=int, default=1)
        p.add_argument("--duration", type=float, default=1.0)
        p.add_argument("--startup-budget", type=float, default=2.0)
        p.add_argument("--per-run-teardown", type=float, default=0.5)
        p.add_argument("--inter-run-gap", type=float, default=0.2)
        p.add_argument("--finalization-budget", type=float, default=1.0)
        p.add_argument("--required", action="append", default=None)
        p.add_argument("--log", default=None)

    pl = sub.add_parser("launch")
    add_common(pl)
    pl.add_argument("--batch-id", required=True)
    pl.add_argument("producer", nargs=argparse.REMAINDER)

    pm = sub.add_parser("monitor")
    pm.add_argument("--artifact-root", required=True)

    args = ap.parse_args()
    if args.cmd == "launch":
        prod = args.producer
        if prod and prod[0] == "--":
            prod = prod[1:]
        if not prod:
            die(RC_USAGE, "launch 需要 producer argv(在 -- 之后)")
        args.producer = prod
        return cmd_launch(args)
    if args.cmd == "monitor":
        return cmd_monitor(args)
    die(RC_USAGE, "未知子命令")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        die(RC_INTERNAL, f"内部错误: {e!r}")
