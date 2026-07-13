#!/usr/bin/env bash
# M2 slice5 port side: our voxblox esdf_server on Jazzy, deterministic frames
# -> save_map (file = TSDF layer + appended ESDF layer, esdf_server.cc).
# Usage: run_port_ros2_esdf.sh [method]   (default simple)
METHOD=${1:-simple}
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/../src/voxblox_ros2_minimal" && pwd)"
OUT="${OUT:-$HOME/cmp_out}"
mkdir -p "$OUT"

docker run --rm -v "$SRC":/src:ro -v "$HERE":/cmp:ro -v "$OUT":/out voxblox_ros2_deps:jazzy bash -c '
  set -e
  source /opt/ros/jazzy/setup.bash
  mkdir -p /ws/src && cp -r /src /ws/src/voxblox_ros2_minimal && cd /ws
  export MAKEFLAGS=-j$(nproc)
  colcon build --merge-install --executor sequential --packages-up-to voxblox_ros \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -2
  source install/setup.bash
  echo "=== frames sha (port side) ==="
  cd /cmp && python3 frames_common.py | tail -1
  # esdf_server names its node "voxblox" (esdf_server_node.cc) -> private
  # topic /voxblox/pointcloud, service /voxblox/save_map.
  /ws/install/lib/voxblox_ros/esdf_server --ros-args \
    -p method:='"$METHOD"' \
    -p tsdf_voxel_size:=0.2 -p tsdf_voxels_per_side:=16 \
    -p truncation_distance:=0.6 \
    -p max_ray_length_m:=12.0 -p min_ray_length_m:=0.1 \
    -p clearing_ray_weight_factor:=0.01 \
    -p min_time_between_msgs_sec:=0.0 \
    -p update_mesh_every_n_sec:=0.0 \
    -p esdf_max_distance_m:=4.0 -p esdf_default_distance_m:=4.0 \
    -p world_frame:=world -p verbose:=false >/tmp/esdf.log 2>&1 &
  sleep 4
  python3 /cmp/pub_ros2.py /out/port_esdf_'"$METHOD"'.voxblox voxblox
  sleep 1
  ls -la /out/
  echo "--- esdf_server log tail ---"; tail -5 /tmp/esdf.log
'
echo "DOCKER_RC=$?"
