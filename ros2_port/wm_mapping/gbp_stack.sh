#!/usr/bin/env bash
# M5: the ROS2 GBPlanner stack, run INSIDE the gbp_stack container against a
# live world-model simulation (host network, domain 0).
#   tf_clean_relay   -- drop wall-epoch TF poison (slice5 lesson)
#   gbplanner_node   -- voxblox map from /cloud_in, odometry from /slam/odom,
#                       TF via /tf_clean, frames = map
#   pci_trigger_node -- periodic planner calls -> /gbp/trajectory
#   adapter          -- trajectory_to_intent.py (rclpy, bridge-era logic unchanged)
#   gbp_enabler      -- arms /gbp/enable once the FCU controller is ready
set -o pipefail
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
pkill -x gbplanner_node 2>/dev/null
pkill -f '/pci_trigger_node' 2>/dev/null
pkill -f tf_clean_relay 2>/dev/null
pkill -f trajectory_to_intent 2>/dev/null
pkill -f gbp_enabler 2>/dev/null
sleep 1

python3 /wm/tf_clean_relay.py > /out/m5_tf_relay.log 2>&1 &

/ws/install/lib/gbplanner_node/gbplanner_node --ros-args \
  --params-file /gbcfg/wm_gbplanner.yaml \
  -r /tf:=/tf_clean \
  -r /odometry:=/slam/odom \
  -r /gbplanner_node/pointcloud:=/cloud_in \
  -p use_sim_time:=true \
  > /out/m5_gbp_node.log 2>&1 &

sleep 3
/ws/install/lib/gbplanner_node/pci_trigger_node --ros-args \
  -p trigger_period_sec:=4.0 -p frame_id:=map -p use_sim_time:=true \
  > /out/m5_pci.log 2>&1 &

python3 /adapter/trajectory_to_intent.py \
  > /out/m5_adapter.log 2>&1 &

python3 /wm/gbp_enabler.py > /out/m5_enabler.log 2>&1 &

echo "GBP_STACK_UP"
wait
