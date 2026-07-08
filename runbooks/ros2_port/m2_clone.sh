#!/usr/bin/env bash
# M2: fetch voxblox sources per docs/ros2迁移_voxblox选型_2026-07-07.md §6
# - base:      snt-arg/voxblox_ros2_minimal   -> ros2_port_ws/src/
# - jazzy ref: GabrieleSantangelo/voxblox-ros2 -> ros2_port_ws/ref/
# - diff refs: ntnu-arl/voxblox + ethz-asl/voxblox -> ros2_port_ws/ref/
export PATH=/usr/local/go/bin:/usr/bin:/bin
set -o pipefail
WS=/home/ai4s/ros2_port_ws
mkdir -p "$WS/src" "$WS/ref"

clone() { # url dest
  if [ -d "$2/.git" ]; then
    echo "SKIP(exists): $2"
  else
    git clone --depth 50 "$1" "$2" 2>&1 | tail -2
  fi
  echo "HEAD($2)=$(git -C "$2" rev-parse --short HEAD 2>/dev/null) $(git -C "$2" log -1 --format=%cs 2>/dev/null)"
}

clone https://github.com/snt-arg/voxblox_ros2_minimal   "$WS/src/voxblox_ros2_minimal"
clone https://github.com/GabrieleSantangelo/voxblox-ros2 "$WS/ref/voxblox-ros2-gabriele"
clone https://github.com/ntnu-arl/voxblox                "$WS/ref/voxblox-ntnu"
clone https://github.com/ethz-asl/voxblox                "$WS/ref/voxblox-ethz"

echo "=== layout ==="
ls "$WS/src/voxblox_ros2_minimal"
echo "=== packages in base ==="
find "$WS/src/voxblox_ros2_minimal" -name package.xml -maxdepth 3 | sort
echo "=== jazzy dockerfile in gabriele ref ==="
find "$WS/ref/voxblox-ros2-gabriele" -maxdepth 2 -iname 'dockerfile*' -o -maxdepth 2 -iname 'makefile*' | sort
echo "=== DONE ==="
