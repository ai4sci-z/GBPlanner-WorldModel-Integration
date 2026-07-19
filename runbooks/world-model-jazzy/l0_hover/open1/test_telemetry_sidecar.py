#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1 · sidecar 反例门(E1-01.4 红案 11-19/22/23 + 采集器 + 容量 + 只读适配层)。

expected 来源:原子文件语义(tmp→fsync→rename→dirfsync)、Linux /proc 文本格式、
WP304 §10 D4/D5 契约。全 fixture/fake:不触真实 Docker daemon、不建 ROS 节点、不跑仿真。
"""
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telemetry_contract as C  # noqa: E402
import telemetry_sidecar as S  # noqa: E402

FAIL = 0


def ck(name, got, want):
    global FAIL
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}: {name} expected={want!r} actual={got!r}")
    if not ok:
        FAIL += 1


def rejects(name, fn, exc=None):
    global FAIL
    exc = exc or S.TelemetryWriteError
    try:
        fn()
        print(f"FAIL: {name} expected={exc.__name__} actual=被放行")
        FAIL += 1
    except exc as e:
        print(f"PASS: {name} expected={exc.__name__} actual={exc.__name__}")
        print(f"    ↳ {e}")
    except Exception as e:
        print(f"FAIL: {name} expected={exc.__name__} actual={type(e).__name__}: {e}")
        FAIL += 1


RUN_ID = "20260715T204428.255001623Z"
IDENT = {"batch_id": "b1", "run_id": RUN_ID, "pid": os.getpid(),
         "pid_starttime": "111", "boot_id": "boot-x"}


def new_run():
    base = tempfile.mkdtemp()
    run = os.path.join(base, RUN_ID)
    os.makedirs(os.path.join(run, "telemetry"))
    return base, run


def rec(i, field="host.loadavg", value=None):
    return {"schema_version": C.SCHEMA_VERSION, "batch_id": "b1", "run_id": RUN_ID,
            "utc_ns": 1_800_000_000_000_000_000 + i, "mono_ns": 1000 + i,
            "field": field, "value": value if value is not None else {"i": i}}


print("======== 原子写(E1-02.1;红案 16/17/18)========")
base, run = new_run()
p = os.path.join(run, "telemetry", "freeze.json")
S.atomic_write(p, b'{"a":1}', run_root=run)
ck("原子写落盘", open(p, "rb").read(), b'{"a":1}')
ck("无 tmp 残留", [f for f in os.listdir(os.path.dirname(p)) if f.endswith(".tmp")], [])
rejects("红案18 默认拒绝覆盖正式文件", lambda: S.atomic_write(p, b"x", run_root=run))
rejects("红案16 输出越出 run 根",
        lambda: S.atomic_write(os.path.join(base, "escape.json"), b"x", run_root=run))
rejects("红案16b ../ 逃逸",
        lambda: S.atomic_write(os.path.join(run, "telemetry", "..", "..", "esc.json"), b"x", run_root=run))
lnk = os.path.join(run, "telemetry", "link.json")
outside = os.path.join(base, "outside.json")
open(outside, "w").write("orig")
os.symlink(outside, lnk)
rejects("红案17 symlink 将输出引出 run 根", lambda: S.atomic_write(lnk, b"x", run_root=run))
ck("红案17b symlink 目标未被改写", open(outside).read(), "orig")

print("======== 不可变段 + index(E1-02.2;红案 11-15)========")
base, run = new_run()
tdir = os.path.join(run, "telemetry")
store = S.SegmentStore(tdir, run_root=run, identity=dict(IDENT))
for i in range(3):
    store.append(rec(i))
store.seal()
seg1 = os.path.join(tdir, "segment-1.jsonl")
ck("段1 落盘", os.path.exists(seg1), True)
idx = json.load(open(os.path.join(tdir, "index.json")))
e = idx["segments"][0]
ck("index 记录 record_count", e["record_count"], 3)
ck("index 记录 sha256", e["sha256"], hashlib.sha256(open(seg1, "rb").read()).hexdigest())
for k in ("segment", "schema_version", "first_utc_ns", "last_utc_ns",
          "first_mono_ns", "last_mono_ns", "bytes", "truncated", "dropped_records"):
    ck(f"index 字段 {k} 在档", k in e, True)
ck("红案15 已封存段权限只读(0444)", oct(os.stat(seg1).st_mode & 0o777), "0o444")
rejects("红案15b 封存后无追加路径(直接写被拒)",
        lambda: open(seg1, "ab").write(b"x"), exc=PermissionError)
store.append(rec(10))
store.seal()
ck("第二段编号递增不复用", os.path.exists(os.path.join(tdir, "segment-2.jsonl")), True)

# 恢复:正常
r = S.recover(tdir)
ck("恢复:两段全承认", [e["segment"] for e in r["segments"]], [1, 2])
ck("恢复:状态 OK", r["status"], "OK")
# 红案14:.tmp 只能登记未完成,不得当正式证据
open(os.path.join(tdir, "segment-3.tmp"), "w").write('{"x":1}\n')
r = S.recover(tdir)
ck("红案14 .tmp 不进正式段", [e["segment"] for e in r["segments"]], [1, 2])
ck("红案14b .tmp 登记为未完成", r["incomplete_tmp"], ["segment-3.tmp"])
os.unlink(os.path.join(tdir, "segment-3.tmp"))
# 红案11:损坏 segment(sha 不符)必须 CORRUPT
os.chmod(seg1, 0o644)
with open(seg1, "ab") as f:
    f.write(b"TAMPER\n")
os.chmod(seg1, 0o444)
r = S.recover(tdir)
ck("红案11 损坏段被 index 拒绝 → CORRUPT", r["status"], "CORRUPT")
# 红案12:index 指向不存在的 segment
base, run = new_run()
tdir = os.path.join(run, "telemetry")
store = S.SegmentStore(tdir, run_root=run, identity=dict(IDENT))
store.append(rec(0)); store.seal()
os.chmod(os.path.join(tdir, "segment-1.jsonl"), 0o644)
os.unlink(os.path.join(tdir, "segment-1.jsonl"))
r = S.recover(tdir)
ck("红案12 index 指向不存在段 → CORRUPT", r["status"], "CORRUPT")
# 红案13:重复段号
base, run = new_run()
tdir = os.path.join(run, "telemetry")
store = S.SegmentStore(tdir, run_root=run, identity=dict(IDENT))
store.append(rec(0)); store.seal()
idxp = os.path.join(tdir, "index.json")
d = json.load(open(idxp)); d["segments"].append(dict(d["segments"][0]))
open(idxp, "w").write(json.dumps(d))
r = S.recover(tdir)
ck("红案13 重复段号 → CORRUPT", r["status"], "CORRUPT")
# 红案19:第二 writer 拒绝
base, run = new_run()
tdir = os.path.join(run, "telemetry")
s1 = S.SegmentStore(tdir, run_root=run, identity=dict(IDENT))
rejects("红案19 第二 writer 同 run 被拒",
        lambda: S.SegmentStore(tdir, run_root=run,
                               identity={**IDENT, "pid": IDENT["pid"] + 1, "pid_starttime": "222"}))
# 崩溃恢复接管:同身份可重开(不重编号)
s1.append(rec(0)); s1.seal(); s1.close()
s2 = S.SegmentStore(tdir, run_root=run, identity=dict(IDENT))
s2.append(rec(1)); s2.seal()
r = S.recover(tdir)
ck("重启接管:续编号不重号", [e["segment"] for e in r["segments"]], [1, 2])

print("======== 宿主采集器(E1-03.1;红案23)========")
ck("loadavg 解析", S.parse_loadavg("0.52 0.58 0.59 1/1219 12345\n"),
   {"load1": 0.52, "load5": 0.58, "load15": 0.59})
ck("loadavg 截断行 → UNAVAILABLE", S.parse_loadavg("0.52"), C.UNAVAILABLE)
ck("loadavg 缺失 → UNAVAILABLE", S.parse_loadavg(None), C.UNAVAILABLE)
STAT1 = "cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 50 0 50 400 0 0 0 0 0 0\ncpu1 50 0 50 400 0 0 0 0 0 0\n"
STAT2 = "cpu  150 0 150 900 0 0 0 0 0 0\ncpu0 75 0 75 450 0 0 0 0 0 0\ncpu1 75 0 75 450 0 0 0 0 0 0\n"
a = S.parse_proc_stat(STAT1); b = S.parse_proc_stat(STAT2)
d = S.cpu_pct(a, b)
ck("cpu 总差分 pct", d["total_pct"], 50.0)
ck("cpu 每核差分", d["per_core_pct"], {"cpu0": 50.0, "cpu1": 50.0})
STAT3 = "cpu  200 0 200 1200 0 0 0 0 0 0\ncpu0 100 0 100 600 0 0 0 0 0 0\ncpu1 100 0 100 600 0 0 0 0 0 0\ncpu2 0 0 0 0 0 0 0 0 0 0\n"
d = S.cpu_pct(b, S.parse_proc_stat(STAT3))
ck("核数变化不炸(新核跳过差分)", sorted(d["per_core_pct"]), ["cpu0", "cpu1"])
d = S.cpu_pct(b, a)
ck("计数回绕 → counter_wrap 标记", d["counter_wrap"], True)
ck("meminfo 解析", S.parse_meminfo("MemTotal:  16000000 kB\nMemFree: 1 kB\nMemAvailable: 8000000 kB\n"),
   {"mem_total_kb": 16000000, "mem_available_kb": 8000000})
ck("meminfo 缺字段 → UNAVAILABLE", S.parse_meminfo("MemTotal: 1 kB\n"), C.UNAVAILABLE)
DS1 = "   8       0 sda 100 0 1000 0 50 0 500 0 0 0 0 0 0 0 0 0 0\n"
DS2 = "   8       0 sda 120 0 1600 0 60 0 900 0 0 0 0 0 0 0 0 0 0\n"
d = S.diskstats_delta(S.parse_diskstats(DS1), S.parse_diskstats(DS2))
ck("diskstats 扇区差分", d, {"sda": {"read_sectors": 600, "written_sectors": 400}})
ck("红案23 cpu_freq 不可读 → UNAVAILABLE(禁伪造 0)",
   S.read_cpu_freq(lambda p: (_ for _ in ()).throw(OSError("EACCES"))), C.UNAVAILABLE)
ck("cpu_freq 可读", S.read_cpu_freq(lambda p: "2400000\n"), 2400000)

print("======== 冻结身份(E1-03.2,注入适配层)========")
calls = []


def fake_git(*args):
    calls.append(args)
    if args[:2] == ("rev-parse", "HEAD"):
        return "750032a3aad8b62b0c8ef2b00f740ee125fdb382\n"
    if args[:2] == ("status", "--porcelain"):
        return ""
    raise AssertionError(args)


fz = S.collect_freeze(git_runner=fake_git,
                      image_inspect=lambda ref: {"tag": ref, "digest": "sha256:deadbeef"},
                      config_hash="cafe" * 8, batch_id="b1", run_id=RUN_ID,
                      image_refs=["navlab/companion:jazzy-x"])
ck("freeze wm commit(注入,非真仓)", fz["world_model_commit"], "750032a3aad8b62b0c8ef2b00f740ee125fdb382")
ck("freeze dirty=False", fz["world_model_dirty"], False)
ck("freeze canonical hash 透传(复用 E0 实现,不再造第二套)", fz["canonical_config_hash"], "cafe" * 8)
ck("freeze 镜像 digest", fz["images"][0]["digest"], "sha256:deadbeef")
ck("git 只读调用(rev-parse/status)", all(a[0] in ("rev-parse", "status") for a in calls), True)

print("======== Docker 只读适配层(E1-03.3;红案22)========")


class RecordingDocker:
    def __init__(self):
        self.calls = []

    def inspect(self, name):
        self.calls.append(("inspect", name)); return {"Image": "sha256:img"}

    def top(self, name):
        self.calls.append(("top", name)); return {"Processes": []}

    def logs(self, name, tail=None):
        self.calls.append(("logs", name)); return "line\n"

    def wait(self, name):
        self.calls.append(("wait", name)); return 0

    def stop(self, name):  # 若被调用即违规
        self.calls.append(("stop", name))


fake = RecordingDocker()
ad = S.DockerReadOnlyAdapter(fake)
ad.inspect("c"); ad.top("c"); ad.logs("c"); code = ad.wait("c")
ck("只读四方法可用", [c[0] for c in fake.calls], ["inspect", "top", "logs", "wait"])
for m in ("stop", "kill", "restart", "exec_run", "update", "signal", "attach"):
    ck(f"禁用方法不存在: {m}", hasattr(ad, m), False)
f = S.container_exit_fields(code)
ck("红案22a 容器退出码字段名", f["official_baseline_container_exit_code"], 0)
ck("红案22b SITL 进程级退出码恒 UNAVAILABLE", f["sitl_process_exit_code"], C.UNAVAILABLE)
ck("红案22c 两字段并存不混写", sorted(f), ["official_baseline_container_exit_code", "sitl_process_exit_code"])

print("======== ROS 只订不发(E1-03.4,fake node)========")


class FakeNode:
    def __init__(self):
        self.subs = []

    def create_subscription(self, *a, **k):
        self.subs.append(a); return object()

    def create_publisher(self, *a, **k):
        raise AssertionError("不得创建 publisher")


node = FakeNode()
sub = S.SubscribeOnlyNode(node, ros_domain_id="7", system_domain_id="7")
sub.create_subscription("String", "/external_nav/status", lambda m: None, 10)
ck("订阅创建成功", len(node.subs), 1)
for m in ("create_publisher", "create_service", "create_client", "set_parameters",
          "declare_parameter", "publish"):
    rejects(f"只订不发:{m} 被拒", lambda m=m: getattr(sub, m), exc=S.RosWriteRefused)
rejects("跨 domain 拒绝(必须与被测系统同 ROS_DOMAIN_ID)",
        lambda: S.SubscribeOnlyNode(FakeNode(), ros_domain_id="7", system_domain_id="8"),
        exc=S.RosWriteRefused)

print("======== 容量/预算(E1-03.5;红案20-21 见 entry 测试)========")
gov = S.CapacityGovernor(limits={"host.jsonl": 100}, cpu_budget_pct=3.0, mem_budget_mb=64.0)
ck("限内放行", gov.admit("host.jsonl", 60), True)
ck("超限拒绝并计数", gov.admit("host.jsonl", 60), False)
ck("truncated 标记", gov.truncated["host.jsonl"], True)
ck("dropped_records 计数", gov.dropped["host.jsonl"], 1)
clockv = [0.0]
gov2 = S.CapacityGovernor(limits={}, cpu_budget_pct=3.0, mem_budget_mb=64.0,
                          clock=lambda: clockv[0])
ck("cadence 1Hz:首拍放行", gov2.cadence_ok("host", 1.0), True)
ck("cadence 1Hz:同秒第二拍拒", gov2.cadence_ok("host", 1.0), False)
clockv[0] = 1.01
ck("cadence 1Hz:下一秒放行", gov2.cadence_ok("host", 1.0), True)
rejects("预算超限 → TelemetryOverrun(sidecar 自杀,producer 不受影响)",
        lambda: gov2.check_budget(cpu_pct=5.0, mem_mb=10.0), exc=S.TelemetryOverrun)
rejects("内存超限 → TelemetryOverrun",
        lambda: gov2.check_budget(cpu_pct=1.0, mem_mb=65.0), exc=S.TelemetryOverrun)
gov2.check_budget(cpu_pct=2.9, mem_mb=63.9)
print("PASS: 预算内不触发")

print("================================")
print(f"结果: FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
