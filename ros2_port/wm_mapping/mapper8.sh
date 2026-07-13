#!/usr/bin/env bash
# M2 slice5 wm-mapping, production take: gate the cloud stream so the queue
# drains before save_map (works around the canTransform(0.1s) executor
# starvation, transformer.cc:162 -- port bug noted for M2 ledger).
set -o pipefail
MAP_SEC=${MAP_SEC:-70}
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
pkill -f tf_clean_relay 2>/dev/null
pkill -f cloud_gate 2>/dev/null
pkill -x esdf_server 2>/dev/null
pkill -x rviz2 2>/dev/null
rm -f /out/gate_off /out/wm_scene_esdf.voxblox
sleep 1

echo "=== [m8] waiting for /cloud_in ==="
python3 /wm/mapper.py 180 | tail -2 || { echo M8_ABORT; exit 1; }

python3 /wm/tf_clean_relay.py > /out/tf_relay8.log 2>&1 &
python3 /wm/cloud_gate.py    > /out/gate8.log 2>&1 &
sleep 2

/ws/install/lib/voxblox_ros/esdf_server --ros-args \
  -r /tf:=/tf_clean -r /voxblox/pointcloud:=/cloud_gated \
  -p use_sim_time:=true -p method:=simple \
  -p tsdf_voxel_size:=0.2 -p tsdf_voxels_per_side:=16 \
  -p truncation_distance:=0.6 -p max_ray_length_m:=12.0 -p min_ray_length_m:=0.1 \
  -p min_time_between_msgs_sec:=0.0 -p update_mesh_every_n_sec:=1.0 \
  -p publish_pointclouds:=true -p esdf_max_distance_m:=4.0 -p esdf_default_distance_m:=4.0 \
  -p world_frame:=map -p verbose:=false > /out/esdf8.log 2>&1 &

LIBGL_ALWAYS_SOFTWARE=1 rviz2 -d /wm/scene.rviz --ros-args -p use_sim_time:=true > /out/rviz8.log 2>&1 &

python3 /wm/live_stats.py $((MAP_SEC + 15)) /out/live_stats.txt > /dev/null 2>&1 &
STATS=$!

echo "=== [m8] mapping ${MAP_SEC}s ==="
sleep "${MAP_SEC}"

echo "=== [m8] closing the gate, draining queue ==="
touch /out/gate_off
sleep 10

echo "=== [m8] save_map (long timeout) ==="
python3 - <<'PY'
import rclpy
from rclpy.node import Node
from voxblox_msgs.srv import FilePath
rclpy.init()
n = Node('m8_saver')
cli = n.create_client(FilePath, '/voxblox/save_map')
print('svc:', cli.wait_for_service(timeout_sec=15))
fut = cli.call_async(FilePath.Request(file_path='/out/wm_scene_esdf.voxblox'))
rclpy.spin_until_future_complete(n, fut, timeout_sec=90)
print('save:', fut.result())
PY
ls -la /out/wm_scene_esdf.voxblox 2>/dev/null || echo M8_SAVE_FAILED
wait $STATS
echo "=== [m8] live stats ==="
cat /out/live_stats.txt
echo "M8_DONE"
