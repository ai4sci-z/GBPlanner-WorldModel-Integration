#!/usr/bin/env bash
# clean 分支提交:EKF/external-nav 参考系修复(3件套)+ external strategy + lidar3d 净增量
set -e
CLEAN=/home/ai4s/ws-clean/world-model
cd "$CLEAN"
git add docker/profiles/navlab-sitl-external-nav.parm \
        orchestration/sim/internal/tasks/helpers/templates/parm/official_external_nav.parm.tmpl \
        orchestration/sim/internal/tasks/runtime_specs.go \
        orchestration/sim/internal/tasks/runtime_specs_test.go \
        orchestration/sim/internal/tasks/runtime_artifacts_test.go \
        orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl \
        orchestration/sim/internal/tasks/helpers/templates/sdf/rangefinder_down_overlay.sdf.tmpl \
        orchestration/sim/internal/tasks/helpers/templates/yaml/bridge_override.yaml.tmpl
git commit -m "fix(sim): align EKF yaw source with external-nav frame; add external strategy + 3D lidar overlay

EKF reference-frame conflict (root-caused via BIN forensics, runs 20260707T03*):
EK3_SRC1_YAW=1 (compass, world frame) + EK3_SRC1_POSXY=6 (external nav, SLAM map
frame) differ by a per-run constant rotation. Stationary flight hides it; real
motion makes the rotated position innovations visible, EKF3 stops aiding
('stopped aiding' -> 'EKF variance: position lost' -> Land failsafe) and the
position estimate runs away (34m in a 5m maze). This also explains the large
path-length variance of frontier_lite baseline runs.

Fix (standard GPS-less external-nav config):
- EK3_SRC1_YAW 1->6 and COMPASS_USE/USE2/USE3=0 in
  docker/profiles/navlab-sitl-external-nav.parm (runtime source; the parm
  template is the test fixture and is kept in sync)
- pass --no-align-yaw-to-fcu to mavlink_external_nav sender in sim specs:
  its argparse default True feeds the FCU's own yaw back to the EKF (circular,
  yaw never corrected); with the flag the true SLAM yaw is sent, making yaw
  and position references consistent.

Also included (bridge integration prerequisites):
- exploration workflow: 'external' strategy = built-in frontier_lite fully
  passive, an out-of-process planner owns intent/status (de-mixed flow)
- net-new lidar3d sensor overlay (360x30 +/-30deg) on its own topic /lidar3d,
  bridged as wm/cloud3d; X2 2D SLAM chain untouched
- go build/vet/test green after each step

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -n 3
