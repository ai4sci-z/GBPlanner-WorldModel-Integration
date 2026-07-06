#!/usr/bin/env python3
# 从 rosbag mcap(.zstd) 里取指定话题的首/末条 log_time,判定探针窗口时是否已在发布。
# 只读消息头时间戳,不 decode payload。缺依赖时如实打印缺什么。
# 用法: pose_first_ts.py <run_dir> [topic ...]
import sys, os, glob, json, subprocess, shutil, tempfile

run = sys.argv[1]
topics = sys.argv[2:] or ["/ap/v1/pose/filtered", "/tf_static", "/slam/odom"]

files = glob.glob(os.path.join(run, "rosbag", "**", "*.mcap*"), recursive=True)
print("bag files:", files)
if not files:
    sys.exit("NO_MCAP")

try:
    from mcap.reader import make_reader
except Exception as exc:
    print("MISSING_DEP: pip install mcap  (", exc, ")")
    sys.exit(2)

def open_mcap(path):
    if path.endswith(".zstd"):
        if shutil.which("zstd") is None:
            try:
                import zstandard
            except Exception:
                print("MISSING_DEP: zstd binary or pip install zstandard")
                sys.exit(2)
            dst = tempfile.NamedTemporaryFile(suffix=".mcap", delete=False)
            with open(path, "rb") as f:
                zstandard.ZstdDecompressor().copy_stream(f, dst)
            dst.close()
            return dst.name
        dst = path[:-5]
        tmp = os.path.join(tempfile.gettempdir(), os.path.basename(dst))
        subprocess.run(["zstd", "-d", "-f", path, "-o", tmp], check=True, capture_output=True)
        return tmp
    return path

stats = {}  # topic -> [first, last, count]
for path in files:
    mp = open_mcap(path)
    with open(mp, "rb") as f:
        reader = make_reader(f)
        # 优先用 summary 的 statistics(channel_message_counts)+ chunk index?简化:直接遍历消息头
        for schema, channel, message in reader.iter_messages(topics=topics):
            s = stats.setdefault(channel.topic, [None, None, 0])
            t = message.log_time
            s[0] = t if s[0] is None else min(s[0], t)
            s[1] = t if s[1] is None else max(s[1], t)
            s[2] += 1

print("\n========== 话题首/末条 log_time (epoch s) ==========")
for t in topics:
    if t in stats:
        lo, hi, n = stats[t]
        print("  %-28s first=%.3f last=%.3f count=%d" % (t, lo / 1e9, hi / 1e9, n))
    else:
        print("  %-28s (no messages)" % t)

# 探针窗口
p = os.path.join(run, "probes", "frame_contract_probe.json")
if os.path.exists(p):
    d = json.load(open(p))
    st = (d.get("started_ms") or 0) / 1000.0
    lat = 0.0
    for tt, s in (d.get("samples") or {}).items():
        if isinstance(s, dict):
            lat = max(lat, float(s.get("latency_sec", 0) or 0))
            ra = s.get("rclpy_attempt")
            if isinstance(ra, dict):
                lat = max(lat, float(ra.get("latency_sec", 0) or 0))
    print("\nframe_contract_probe 窗口≈ [%.3f, %.3f]" % (st, st + lat))
    for t, (lo, hi, n) in stats.items():
        lo /= 1e9; hi /= 1e9
        if lo > st + lat:
            print("  %-28s TIMING坐实: 首条晚于探针窗口 %.1fs" % (t, lo - (st + lat)))
        elif hi < st:
            print("  %-28s 话题在探针前就停发(早 %.1fs)" % (t, st - hi))
        else:
            print("  %-28s OVERLAP: 窗口内在发 -> 非时序,另查" % t)
