#!/usr/bin/env bash
# M2 slice5 wm-mapping: run INSIDE voxblox_ros2_port container (started by
# run_wm_mapping.sh). Waits for the live sim's cloud, maps ~MAP_SEC seconds
# with our esdf_server, shows rviz2, saves the scene layers to /out.
set -o pipefail
MAP_SEC=${MAP_SEC:-75}
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash

echo "=== [mapper] waiting for /cloud_in (rclpy) ==="
PROBE=$(python3 /wm/mapper.py 180) || { echo "$PROBE"; echo "MAPPER_ABORT"; exit 1; }
echo "$PROBE"
FRAME=$(echo "$PROBE" | grep -oP 'CLOUD_FRAME=\K\S+')

echo "=== [mapper] starting tf_clean_relay (drop wall-epoch TF poison) ==="
python3 /wm/tf_clean_relay.py > /out/tf_relay.log 2>&1 &

echo "=== [mapper] starting esdf_server (world_frame=map, sim time, /tf via /tf_clean) ==="
/ws/install/lib/voxblox_ros/esdf_server --ros-args \
  -r /tf:=/tf_clean \
  -r /voxblox/pointcloud:=/cloud_in \
  -p use_sim_time:=true \
  -p method:=simple \
  -p tsdf_voxel_size:=0.2 -p tsdf_voxels_per_side:=16 \
  -p truncation_distance:=0.6 \
  -p max_ray_length_m:=12.0 -p min_ray_length_m:=0.1 \
  -p min_time_between_msgs_sec:=0.0 \
  -p update_mesh_every_n_sec:=1.0 \
  -p publish_pointclouds:=true \
  -p esdf_max_distance_m:=4.0 -p esdf_default_distance_m:=4.0 \
  -p world_frame:=map -p verbose:=false > /out/esdf_server.log 2>&1 &
ESDF_PID=$!

echo "=== [mapper] starting rviz2 ==="
# hybrid laptop: X display runs on the Intel iGPU, container has no /dev/dri
# and NVIDIA GLX is rejected by the X server -> render rviz with llvmpipe.
LIBGL_ALWAYS_SOFTWARE=1 rviz2 -d /wm/scene.rviz --ros-args -p use_sim_time:=true > /out/rviz.log 2>&1 &

echo "=== [mapper] mapping for ${MAP_SEC}s (frame=${FRAME}) ==="
sleep "${MAP_SEC}"

echo "=== [mapper] save_map ==="
python3 - <<'PY'
import rclpy
from rclpy.node import Node
from voxblox_msgs.srv import FilePath
rclpy.init()
n = Node('slice5_saver')
cli = n.create_client(FilePath, '/voxblox/save_map')
assert cli.wait_for_service(timeout_sec=15.0), 'save_map service missing'
fut = cli.call_async(FilePath.Request(file_path='/out/wm_scene_esdf.voxblox'))
rclpy.spin_until_future_complete(n, fut, timeout_sec=30.0)
print('save_map ->', fut.result())
PY
ls -la /out/wm_scene_esdf.voxblox 2>/dev/null || echo "SAVE_FAILED"
echo "=== [mapper] keeping rviz alive for screenshot; esdf_server pid=$ESDF_PID ==="
echo "MAPPER_DONE"
