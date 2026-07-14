#!/usr/bin/env bash
# L0 hover gate — GATE-4b bisection, layer L0 (Review 002 §3.2).
# Same container / same launch / same FROZEN vehicle model as the failing
# hover runs; the ONLY changes vs. that stack:
#   1. SITL params = official gazebo-iris defaults (GPS+compass EKF) —
#      the external-nav parm overlay is NOT bind-mounted;
#   2. no SLAM / external-nav / companion services at all.
# Purpose: isolate rigid body + ArduPilotPlugin + motors + lockstep.
# mutates: nothing in any git repo (artifacts only). requires: docker
# default-runtime=nvidia, images per pins_2026-07-14.yaml.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WM=${WM:-/home/ai4s/projects/world-model}
ALT=${1:-0.5}
HOVER_SEC=${2:-60}
IMAGE=navlab/official-baseline:jazzy-latest
FROZEN_MODEL="$HERE/model_overlay_frozen.sdf"

# single-instance lock (Review 001 P0-3: no concurrent runs fighting)
exec 9>"/tmp/l0_hover_gate.lock"
flock -n 9 || { echo "another l0_hover_gate is running"; exit 90; }

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-alt${ALT}"
ART_HOST="$WM/artifacts/sim/l0_hover/$RUN_ID"
ART_CTR="/workspace/artifacts/sim/l0_hover/$RUN_ID"
mkdir -p "$ART_HOST/sitl" "$ART_HOST/logs"
CNAME="l0_hover_$RUN_ID"

# config snapshot (Review 001 P0-3 acceptance: every run self-describes)
{
  echo "run_id: $RUN_ID"
  echo "alt: $ALT"; echo "hover_sec: $HOVER_SEC"
  echo "image: $(docker images --no-trunc --format '{{.ID}}' "$IMAGE" | head -1)"
  echo "model_overlay_sha256: $(sha256sum "$FROZEN_MODEL" | cut -d' ' -f1)"
  echo "world_model_head: $(git -C "$WM" rev-parse HEAD)"
  echo "world_model_dirty: $(git -C "$WM" status --porcelain | wc -l) files"
  echo "parm: OFFICIAL DEFAULTS (no external-nav overlay mounted)"
} > "$ART_HOST/config_manifest.txt"

cleanup() { docker rm -f "$CNAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$CNAME" --net host \
  -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 \
  -v "$WM:/workspace" \
  -v "$HERE:/l0:ro" \
  -v "$FROZEN_MODEL:/opt/navlab_official_ws/install/ardupilot_gz_description/share/ardupilot_gz_description/models/iris_with_lidar/model.sdf:ro" \
  --entrypoint bash "$IMAGE" -lc "
set -eo pipefail
source /opt/ros/\${ROS_DISTRO:-jazzy}/setup.bash
source /opt/navlab_official_ws/install/setup.bash
export PYTHONPATH=/workspace:\${PYTHONPATH:-}
export NAVLAB_OFFICIAL_SDF_ROOTS=/opt/navlab_official_ws/install/ardupilot_gazebo/share:/opt/navlab_official_ws/install/ardupilot_gz_description/share
export SDF_PATH=\${NAVLAB_OFFICIAL_SDF_ROOTS}:\${SDF_PATH:-}
export GZ_SIM_RESOURCE_PATH=\${NAVLAB_OFFICIAL_SDF_ROOTS}:\${GZ_SIM_RESOURCE_PATH:-}
python3 -m navlab.sim.gazebo_sensor.benewake_tfmini_serial --virtual-serial-link /tmp/navlab_benewake_tfmini --log-file $ART_CTR/logs/benewake.log &
for _ in \$(seq 1 200); do [ -e /tmp/navlab_benewake_tfmini ] && break; sleep 0.05; done
cd $ART_CTR/sitl
exec ros2 launch ardupilot_gz_bringup iris_maze.launch.py serial7:=uart:/tmp/navlab_benewake_tfmini:115200 use_gz_sim_gui:=false rviz:=false use_dds_agent:=true use_gz_sim_server:=true spawn_robot:=true
" > "$ART_HOST/logs/container_start.log"

# mavproxy (started by the launch) owns tcp:5760; the mission driver uses
# SITL's second serial port tcp:5762 instead.
echo "[l0] container $CNAME up; waiting for SITL tcp:5762 ..."
for i in $(seq 1 120); do
  if docker exec "$CNAME" bash -c 'exec 3<>/dev/tcp/127.0.0.1/5762' 2>/dev/null; then break; fi
  if [ "$i" = 120 ]; then echo "[l0] SITL never opened 5762"; docker logs "$CNAME" | tail -30; exit 91; fi
  sleep 1
done
echo "[l0] SITL is up; starting mission (alt=${ALT}m hover=${HOVER_SEC}s)"

set +e
docker exec "$CNAME" bash -lc "source /opt/ros/jazzy/setup.bash && python3 /l0/l0_hover_mission.py --endpoint tcp:127.0.0.1:5762 --alt $ALT --hover-sec $HOVER_SEC --out $ART_CTR/mission.json" \
  2>&1 | tee "$ART_HOST/logs/mission.log"
MISSION_RC=${PIPESTATUS[0]}

docker logs "$CNAME" > "$ART_HOST/logs/container_full.log" 2>&1 || true

# The dataflash BIN is only fully flushed once ArduPilot exits — judging it
# while SITL still runs truncates the log (observed: 25 s of a 85 s flight).
echo "[l0] stopping SITL so the BIN flushes ..."
docker stop -t 30 "$CNAME" >/dev/null 2>&1 || true

docker run --rm -v "$WM:/workspace" -v "$HERE:/l0:ro" --entrypoint bash "$IMAGE" -lc \
  "python3 /l0/l0_bin_verdict.py --logdir $ART_CTR/sitl --alt $ALT --hover-sec $HOVER_SEC --out $ART_CTR/verdict.json" \
  2>&1 | tee "$ART_HOST/logs/verdict.log"
VERDICT_RC=${PIPESTATUS[0]}
set -e
echo "[l0] run $RUN_ID: mission_rc=$MISSION_RC verdict_rc=$VERDICT_RC (artifacts: $ART_HOST)"
# business verdict decides the exit code (Review 001 P1-8)
exit "$VERDICT_RC"
