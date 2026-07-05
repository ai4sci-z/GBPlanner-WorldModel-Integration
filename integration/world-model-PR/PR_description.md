# PR: fix exploration script compile bug + add map-aware `gbplanner_gain` strategy

> Paste the title and body below into the GitHub "Open a pull request" form.
> Base: `SZ-surveying/world-model` `main` · Compare: `<your-fork>:feat/gbplanner-gain-exploration-strategy`

## Title

```
exploration: fix generated-script compile bug and add map-aware gbplanner_gain strategy
```

## Body

```markdown
## Summary

Two related changes to the exploration workflow (`orchestration/sim`):

1. **Bug fix** — the generated `exploration_workflow_runtime.py` does not compile.
2. **Feature** — add an optional, map-aware exploration strategy `gbplanner_gain`,
   alongside the existing default `frontier_lite` (which is left unchanged).

Fixes #<ISSUE_NUMBER>.

## 1. Bug: generated exploration script fails to compile

`exploration_workflow_runtime.py.tmpl` contains:

```python
command = dict(pattern[goal_index %% len(pattern)])
```

The template is rendered with `text/template` and written straight to disk by
`writeGeneratedScript` (no `fmt.Sprintf` pass), so the doubled percent reaches the
generated file verbatim. The result is invalid Python:

```
$ python3 -m py_compile exploration_workflow_runtime.py
  File "exploration_workflow_runtime.py", line 147
    command = dict(pattern[goal_index %% len(pattern)])
                                       ^
SyntaxError: invalid syntax
```

Because the whole module fails to parse, the `navlab_exploration_workflow` node
cannot start. Fix: use a single `%`. After the fix the generated script passes
`python3 -m py_compile`.

## 2. Feature: map-aware `gbplanner_gain` strategy

Today the default `frontier_lite` strategy produces motion from a fixed 3-step
pattern indexed by an elapsed-time counter (`pattern[goal_index % len(pattern)]`)
and **does not subscribe to any map** — it is effectively an open-loop control-chain
smoke test rather than an exploration policy (the review topic even labels its source
`bounded_lite_pattern`).

This PR adds an **optional** strategy that implements the core idea of GBPlanner
(Dang et al., *Graph-based subterranean exploration path planning*, J. Field Robotics 2020 (original GBPlanner paper)):
read the SLAM occupancy grid and move toward the direction of highest information gain.

When `strategy == "gbplanner_gain"`:
- the workflow subscribes to `map_topic` (`nav_msgs/OccupancyGrid`, default `/map`);
- it ray-casts in 24 directions (3-ray fan each), counts reachable **UNKNOWN** cells
  as a 2D volumetric-gain proxy, applies a turn penalty `score = gain − k·Δheading`;
- it steers toward the best-scoring heading via `setpoint/intent`, and reports the
  chosen heading/gain on the existing review topics.

### Design notes / scope
- **Additive and opt-in.** The default `frontier_lite` path is unchanged; the new
  helper code is rendered unconditionally but only *executed* when the strategy is
  `gbplanner_gain`, and the map subscription is only created in that case.
- This is a **2D, ROS2-native** first step (no `ros1_bridge`, no 3D voxblox). It is
  intended as the decision-layer integration point; a full GBPlanner stack would
  swap the gain evaluator for the upstream ROS1 planner over a bridge.
- Acceptance gates (`min_accepted_goals`, `min_path_length_m`) are untouched.

## New / changed config

`ExplorationWorkflowSpec` gains `MapTopic` (default `/map`), surfaced in the rendered
spec as `map_topic`. To use the new strategy, set in the exploration runtime config:

```toml
[exploration_gate.runtime]
strategy  = "gbplanner_gain"
map_topic = "/map"
```

## Verification

- `go build ./...`, `go vet ./internal/tasks/helpers/`, `go test ./internal/tasks/helpers/` — all pass.
- Both strategies render to scripts that pass `python3 -m py_compile`
  (`frontier_lite` and `gbplanner_gain`).

## Not included

- End-to-end simulation run (requires the full ArduPilot + Gazebo stack). The change
  is verified at the unit/render/compile level; reviewers with the full stack can
  exercise `strategy = "gbplanner_gain"` directly.
```
