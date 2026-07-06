#!/usr/bin/env python3
# 判定 frame_contract_probe 采不到某话题是不是时序问题:
# 对比 rosbag 里该话题首/末条消息时间戳(system clock ns) vs 探针运行窗口(probe json started_ms + latency)。
# 用法: probe_timing.py <run_dir> [topic ...]  (默认查 /ap/v1/pose/filtered /tf_static /tf)
import sys, os, json, glob, sqlite3

run = sys.argv[1]
topics = sys.argv[2:] or ["/ap/v1/pose/filtered", "/tf_static", "/tf"]

# 1) 探针窗口
print("========== 探针窗口 (system clock) ==========")
windows = {}
for name in ["frame_contract_probe", "exploration_probe", "imu_probe", "rangefinder_probe"]:
    p = os.path.join(run, "probes", name + ".json")
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    st = d.get("started_ms")
    if st is None:
        continue
    # 各话题采样 latency 最大值≈探针总时长下界
    lat = 0.0
    for t, s in (d.get("samples") or {}).items():
        if isinstance(s, dict):
            lat = max(lat, float(s.get("latency_sec", 0) or 0))
            ra = s.get("rclpy_attempt")
            if isinstance(ra, dict):
                lat = max(lat, float(ra.get("latency_sec", 0) or 0))
    windows[name] = (st / 1000.0, lat)
    print("  %-22s start=%.3f  max_sample_latency=%.1fs  ok=%s" % (name, st / 1000.0, lat, d.get("ok")))

# 2) rosbag 各话题首/末条
print("\n========== rosbag 话题时间戳 ==========")
db3s = glob.glob(os.path.join(run, "rosbag", "**", "*.db3"), recursive=True)
mcaps = glob.glob(os.path.join(run, "rosbag", "**", "*.mcap"), recursive=True)
if not db3s and mcaps:
    print("  (mcap 格式,本脚本只支持 db3;文件:", mcaps, ")")
    sys.exit(1)
if not db3s:
    print("  (no db3 found)")
    sys.exit(1)

first_last = {}
for db in db3s:
    con = sqlite3.connect(db)
    cur = con.cursor()
    tmap = {name: tid for tid, name in cur.execute("SELECT id, name FROM topics")}
    for t in topics:
        if t not in tmap:
            continue
        row = cur.execute(
            "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM messages WHERE topic_id=?",
            (tmap[t],),
        ).fetchone()
        if row and row[2]:
            lo, hi, n = row
            cur_fl = first_last.get(t)
            if cur_fl:
                lo = min(lo, cur_fl[0]); hi = max(hi, cur_fl[1]); n += cur_fl[2]
            first_last[t] = (lo, hi, n)
    con.close()

for t in topics:
    if t not in first_last:
        print("  %-28s (not in bag)" % t)
        continue
    lo, hi, n = first_last[t]
    print("  %-28s first=%.3f last=%.3f count=%d" % (t, lo / 1e9, hi / 1e9, n))

# 3) 对比判定
print("\n========== 判定 ==========")
fc = windows.get("frame_contract_probe")
if fc:
    p_start, p_lat = fc
    p_end = p_start + max(p_lat, 1.0)
    print("frame_contract_probe 窗口≈ [%.3f, %.3f]" % (p_start, p_end))
    for t in topics:
        if t not in first_last:
            continue
        lo, hi, n = first_last[t]
        lo /= 1e9; hi /= 1e9
        if lo > p_end:
            verdict = "TIMING: 首条消息晚于探针窗口 %.1fs -> 时序问题坐实" % (lo - p_end)
        elif hi < p_start:
            verdict = "TIMING: 末条消息早于探针窗口 %.1fs (话题停发) " % (p_start - hi)
        else:
            verdict = "OVERLAP: 探针窗口内话题在发 -> 非时序,另查(QoS/type-hash)"
        print("  %-28s %s" % (t, verdict))
