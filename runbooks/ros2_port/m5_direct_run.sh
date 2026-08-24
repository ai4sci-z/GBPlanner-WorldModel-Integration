#!/usr/bin/env bash
# M5: world-model direct-integration run.
#   sg docker -c 'bash runbooks/ros2_port/m5_direct_run.sh'
# Starts the ROS2 GBPlanner stack container, then a world-model live run of
# the EXPLORATION task with strategy switched to "external" via the harness's
# --exploration-strategy run override (world-model 9852e46+; Review_001 P0-3
# closed: tracked YAML is never modified by this script anymore).
# The adapter owns /navlab/fcu/setpoint/intent + /navlab/exploration/status.
# Acceptance: exploration_probe consumes the adapter's status (strategy label
# "gbplanner"), run reaches TASK_STATUS_* verdict with real waypoints.
set -o pipefail
WM="${WM:-/home/ai4s/projects/world-model}"
FEAT="${FEAT:-/home/ai4s/projects/gbp-feat}"
OUT="${OUT:-$HOME/cmp_out}"
YAML="$WM/orchestration/sim/configs/tasks/exploration.yaml"
RUN_ID="m5_$(date +%Y%m%dT%H%M%S)_$$"
LOCK="$OUT/m5_direct_run.lock"
RUN_OUT="$OUT/$RUN_ID"
mkdir -p "$OUT"
mkdir -p "$RUN_OUT"

# Exclusive lock: refuse concurrent runs (SITL/DDS cannot be shared).
exec 9>"$LOCK"
flock -n 9 || { echo "another m5_direct_run holds $LOCK, refusing"; exit 7; }

# Sanity: baseline YAML must be untouched — this script never modifies it;
# the strategy switch happens at run time via --exploration-strategy.
if ! git -C "$WM" diff --quiet -- orchestration/sim/configs/tasks/exploration.yaml; then
  echo "exploration.yaml has local modifications; baseline comparability broken, refusing"; exit 8
fi
trap 'docker rm -f gbp_stack >/dev/null 2>&1' EXIT
echo "RUN_ID=$RUN_ID (strategy override: external, tracked YAML untouched)"
{
  echo "MAIN_HEAD=$(git -C /home/ai4s/projects/GBPlanner-WorldModel-Integration rev-parse HEAD)"
  echo "FEAT_HEAD=$(git -C "$FEAT" rev-parse HEAD)"
  echo "WM_HEAD=$(git -C "$WM" rev-parse HEAD)"
  docker image inspect gbplanner_stack:jazzy --format 'STACK_IMAGE_ID={{.Id}}'
  sha256sum "$YAML"
} > "$RUN_OUT/pins.txt"

docker rm -f gbp_stack >/dev/null 2>&1
docker run -d --name gbp_stack --network=host \
  -e ROS_DOMAIN_ID=0 -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  -e "CYCLONEDDS_URI=<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>" \
  -v "$FEAT/ros2_port/wm_mapping":/wm:ro \
  -v "$FEAT/ros2_port/src/gbplanner_node/config":/gbcfg:ro \
  -v "$FEAT/ros2_port/adapter":/adapter:ro \
  -v "$RUN_OUT":/out \
  gbplanner_stack:jazzy sleep infinity >/dev/null
docker exec -d gbp_stack bash /wm/gbp_stack.sh
for _ in $(seq 1 30); do
  [ -s "$RUN_OUT/m5_stack_contract.log" ] && break
  sleep 1
done
[ -s "$RUN_OUT/m5_stack_contract.log" ] || {
  echo "GBPlanner stack did not publish its runtime contract" >&2
  exit 10
}
echo "=== gbp_stack up; starting world-model live run (strategy=external) ==="

export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
export GOFLAGS=-mod=mod
cd "$WM/orchestration/sim" || exit 9
timeout 600 go run ./cmd/navlab-sim run exploration --exploration-strategy external \
  --live-preflight > "$RUN_OUT/m5_run.log" 2>&1
RC=$?
echo "RUN_RC=$RC"
tail -8 "$RUN_OUT/m5_run.log"

REL_RUNDIR=$(sed -n 's/^artifact_dir=//p' "$RUN_OUT/m5_run.log" | tail -1)
RUNDIR=""
if [ -n "$REL_RUNDIR" ]; then
  RUNDIR=$(realpath -m "$WM/orchestration/sim/$REL_RUNDIR")
fi
echo "RUNDIR=$RUNDIR"
case "$RUNDIR" in
  "$WM"/artifacts/sim/exploration/*) ;;
  *) echo "run did not report a valid new exploration artifact directory" >&2; RUNDIR="" ;;
esac

ACCEPT_RC=20
if [ -n "$RUNDIR" ] && [ -d "$RUNDIR" ]; then
  python3 "$FEAT/runbooks/ros2_port/validate_m5_run.py" \
    --run-dir "$RUNDIR" \
    --stack-log-dir "$RUN_OUT" \
    --output "$RUN_OUT/m5_acceptance.json"
  ACCEPT_RC=$?
else
  echo '{"ok":false,"failures":["run_dir_missing"]}' > "$RUN_OUT/m5_acceptance.json"
fi
echo "=== stack logs (tails) ==="
for f in m5_gbp_node m5_pci m5_adapter m5_enabler; do
  echo "-- $f --"
  grep -vE "type hash|USER_DATA" "$RUN_OUT/$f.log" 2>/dev/null | tail -3
done
echo "ACCEPT_RC=$ACCEPT_RC"
[ "$RC" -eq 0 ] || exit "$RC"
exit "$ACCEPT_RC"
