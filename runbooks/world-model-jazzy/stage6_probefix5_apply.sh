#!/usr/bin/env bash
# 跑通攻坚·探针修复⑤(B16 收尾洞):publisher QoS 内省在发现竞态下返回空 →
# 回退 volatile 收不到 latched /tf_static → rc124。修:info 重试 + tf_static 默认 transient_local。
set -e
CLEAN=/home/ai4s/ws-clean/world-model
F=$CLEAN/orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl
cd "$CLEAN"
python3 - <<'PY'
import io
f = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl"
src = io.open(f, encoding="utf-8").read()
old = """        sub_qos = qos_profile_sensor_data
        try:
            infos = node.get_publishers_info_by_topic(topic)
        except Exception:
            infos = []
"""
new = """        sub_qos = qos_profile_sensor_data
        # Publisher-info discovery races the same DDS propagation as everything
        # else: an empty result here made the subscription fall back to a
        # volatile QoS and silently miss latched topics (/tf_static). Retry the
        # query within a small budget, and if it stays empty for a latched-by-
        # convention topic, default to TRANSIENT_LOCAL instead of guessing.
        infos = []
        info_deadline = time.monotonic() + min(10.0, PROBE_TIMEOUT_SEC / 3.0)
        while time.monotonic() < info_deadline:
            try:
                infos = node.get_publishers_info_by_topic(topic)
            except Exception:
                infos = []
            if infos:
                break
            rclpy.spin_once(node, timeout_sec=0.2)
        if not infos and topic.endswith("tf_static"):
            from rclpy.qos import QoSProfile, QoSHistoryPolicy, QoSDurabilityPolicy, QoSReliabilityPolicy
            sub_qos = QoSProfile(
                history=QoSHistoryPolicy.KEEP_LAST, depth=100,
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            )
"""
assert src.count(old) == 1, src.count(old)
io.open(f, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
print("PATCHED publisher-info retry + tf_static transient_local fallback")
PY
export PATH=/usr/local/go/bin:$PATH
cd orchestration/sim
go build ./... && go test ./internal/tasks/... 2>&1 | tail -3
git -C "$CLEAN" status --short | head -3
