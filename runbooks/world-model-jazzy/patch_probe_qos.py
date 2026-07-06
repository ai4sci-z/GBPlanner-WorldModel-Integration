#!/usr/bin/env python3
# 修 ros_probe.py.tmpl: rclpy 订阅按发布端 QoS 匹配(reliability+durability),
# 让 latched 话题(/tf_static, TRANSIENT_LOCAL)能被探针采到。默认 qos_profile_sensor_data
# 是 BEST_EFFORT+VOLATILE,对锁存话题收不到已发布的保留样本。
# 用法: patch_probe_qos.py <tmpl_path>
import sys, io

path = sys.argv[1]
src = io.open(path, "r", encoding="utf-8").read()

OLD_LINE = "        subscription = node.create_subscription(msg_type, topic, on_msg, qos_profile_sensor_data)"
NEW_BLOCK = (
    "        sub_qos = qos_profile_sensor_data\n"
    "        try:\n"
    "            infos = node.get_publishers_info_by_topic(topic)\n"
    "        except Exception:\n"
    "            infos = []\n"
    "        if infos:\n"
    "            from rclpy.qos import QoSProfile, QoSHistoryPolicy\n"
    "            src_qos = infos[0].qos_profile\n"
    "            sub_qos = QoSProfile(\n"
    "                history=QoSHistoryPolicy.KEEP_LAST,\n"
    "                depth=max(1, getattr(src_qos, \"depth\", 0) or 10),\n"
    "                reliability=src_qos.reliability,\n"
    "                durability=src_qos.durability,\n"
    "            )\n"
    "        subscription = node.create_subscription(msg_type, topic, on_msg, sub_qos)"
)

if NEW_BLOCK.splitlines()[0] in src and "get_publishers_info_by_topic" in src:
    print("ALREADY_PATCHED")
    sys.exit(0)

if OLD_LINE not in src:
    print("PATTERN_NOT_FOUND")
    sys.exit(2)

src = src.replace(OLD_LINE, NEW_BLOCK, 1)
io.open(path, "w", encoding="utf-8", newline="\n").write(src)
print("PATCHED_OK")
