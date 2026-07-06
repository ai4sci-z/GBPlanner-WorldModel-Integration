#!/usr/bin/env python3
# 修"后加入 participant 对 micro-ROS agent endpoints 发现 ~29s"导致 frame_contract_probe
# 采不到 /ap/v1/pose/filtered(实测:订阅后 28.97s 才匹配,匹配后 40ms 即收到首条)。
# 3 处最小改动,全部幂等。
import io, sys

CLEAN = "/home/ai4s/ws-clean/world-model"
ok = True

def patch(path, old, new, tag):
    global ok
    src = io.open(path, "r", encoding="utf-8").read()
    if new in src:
        print("ALREADY:", tag)
        return
    if old not in src:
        print("PATTERN_NOT_FOUND:", tag)
        ok = False
        return
    io.open(path, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
    print("PATCHED:", tag)

# A) FrameContractSpec 加 ProbeTimeoutSec 字段 + 默认 45(模板已认该 key;exploration probe 先例=45)
f = CLEAN + "/orchestration/sim/internal/tasks/helpers/runtime_specs.go"
patch(
    f,
    "\tMaxDirectionErrorRad    float64\n\tProbeDurationSec        float64\n}",
    "\tMaxDirectionErrorRad    float64\n\tProbeDurationSec        float64\n\t// ProbeTimeoutSec is the per-topic sampling budget for the frame contract\n\t// probe. Matching a late-joining subscription to the ArduPilot micro-ROS\n\t// agent's publishers takes ~30s of DDS endpoint discovery (measured), so\n\t// the default 8s template budget misses /ap/v1/pose/filtered every time.\n\tProbeTimeoutSec         float64\n}",
    "A1 struct field",
)
patch(
    f,
    "\t\tProbeDurationSec:        12.0,\n\t}",
    "\t\tProbeDurationSec:        12.0,\n\t\tProbeTimeoutSec:         45.0,\n\t}",
    "A2 default 45",
)

# B) 容器超时:frame_contract_probe 30 -> 90(与 exploration_probe 一致)
f = CLEAN + "/orchestration/sim/internal/tasks/runtime_specs.go"
patch(
    f,
    "\tif name == \"exploration_probe\" {\n\t\treturn 90\n\t}",
    "\tif name == \"exploration_probe\" {\n\t\treturn 90\n\t}\n\tif name == \"frame_contract_probe\" {\n\t\t// The per-topic sampling budget is 45s (see FrameContractSpec) because\n\t\t// late-joining DDS endpoint discovery against the ArduPilot micro-ROS\n\t\t// agent takes ~30s; 30s of container budget kills the probe first.\n\t\treturn 90\n\t}",
    "B container timeout 90",
)

# C) 模板:type 已发现(发布者存在)时订阅等待上限用 PROBE_TIMEOUT_SEC
f = CLEAN + "/orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl"
patch(
    f,
    "        subscription = node.create_subscription(msg_type, topic, on_msg, sub_qos)\n        deadline = time.monotonic() + TOPIC_SAMPLE_TIMEOUT_SEC",
    "        subscription = node.create_subscription(msg_type, topic, on_msg, sub_qos)\n        # The topic type was discovered above, so a publisher exists. Allow the\n        # full probe budget here: matching a late-joining subscription to some\n        # publishers (e.g. the ArduPilot micro-ROS agent) takes ~30s of DDS\n        # endpoint discovery, while data flows immediately once matched.\n        deadline = time.monotonic() + PROBE_TIMEOUT_SEC",
    "C template wait budget",
)

sys.exit(0 if ok else 2)
