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
mkdir -p "$OUT"

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
sha256sum "$YAML" > "$OUT/exploration.yaml.sha.$RUN_ID"

docker rm -f gbp_stack >/dev/null 2>&1
docker run -d --name gbp_stack --network=host \
  -e ROS_DOMAIN_ID=0 -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  -e "CYCLONEDDS_URI=<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>" \
  -v "$FEAT/ros2_port/wm_mapping":/wm:ro \
  -v "$FEAT/ros2_port/src/gbplanner_node/config":/gbcfg:ro \
  -v "$FEAT/ros2_port/adapter":/adapter:ro \
  -v "$OUT":/out \
  gbplanner_stack:jazzy sleep infinity >/dev/null
docker exec -d gbp_stack bash /wm/gbp_stack.sh
echo "=== gbp_stack up; starting world-model live run (strategy=external) ==="

export PATH=/usr/local/go/bin:$PATH
export NAVLAB_SIM_DISTRO=jazzy
export GOFLAGS=-mod=mod
cd "$WM/orchestration/sim" || exit 9
timeout 600 go run ./cmd/navlab-sim run exploration --exploration-strategy external \
  --live-preflight > "$OUT/m5_run.log" 2>&1
RC=$?
echo "RUN_RC=$RC"
tail -8 "$OUT/m5_run.log"

RUNDIR=$(ls -dt "$WM"/artifacts/sim/exploration/*/ 2>/dev/null | head -1)
echo "RUNDIR=$RUNDIR"
[ -n "$RUNDIR" ] && python3 - "$RUNDIR" <<'PY'
import json, sys, glob
rd = sys.argv[1]
try:
    d = json.load(open(rd + '/summary.json'))
    print('task_status =', d.get('task_status') or d.get('status'))
    print('blockers    =', sorted(set(b.get('code') for b in (d.get('blockers') or []))))
except Exception as e:
    print('summary unavailable:', e)
for f in glob.glob(rd + '/**/exploration_probe*.json', recursive=True)[:1]:
    e = json.load(open(f))
    s = e['samples'].get('/navlab/exploration/status', {}).get('parsed', {})
    print('[external strategy] strategy=%s accepted=%s path=%sm blockers=%s'
          % (s.get('strategy'), s.get('accepted_goals'),
             s.get('path_length_m'), s.get('blockers')))
PY
echo "=== stack logs (tails) ==="
for f in m5_gbp_node m5_pci m5_adapter m5_enabler; do
  echo "-- $f --"
  grep -vE "type hash|USER_DATA" "$OUT/$f.log" 2>/dev/null | tail -3
done
exit $RC
