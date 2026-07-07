#!/usr/bin/env bash
# clean 分支提交:探针修复⑤(完整)+⑥(半成品,诚实标注真源头待改)
set -e
CLEAN=/home/ai4s/ws-clean/world-model
cd "$CLEAN"
git add orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl \
        orchestration/sim/internal/tasks/helpers/runtime_specs.go \
        orchestration/sim/internal/tasks/runtime_specs.go
git commit -m "fix(sim): probe publisher-info retry + tf_static latched fallback; WIP consumed-route pose sampling

Fix 5 (complete, tested): the publisher-info query used for QoS introspection
races DDS discovery like everything else; an empty result silently fell back
to a volatile subscription and missed latched topics (/tf_static, rc=124).
Retry the query within a small budget and default to TRANSIENT_LOCAL for
tf_static-like topics when it stays empty. Verified: next run sampled
tf_static fine (failure moved on, see below).

Fix 6 (WIP, honest note): /ap/v1/pose/filtered sampling still flakes because
micro-ROS agent endpoint matching has an unbounded tail (measured 29s..97s+)
and the pipeline does not actually consume that DDS debug stream - pose is
consumed via the MAVLink-republished /navlab/fcu/local_position_pose. The
FCUPoseTopic change in helpers/runtime_specs.go:459 is NOT effective at
runtime: the rendered probe still gets the old topic via
runtime_artifacts.go:722 spec.FCUPoseTopic = frame.FCUPoseTopic, whose value
comes from config/defaults.go frame-contract default. Next step: change that
default (+test sync) and re-verify.

Fresh-run evidence with fix 5: exploration gate passed 4/4 verification runs
(probe-budget fixes benefit the frontier baseline too); one full
TASK_STATUS_OK green (20260707T134823).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -n 2
