#!/usr/bin/env python3
# Stage4a 证据:从 run rosbag 抽 /navlab/fcu/setpoint/output 与 /navlab/fcu/setpoint/intent,
# 统计 goal_id 前缀分布(gbp_* = 我们的 intent 被 fcu_controller 消费/回显的证据)。
# 用法: check_output_gbp.py <run_dir>
import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

run = sys.argv[1]
topics = ["/navlab/fcu/setpoint/output", "/navlab/fcu/setpoint/intent"]
files = glob.glob(os.path.join(run, "rosbag", "**", "*.mcap*"), recursive=True)
if not files:
    sys.exit("NO_MCAP")

from mcap.reader import make_reader

def open_mcap(path):
    if path.endswith(".zstd"):
        tmp = os.path.join(tempfile.gettempdir(), os.path.basename(path)[:-5])
        if shutil.which("zstd"):
            subprocess.run(["zstd", "-d", "-f", path, "-o", tmp], check=True, capture_output=True)
        else:
            import zstandard
            with open(path, "rb") as fin, open(tmp, "wb") as fout:
                zstandard.ZstdDecompressor().copy_stream(fin, fout)
        return tmp
    return path

def decode(raw):
    try:
        n = struct.unpack_from("<I", raw, 4)[0]
        return raw[8:8 + n - 1].decode("utf-8", "replace")
    except Exception:
        return ""

for t in topics:
    counts = {}
    first_gbp = last_gbp = None
    total = 0
    for path in files:
        with open(open_mcap(path), "rb") as f:
            for schema, channel, message in make_reader(f).iter_messages(topics=[t]):
                total += 1
                s = decode(message.data)
                try:
                    d = json.loads(s)
                except Exception:
                    continue
                gid = str(d.get("goal_id", d.get("source", "?")))
                key = gid.split("_")[0] if gid else "?"
                counts[key] = counts.get(key, 0) + 1
                if gid.startswith("gbp"):
                    if first_gbp is None:
                        first_gbp = (message.log_time / 1e9, s[:160])
                    last_gbp = (message.log_time / 1e9, s[:160])
    print("== %s total=%d prefix_counts=%s" % (t, total, counts))
    if first_gbp:
        print("   FIRST gbp @%.3f: %s" % first_gbp)
        print("   LAST  gbp @%.3f: %s" % last_gbp)
