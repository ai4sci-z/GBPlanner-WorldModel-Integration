#!/usr/bin/env bash
# M4 smoke: gbplanner_node + pci_trigger + synthetic feeder in one container.
# Acceptance: /gbp/trajectory carries a non-empty path (task-book first-stage
# gate: build + consume cloud/odom/TF + emit trajectory).
set -o pipefail
source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash
pkill -x gbplanner_node 2>/dev/null
pkill -f '/pci_trigger_node' 2>/dev/null
sleep 1

/ws/install/lib/gbplanner_node/gbplanner_node --ros-args \
  --params-file /src/gbplanner_node/config/sim_gbplanner.yaml \
  > /tmp/gbp_node.log 2>&1 &
sleep 4
/ws/install/lib/gbplanner_node/pci_trigger_node --ros-args \
  -p trigger_period_sec:=3.0 -p frame_id:=world \
  > /tmp/pci.log 2>&1 &

python3 /src/gbplanner_node/test/m4_feeder.py 60
RC=$?
echo "=== gbplanner_node log tail ==="
grep -vE "type hash|USER_DATA" /tmp/gbp_node.log | tail -12
echo "=== pci log tail ==="
grep -vE "type hash|USER_DATA" /tmp/pci.log | tail -4
pkill -x gbplanner_node; pkill -f '/pci_trigger_node'
exit $RC
