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


# ---------- 不可变 JSONL 段 + index(E1-02.2/02.3) ----------
class SegmentStore:
    """段式 JSONL 证据仓:当前段只在内存;seal() 才落盘为不可变段并登记 index。
    单 writer 互斥:writer.lock 记录身份;身份不符即拒(红案19)。"""

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
        self._lock_path = os.path.join(dir_path, "writer.lock")
        if os.path.exists(self._lock_path):
            try:
                prev = json.load(open(self._lock_path, encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise TelemetryWriteError(f"writer.lock 不可读: {e}") from e
            if not C.identity_matches(prev, self._ident):
                raise TelemetryWriteError(
                    f"第二 writer 被拒:锁持有者 {prev.get('pid')}/{prev.get('pid_starttime')}"
                    f" ≠ 本身份 {self._ident['pid']}/{self._ident['pid_starttime']}")
        else:
            atomic_write(self._lock_path,
                         json.dumps(self._ident, sort_keys=True).encode("utf-8"),
                         run_root=run_root)
        self._next = self._recover_next_number()

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
        p = os.path.join(dir_path, f"segment-{e.get('segment')}.jsonl")
        if not os.path.exists(p):
            reasons.append(f"index 指向不存在的段: {os.path.basename(p)}")
            continue
        data = open(p, "rb").read()
        if hashlib.sha256(data).hexdigest() != e.get("sha256"):
            reasons.append(f"段内容与 index sha256 不符: {os.path.basename(p)}")
            continue
        segments.append(e)
    # 未登记的正式段文件 = writer 序列被绕过 → CORRUPT
    on_disk = {f for f in os.listdir(dir_path)
               if f.startswith("segment-") and f.endswith(".jsonl")}
    listed = {f"segment-{e.get('segment')}.jsonl" for e in idx.get("segments", [])}
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
