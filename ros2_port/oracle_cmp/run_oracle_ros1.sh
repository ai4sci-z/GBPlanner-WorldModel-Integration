#!/usr/bin/env bash
# Oracle side: ntnu voxblox @ dev/noetic (0ee88c2) inside gbplanner-ref:latest.
# Fresh container (no wm_planner CMD), deterministic frames -> save_map.
# Usage: run_oracle_ros1.sh [method] (default simple)
METHOD=${1:-simple}
CMP=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/ros2_port/oracle_cmp
OUT=/home/ai4s/cmp_out
mkdir -p "$OUT"

docker run --rm -v "$CMP":/cmp:ro -v "$OUT":/out gbplanner-ref:latest bash -c '
  set -e
  source /opt/ros/noetic/setup.bash
  source /root/gbp_ws/devel/setup.bash
  roscore >/tmp/roscore.log 2>&1 &
  sleep 3
  echo "=== frames sha (oracle side) ==="
  cd /cmp && python3 frames_common.py | tail -1
  rosrun voxblox_ros tsdf_server __name:=voxblox \
    _method:='"$METHOD"' \
    _tsdf_voxel_size:=0.2 _tsdf_voxels_per_side:=16 \
    _truncation_distance:=0.6 \
    _max_ray_length_m:=12.0 _min_ray_length_m:=0.1 \
    _clearing_ray_weight_factor:=0.01 \
    _min_time_between_msgs_sec:=0.0 \
    _update_mesh_every_n_sec:=0.0 \
    _world_frame:=world _verbose:=false >/tmp/tsdf.log 2>&1 &
  sleep 4
  python3 /cmp/pub_ros1.py /out/oracle_tsdf_'"$METHOD"'.voxblox
  sleep 1
  ls -la /out/
  echo "--- tsdf_server log tail ---"; tail -5 /tmp/tsdf.log
'
echo "DOCKER_RC=$?"
