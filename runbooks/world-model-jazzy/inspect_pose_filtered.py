#!/usr/bin/env python3
# 深查 /ap/v1/pose/filtered 采不到的细节:探针 sample 全字段 + rosbag metadata 里的 count/QoS + bag 时间窗。
# 用法: inspect_pose_filtered.py <run_dir> [topic]
import sys, os, json, glob

run = sys.argv[1]
topic = sys.argv[2] if len(sys.argv) > 2 else "/ap/v1/pose/filtered"

print("========== 1) frame_contract_probe 里该话题的完整 sample ==========")
p = os.path.join(run, "probes", "frame_contract_probe.json")
d = json.load(open(p))
print("probe started_ms:", d.get("started_ms"), " ok:", d.get("ok"), " blockers:", d.get("blockers"))
samp = (d.get("samples") or {}).get(topic)
print(json.dumps(samp, indent=2, sort_keys=True)[:3500])

print("\n========== 2) rosbag metadata: 该话题 count/QoS + bag 时间窗 ==========")
metas = glob.glob(os.path.join(run, "rosbag", "**", "metadata.yaml"), recursive=True)
for mp in metas:
    raw = open(mp, encoding="utf-8", errors="replace").read()
    try:
        import yaml
        info = yaml.safe_load(raw).get("rosbag2_bagfile_information", {})
        st = info.get("starting_time", {}).get("nanoseconds_since_epoch")
        dur = info.get("duration", {}).get("nanoseconds")
        if st is not None:
            print("bag start=%.3f  end=%.3f  duration=%.1fs" % (st / 1e9, (st + (dur or 0)) / 1e9, (dur or 0) / 1e9))
        for t in info.get("topics_with_message_count", []):
            meta = t.get("topic_metadata", {})
            if meta.get("name") in (topic, "/tf_static"):
                print("  %-28s count=%s type=%s" % (meta.get("name"), t.get("message_count"), meta.get("type")))
                print("    qos:", str(meta.get("offered_qos_profiles"))[:300])
    except Exception as exc:
        print("(yaml parse failed:", exc, ") raw lines with topic:")
        lines = raw.splitlines()
        for i, line in enumerate(lines):
            if topic in line:
                print("\n".join(lines[max(0, i - 2): i + 8]))

print("\n========== 3) 探针窗口 vs bag 时间窗 ==========")
st_ms = d.get("started_ms")
if st_ms:
    print("frame_contract_probe start = %.3f (epoch s)" % (st_ms / 1000.0))
