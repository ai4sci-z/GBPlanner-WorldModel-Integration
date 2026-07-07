#!/usr/bin/env bash
# clean 分支提交:探针观测预算三连修(C类/B类根治,B16 同族)
set -e
CLEAN=/home/ai4s/ws-clean/world-model
cd "$CLEAN"
git add orchestration/sim/internal/tasks/helpers/runtime_specs.go \
        orchestration/sim/internal/tasks/runtime_specs.go \
        orchestration/sim/internal/tasks/helpers/templates/python/ros_probe.py.tmpl
git commit -m "fix(sim): probe observation budgets must cover task completion and DDS discovery

Three related probe-budget calibration fixes (same family as the earlier
frame-contract 45s budget fix):

1. exploration probe status budget 35s -> 90s (runtime_specs.go helpers):
   probes launch concurrently with services, so a 35s ok=true wait closed
   before slower-converging runs finished the 26s exploration window that
   starts only after ~45s of bootstrap/takeoff readiness. Measured: passing
   runs sampled ok at 37s (border), failing runs exhausted the budget while
   the workflow later completed legitimately.

2. exploration probe container ceiling 90s -> 150s (tasks/runtime_specs.go):
   the container deadline must strictly exceed the in-script budget or the
   probe is killed as 'context deadline exceeded' before it can report.

3. ros_probe type-discovery loop: use the full probe budget instead of the
   2s TOPIC_SAMPLE gate (templates/python/ros_probe.py.tmpl). Type discovery
   for late-joining participants is subject to the same slow DDS propagation
   as endpoint matching (micro-ROS agent topics measured at ~29s); the 2s
   gate starved the 45s message-wait budget and made /ap/v1/pose/filtered
   sampling flaky (measured: failed samples bail at latency=2.2s).

go build/vet/test green.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git log --oneline -n 2
