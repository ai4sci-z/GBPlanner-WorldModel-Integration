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
# E1C-02 · 正式可执行 sidecar:CLI + 单一主循环(fixture/real 同编排,只换数据源)
# ============================================================================
REQUIRED_ARTIFACTS = (
    "telemetry/host.jsonl",
    "telemetry/sitl_proc.jsonl",
    "telemetry/sitl_console.log",
    "telemetry/official_baseline_container_exit.json",
    "telemetry/readiness.jsonl",
    "telemetry/extnav.jsonl",
    "telemetry/freeze.json",
)


class FixtureBackend:
    """fixture 数据源:与 real 走同一主循环,只替换 I/O。输入=JSON 文件:
    {"proc": {path: [text,...]}, "docker": {...}, "ros": {"readiness": [...], "extnav": [...]},
     "git": {...}, "images": [...], "config_hash": "...", "container": "name",
     "host_samples": N}"""

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

    def host_sample_count(self):
        return int(self.data.get("host_samples", 2))

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

    def docker_backend(self):
        d = self.data.get("docker", {})

        class _B:
            def inspect(self, name, _d=d):
                return _d.get("inspect", {})

            def top(self, name, _d=d):
                return _d.get("top", {"Processes": []})

            def logs(self, name, tail=None, _d=d):
                if _d.get("omit_console"):
                    raise OSError("fixture: console 不可得")
                return _d.get("logs", "")

            def wait(self, name, _d=d):
                return int(_d.get("wait", 0))
        return _B()

    def container_name(self):
        return self.data.get("container", "official_baseline")

    def ros_messages(self, topic_key):
        return self.data.get("ros", {}).get(topic_key, [])

    def force_rc(self):
        return self.data.get("force_rc")


class RealBackend:
    """real 数据源(--backend real 才构造;本轮任何测试/dry-run 不得使用)。
    Docker 经只读 CLI(inspect/top/logs/wait);ROS 经 rclpy 只订不发。"""

    def __init__(self, container, ros_domain_id):
        self._container = container
        self._ros_domain = ros_domain_id

    def read_file(self, path):
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def host_sample_count(self):
        return 2

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

    def docker_backend(self):
        import subprocess

        class _B:
            def __init__(self, name):
                self._n = name

            def inspect(self, name):
                return json.loads(subprocess.run(["docker", "inspect", name],
                                                 capture_output=True, text=True).stdout or "[]")

            def top(self, name):
                out = subprocess.run(["docker", "top", name], capture_output=True, text=True)
                return {"raw": out.stdout}

            def logs(self, name, tail=None):
                cmd = ["docker", "logs"] + (["--tail", str(tail)] if tail else []) + [name]
                return subprocess.run(cmd, capture_output=True, text=True).stdout

            def wait(self, name):
                return int(subprocess.run(["docker", "wait", name],
                                          capture_output=True, text=True).stdout.strip() or 255)
        return _B(self._container)

    def container_name(self):
        return self._container

    def ros_messages(self, topic_key):
        raise TelemetryWriteError("real ROS 采集本轮禁用(A/A 未放行)")


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


def _rec(cfg, run_id, field, value):
    utc, mono = _now_pair()
    return {"schema_version": C.SCHEMA_VERSION, "batch_id": cfg["batch_id"],
            "run_id": run_id, "utc_ns": utc, "mono_ns": mono,
            "field": field, "value": value}


