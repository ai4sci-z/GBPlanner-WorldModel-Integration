#!/usr/bin/env bash
# 坑#17 修复:external_nav_bridge 把喂给飞控的 /external_nav/odom 硬绑在 2Hz 状态定时器上,
# ArduPilot ExternalNav/VisOdom 因输入太慢报 not healthy、GUIDED 拒绝起飞。
# 修法:发布率(独立高频定时器,默认30Hz)与就绪评估率(2Hz状态)解耦。最小改动,通用向后兼容。
set -euo pipefail
F=/home/ai4s/ws/world-model/navlab/common/slam/ros/bridges/navlab_external_nav_bridge/src/navlab_external_nav_bridge_node.cpp
Y=/home/ai4s/ws/world-model/navlab/common/slam/ros/bridges/navlab_external_nav_bridge/config/navlab_external_nav_bridge.params.yaml
python3 - "$F" << 'PYEOF'
import sys
p=sys.argv[1]; s=open(p).read()

# 1) 参数声明:coordinate_mode 之后加 output_odom_rate_hz
old1='''    coordinate_mode_ =
        declare_parameter<std::string>("coordinate_mode", "pass_through_enu_flu");
'''
new1=old1+'''    output_odom_rate_hz_ =
        declare_parameter("output_odom_rate_hz", 30.0);
'''
assert old1 in s, "anchor1 miss"; s=s.replace(old1,new1,1)

# 2) 构造区:状态定时器之后加独立高频 odom 定时器
old2='''    timer_ = create_wall_timer(
        500ms, std::bind(&NavlabExternalNavBridgeNode::publish_status, this));
'''
new2=old2+'''    const double odom_hz = std::max(1.0, output_odom_rate_hz_);
    odom_timer_ = create_wall_timer(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::duration<double>(1.0 / odom_hz)),
        std::bind(&NavlabExternalNavBridgeNode::publish_odom_tick, this));
'''
assert old2 in s, "anchor2 miss"; s=s.replace(old2,new2,1)

# 3) publish_status:不再直接发 odom,改为缓存就绪标志(由高频定时器发)
old3='''    if (ready) {
      publish_external_nav_odom();
    }
'''
new3='''    last_ready_ = ready;
'''
assert old3 in s, "anchor3 miss"; s=s.replace(old3,new3,1)

# 4) 加 publish_odom_tick 方法(在 publish_external_nav_odom 定义前)
old4='''  void publish_external_nav_odom() {'''
new4='''  void publish_odom_tick() {
    if (last_ready_) {
      publish_external_nav_odom();
    }
  }

  void publish_external_nav_odom() {'''
assert old4 in s, "anchor4 miss"; s=s.replace(old4,new4,1)

# 5) 成员声明
old5='''  rclcpp::TimerBase::SharedPtr timer_;
};'''
new5='''  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::TimerBase::SharedPtr odom_timer_;
  double output_odom_rate_hz_{30.0};
  bool last_ready_{false};
};'''
assert old5 in s, "anchor5 miss"; s=s.replace(old5,new5,1)

open(p,"w").write(s)
print("cpp patched OK")
PYEOF

# params.yaml 加显式参数(可发现性)
python3 - "$Y" << 'PYEOF'
import sys
p=sys.argv[1]; s=open(p).read()
if "output_odom_rate_hz" not in s:
    s=s.replace("    output_odom_topic: /external_nav/odom",
                "    output_odom_rate_hz: 30.0\n    output_odom_topic: /external_nav/odom",1)
    open(p,"w").write(s); print("yaml patched OK")
else:
    print("yaml already has param")
PYEOF
echo "=== 验证改动 ==="
grep -n "output_odom_rate_hz\|publish_odom_tick\|odom_timer_\|last_ready_" "$F"
