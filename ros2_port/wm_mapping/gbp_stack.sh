#!/usr/bin/env bash
# M5: the ROS2 GBPlanner stack, run INSIDE the gbp_stack container against a
# live world-model simulation (host network, domain 0).
#   tf_clean_relay   -- drop wall-epoch TF poison (slice5 lesson)
#   gbplanner_node   -- voxblox map from /wm/cloud3d, odometry from /slam/odom,
#                       TF via /tf_clean, frames = map
#   pci_trigger_node -- periodic planner calls -> /gbp/trajectory
#   adapter          -- trajectory_to_intent.py (rclpy, bridge-era logic unchanged)
#   gbp_enabler      -- arms /gbp/enable once the FCU controller is ready
# ROS 2 setup.bash reads optional variables before assigning defaults, so this
# entrypoint cannot enable nounset while sourcing the Jazzy environment.
set -e -o pipefail
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
POINTCLOUD_TOPIC="${GBP_POINTCLOUD_TOPIC:-/wm/cloud3d}"
pkill -x gbplanner_node 2>/dev/null || true
pkill -f '/pci_trigger_node' 2>/dev/null || true
pkill -f tf_clean_relay 2>/dev/null || true
pkill -f 'static_transform_publisher.*lidar3d_frame' 2>/dev/null || true
pkill -f trajectory_to_intent 2>/dev/null || true
pkill -f gbp_enabler 2>/dev/null || true
sleep 1

python3 /wm/tf_clean_relay.py > /out/m5_tf_relay.log 2>&1 &

# The net-new 3D lidar is an SDF overlay, so robot_state_publisher does not own
# its fixed joint. Publish the exact overlay extrinsic for tf2 consumers.
/opt/ros/jazzy/lib/tf2_ros/static_transform_publisher \
  --x 0 --y 0 --z 0.10 --roll 0 --pitch 0 --yaw 0 \
  --frame-id base_link --child-frame-id lidar3d_frame \
  > /out/m5_lidar3d_static_tf.log 2>&1 &

/ws/install/lib/gbplanner_node/gbplanner_node --ros-args \
  --params-file /gbcfg/wm_gbplanner.yaml \
  -r /tf:=/tf_clean \
  -r /odometry:=/slam/odom \
  -r "/gbplanner_node/pointcloud:=$POINTCLOUD_TOPIC" \
  -p use_sim_time:=true \
  > /out/m5_gbp_node.log 2>&1 &

sleep 3
/ws/install/lib/gbplanner_node/pci_trigger_node --ros-args \
  -p trigger_period_sec:=4.0 -p frame_id:=map -p use_sim_time:=true \
  > /out/m5_pci.log 2>&1 &

python3 /adapter/trajectory_to_intent.py \
  > /out/m5_adapter.log 2>&1 &

python3 /wm/gbp_enabler.py > /out/m5_enabler.log 2>&1 &

printf 'POINTCLOUD_TOPIC=%s\nPOINTCLOUD_FRAME=lidar3d_frame\nEXTRINSIC=base_link:lidar3d_frame:0,0,0.10\n' \
  "$POINTCLOUD_TOPIC" > /out/m5_stack_contract.log
echo "GBP_STACK_UP"
wait