def _write_jsonl_records(run_dir, rel, records, cfg, run_id, gov):
    """经 SegmentStore 落一个 required jsonl(单段封存;容量入 governor)。"""
    tdir = os.path.join(run_dir, "telemetry")
    sub = rel.replace("telemetry/", "").replace(".jsonl", "")
    store = SegmentStore(tdir, run_root=run_dir, identity=_self_identity(cfg["batch_id"], run_id),
                        name=f"{sub}-segment")
    try:
        dropped = 0
        for r in records:
            payload = json.dumps(r, sort_keys=True)
            if not gov.admit(rel, len(payload) + 1):
                dropped += 1
                continue
            store.append(r)
        if store._buf:
            store.seal(truncated=bool(dropped), dropped_records=dropped)
        # 目标 rel 文件 = 段清单指针文件(正式 artifact 存在性锚点)
        atomic_write(os.path.join(run_dir, rel),
                     json.dumps({"schema_version": C.SCHEMA_VERSION,
                                 "segments_prefix": f"{sub}-segment",
                                 "records": len(records) - dropped,
                                 "dropped_records": dropped},
                                sort_keys=True).encode("utf-8"),
                     run_root=run_dir, overwrite=False)
    finally:
        store.close()
    return dropped


REQUIRED_PROBE = {"telemetry/host.jsonl": "host.loadavg",
                  "telemetry/sitl_proc.jsonl": "sitl.proc",
                  "telemetry/sitl_console.log": "sitl.console",
                  "telemetry/official_baseline_container_exit.json":
                      "official_baseline_container_exit_code",
                  "telemetry/readiness.jsonl": "readiness",
                  "telemetry/extnav.jsonl": "extnav",
                  "telemetry/freeze.json": "freeze"}


def evaluate_run_evidence(run_dir):
    """E1C-05.1 required artifact 闭包(正式入口,CLI 主循环调用):
    逐项存在性+可解析性 → PRESENT_VALID/MISSING/CORRUPT;业务结果独立读取。"""
    statuses = {}
    for rel, field in REQUIRED_PROBE.items():
        p = os.path.join(run_dir, rel)
        if not os.path.exists(p):
            statuses[field] = "MISSING"
            continue
        try:
            if rel.endswith(".log"):
                open(p, "rb").read()
            else:
                json.load(open(p, encoding="utf-8"))
            statuses[field] = "PRESENT_VALID"
        except (OSError, ValueError):
            statuses[field] = "CORRUPT"
    business_ok = False
    biz = "UNKNOWN"
    sp = os.path.join(run_dir, "summary.json")
    try:
        s = json.load(open(sp, encoding="utf-8"))
        if isinstance(s.get("ok"), bool):
            business_ok = s["ok"]
            biz = "OK" if s["ok"] else "FAILED"
    except (OSError, ValueError):
        pass
    return statuses, business_ok, biz


