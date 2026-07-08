#!/usr/bin/env bash
# clean branch commit: fix 7 (rosbag required topics ride the consumed route)
set -e
export PATH=/usr/local/go/bin:/usr/bin:/bin
cd /home/ai4s/ws-clean/world-model
git add orchestration/sim/internal/tasks/helpers/rosbag_topic_sets.go
git commit -m "fix(sim): exploration rosbag gate requires consumed-route FCU pose (stage6 fix 7)

Same root cause as the frame_contract fix (ff24087), different organ: the
exploration rosbag recorder hard-required /ap/v1/pose/filtered and
/ap/v1/twist/filtered, but those micro-ROS DDS debug streams have an
unbounded discovery tail and are not on the consumed route - pose is
consumed via the MAVLink-republished /navlab/fcu/local_position_pose.
When discovery flaked, the recorder ended in required_topics_missing and
the whole run went TASK_STATUS_BLOCKED (observed run 20260708T100753:
bag had 463 local_position_pose msgs, both /ap/v1 streams absent).

Move the required set to /navlab/fcu/local_position_pose; the review
recording list still captures the /ap/v1 streams when discoverable.
NavigationTaskRequiredTopics has the same pattern - left untouched (not
on the validation path), noted as debt.

Evidence: go test config/helpers/tasks all green; next live run
20260708T101402 = TASK_STATUS_OK, blockers=[], rosbag recorder completed,
frame_contract ok=True sampling the consumed route.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -n 3
git status --short | head -5
