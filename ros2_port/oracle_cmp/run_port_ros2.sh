#!/usr/bin/env bash
# Port side: our patched voxblox (ntnu behavior on snt-arg base) on Jazzy.
# Builds from the repo vendored copy, feeds the SAME frames, save_map.
# Usage: run_port_ros2.sh [method] (default simple)
METHOD=${1:-simple}
SRC=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/ros2_port/src/voxblox_ros2_minimal
CMP=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/ros2_port/oracle_cmp
OUT=/home/ai4s/cmp_out
mkdir -p "$OUT"

docker run --rm -v "$SRC":/src:ro -v "$CMP":/cmp:ro -v "$OUT":/out voxblox_ros2_deps:jazzy bash -c '
  set -e
  source /opt/ros/jazzy/setup.bash
  mkdir -p /ws/src && cp -r /src /ws/src/voxblox_ros2_minimal && cd /ws
  export MAKEFLAGS=-j8
  colcon build --merge-install --executor sequential --packages-up-to voxblox_ros \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -2
  source install/setup.bash
  echo "=== frames sha (port side) ==="
  cd /cmp && python3 frames_common.py | tail -1
  /ws/install/lib/voxblox_ros/tsdf_server --ros-args \
    -p method:='"$METHOD"' \
    -p tsdf_voxel_size:=0.2 -p tsdf_voxels_per_side:=16 \
    -p truncation_distance:=0.6 \
    -p max_ray_length_m:=12.0 -p min_ray_length_m:=0.1 \
    -p clearing_ray_weight_factor:=0.01 \
    -p min_time_between_msgs_sec:=0.0 \
    -p update_mesh_every_n_sec:=0.0 \
    -p world_frame:=world -p verbose:=false >/tmp/tsdf.log 2>&1 &
  sleep 4
  python3 /cmp/pub_ros2.py /out/port_tsdf_'"$METHOD"'.voxblox
  sleep 1
  ls -la /out/
  echo "--- tsdf_server log tail ---"; tail -5 /tmp/tsdf.log
'
echo "DOCKER_RC=$?"