def run_sidecar(cfg, backend):
    """唯一主循环(fixture/real 共用):registry→run 身份→采集→原子落盘→
    evidence gate→final status。返回进程 rc。"""
    import run_registry as RR
    art_root = cfg["artifact_root"]
    final = {"schema_version": C.SCHEMA_VERSION, "batch_id": cfg["batch_id"],
             "run_ids_processed": [], "process_rc": None, "evidence_state": "UNKNOWN",
             "finalization_state": "MISSING", "failure_reasons": [],
             "truncated": {}, "dropped_records": {}, "telemetry_overrun": False,
             "business_outcome": "UNKNOWN", "evidence_gate": None}

    def write_batch_final(rc):
        final["process_rc"] = rc
        final["finalization_state"] = "WRITTEN"
        os.makedirs(os.path.join(art_root, "telemetry"), exist_ok=True)
        atomic_write(os.path.join(art_root, "telemetry", "sidecar_final_status.json"),
                     json.dumps(final, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8"),
                     run_root=art_root, overwrite=True)

    stop = {"flag": False}

    def _sig(_s, _f):
        stop["flag"] = True

    import signal as _signal
    _signal.signal(_signal.SIGTERM, _sig)
    _signal.signal(_signal.SIGINT, _sig)

    try:
        # 1) run 身份:只从 registry 取,不自行扫描"最新目录"
        deadline = time.monotonic() + float(cfg.get("registry_wait_sec", 5.0))
        entries = []
        while True:
            reg = RR.load_registry(cfg["run_registry"], cfg["batch_id"])
            if reg["errors"]:
                final["failure_reasons"] += reg["errors"]
                final["evidence_state"] = "INCOMPLETE"
                write_batch_final(3)
                return 3
            entries = [e for e in reg["entries"] if e.get("identity_status") == "RESOLVED"]
            if entries or cfg.get("once") or time.monotonic() >= deadline or stop["flag"]:
                break
            time.sleep(0.05)
        if not entries:
            final["failure_reasons"].append("registry 无 RESOLVED run(身份未握手)")
            final["evidence_state"] = "INCOMPLETE"
            write_batch_final(4)
            return 4
        gov = CapacityGovernor()
        worst = "COMPLETE"
        for e in entries:
            run_id = e["world_model_run_id"]
            run_dir = e["world_model_run_dir"]
            if os.path.basename(os.path.normpath(run_dir)) != run_id:
                raise TelemetryWriteError(f"run_dir 基名≠run_id: {run_dir}")
            wm_root = os.path.realpath(cfg["world_model_root"])
            if not os.path.realpath(run_dir).startswith(wm_root + os.sep):
                raise TelemetryWriteError(f"run_dir 越出 world-model 根: {run_dir}")
            os.makedirs(os.path.join(run_dir, "telemetry"), exist_ok=True)
            # 2) 宿主采集(collectors + governor)
            host_recs = []
            prev_stat = None
            for _ in range(backend.host_sample_count()):
                if stop["flag"]:
                    break
                try:
                    la = parse_loadavg(backend.read_file("/proc/loadavg"))
                except OSError:
                    la = C.UNAVAILABLE
                try:
                    cur = parse_proc_stat(backend.read_file("/proc/stat"))
                except OSError:
                    cur = C.UNAVAILABLE
                pct = cpu_pct(prev_stat, cur) if prev_stat is not None else None
                prev_stat = cur
                try:
                    mem = parse_meminfo(backend.read_file("/proc/meminfo"))
                except OSError:
                    mem = C.UNAVAILABLE
                freq = read_cpu_freq(backend.read_file)
                host_recs.append(_rec(cfg, run_id, "host.loadavg", la))
                if pct is not None:
                    host_recs.append(_rec(cfg, run_id, "host.cpu_pct", pct))
                host_recs.append(_rec(cfg, run_id, "host.mem", mem))
                host_recs.append(_rec(cfg, run_id, "host.cpu_freq", freq))
            d = _write_jsonl_records(run_dir, "telemetry/host.jsonl", host_recs, cfg, run_id, gov)
            if d:
                final["dropped_records"]["telemetry/host.jsonl"] = d
            # 3) docker 只读:sitl_proc / console / 容器退出码
            dk = DockerReadOnlyAdapter(backend.docker_backend())
            cname = backend.container_name()
            top = dk.top(cname)
            _write_jsonl_records(run_dir, "telemetry/sitl_proc.jsonl",
                                 [_rec(cfg, run_id, "sitl.proc", top)], cfg, run_id, gov)
            try:
                logs = dk.logs(cname)
                if gov.admit("telemetry/sitl_console.log", len(logs.encode("utf-8"))):
                    atomic_write(os.path.join(run_dir, "telemetry", "sitl_console.log"),
                                 logs.encode("utf-8"), run_root=run_dir)
            except OSError:
                pass  # 不可得 → 闭包判 MISSING → INCOMPLETE(rc=0 也不 OK)
            code = dk.wait(cname)
            atomic_write(os.path.join(run_dir, "telemetry", "official_baseline_container_exit.json"),
                         json.dumps(container_exit_fields(code), sort_keys=True).encode("utf-8"),
                         run_root=run_dir)
            # 4) ROS 只订不发(fixture=预录消息;real 本轮禁用)
            for key, rel in (("readiness", "telemetry/readiness.jsonl"),
                             ("extnav", "telemetry/extnav.jsonl")):
                msgs = backend.ros_messages(key)
                recs = [_rec(cfg, run_id, key, m) for m in msgs]
                _write_jsonl_records(run_dir, rel, recs, cfg, run_id, gov)
            # 5) 冻结身份(canonical hash 由 E0 实现算出后经 backend 提供)
            fz = collect_freeze(git_runner=backend.git, image_inspect=backend.image_inspect,
                                config_hash=backend.config_hash(), batch_id=cfg["batch_id"],
                                run_id=run_id, image_refs=backend.image_refs())
            atomic_write(os.path.join(run_dir, "telemetry", "freeze.json"),
                         json.dumps(fz, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                         run_root=run_dir)
            # 6) required artifact 闭包 → evidence gate(正式调用,非测试专用)
            statuses, business_ok, biz = evaluate_run_evidence(run_dir)
            gate = C.evidence_gate(statuses, business_ok=business_ok)
            final["evidence_gate"] = gate
            final["business_outcome"] = biz
            order = {"COMPLETE": 0, "INCOMPLETE": 1, "CORRUPT": 2}
            if order.get(gate["status"], 1) > order.get(worst, 0):
                worst = gate["status"]
            final["run_ids_processed"].append(run_id)
            # run 级 final status(聚合器消费)
            run_final = dict(final)
            run_final["evidence_state"] = gate["status"]
            run_final["run_ids_processed"] = [run_id]
            run_final["process_rc"] = 0
            run_final["finalization_state"] = "WRITTEN"
            atomic_write(os.path.join(run_dir, "telemetry", "sidecar_final_status.json"),
                         json.dumps(run_final, ensure_ascii=False, sort_keys=True,
                                    indent=1).encode("utf-8"),
                         run_root=run_dir, overwrite=True)
        final["truncated"] = dict(gov.truncated)
        for k, v in gov.dropped.items():
            final["dropped_records"][k] = final["dropped_records"].get(k, 0) + v
        final["evidence_state"] = worst
        rc = 0
        force = getattr(backend, "force_rc", None)
        if callable(force):
            fr = force()
            if fr is not None:
                rc = int(fr)
                final["failure_reasons"].append(f"fixture force_rc={fr}(进程失败与证据状态并存)")
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
    except Exception as e:  # 顶层异常必须产出 final status,不静默
        final["failure_reasons"].append(f"{type(e).__name__}: {e}")
        final["evidence_state"] = "INCOMPLETE"
        try:
            write_batch_final(6)
        except Exception:
            pass
        return 6


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="telemetry_sidecar",
        description="WP304 E1 纯旁路 telemetry sidecar(正式 CLI;fixture/real 同一主循环)")
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--batch-id", required=True)
    ap.add_argument("--run-registry", required=True)
    ap.add_argument("--world-model-root", required=True)
    ap.add_argument("--backend", required=True, choices=["real", "fixture"])
    ap.add_argument("--fixture-input", default=None)
    ap.add_argument("--ros-domain-id", default=None)
    ap.add_argument("--segment-record-limit", type=int, default=1000)
    ap.add_argument("--flush-interval", type=float, default=1.0)
    ap.add_argument("--registry-wait-sec", type=float, default=5.0)
    ap.add_argument("--once", action="store_true",
                    help="有限模式:处理 registry 当前 RESOLVED 条目后退出")
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args(argv)
    cfg = {"artifact_root": a.artifact_root, "batch_id": a.batch_id,
           "run_registry": a.run_registry, "world_model_root": a.world_model_root,
           "once": a.once, "registry_wait_sec": a.registry_wait_sec,
           "segment_record_limit": a.segment_record_limit,
           "flush_interval": a.flush_interval, "ros_domain_id": a.ros_domain_id}
    if a.backend == "fixture":
        if not a.fixture_input:
            ap.error("--backend fixture 需要 --fixture-input")
        backend = FixtureBackend(a.fixture_input)
    else:
        backend = RealBackend(container="official_baseline", ros_domain_id=a.ros_domain_id)
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
