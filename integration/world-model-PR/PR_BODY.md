> 🚧 **DRAFT — 请勿提交(2026-07-06 重写)**
>
> 本文是**草稿**,不得直接用于提交 PR。前置条件未满足:
> 1. ❌ **exploration 端到端尚未全绿**——剩 `frame_contract_probe`(`/tf_static` QoS + `/ap/v1/pose/filtered` 时序)与 `accepted_goals` 波动(实测 2<3)。
> 2. ✅ clean diff 已去参数 hack(commit `77d951a`,`CLEAN_REPRO_takeoff_fixes.diff` 已重导为净版)。
> 3. ⏳ 是否拆成 PR-A(通用 bugfix)/ PR-B(`gbplanner_gain` 2D 原型)待定。
>
> **唯一事实源** = [`docs/world-model端到端Bug台账_给作者PR.md`](../../docs/world-model端到端Bug台账_给作者PR.md)。本文所有条目以台账 + 净 diff `CLEAN_REPRO_takeoff_fixes.diff` 为准。旧版(仅 tomllib/%%/gbplanner_gain)已作废。

---

## Summary (draft)

Make the `exploration` workflow reach an actual physical takeoff end-to-end on a
fresh upstream clone (`09a5aa4`), by fixing a chain of real upstream bugs plus one
phase-ordering deadlock. Verified on jazzy: with these fixes (and **no** parameter
hacks) the vehicle physically lifts off — run `20260706T110405`, BIN ground-truth
SIM altitude +0.760 m, motor PWM peak 1950, CTUN DAlt 0.655 m, `takeoff.ok=True`.

> Honesty: the **full exploration gate is not yet green** on this hardware
> (`frame_contract_probe` still misses `/tf_static` and `/ap/v1/pose/filtered`;
> `accepted_goals` = 2 < 3 in that run). These are probe/tuning issues, tracked
> separately; the code changes below are the takeoff-path bugfixes.

## Real bug chain (all in `CLEAN_REPRO_takeoff_fixes.diff`, net no-hack, 153 lines)

1. **B1 `%%` → `%`** (`exploration_workflow_runtime.py.tmpl`): `text/template` does
   not `Sprintf`, so `pattern[i %% len]` reaches disk verbatim → generated script
   fails `py_compile` (SyntaxError). Anyone running exploration hits this first.
2. **B3 omit empty launch args** (`backends.py`): ROS 2 (humble & jazzy) rejects an
   empty `name:=` argument; skip empties so the launch file's own default is used.
3. **B6/B7 SLAM IMU echo** (`slam.go` + `defaults.go`): the IMU sanitising bridge
   `output` defaulted to `/imu` = its own `source` → self-feedback → cartographer
   aborts (Non-sorted data). Output topic must differ (`/navlab/slam/imu`).
4. **B14 rangefinder param-name drift** (`navlab_models.go` + parm/tmpl): author uses
   pre-4.5 names `RNGFND1_MIN_CM/MAX_CM/GNDCLEAR`; current firmware silently ignores
   them → `MIN` falls to its 0.20 m default → the 0.095 m sim reading is rejected →
   `EK3_SRC1_POSZ` height source dies. Use `RNGFND1_MIN/MAX/GNDCLR` (cm→m).
5. **B15 takeoff deadlock (key)** (`fcu_controller_runtime.py.tmpl`): `on_setpoint_intent`
   unconditionally forwarded the exploration intent as cmd_vel / local-position
   setpoint. Before takeoff that intent is a stationary "hold" and overrides the
   GUIDED takeoff climb (CTUN.DAlt pinned to current alt) → never lifts off → takeoff
   never ok → controller never ready → workflow keeps emitting hold → **deadlock**.
   Fix = gate forwarding on `bootstrap_ready(state)` (phase-order mutual exclusion).

## feat (opt-in, honest): `gbplanner_gain` strategy

Adds an **opt-in** map-aware strategy (default `frontier_lite` unchanged): subscribes
to `map_topic` (`nav_msgs/OccupancyGrid`, default `/map`), ray-casts 24 directions,
counts reachable UNKNOWN cells as a 2D volumetric-gain proxy, applies a turn penalty,
steers to the best heading.

- **This is a 2D occupancy-grid prototype, NOT the full GBPlanner** (no RRG graph
  search, no 3D voxblox gain). It is the ROS 2-native decision-layer step; full
  GBPlanner integration bridges the upstream ROS 1 planner (see `integration/ros1_bridge/`).

## Explicitly NOT in this PR (reverted, do not re-add)

The 3 parameter hacks that were briefly committed (`79643b9`) and then reverted
(`77d951a`) — **not physically justified, and not needed for takeoff**:
`DISARM_DELAY 0`, `EK3_SRC1_POSZ 1` (baro), `ReadinessTimeoutSec 90`. The vehicle
takes off with the author's originals (rangefinder POSZ=2, disarm safety on).

## Verification (current, real)

- `go build ./...`, `go vet`, `go test ./internal/tasks/helpers/` pass.
- Both strategies render scripts that pass `python3 -m py_compile`.
- Physical takeoff (no hacks): run `20260706T110405` BIN — SIM +0.760 m, PWM 1950.
- **Not green yet**: `frame_contract_probe` (`/tf_static` needs matched
  TRANSIENT_LOCAL QoS; `/ap/v1/pose/filtered` is volatile/best_effort so it is a
  timing/type issue, not QoS) and `accepted_goals` 2<3. See Bug 台账.
