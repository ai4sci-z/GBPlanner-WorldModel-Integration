#!/usr/bin/env python3
# 查 rosbag metadata: /tf_static、/tf、/ap/v1/pose/filtered 到底发没发、offered QoS(durability)。
# 用法: check_rosbag_qos.py <run_dir>
import sys, os, glob

run = sys.argv[1]
metas = glob.glob(os.path.join(run, "rosbag", "**", "metadata.yaml"), recursive=True)
if not metas:
    metas = glob.glob(os.path.join(run, "**", "metadata.yaml"), recursive=True)
print("metadata files:", metas)

WANT = ("/tf_static", "/tf", "/ap/v1/pose/filtered")

for mp in metas:
    print("\n==========", mp)
    raw = open(mp, encoding="utf-8", errors="replace").read()
    try:
        import yaml
        d = yaml.safe_load(raw)
        info = d.get("rosbag2_bagfile_information", d)
        print("total message_count:", info.get("message_count"))
        for t in info.get("topics_with_message_count", []):
            meta = t.get("topic_metadata", {})
            name = meta.get("name")
            cnt = t.get("message_count")
            qos = str(meta.get("offered_qos_profiles", ""))
            dur = "transient_local" if "transient_local" in qos else ("volatile" if "volatile" in qos else "?")
            rel = "best_effort" if "best_effort" in qos else ("reliable" if "reliable" in qos else "?")
            flag = "  <<<" if name in WANT else ""
            print("  %-42s count=%-5s dur=%-16s rel=%-11s type=%s%s" % (
                name, cnt, dur, rel, meta.get("type"), flag))
    except Exception as exc:
        print("[yaml unavailable / parse failed:", exc, "] -- 打印含关键话题的原始行:")
        for i, line in enumerate(raw.splitlines()):
            if any(w in line for w in WANT) or "durability" in line or "message_count" in line:
                print("   L%d: %s" % (i, line.strip()[:160]))
