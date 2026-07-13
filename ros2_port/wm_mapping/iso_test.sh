#!/usr/bin/env bash
# Isolation test: exact mapper esdf_server wiring, synthetic inputs.
set -o pipefail
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
pkill -f esdf_server 2>/dev/null; sleep 1
rm -f /out/iso_test.voxblox

/ws/install/lib/voxblox_ros/esdf_server --ros-args \
  -r /tf:=/tf_clean \
  -r /voxblox/pointcloud:=/cloud_in \
  -p use_sim_time:=true -p method:=simple \
  -p tsdf_voxel_size:=0.2 -p tsdf_voxels_per_side:=16 \
  -p truncation_distance:=0.6 -p max_ray_length_m:=12.0 -p min_ray_length_m:=0.1 \
  -p min_time_between_msgs_sec:=0.0 -p update_mesh_every_n_sec:=1.0 \
  -p publish_pointclouds:=true -p esdf_max_distance_m:=4.0 -p esdf_default_distance_m:=4.0 \
  -p world_frame:=map -p verbose:=false > /out/iso_esdf.log 2>&1 &
sleep 3
python3 /wm/${FEEDER:-iso_feeder.py}
echo "── esdf log (filtered) ──"
grep -vE "type hash|USER_DATA" /out/iso_esdf.log | tail -4
ls -la /out/iso_test.voxblox 2>/dev/null || echo "ISO_SAVE_FAILED"
pkill -f esdf_server
