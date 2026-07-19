#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP304 E1 · 纯旁路 telemetry sidecar:原子证据存储 + 宿主采集 + 只读适配层 + 容量约束。

旁路契约(WP304 §10 D5):零写入被测系统;写失败只改变证据状态,绝不改变
producer 业务结果或退出码;所有外部系统(git/docker/ros)经注入适配层访问,
fixture 全 fake——本模块自身不连接真实 daemon、不创建真实 ROS 节点。
原子语义:同目录 tmp → write → flush → fsync(file) → rename → fsync(dir);
JSONL 为不可变段(segment-N.tmp→rename segment-N.jsonl,封存后 0444 永久只读),
段清单由原子 index.json 记录(number/schema/count/首末双时戳/bytes/sha256/truncated/dropped)。
"""
import hashlib
import json
import os
import time

import telemetry_contract as C


class TelemetryWriteError(Exception):
    """证据写入违规/失败:只影响 evidence 状态,不得触碰 producer。"""


class TelemetryOverrun(Exception):
    """资源预算超限:sidecar 自行退出并记录 telemetry_overrun。"""


class RosWriteRefused(Exception):
    """ROS 旁路违规:任何发布/服务/参数写路径一律拒绝。"""


# ---------- 原子单文件写(E1-02.1) ----------
def _assert_inside(path, run_root):
    root = os.path.realpath(run_root)
    parent = os.path.realpath(os.path.dirname(path))
    if parent != root and not parent.startswith(root + os.sep):
        raise TelemetryWriteError(f"输出越出 run 根: {path} ∉ {root}")


def atomic_write(path, data, run_root, overwrite=False):
    """同目录 tmp → write → flush → fsync(file) → rename → fsync(directory)。
    拒 symlink 目标、拒越出 run 根、默认拒覆盖;只清理本次创建的 tmp。"""
    if not isinstance(data, (bytes, bytearray)):
        raise TelemetryWriteError("atomic_write 只收 bytes")
    _assert_inside(path, run_root)
    if os.path.islink(path):
        raise TelemetryWriteError(f"拒绝 symlink 目标: {path}")
    if os.path.exists(path) and not overwrite:
        raise TelemetryWriteError(f"拒绝覆盖既有证据: {path}")
    d = os.path.dirname(path)
    tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)
        dfd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except TelemetryWriteError:
        raise
    except OSError as e:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)  # 只清理本次创建的 tmp
        except OSError:
            pass
        raise TelemetryWriteError(f"原子写失败: {path}: {e}") from e


# ---------- 不可变 JSONL 段 + index(E1-02.2/02.3;E1C-04 内核锁互斥+恢复协议) ----------
def _current_boot_id():
    try:
        return open("/proc/sys/kernel/random/boot_id").read().strip()
    except OSError:
        return "UNKNOWN"


def _identity_alive(ident):
    """旧 writer 存活判定:同 boot ∧ PID 在 ∧ starttime 匹配。
    boot_id 不同 → 不是同一存活进程(跨 boot 不得冒充连续)。"""
    if ident.get("boot_id") != _current_boot_id():
        return False
    pid = ident.get("pid")
    try:
        data = open(f"/proc/{pid}/stat").read()
    except (OSError, TypeError):
        return False
    f = data[data.rfind(")") + 2:].split()
    if not f or f[0] == "Z":
        return False
    return len(f) > 19 and f[19] == str(ident.get("pid_starttime"))


class SegmentStore:
    """段式 JSONL 证据仓:当前段只在内存;seal() 才落盘为不可变段并登记 index。

    互斥与恢复协议(E1C-04):
    - 并发互斥 = 内核锁:独立 lock fd + flock(LOCK_EX|LOCK_NB),writer 生命周期持有,
      进程亡由内核自动释放。任何并发第二 writer(无论身份)立即失败。
    - writer.json 只是审计元数据,不是锁。拿到内核锁后:旧身份仍活(同 boot+PID+starttime)
      → 拒绝;已死 → 走恢复:recover() 核 index/segment 完整性,CORRUPT 拒写,
      tmp 只登记 incomplete,从已验证 index 取 next 段号,写入**新**身份(不复用旧 PID/starttime)。"""

    def __init__(self, dir_path, run_root, identity, name="segment"):
        C.validate_writer_identity(identity, run_root)
        _assert_inside(os.path.join(dir_path, "x"), run_root)
        self._dir = dir_path
        self._root = run_root
        self._name = name
        self._ident = dict(identity)
        self._buf = []
        self._closed = False
        os.makedirs(dir_path, exist_ok=True)
        # 1) 内核锁(并发互斥的唯一权威)
        self._lock_fd = os.open(os.path.join(dir_path, "writer.lockfd"),
                                os.O_CREAT | os.O_RDWR, 0o600)
        try:
            import fcntl
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(self._lock_fd)
            raise TelemetryWriteError(f"第二 writer 被拒(内核锁被持有): {e}") from e
        try:
            # 2) 审计身份与恢复协议
            self._audit_path = os.path.join(dir_path, "writer.json")
            prev = None
            if os.path.exists(self._audit_path):
                try:
                    prev = json.load(open(self._audit_path, encoding="utf-8"))
                except (OSError, ValueError) as e:
                    raise TelemetryWriteError(f"writer 审计元数据损坏: {e}") from e
            if prev is not None and not C.identity_matches(prev, self._ident):
                if _identity_alive(prev):
                    raise TelemetryWriteError(
                        f"第二 writer 被拒:旧 writer 仍存活 "
                        f"{prev.get('pid')}/{prev.get('pid_starttime')}/{prev.get('boot_id')}")
                # 旧 writer 已死:显式恢复(核完整性,不猜修,不复用旧身份)
                rec = recover(dir_path)
                if rec["status"] == "CORRUPT":
                    raise TelemetryWriteError(
                        f"恢复拒绝:index/segment 不一致 → CORRUPT: {rec['reasons']}")
            atomic_write(self._audit_path,
                         json.dumps(self._ident, sort_keys=True).encode("utf-8"),
                         run_root=run_root, overwrite=True)
            self._next = self._recover_next_number()
        except TelemetryWriteError:
            self._release_lock()
            raise

    def _release_lock(self):
        try:
            os.close(self._lock_fd)
        except OSError:
            pass

    def _index_path(self):
        return os.path.join(self._dir, "index.json")

    def _load_index(self):
        p = self._index_path()
        if not os.path.exists(p):
            return {"schema_version": C.SCHEMA_VERSION, "segments": []}
        return json.load(open(p, encoding="utf-8"))

    def _recover_next_number(self):
        idx = self._load_index()
        nums = [e["segment"] for e in idx["segments"]]
        return (max(nums) + 1) if nums else 1

    def append(self, record):
        if self._closed:
            raise TelemetryWriteError("store 已关闭")
        C.validate_record(record)
        if record["batch_id"] != self._ident["batch_id"] or record["run_id"] != self._ident["run_id"]:
            raise TelemetryWriteError("record 身份与 writer 不符")
        self._buf.append(record)

    def seal(self, truncated=False, dropped_records=0):
        if not self._buf:
            raise TelemetryWriteError("空段不封存")
        n = self._next
        final = os.path.join(self._dir, f"{self._name}-{n}.jsonl")
        if os.path.exists(final):
            raise TelemetryWriteError(f"段号已存在,拒绝复用: {final}")
        payload = "".join(json.dumps(r, sort_keys=True) + "\n" for r in self._buf).encode("utf-8")
        atomic_write(final, payload, run_root=self._root)
        os.chmod(final, 0o444)  # 已封存段永久只读
        entry = {
            "segment": n,
            "file": os.path.basename(final),
            "sealed_monotonic_ns": time.monotonic_ns(),
            "schema_version": C.SCHEMA_VERSION,
            "record_count": len(self._buf),
            "first_utc_ns": self._buf[0]["utc_ns"],
            "last_utc_ns": self._buf[-1]["utc_ns"],
            "first_mono_ns": self._buf[0]["mono_ns"],
            "last_mono_ns": self._buf[-1]["mono_ns"],
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "truncated": bool(truncated),
            "dropped_records": int(dropped_records),
        }
        idx = self._load_index()
        idx["segments"].append(entry)
        atomic_write(self._index_path(),
                     json.dumps(idx, sort_keys=True, indent=1).encode("utf-8"),
                     run_root=self._root, overwrite=True)
        self._buf = []
        self._next = n + 1
        return entry

    def close(self):
        self._closed = True
        self._release_lock()


def recover(dir_path):
    """重启恢复:只承认 index 登记且 sha/存在性核对通过的正式段;
    tmp 只登记未完成;任何不一致 → CORRUPT,禁止猜测修复/重新编号。"""
    idx_path = os.path.join(dir_path, "index.json")
    reasons = []
    segments = []
    incomplete = sorted(f for f in os.listdir(dir_path) if f.endswith(".tmp"))
    if not os.path.exists(idx_path):
        return {"status": "OK", "segments": [], "incomplete_tmp": incomplete,
                "reasons": ["无 index(尚未封存任何段)"]}
    try:
        idx = json.load(open(idx_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"status": "CORRUPT", "segments": [], "incomplete_tmp": incomplete,
                "reasons": [f"index 不可解析: {e}"]}
    nums = [e.get("segment") for e in idx.get("segments", [])]
    if len(nums) != len(set(nums)):
        reasons.append(f"重复段号: {sorted(nums)}")
    for e in idx.get("segments", []):
        fname = e.get("file") or f"segment-{e.get('segment')}.jsonl"
        p = os.path.join(dir_path, fname)
        if not os.path.exists(p):
            reasons.append(f"index 指向不存在的段: {os.path.basename(p)}")
            continue
        data = open(p, "rb").read()
        if hashlib.sha256(data).hexdigest() != e.get("sha256"):
            reasons.append(f"段内容与 index sha256 不符: {os.path.basename(p)}")
            continue
        segments.append(e)
    # 未登记的正式段文件 = writer 序列被绕过 → CORRUPT
    import re as _re
    on_disk = {f for f in os.listdir(dir_path)
               if _re.match(r"^(.+-)?segment-\d+\.jsonl$", f)}
    listed = {(e.get("file") or f"segment-{e.get('segment')}.jsonl")
              for e in idx.get("segments", [])}
    for orphan in sorted(on_disk - listed):
        reasons.append(f"存在未登记段: {orphan}")
    status = "CORRUPT" if reasons else "OK"
    return {"status": status, "segments": segments,
            "incomplete_tmp": incomplete, "reasons": reasons}


# ---------- 宿主采集器(E1-03.1;纯解析,I/O 经注入 reader) ----------
def parse_loadavg(text):
    if not text:
        return C.UNAVAILABLE
    parts = text.split()
    if len(parts) < 3:
        return C.UNAVAILABLE
    try:
        return {"load1": float(parts[0]), "load5": float(parts[1]), "load15": float(parts[2])}
    except ValueError:
        return C.UNAVAILABLE


def parse_proc_stat(text):
    if not text:
        return C.UNAVAILABLE
    out = {}
    for line in text.splitlines():
        f = line.split()
        if not f or not f[0].startswith("cpu"):
            continue
        try:
            vals = [int(x) for x in f[1:]]
        except ValueError:
            continue
        out[f[0]] = {"total": sum(vals), "idle": vals[3] if len(vals) > 3 else 0}
    return out if out else C.UNAVAILABLE


def cpu_pct(prev, cur):
    """差分 CPU 占用;计数回绕(cur<prev)→ counter_wrap=True 且不输出伪造值。"""
    res = {"total_pct": None, "per_core_pct": {}, "counter_wrap": False}
    if prev is C.UNAVAILABLE or cur is C.UNAVAILABLE:
        return res
    for key in cur:
        if key not in prev:
            continue  # 新核:无前样本,跳过差分(核数变化容忍)
        dt = cur[key]["total"] - prev[key]["total"]
        didle = cur[key]["idle"] - prev[key]["idle"]
        if dt < 0 or didle < 0:
            res["counter_wrap"] = True
            continue
        pct = 0.0 if dt == 0 else round(100.0 * (dt - didle) / dt, 4)
        if key == "cpu":
            res["total_pct"] = pct
        else:
            res["per_core_pct"][key] = pct
    return res


def parse_meminfo(text):
    if not text:
        return C.UNAVAILABLE
    vals = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("MemTotal:", "MemAvailable:"):
            try:
                vals[parts[0][:-1]] = int(parts[1])
            except ValueError:
                return C.UNAVAILABLE
    if "MemTotal" not in vals or "MemAvailable" not in vals:
        return C.UNAVAILABLE
    return {"mem_total_kb": vals["MemTotal"], "mem_available_kb": vals["MemAvailable"]}


def parse_diskstats(text):
    if not text:
        return C.UNAVAILABLE
    out = {}
    for line in text.splitlines():
        f = line.split()
        if len(f) >= 10:
            try:
                out[f[2]] = {"read_sectors": int(f[5]), "written_sectors": int(f[9])}
            except ValueError:
                continue
    return out if out else C.UNAVAILABLE


def diskstats_delta(prev, cur):
    if prev is C.UNAVAILABLE or cur is C.UNAVAILABLE:
        return C.UNAVAILABLE
    out = {}
    for dev in cur:
        if dev not in prev:
            continue
        dr = cur[dev]["read_sectors"] - prev[dev]["read_sectors"]
        dw = cur[dev]["written_sectors"] - prev[dev]["written_sectors"]
        if dr < 0 or dw < 0:
            continue  # 回绕:该设备本拍不出数,不伪造
        out[dev] = {"read_sectors": dr, "written_sectors": dw}
    return out


def read_cpu_freq(reader, path="/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"):
    """cpu_freq 不可读 → UNAVAILABLE(D4-03 显式;禁止伪造 0)。"""
    try:
        text = reader(path)
        return int(text.strip())
    except Exception:
        return C.UNAVAILABLE


def read_boot_id(reader):
    try:
        return reader("/proc/sys/kernel/random/boot_id").strip()
    except Exception:
        return C.UNAVAILABLE


# ---------- 冻结身份(E1-03.2;git/docker 全注入) ----------
def collect_freeze(git_runner, image_inspect, config_hash, batch_id, run_id, image_refs):
    """只读采集冻结身份。canonical_config_hash 由调用方用 E0 已验证实现算好传入
    (open1_extract 的实现是唯一算法源,本模块不复制第二套)。"""
    commit = git_runner("rev-parse", "HEAD").strip()
    dirty = bool(git_runner("status", "--porcelain").strip())
    images = []
    for ref in image_refs:
        info = image_inspect(ref)
        images.append({"ref": ref, "tag": info.get("tag"), "digest": info.get("digest")})
    return {"schema_version": C.SCHEMA_VERSION, "batch_id": batch_id, "run_id": run_id,
            "world_model_commit": commit, "world_model_dirty": dirty,
            "canonical_config_hash": config_hash, "images": images}


# ---------- Docker 只读适配层(E1-03.3) ----------
class DockerReadOnlyAdapter:
    """只暴露 inspect/top/logs/wait 四个只读方法;不定义任何写/停/杀方法。"""

    __slots__ = ("_backend",)

    def __init__(self, backend):
        self._backend = backend

    def inspect(self, name):
        return self._backend.inspect(name)

    def top(self, name):
        return self._backend.top(name)

    def logs(self, name, tail=None):
        return self._backend.logs(name, tail=tail) if tail is not None else self._backend.logs(name)

    def wait(self, name):
        return self._backend.wait(name)


def container_exit_fields(container_exit_code):
    """D4-10:容器退出码与 SITL 进程退出码是两个字段,后者恒 UNAVAILABLE
    (SITL 是容器内 ros2 launch 的孙进程,产物无记录),严禁冒充。"""
    return {"official_baseline_container_exit_code": int(container_exit_code),
            "sitl_process_exit_code": C.UNAVAILABLE}


# ---------- ROS 只订不发(E1-03.4) ----------
_ROS_FORBIDDEN = ("create_publisher", "create_service", "create_client",
                  "set_parameters", "declare_parameter", "declare_parameters",
                  "publish", "call", "call_async")


class SubscribeOnlyNode:
    """订阅专用包装:与被测系统同一 ROS_DOMAIN_ID(否则订不到,拒绝启动);
    只透传 create_subscription;一切发布/服务/参数写路径 → RosWriteRefused。"""

    def __init__(self, node, ros_domain_id, system_domain_id):
        if str(ros_domain_id) != str(system_domain_id):
            raise RosWriteRefused(
                f"必须与被测系统同一 ROS_DOMAIN_ID(自 {ros_domain_id} ≠ 被测 {system_domain_id})")
        self._node = node

    def create_subscription(self, *args, **kwargs):
        return self._node.create_subscription(*args, **kwargs)

    def __getattr__(self, name):
        if name in _ROS_FORBIDDEN:
            raise RosWriteRefused(f"只订不发:禁止 {name}")
        raise AttributeError(name)


# ---------- 容量与预算(E1-03.5) ----------
DEFAULT_LIMITS = {
    "telemetry/host.jsonl": 5 * 1024 * 1024,
    "telemetry/readiness.jsonl": 10 * 1024 * 1024,
    "telemetry/extnav.jsonl": 10 * 1024 * 1024,
    "telemetry/sitl_console.log": 50 * 1024 * 1024,
}


class CapacityGovernor:
    """字节上限 + 节奏上限 + CPU/内存预算。超字节上限:停止正文增长并计
    truncated/dropped;超预算:抛 TelemetryOverrun(sidecar 自行退出,
    evidence=CORRUPT,producer 业务结果不受影响)。"""

    def __init__(self, limits=None, cpu_budget_pct=3.0, mem_budget_mb=64.0, clock=None):
        self._limits = dict(DEFAULT_LIMITS if limits is None else limits)
        self._used = {}
        self.truncated = {}
        self.dropped = {}
        self._cpu = cpu_budget_pct
        self._mem = mem_budget_mb
        self._clock = clock or time.monotonic
        self._last = {}

    def admit(self, artifact, nbytes):
        cap = self._limits.get(artifact)
        used = self._used.get(artifact, 0)
        if cap is not None and used + nbytes > cap:
            self.truncated[artifact] = True
            self.dropped[artifact] = self.dropped.get(artifact, 0) + 1
            return False
        self._used[artifact] = used + nbytes
        return True

    def cadence_ok(self, field, max_hz):
        if max_hz <= 0:
            return True
        now = self._clock()
        last = self._last.get(field)
        if last is not None and (now - last) < (1.0 / max_hz):
            return False
        self._last[field] = now
        return True

    def check_budget(self, cpu_pct, mem_mb):
        if cpu_pct > self._cpu or mem_mb > self._mem:
            raise TelemetryOverrun(
                f"telemetry_overrun: cpu={cpu_pct}%>{self._cpu}% 或 mem={mem_mb}MB>{self._mem}MB")
        return True



# ============================================================================
# E1C-02/E1L · 正式可执行 sidecar:CLI + 运行期状态机(fixture/real 同一编排)
# 状态机:WAIT_IDENTITY → ACTIVE(连续采集+周期封存)→ FINISHING → COMPLETE/
# INCOMPLETE/CORRUPT;--once=完整处理一个 attempt(PENDING→RESOLVED→FINISHED)
# 后退出,绝不是"只查一次 registry"。多 run 用 --expected-runs N。
# 并发:host/top/logs-follow/container-wait/ros 各自独立线程,互不阻塞。
# ============================================================================
import queue as _queue
import threading as _threading

REQUIRED_ARTIFACTS = (
    "telemetry/host.jsonl",
    "telemetry/sitl_proc.jsonl",
    "telemetry/sitl_console.log",
    "telemetry/official_baseline_container_exit.json",
    "telemetry/readiness.jsonl",
    "telemetry/extnav.jsonl",
    "telemetry/freeze.json",
)

REQUIRED_PROBE = {"telemetry/host.jsonl": "host.loadavg",
                  "telemetry/sitl_proc.jsonl": "sitl.proc",
                  "telemetry/sitl_console.log": "sitl.console",
                  "telemetry/official_baseline_container_exit.json":
                      "official_baseline_container_exit_code",
                  "telemetry/readiness.jsonl": "readiness",
                  "telemetry/extnav.jsonl": "extnav",
                  "telemetry/freeze.json": "freeze"}


class RosAdapterUnavailable(Exception):
    """rclpy 不可用/适配层无法建立:required ROS 采集 → INCOMPLETE,不碰 producer。"""


# 各 jsonl 入口指针文件与其 required 字段的对应(段链闭包用)
_JSONL_REQUIRED_FIELD = {"telemetry/host.jsonl": "host.loadavg",
                         "telemetry/sitl_proc.jsonl": "sitl.proc",
                         "telemetry/readiness.jsonl": "readiness",
                         "telemetry/extnav.jsonl": "extnav"}


def _verify_segment_chain(run_dir, batch_id):
    """E1L-CORRECT-01:入口指针、index.json、段文件三者一致闭包。
    返回 (chain_corrupt: bool, reasons: list, actual_field_counts: dict)。
    - 复用 recover():index schema/段存在性/SHA/未登记段/重复段号/tmp 登记;
    - 逐行解析全部登记段;不可解析 → CORRUPT;
    - 每条记录 run_id 必须==run 目录基名;batch_id(给定时)必须一致;
    - 输出段内逐字段真实计数(与入口 field_records 闭包比对)。"""
    td = os.path.join(run_dir, "telemetry")
    run_id = os.path.basename(os.path.normpath(run_dir))
    reasons = []
    counts = {}
    rec_report = recover(td)
    if rec_report["status"] == "CORRUPT":
        reasons += [f"段链结构: {x}" for x in rec_report["reasons"]]
    for e in rec_report["segments"]:
        p = os.path.join(td, e["file"])
        try:
            lines = open(p, encoding="utf-8").read().splitlines()
        except OSError as exc:
            reasons.append(f"段不可读: {e['file']}: {exc}")
            continue
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                reasons.append(f"段行不可解析: {e['file']}")
                break
            if r.get("run_id") != run_id:
                reasons.append(f"段记录 run_id 串写: {e['file']}: "
                               f"{r.get('run_id')!r} != {run_id!r}")
                break
            if batch_id is not None and r.get("batch_id") != batch_id:
                reasons.append(f"段记录 batch_id 不符: {e['file']}: "
                               f"{r.get('batch_id')!r} != {batch_id!r}")
                break
            f = r.get("field")
            counts[f] = counts.get(f, 0) + 1
    return bool(reasons), reasons, counts


def evaluate_run_evidence(run_dir, batch_id=None):
    """E1C-05.1/E1L-CORRECT-01 required artifact 闭包(正式入口,CLI 主循环调用)。
    不只看入口文件可否 json.load:入口指针/index/段文件必须一致闭包;
    结构损坏→CORRUPT;required 字段真实零记录→INCOMPLETE(MISSING);
    业务成功/rc=0/full_pass 均不覆盖证据失败(gate 内规则)。"""
    statuses = {}
    chain_corrupt, chain_reasons, actual_counts = _verify_segment_chain(run_dir, batch_id)
    for rel, field in REQUIRED_PROBE.items():
        p = os.path.join(run_dir, rel)
        if not os.path.exists(p):
            statuses[field] = "MISSING"
            continue
        try:
            if rel.endswith(".log"):
                open(p, "rb").read()
                statuses[field] = "PRESENT_VALID"
                continue
            pointer = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            statuses[field] = "CORRUPT"
            continue
        if rel in _JSONL_REQUIRED_FIELD:
            # jsonl 证据:入口指针存在≠证据存在——必须经段链闭包
            if chain_corrupt:
                statuses[field] = "CORRUPT"
                continue
            declared = pointer.get("field_records")
            if not isinstance(declared, dict):
                statuses[field] = "CORRUPT"
                continue
            mismatch = [f for f, n in declared.items() if actual_counts.get(f, 0) != n]
            if mismatch:
                statuses[field] = "CORRUPT"
                continue
            if actual_counts.get(_JSONL_REQUIRED_FIELD[rel], 0) <= 0:
                # required 字段真实零记录(无论有无 error_state)→ 等同缺失
                statuses[field] = "MISSING"
                continue
            statuses[field] = "PRESENT_VALID"
        else:
            statuses[field] = "PRESENT_VALID"
    business_ok = False
    biz = "UNKNOWN"
    sp = os.path.join(run_dir, "summary.json")
    try:
        sj = json.load(open(sp, encoding="utf-8"))
        if isinstance(sj.get("ok"), bool):
            business_ok = sj["ok"]
            biz = "OK" if sj["ok"] else "FAILED"
    except (OSError, ValueError):
        pass
    return statuses, business_ok, biz


def _interruptible_sleep(sec, *stops):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        if any(e.is_set() for e in stops):
            return False
        time.sleep(min(0.02, max(0.0, end - time.monotonic())))
    return True


class FixtureBackend:
    """fixture 数据源:与 real 走同一状态机/线程编排,只替换 I/O。
    输入 JSON:proc{path:[text...]} / docker{inspect,top,logs|logs_chunks,wait,wait_delay_sec,
    omit_console} / ros_stream{key:[{delay,msg}...]}|ros{key:[msg...]} / git / image_refs /
    images_by_ref / config_hash / container / host_interval_sec / force_rc。"""

    def __init__(self, fixture_path):
        with open(fixture_path, encoding="utf-8") as f:
            self.data = json.load(f)
        self._cursors = {}

    def read_file(self, path):
        seq = self.data.get("proc", {}).get(path)
        if seq is None:
            raise OSError(f"fixture 无此文件: {path}")
        i = self._cursors.get(path, 0)
        self._cursors[path] = min(i + 1, len(seq) - 1)
        return seq[min(i, len(seq) - 1)]

    def host_interval_sec(self):
        return float(self.data.get("host_interval_sec", 0.05))

    def git(self, *args):
        key = " ".join(args)
        out = self.data.get("git", {}).get(key)
        if out is None:
            raise OSError(f"fixture 无 git 输出: {key}")
        return out

    def image_inspect(self, ref):
        return self.data.get("images_by_ref", {}).get(ref, {"tag": ref, "digest": "UNAVAILABLE"})

    def image_refs(self):
        return self.data.get("image_refs", [])

    def config_hash(self):
        return self.data.get("config_hash", "UNAVAILABLE")

    def container_name(self):
        if self.data.get("omit_container_identity"):
            raise TelemetryWriteError("fixture: 容器身份不可得")
        return self.data.get("container", "official_baseline")

    def docker_inspect(self, name):
        return self.data.get("docker", {}).get("inspect", {})

    def docker_top(self, name):
        return self.data.get("docker", {}).get("top", {"Processes": []})

    def logs_follow(self, name, should_stop):
        d = self.data.get("docker", {})
        if d.get("omit_console"):
            raise OSError("fixture: console 不可得")
        chunks = d.get("logs_chunks")
        if chunks is None:
            chunks = [{"delay": 0.0, "text": d.get("logs", "")}]
        for ch in chunks:
            if should_stop():
                return
            if ch.get("delay"):
                _t = time.monotonic() + float(ch["delay"])
                while time.monotonic() < _t:
                    if should_stop():
                        return
                    time.sleep(0.01)
            yield ch.get("text", "")

    def wait_blocking(self, name, should_stop):
        d = self.data.get("docker", {})
        delay = float(d.get("wait_delay_sec", 0.0))
        t = time.monotonic() + delay
        while time.monotonic() < t:
            if should_stop():
                return None
            time.sleep(0.01)
        return int(d.get("wait", 0))

    def ros_stream(self, key, should_stop):
        if self.data.get("ros_raise"):
            raise RosAdapterUnavailable("fixture: adapter 初始化异常")
        stream = self.data.get("ros_stream", {}).get(key)
        if stream is None:
            stream = [{"delay": 0.0, "msg": m} for m in self.data.get("ros", {}).get(key, [])]
        for item in stream:
            if should_stop():
                return
            if item.get("delay"):
                t = time.monotonic() + float(item["delay"])
                while time.monotonic() < t:
                    if should_stop():
                        return
                    time.sleep(0.01)
            yield item["msg"]

    def force_rc(self):
        return self.data.get("force_rc")


# ---------- E1L-05 · concrete ROS 只订不发适配层(real backend 专用) ----------
# 权威 topic/消息类型注册(逐条绑 wm 冻结源码证据;不在册=未验证=fail-closed)
AUTHORITATIVE_TOPIC_TYPES = {
    # navlab_external_nav_bridge_node.cpp L42-43/L89:status_topic 默认
    # "/external_nav/status",create_publisher<std_msgs::msg::String>
    "/external_nav/status": "std_msgs/msg/String",
    # external_nav.py L653/L340:--status-topic 默认 "/mavlink_external_nav/status",
    # create_publisher(String, ...)
    "/mavlink_external_nav/status": "std_msgs/msg/String",
}
# readiness 连续 topic:负责人裁决(2026-07-20,WP304 §11.7)= /mavlink_external_nav/status
# (已实证 std_msgs/String,external_nav.py L340/653)。extnav=已实证 /external_nav/status。
ROS_SUBSCRIBE_TOPICS = {"readiness": "/mavlink_external_nav/status",
                        "extnav": "/external_nav/status"}


class ConcreteRosSubscribeAdapter:
    """真实 rclpy 只订不发适配层(lazy import;仅 --backend real 构造)。
    只创建 subscription;callback 只写内部队列(不保留可写 node 引用);
    有界 spin;shutdown 幂等。rclpy 不可用 → RosAdapterUnavailable
    (调用方标 readiness/extnav INCOMPLETE,producer 不受影响)。"""

    def __init__(self, ros_domain_id, system_domain_id, topics=None, node_factory=None,
                 msg_type="std_msgs/msg/String"):
        if ros_domain_id is None or str(ros_domain_id).strip() == "":
            raise RosAdapterUnavailable("sidecar ROS domain 未配置(禁止静默 domain 0)")
        if system_domain_id is None or str(system_domain_id).strip() == "":
            raise RosAdapterUnavailable("被测系统 ROS domain 未知(fail-closed)")
        if str(ros_domain_id) != str(system_domain_id):
            raise RosWriteRefused(
                f"必须与被测系统同一 ROS_DOMAIN_ID(自 {ros_domain_id} ≠ 被测 {system_domain_id})")
        self._topics = dict(topics or ROS_SUBSCRIBE_TOPICS)
        for key, topic in self._topics.items():
            if not topic:
                raise RosAdapterUnavailable(
                    f"{key} 订阅 topic 未配置(须 A/A runbook 裁决后显式传入)")
            auth = AUTHORITATIVE_TOPIC_TYPES.get(topic)
            if auth is None:
                raise RosAdapterUnavailable(
                    f"{key} topic {topic} 的消息类型未经 wm 源码验证(fail-closed)")
            if auth != msg_type:
                raise RosWriteRefused(
                    f"{key} topic {topic} 类型不符:权威={auth} 配置={msg_type}")
        self._msg_type = msg_type
        self._q = _queue.Queue()
        self._shut = False
        factory = node_factory or self._default_factory
        self._node, self._spin_once, self._do_shutdown = factory()
        q = self._q          # callback 闭包只捕获队列,不捕获 self/node

        def make_cb(key):
            def _cb(msg):
                if not self._shut:
                    q.put((key, getattr(msg, "data", msg),
                           time.time_ns(), time.monotonic_ns()))
            return _cb
        for key, topic in self._topics.items():
            self._node.create_subscription(self._msg_type, topic, make_cb(key), 10)

    @staticmethod
    def _default_factory():
        try:
            import rclpy
            from rclpy.node import Node  # noqa: F401
            from std_msgs.msg import String  # noqa: F401
        except Exception as e:
            raise RosAdapterUnavailable(f"rclpy 不可用: {e}") from e
        rclpy.init()
        node = rclpy.create_node("wp304_telemetry_subonly")

        def spin_once(timeout_sec):
            rclpy.spin_once(node, timeout_sec=timeout_sec)

        def shutdown():
            try:
                node.destroy_node()
            finally:
                rclpy.shutdown()
        return node, spin_once, shutdown

    def spin_bounded(self, duration_sec, should_stop):
        end = time.monotonic() + duration_sec
        while time.monotonic() < end and not should_stop() and not self._shut:
            self._spin_once(0.05)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except _queue.Empty:
                return out

    def shutdown(self):
        if self._shut:
            return
        self._shut = True
        try:
            self._do_shutdown()
        except Exception:
            pass


OFFICIAL_BASELINE_LOGICAL = "official_baseline"


def resolve_container_identity(run_dir, run_id=None, logical_service=OFFICIAL_BASELINE_LOGICAL):
    """AA-PF-02:容器身份权威解析(禁 docker ps/前缀/唯一容器假设/全局字符串)。
    权威来源=本 run 的 summary.json service_handles(收官落盘→仅 post-run 可得;
    live 模式无上游预启动 handle 产物 → UNAVAILABLE,须上游契约,见 WP304 §11.3)。
    绑定:run_dir 基名==run_id;handle.service_name==logical;唯一;记录来源 sha256。"""
    rid = os.path.basename(os.path.normpath(run_dir))
    if run_id is not None and run_id != rid:
        return {"status": "CORRUPT", "reason": f"run_id 不绑:{run_id}!={rid}"}
    # live 权威来源(上游契约,wm service.started 原子发布):优先消费
    lp = os.path.join(run_dir, "runtime", "service_handles.json")
    if os.path.exists(lp):
        try:
            raw = open(lp, "rb").read()
            doc = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError) as e:
            return {"status": "CORRUPT", "reason": f"service_handles.json 不可解析: {e}"}
        if doc.get("schema_version") != "navlab.runtime.service_handles.v1":
            return {"status": "CORRUPT",
                    "reason": f"service_handles schema 未知: {doc.get('schema_version')!r}"}
        if doc.get("run_id") != rid:
            return {"status": "CORRUPT",
                    "reason": f"service_handles run_id 不绑: {doc.get('run_id')!r}!={rid}"}
        cands = [h for h in (doc.get("handles") or [])
                 if h.get("service_name") == logical_service]
        if not cands:
            return {"status": "UNAVAILABLE",
                    "reason": f"service_handles 尚无 {logical_service}(服务未启动)"}
        if len(cands) > 1:
            return {"status": "AMBIGUOUS", "reason": f"service_handles 多候选={len(cands)}"}
        h = cands[0]
        name = (h.get("container_name") or "").strip()
        if not name:
            return {"status": "CORRUPT", "reason": "service_handles.container_name 为空"}
        return {"status": "RESOLVED", "logical_service": logical_service,
                "runtime_container_name": name,
                "identifier": (h.get("identifier") or "UNAVAILABLE"),
                "container_id": (h.get("container_id") or "UNAVAILABLE"),
                "identifier_matches_name": None,
                "source_artifact": "runtime/service_handles.json",
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "run_id_bound": rid, "live_capable": True,
                "fixture_test_only": False}
    sp = os.path.join(run_dir, "summary.json")
    if not os.path.exists(sp):
        return {"status": "UNAVAILABLE",
                "reason": "无 runtime/service_handles.json 且无 summary.json"
                          "(live 权威产物须上游契约版本 wm≥9a1ce95)"}
    try:
        raw = open(sp, "rb").read()
        sj = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as e:
        return {"status": "CORRUPT", "reason": f"summary.json 不可解析: {e}"}
    handles = []

    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("service_name") == logical_service and "container_name" in obj:
                handles.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)
    walk(sj)
    # 去重(同一 handle 序列化多处出现时按内容折叠)
    uniq = {json.dumps(h, sort_keys=True) for h in handles}
    handles = [json.loads(x) for x in sorted(uniq)]
    if not handles:
        return {"status": "UNAVAILABLE",
                "reason": f"summary 无 {logical_service} runtime handle(只有逻辑名不算身份)"}
    if len(handles) > 1:
        return {"status": "AMBIGUOUS", "reason": f"多候选 handle={len(handles)}"}
    h = handles[0]
    name = (h.get("container_name") or "").strip()
    ident = (h.get("identifier") or "").strip()
    if not name:
        return {"status": "CORRUPT", "reason": "handle.container_name 为空"}
    return {"status": "RESOLVED",
            "logical_service": logical_service,
            "runtime_container_name": name,
            "identifier": ident or "UNAVAILABLE",
            "identifier_matches_name": (ident == name) if ident else None,
            "source_artifact": "summary.json",
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "run_id_bound": rid,
            "fixture_test_only": False}


def verify_container_identity_source(run_dir, recorded):
    """来源防篡改:重算 summary.json sha256 与记录比对。"""
    try:
        raw = open(os.path.join(run_dir, recorded.get("source_artifact", "summary.json")),
                   "rb").read()
    except OSError:
        return False
    return hashlib.sha256(raw).hexdigest() == recorded.get("source_sha256")


class RealBackend:
    """real 数据源(--backend real 才构造;本轮任何测试/dry-run 不得使用/未实测)。"""

    def __init__(self, container=None, ros_domain_id=None, system_ros_domain_id=None,
                 ros_topics=None):
        self._container = container   # real 模式禁默认名:须经权威解析注入(set_container)
        self._ros_domain = ros_domain_id            # sidecar 域(--ros-domain-id)
        self._system_ros_domain = system_ros_domain_id   # 被测系统域(独立来源)
        self._ros_topics = ros_topics
        self._ros_adapter = None

    def read_file(self, path):
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def host_interval_sec(self):
        return 1.0

    def git(self, *args):
        import subprocess
        return subprocess.run(["git", "-C", os.environ.get("WM", "/home/ai4s/projects/world-model"),
                               *args], capture_output=True, text=True, check=True).stdout

    def image_inspect(self, ref):
        import subprocess
        out = subprocess.run(["docker", "image", "inspect", "--format",
                              "{{index .RepoDigests 0}}", ref],
                             capture_output=True, text=True)
        return {"tag": ref, "digest": out.stdout.strip() if out.returncode == 0 else "UNAVAILABLE"}

    def image_refs(self):
        return []

    def config_hash(self):
        return "UNAVAILABLE"

    def set_container(self, name):
        self._container = name

    def container_name(self):
        if not self._container:
            raise TelemetryWriteError(
                "real backend 容器身份未注入(禁默认名/禁 docker ps 猜测;须权威解析)")
        return self._container

    def docker_inspect(self, name):
        import subprocess
        out = subprocess.run(["docker", "inspect", name], capture_output=True, text=True)
        try:
            return json.loads(out.stdout or "[]")
        except ValueError:
            return {"error": "inspect 不可解析"}

    def docker_top(self, name):
        import subprocess
        out = subprocess.run(["docker", "top", name], capture_output=True, text=True)
        return {"raw": out.stdout}

    def logs_follow(self, name, should_stop):
        import subprocess
        proc = subprocess.Popen(["docker", "logs", "--follow", name],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            while not should_stop():
                line = proc.stdout.readline()
                if not line:
                    return
                yield line
        finally:
            proc.terminate()

    def wait_blocking(self, name, should_stop):
        import subprocess
        proc = subprocess.Popen(["docker", "wait", name], stdout=subprocess.PIPE, text=True)
        while proc.poll() is None:
            if should_stop():
                proc.terminate()
                return None
            time.sleep(0.05)
        out = (proc.stdout.read() or "").strip()
        return int(out) if out.isdigit() else None

    def ros_stream(self, key, should_stop):
        if self._ros_adapter is None:
            # 双域独立来源(CLI 显式传入;缺任一 → fail-closed,不读 env 双充、不默认 0)
            self._ros_adapter = ConcreteRosSubscribeAdapter(
                ros_domain_id=self._ros_domain,
                system_domain_id=self._system_ros_domain,
                topics=self._ros_topics)
        ad = self._ros_adapter
        while not should_stop():
            ad.spin_bounded(0.2, should_stop)
            for k, data, _utc, _mono in ad.drain():
                if k == key:
                    yield data

    def force_rc(self):
        return None


def _now_pair():
    return time.time_ns(), time.monotonic_ns()


def _self_identity(batch_id, run_id):
    pid = os.getpid()
    try:
        data = open(f"/proc/{pid}/stat").read()
        st = data[data.rfind(")") + 2:].split()[19]
    except OSError:
        st = "UNKNOWN"
    return {"batch_id": batch_id, "run_id": run_id, "pid": pid,
            "pid_starttime": st, "boot_id": _current_boot_id()}


def _rec(cfg, run_id, field, value, post_run=False):
    utc, mono = _now_pair()
    r = {"schema_version": C.SCHEMA_VERSION, "batch_id": cfg["batch_id"],
         "run_id": run_id, "utc_ns": utc, "mono_ns": mono,
         "field": field, "value": value}
    if post_run:
        r["post_run_derived"] = True
    return r


def _new_collector(requirement):
    return {"started": None, "first_sample_mono_ns": None, "last_sample_mono_ns": None,
            "records": 0, "dropped": 0, "truncated": False,
            "error_state": None, "stopped": None, "requirement": requirement,
            "evidence_effect": ("INCOMPLETE" if requirement == "required" else "UNAVAILABLE")}


def _process_attempt(cfg, backend, entry, live, batch_final):
    """单 attempt 状态机:RESOLVED→ACTIVE(连续采集+周期封存)→FINISHING→run final。
    live=False(启动时已 FINISHED)→ 事后一次性快照,全记录标 post_run_derived。"""
    run_id = entry["world_model_run_id"]
    run_dir = entry["world_model_run_dir"]
    if os.path.basename(os.path.normpath(run_dir)) != run_id:
        raise TelemetryWriteError(f"run_dir 基名≠run_id: {run_dir}")
    wm_root = os.path.realpath(cfg["world_model_root"])
    if not os.path.realpath(run_dir).startswith(wm_root + os.sep):
        raise TelemetryWriteError(f"run_dir 越出 world-model 根: {run_dir}")
    os.makedirs(os.path.join(run_dir, "telemetry"), exist_ok=True)
    tdir = os.path.join(run_dir, "telemetry")
    store = SegmentStore(tdir, run_root=run_dir,
                         identity=_self_identity(cfg["batch_id"], run_id))
    gov = CapacityGovernor()
    recq = _queue.Queue()
    stop_local = _threading.Event()
    finished_evt = _threading.Event()
    collectors = {name: _new_collector("required")
                  for name in ("host", "sitl_proc", "sitl_console",
                               "container_exit", "readiness", "extnav")}
    console_chunks = []
    console_lock = _threading.Lock()
    wait_result = {"code": None, "post_run": False}
    # AA-PF-02:容器身份判定(fixture=测试注入显式标记;real=本 run 权威产物解析)
    if isinstance(backend, FixtureBackend):
        try:
            cident = {"status": "RESOLVED",
                      "runtime_container_name": backend.container_name(),
                      "logical_service": OFFICIAL_BASELINE_LOGICAL,
                      "source_artifact": "fixture_input",
                      "fixture_test_only": True}
        except TelemetryWriteError as e:
            cident = {"status": "UNAVAILABLE", "reason": str(e), "fixture_test_only": True}
    else:
        cident = resolve_container_identity(run_dir, run_id)
        if cident.get("status") == "RESOLVED":
            if cident.get("identifier_matches_name") is False:
                cident = {"status": "UNKNOWN",
                          "reason": f"identifier≠container_name({cident['identifier']}"
                                    f"≠{cident['runtime_container_name']}),不可信",
                          **{k: v for k, v in cident.items() if k != "status"}}
            else:
                backend.set_container(cident["runtime_container_name"])
    cident["batch_id"] = cfg["batch_id"]
    cident["run_index"] = entry.get("run_index")
    container_ok = cident.get("status") == "RESOLVED"
    cname = cident.get("runtime_container_name") if container_ok else None
    if not container_ok:
        for nm in ("sitl_proc", "sitl_console", "container_exit"):
            collectors[nm]["error_state"] = f"容器身份不可信/不可得: {cident.get('reason', cident.get('status'))}"

    def should_stop():
        return stop_local.is_set()

    def guard(name, fn):
        collectors[name]["started"] = time.monotonic_ns()
        try:
            fn()
        except Exception as e:
            collectors[name]["error_state"] = f"{type(e).__name__}: {e}"
        finally:
            collectors[name]["stopped"] = time.monotonic_ns()

    def host_loop():
        interval = cfg.get("host_interval_sec") or backend.host_interval_sec()
        prev = None
        while not stop_local.is_set() and not finished_evt.is_set():
            try:
                la = parse_loadavg(backend.read_file("/proc/loadavg"))
            except OSError:
                la = C.UNAVAILABLE
            try:
                cur = parse_proc_stat(backend.read_file("/proc/stat"))
            except OSError:
                cur = C.UNAVAILABLE
            pct = cpu_pct(prev, cur) if prev is not None else None
            prev = cur
            try:
                mem = parse_meminfo(backend.read_file("/proc/meminfo"))
            except OSError:
                mem = C.UNAVAILABLE
            freq = read_cpu_freq(backend.read_file)
            recq.put(("host", _rec(cfg, run_id, "host.loadavg", la)))
            if pct is not None:
                recq.put(("host", _rec(cfg, run_id, "host.cpu_pct", pct)))
            recq.put(("host", _rec(cfg, run_id, "host.mem", mem)))
            recq.put(("host", _rec(cfg, run_id, "host.cpu_freq", freq)))
            if not _interruptible_sleep(interval, stop_local, finished_evt):
                return

    def top_loop():
        interval = (cfg.get("host_interval_sec") or backend.host_interval_sec())
        while not stop_local.is_set() and not finished_evt.is_set():
            recq.put(("sitl_proc", _rec(cfg, run_id, "sitl.proc", backend.docker_top(cname))))
            if not _interruptible_sleep(interval, stop_local, finished_evt):
                return

    def logs_loop():
        for chunk in backend.logs_follow(cname, should_stop):
            data = chunk.encode("utf-8")
            if gov.admit("telemetry/sitl_console.log", len(data)):
                with console_lock:
                    console_chunks.append(chunk)
                collectors["sitl_console"]["records"] += 1
                collectors["sitl_console"]["last_sample_mono_ns"] = time.monotonic_ns()
                if collectors["sitl_console"]["first_sample_mono_ns"] is None:
                    collectors["sitl_console"]["first_sample_mono_ns"] = \
                        collectors["sitl_console"]["last_sample_mono_ns"]
            else:
                collectors["sitl_console"]["dropped"] += 1
                collectors["sitl_console"]["truncated"] = True

    def wait_loop():
        code = backend.wait_blocking(cname, should_stop)
        if code is not None:
            wait_result["code"] = code
            wait_result["post_run"] = finished_evt.is_set()
            collectors["container_exit"]["records"] += 1
            collectors["container_exit"]["last_sample_mono_ns"] = time.monotonic_ns()
            if collectors["container_exit"]["first_sample_mono_ns"] is None:
                collectors["container_exit"]["first_sample_mono_ns"] = \
                    collectors["container_exit"]["last_sample_mono_ns"]

    def ros_loop(key):
        def _run():
            for msg in backend.ros_stream(key, should_stop):
                recq.put((key, _rec(cfg, run_id, key, msg)))
        return _run

    threads = []
    if live:
        specs = [("host", host_loop),
                 ("readiness", ros_loop("readiness")), ("extnav", ros_loop("extnav"))]
        if container_ok:
            specs += [("sitl_proc", top_loop), ("sitl_console", logs_loop),
                      ("container_exit", wait_loop)]
        for name, fn in specs:
            t = _threading.Thread(target=guard, args=(name, fn), daemon=True)
            t.start()
            threads.append(t)
    else:
        # 事后模式:一次性快照,全部 post_run_derived
        try:
            la = parse_loadavg(backend.read_file("/proc/loadavg"))
        except OSError:
            la = C.UNAVAILABLE
        recq.put(("host", _rec(cfg, run_id, "host.loadavg", la, post_run=True)))
        try:
            mem = parse_meminfo(backend.read_file("/proc/meminfo"))
        except OSError:
            mem = C.UNAVAILABLE
        recq.put(("host", _rec(cfg, run_id, "host.mem", mem, post_run=True)))
        recq.put(("host", _rec(cfg, run_id, "host.cpu_freq",
                               read_cpu_freq(backend.read_file), post_run=True)))
        if container_ok:
            recq.put(("sitl_proc", _rec(cfg, run_id, "sitl.proc",
                                        backend.docker_top(cname), post_run=True)))
            try:
                for chunk in backend.logs_follow(cname, lambda: False):
                    if gov.admit("telemetry/sitl_console.log", len(chunk.encode("utf-8"))):
                        console_chunks.append(chunk)
                        collectors["sitl_console"]["records"] += 1
            except OSError:
                collectors["sitl_console"]["error_state"] = "console 不可得"
            code = backend.wait_blocking(cname, lambda: False)
            if code is not None:
                wait_result["code"] = code
                wait_result["post_run"] = True
        for key in ("readiness", "extnav"):
            try:
                for msg in backend.ros_stream(key, lambda: False):
                    recq.put((key, _rec(cfg, run_id, key, msg, post_run=True)))
            except (RosAdapterUnavailable, RosWriteRefused, OSError) as e:
                collectors[key]["error_state"] = f"{type(e).__name__}: {e}"
        finished_evt.set()

    # ---- ACTIVE:连续 drain + 周期封存(flush_interval / record limit 先到先封) ----
    field_counts = {}
    dropped_counts = {}
    seg_limit = int(cfg.get("segment_record_limit", 1000))
    flush = float(cfg.get("flush_interval", 1.0))
    last_seal = time.monotonic()
    stop_reported = None
    reg_poll = 0.0

    def drain_once(post_run_flag=False):
        n = 0
        while True:
            try:
                name, r = recq.get_nowait()
            except _queue.Empty:
                return n
            if post_run_flag and not r.get("post_run_derived"):
                r["post_run_derived"] = True
            rel = C.FIELD_CONTRACTS.get(r["field"], {}).get("artifact_rel", "telemetry/host.jsonl")
            payload = len(json.dumps(r)) + 1
            if not gov.admit(rel, payload):
                dropped_counts[rel] = dropped_counts.get(rel, 0) + 1
                if name in collectors:
                    collectors[name]["dropped"] += 1
                    collectors[name]["truncated"] = True
                continue
            store.append(r)
            field_counts[r["field"]] = field_counts.get(r["field"], 0) + 1
            if name in collectors:
                c = collectors[name]
                c["records"] += 1
                c["last_sample_mono_ns"] = r["mono_ns"]
                if c["first_sample_mono_ns"] is None:
                    c["first_sample_mono_ns"] = r["mono_ns"]
            n += 1

    while True:
        drain_once()
        now = time.monotonic()
        if store._buf and (len(store._buf) >= seg_limit or (now - last_seal) >= flush):
            store.seal()
            last_seal = now
        if finished_evt.is_set():
            break
        if cfg["_stop"].is_set():
            stop_reported = "signal"
            break
        if now - reg_poll >= 0.05:
            reg_poll = now
            try:
                cur = json.load(open(os.path.join(
                    cfg["run_registry"], f"attempt_{entry['run_index']}.json"),
                    encoding="utf-8"))
                if cur.get("phase") == "finished":
                    entry = cur
                    finished_evt.set()
                    break
            except (OSError, ValueError):
                pass
        time.sleep(0.02)

    # ---- FINISHING ----
    finished_evt.set()
    stop_local.set()
    for t in threads:
        t.join(timeout=1.0)
    drain_once(post_run_flag=True)   # 结束后到达的记录 → post_run_derived
    if store._buf:
        store.seal()
    # 指针/单文件 artifact
    for rel in ("telemetry/host.jsonl", "telemetry/sitl_proc.jsonl",
                "telemetry/readiness.jsonl", "telemetry/extnav.jsonl"):
        fields = {f: n for f, n in field_counts.items()
                  if C.FIELD_CONTRACTS.get(f, {}).get("artifact_rel") == rel}
        if not fields and rel != "telemetry/host.jsonl":
            fields = {}
        atomic_write(os.path.join(run_dir, rel),
                     json.dumps({"schema_version": C.SCHEMA_VERSION,
                                 "segments_prefix": "segment",
                                 "field_records": fields,
                                 "dropped_records": dropped_counts.get(rel, 0)},
                                sort_keys=True).encode("utf-8"),
                     run_root=run_dir, overwrite=True)
    with console_lock:
        console = "".join(console_chunks)
    if console_chunks or (container_ok and collectors["sitl_console"]["error_state"] is None):
        atomic_write(os.path.join(run_dir, "telemetry", "sitl_console.log"),
                     console.encode("utf-8"), run_root=run_dir, overwrite=True)
    if container_ok:
        exit_fields = container_exit_fields(wait_result["code"]) if wait_result["code"] is not None \
            else {"official_baseline_container_exit_code": C.UNAVAILABLE,
                  "sitl_process_exit_code": C.UNAVAILABLE}
        exit_fields["post_run_derived"] = bool(wait_result["post_run"])
        atomic_write(os.path.join(run_dir, "telemetry", "official_baseline_container_exit.json"),
                     json.dumps(exit_fields, sort_keys=True).encode("utf-8"),
                     run_root=run_dir, overwrite=True)
    fz = collect_freeze(git_runner=backend.git, image_inspect=backend.image_inspect,
                        config_hash=backend.config_hash(), batch_id=cfg["batch_id"],
                        run_id=run_id, image_refs=backend.image_refs())
    atomic_write(os.path.join(run_dir, "telemetry", "freeze.json"),
                 json.dumps(fz, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                 run_root=run_dir, overwrite=True)
    # required 闭包 → evidence gate → run final(只在 FINISHED 之后)
    statuses, business_ok, biz = evaluate_run_evidence(run_dir)
    for name in ("readiness", "extnav", "host", "sitl_proc"):
        if collectors[name]["error_state"] and collectors[name]["records"] == 0:
            field = {"host": "host.loadavg", "sitl_proc": "sitl.proc",
                     "readiness": "readiness", "extnav": "extnav"}[name]
            statuses[field] = "MISSING"
    gate = C.evidence_gate(statuses, business_ok=business_ok)
    run_final = {"schema_version": C.SCHEMA_VERSION, "batch_id": cfg["batch_id"],
                 "run_ids_processed": [run_id], "process_rc": 0,
                 "evidence_state": gate["status"], "finalization_state": "WRITTEN",
                 "failure_reasons": [x for x in [stop_reported] if x],
                 "business_outcome": biz, "evidence_gate": gate,
                 "live_mode": bool(live),
                 "attempt_window_monotonic": {"start": entry.get("start_monotonic"),
                                              "end": entry.get("end_monotonic")},
                 "collectors": collectors,
                 "truncated": dict(gov.truncated),
                 "dropped_records": dropped_counts,
                 "telemetry_overrun": False,
                 "ros_domains": cfg.get("ros_domains"),
                 "container_identity": cident,
                 "finalized_monotonic_ns": time.monotonic_ns()}
    atomic_write(os.path.join(run_dir, "telemetry", "sidecar_final_status.json"),
                 json.dumps(run_final, ensure_ascii=False, sort_keys=True,
                            indent=1).encode("utf-8"),
                 run_root=run_dir, overwrite=True)
    store.close()
    return run_final


def run_sidecar(cfg, backend):
    """状态机驱动的唯一主循环(fixture/real 同编排)。
    --once = 完整处理一个 attempt(等待 PENDING→RESOLVED→FINISHED)后退出;
    --expected-runs N = 依次完整处理 N 个 attempt。"""
    import run_registry as RR
    art_root = cfg["artifact_root"]
    stop = _threading.Event()
    cfg["_stop"] = stop
    import signal as _signal
    _signal.signal(_signal.SIGTERM, lambda *_: stop.set())
    _signal.signal(_signal.SIGINT, lambda *_: stop.set())
    order = {"COMPLETE": 0, "INCOMPLETE": 1, "CORRUPT": 2}
    final = {"schema_version": C.SCHEMA_VERSION, "batch_id": cfg["batch_id"],
             "run_ids_processed": [], "process_rc": None, "evidence_state": "UNKNOWN",
             "finalization_state": "MISSING", "failure_reasons": [],
             "attempts": [], "truncated": {}, "dropped_records": {},
             "telemetry_overrun": False, "business_outcome": "UNKNOWN",
             "evidence_gate": None}

    def write_batch_final(rc):
        final["process_rc"] = rc
        final["finalization_state"] = "WRITTEN"
        os.makedirs(os.path.join(art_root, "telemetry"), exist_ok=True)
        atomic_write(os.path.join(art_root, "telemetry", "sidecar_final_status.json"),
                     json.dumps(final, ensure_ascii=False, sort_keys=True,
                                indent=1).encode("utf-8"),
                     run_root=art_root, overwrite=True)

    worst = None

    def upd(state):
        nonlocal worst
        if worst is None or order.get(state, 1) > order.get(worst, 0):
            worst = state

    try:
        expected = int(cfg["expected_runs"])
        processed = set()
        for _slot in range(expected):
            # ---- WAIT_IDENTITY:等待(而非只查一次)下一 attempt 达到终态身份 ----
            deadline = time.monotonic() + float(cfg.get("registry_wait_sec", 5.0))
            picked = None
            dir_missing = False
            while True:
                reg = RR.load_registry(cfg["run_registry"], cfg["batch_id"])
                if reg["errors"]:
                    only_missing = all("registry 目录不存在" in x for x in reg["errors"])
                    if only_missing:
                        # 入口时序:launcher 先起 sidecar,bc_run 稍后才 begin——
                        # 目录未建=继续等待,不是硬错(超时才 INCOMPLETE)
                        dir_missing = True
                        reg = {"entries": [], "errors": []}
                    else:
                        final["failure_reasons"] += reg["errors"]
                        final["evidence_state"] = "INCOMPLETE"
                        upd("INCOMPLETE")
                        write_batch_final(3)
                        return 3
                cand = [e for e in reg["entries"] if e["run_index"] not in processed]
                terminal = [e for e in cand
                            if e.get("identity_status") in ("RESOLVED", "UNKNOWN")]
                if terminal:
                    picked = sorted(terminal, key=lambda e: e["run_index"])[0]
                    break
                if stop.is_set():
                    final["failure_reasons"].append("signal during WAIT_IDENTITY")
                    final["evidence_state"] = "INCOMPLETE"
                    upd("INCOMPLETE")
                    write_batch_final(0)
                    return 0
                if time.monotonic() >= deadline:
                    final["failure_reasons"].append(
                        ("registry 目录不存在(等待窗口内未出现)" if dir_missing else
                         f"registry 等待超时(仍 PENDING/无条目,attempt slot={_slot + 1})"))
                    final["evidence_state"] = "INCOMPLETE"
                    upd("INCOMPLETE")
                    write_batch_final(4)
                    return 4
                time.sleep(0.05)
            processed.add(picked["run_index"])
            if picked.get("identity_status") == "UNKNOWN":
                # 身份 UNKNOWN:不建 per-run writer,登记 INCOMPLETE
                final["attempts"].append({"run_index": picked["run_index"],
                                          "state": "INCOMPLETE",
                                          "reason": f"identity UNKNOWN({picked.get('discovery_method')})"})
                final["failure_reasons"].append(
                    f"attempt {picked['run_index']} identity UNKNOWN,未启动 writer")
                upd("INCOMPLETE")
                continue
            live = picked.get("phase") != "finished"
            run_final = _process_attempt(cfg, backend, picked, live, final)
            final["run_ids_processed"] += run_final["run_ids_processed"]
            final["attempts"].append({"run_index": picked["run_index"],
                                      "state": run_final["evidence_state"],
                                      "run_id": run_final["run_ids_processed"][0],
                                      "live_mode": run_final["live_mode"]})
            final["business_outcome"] = run_final["business_outcome"]
            final["evidence_gate"] = run_final["evidence_gate"]
            for k, v in run_final["truncated"].items():
                final["truncated"][k] = v
            for k, v in run_final["dropped_records"].items():
                final["dropped_records"][k] = final["dropped_records"].get(k, 0) + v
            upd(run_final["evidence_state"])
        final["evidence_state"] = worst or "INCOMPLETE"
        rc = 0
        force = getattr(backend, "force_rc", None)
        if callable(force):
            fr = force()
            if fr is not None:
                rc = int(fr)
                final["failure_reasons"].append(
                    f"fixture force_rc={fr}(进程失败与证据状态并存)")
        write_batch_final(rc)
        return rc
    except TelemetryOverrun as e:
        final["telemetry_overrun"] = True
        final["evidence_state"] = "CORRUPT"
        final["failure_reasons"].append(str(e))
        write_batch_final(7)
        return 7
    except TelemetryWriteError as e:
        final["evidence_state"] = "CORRUPT" if final["run_ids_processed"] else "INCOMPLETE"
        final["failure_reasons"].append(str(e))
        write_batch_final(5)
        return 5
    except Exception as e:
        final["failure_reasons"].append(f"{type(e).__name__}: {e}")
        final["evidence_state"] = "INCOMPLETE"
        try:
            write_batch_final(6)
        except Exception:
            pass
        return 6
    finally:
        final["evidence_state"] = final.get("evidence_state") or (worst or "UNKNOWN")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="telemetry_sidecar",
        description="WP304 E1 纯旁路 telemetry sidecar(运行期状态机;fixture/real 同一主循环)")
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--run-registry", required=True)
    ap.add_argument("--world-model-root", required=True)
    ap.add_argument("--backend", required=True, choices=["real", "fixture"])
    ap.add_argument("--fixture-input", default=None)
    ap.add_argument("--ros-domain-id", default=None,
                    help="sidecar 自身 ROS domain(real backend 必填)")
    ap.add_argument("--system-ros-domain-id", default=None,
                    help="被测系统 ROS domain(独立来源,real backend 必填)")
    ap.add_argument("--ros-readiness-topic", default="/mavlink_external_nav/status",
                    help="readiness 订阅 topic(负责人裁决 2026-07-20,§11.7)")
    ap.add_argument("--ros-extnav-topic", default="/external_nav/status")
    ap.add_argument("--segment-record-limit", type=int, default=1000)
    ap.add_argument("--flush-interval", type=float, default=1.0)
    ap.add_argument("--host-interval-sec", type=float, default=None)
    ap.add_argument("--registry-wait-sec", type=float, default=5.0)
    ap.add_argument("--once", action="store_true",
                    help="完整处理一个 attempt(等待 PENDING→RESOLVED→FINISHED)后退出")
    ap.add_argument("--expected-runs", type=int, default=None,
                    help="依次完整处理 N 个 attempt(WP303 默认命令使用本模式)")
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args(argv)
    if a.expected_runs is None and not a.once and not a.validate_only:
        ap.error("必须指定 --once 或 --expected-runs N")
    expected = a.expected_runs if a.expected_runs is not None else 1
    cfg = {"artifact_root": a.artifact_root, "batch_id": a.batch_id,
           "run_registry": a.run_registry, "world_model_root": a.world_model_root,
           "expected_runs": expected, "registry_wait_sec": a.registry_wait_sec,
           "segment_record_limit": a.segment_record_limit,
           "flush_interval": a.flush_interval, "host_interval_sec": a.host_interval_sec,
           "ros_domain_id": a.ros_domain_id,
           "system_ros_domain_id": a.system_ros_domain_id,
           "ros_domains": {"sidecar_domain": a.ros_domain_id,
                            "sidecar_domain_source": ("cli_arg" if a.ros_domain_id else "unset"),
                            "system_domain": a.system_ros_domain_id,
                            "system_domain_source": ("cli_arg" if a.system_ros_domain_id else "unset"),
                            "fixture_test_only": a.backend == "fixture"}}
    if a.backend == "fixture":
        if not a.fixture_input:
            ap.error("--backend fixture 需要 --fixture-input")
        backend = FixtureBackend(a.fixture_input)
    else:
        backend = RealBackend(container=None, ros_domain_id=a.ros_domain_id,
                              system_ros_domain_id=a.system_ros_domain_id,
                              ros_topics={"readiness": a.ros_readiness_topic,
                                          "extnav": a.ros_extnav_topic})
    if a.validate_only:
        import run_registry as RR
        reg = RR.load_registry(a.run_registry, a.batch_id)
        print(json.dumps({"validate_only": True, "backend": a.backend,
                          "registry_entries": len(reg["entries"]),
                          "registry_errors": reg["errors"]}, ensure_ascii=False))
        return 0 if not reg["errors"] else 1
    return run_sidecar(cfg, backend)


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
