#!/usr/bin/env python3
# 3b 查证:从 rosbag(mcap.zstd)抽 /navlab/slam/status 的首/中/末条 JSON,
# 判定 slam.ready=False 是"全程未 ready"还是"gate/探针采样太早"。
# 用法: slam_status_timeline.py <run_dir>
import sys, os, glob, json, subprocess, tempfile, shutil

run = sys.argv[1]
topic = "/navlab/slam/status"
files = glob.glob(os.path.join(run, "rosbag", "**", "*.mcap*"), recursive=True)
if not files:
    sys.exit("NO_MCAP")

from mcap.reader import make_reader

def open_mcap(path):
    if path.endswith(".zstd"):
        if shutil.which("zstd"):
            tmp = os.path.join(tempfile.gettempdir(), os.path.basename(path)[:-5])
            subprocess.run(["zstd", "-d", "-f", path, "-o", tmp], check=True, capture_output=True)
            return tmp
        import zstandard
        dst = tempfile.NamedTemporaryFile(suffix=".mcap", delete=False)
        with open(path, "rb") as f:
            zstandard.ZstdDecompressor().copy_stream(f, dst)
        dst.close()
        return dst.name
    return path

msgs = []
for path in files:
    with open(open_mcap(path), "rb") as f:
        for schema, channel, message in make_reader(f).iter_messages(topics=[topic]):
            msgs.append((message.log_time, message.data))

msgs.sort()
print("total", len(msgs), "messages on", topic)
if not msgs:
    sys.exit(0)

def decode(raw):
    # std_msgs/String CDR: 4B encapsulation header + 4B length + utf8 + padding
    try:
        import struct
        n = struct.unpack_from("<I", raw, 4)[0]
        s = raw[8:8 + n - 1].decode("utf-8", "replace")  # length includes NUL
        return json.loads(s)
    except Exception as exc:
        return {"decode_error": str(exc), "head": raw[:40].hex()}

for label, idx in [("FIRST", 0), ("MID", len(msgs) // 2), ("LAST", -1)]:
    t, raw = msgs[idx]
    d = decode(raw)
    keep = {k: d.get(k) for k in ("state", "ready", "mode") if isinstance(d, dict)}
    scan = d.get("scan") if isinstance(d, dict) else None
    imu = d.get("imu") if isinstance(d, dict) else None
    tf = d.get("tf") if isinstance(d, dict) else None
    print("%s t=%.3f %s" % (label, t / 1e9, keep))
    if isinstance(scan, dict):
        print("   scan: present=%s count=%s | imu: present=%s count=%s | tf: present=%s count=%s" % (
            scan.get("present"), scan.get("count"),
            (imu or {}).get("present"), (imu or {}).get("count"),
            (tf or {}).get("present"), (tf or {}).get("received_count")))
    if "decode_error" in (d or {}):
        print("   ", d)
