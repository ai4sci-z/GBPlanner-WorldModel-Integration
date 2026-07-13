#!/usr/bin/env bash
# Take-7 diagnostic: esdf_server + relay + dual tf_dump, all in one file.
set -o pipefail
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
pkill -f tf_clean_relay 2>/dev/null
pkill -x esdf_server 2>/dev/null
sleep 1

echo "=== waiting for cloud (rclpy) ==="
python3 /wm/mapper.py 180 | tail -2 || { echo DIAG_ABORT; exit 1; }

python3 /wm/tf_clean_relay.py > /out/tf_relay7.log 2>&1 &
RELAY=$!
/ws/install/lib/voxblox_ros/esdf_server --ros-args \
  -r /tf:=/tf_clean -r /voxblox/pointcloud:=/cloud_in \
  -p use_sim_time:=true -p method:=simple \
  -p tsdf_voxel_size:=0.2 -p tsdf_voxels_per_side:=16 \
  -p truncation_distance:=0.6 -p max_ray_length_m:=12.0 -p min_ray_length_m:=0.1 \
  -p min_time_between_msgs_sec:=0.0 -p update_mesh_every_n_sec:=1.0 \
  -p publish_pointclouds:=true -p esdf_max_distance_m:=4.0 -p esdf_default_distance_m:=4.0 \
  -p world_frame:=map -p verbose:=false > /out/esdf7.log 2>&1 &
ESDF=$!

python3 /wm/tf_dump.py 70 /out/dump_tf.txt /tf > /dev/null 2>&1 &
D1=$!
python3 /wm/tf_dump.py 70 /out/dump_tfclean.txt /tf_clean > /dev/null 2>&1 &
D2=$!
wait $D1 $D2

echo "=== /tf segments ==="
cat /out/dump_tf.txt
echo "=== /tf_clean segments ==="
cat /out/dump_tfclean.txt
echo "=== esdf symptoms ==="
grep -cE "Waiting|Invalid" /out/esdf7.log
grep forwarded /out/tf_relay7.log | tail -1
kill $RELAY $ESDF 2>/dev/null
echo "DIAG_DONE"
