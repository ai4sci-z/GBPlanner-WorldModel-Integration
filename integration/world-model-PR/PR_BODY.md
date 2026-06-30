## Summary

Three changes to the `exploration` workflow (`orchestration/sim` + `navlab` runtime),
two bug fixes and one optional feature:

1. **fix (primary):** SLAM crashes on Humble/Python 3.10 because `tomllib` is 3.11+.
2. **fix:** the generated exploration runtime script does not compile (`%%`).
3. **feat:** add an optional, map-aware `gbplanner_gain` strategy (default `frontier_lite`
   is unchanged).

Fixes #<ISSUE_NUMBER>.

The two fixes are independent of the feature and are the high-confidence part of this PR;
they can be cherry-picked on their own. The feature is an intentionally simple prototype
(details below).

## 1. fix: `import tomllib` → fall back to `tomli` on Python < 3.11  (primary runtime blocker)

On Humble (Ubuntu 22.04, Python 3.10), `navlab/common/toml_values.py` and
`navlab/sim/companion/runtime/config.py` fail at import with
`ModuleNotFoundError: No module named 'tomllib'` (it is 3.11+ stdlib).
`navlab.common.slam.config` imports `toml_values`, so the SLAM backend dies on startup →
no `/slam/odom`, `/tf`, `/scan` → controller stuck `waiting_for_pose` → all probes `rc=20`.

Fix: `try: import tomllib / except ModuleNotFoundError: import tomli as tomllib`
(`tomli` has the same `load`/`loads` API) and declare `tomli` for Python < 3.11.

## 2. fix: generated exploration script compile bug (`%%` → `%`)

`exploration_workflow_runtime.py.tmpl` renders `pattern[goal_index %% len(pattern)]`.
The template is rendered with `text/template` and written straight to disk by
`writeGeneratedScript` (no `fmt.Sprintf` pass), so the generated script keeps `%%` and
fails `python3 -m py_compile` (SyntaxError). Single `%` fixes it. This is independent of
and downstream of #1.

## 3. feat: optional map-aware `gbplanner_gain` strategy

Today `frontier_lite` drives motion from a fixed 3-step pattern indexed by an elapsed-time
counter and subscribes to no map (its review topic is labeled `bounded_lite_pattern`).
This PR adds an **opt-in** strategy inspired by GBPlanner (Dang et al., arXiv:2201.07067):
when `strategy == "gbplanner_gain"` the workflow subscribes to `map_topic`
(`nav_msgs/OccupancyGrid`, default `/map`), ray-casts in 24 directions, counts reachable
UNKNOWN cells as a 2D volumetric-gain proxy, applies a turn penalty, and steers toward the
best heading.

**Scope / honesty:**
- Additive and opt-in; default `frontier_lite` behaviour is unchanged (the new helper code
  is rendered unconditionally but only executed when the strategy is `gbplanner_gain`, and
  the map subscription is created only then).
- This is a **2D occupancy-grid prototype**, **not** the full GBPlanner (no RRG graph
  search, no 3D voxblox volumetric gain). It is the ROS 2-native decision-layer step; a
  full integration would bridge the upstream ROS 1 planner.
- `ExplorationWorkflowSpec` gains `MapTopic` (default `/map`), surfaced as `map_topic`.

## Verification

- `go build ./...`, `go vet ./internal/tasks/helpers/`, `go test ./internal/tasks/helpers/` pass.
- Both strategies render to scripts that pass `python3 -m py_compile`.
- The `tomllib`→`tomli` fallback was checked in the Humble SLAM container: with the fix +
  `tomli` available, `navlab.common.toml_values` and `navlab.common.slam.config` import
  cleanly (previously `ModuleNotFoundError`).
- Not yet verified end-to-end: a full Gazebo+SITL exploration run on this hardware (heavy;
  the Humble migration has further environment gaps). Reviewers with the full stack can
  exercise `strategy = "gbplanner_gain"` directly.
