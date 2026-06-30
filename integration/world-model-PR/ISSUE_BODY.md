## A. Generated exploration runtime script does not compile

`orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl`
contains a doubled percent in the modulo expression:

```python
command = dict(pattern[goal_index %% len(pattern)])
```

The template is rendered by `renderHelperTemplate` via `text/template` and written
straight to disk by `writeGeneratedScript` (`os.WriteFile`) — there is **no**
`fmt.Sprintf` pass that would collapse `%%` to `%`. So the generated
`exploration_workflow_runtime.py` keeps the literal `%%`:

```
$ python3 -m py_compile exploration_workflow_runtime.py
  File "exploration_workflow_runtime.py", line 147
    command = dict(pattern[goal_index %% len(pattern)])
                                       ^
SyntaxError: invalid syntax
```

Since the whole module fails to parse, the `navlab_exploration_workflow` node cannot
start. (Other runtime templates use single `%` and are unaffected.)

**Repro:** render the script (e.g. `ExplorationWorkflowRuntimeScript(DefaultExplorationWorkflowSpec(), 13.0)`)
and run `python3 -m py_compile` on the output.

**Fix:** single `%`. (See accompanying PR.)

## B. `frontier_lite` is an open-loop motion pattern, not an exploration policy

Independent of the bug above, the default `frontier_lite` strategy makes no use of the
map. Its decision core is:

```python
pattern = [
    {"linear_x_mps": speed,       "yaw_rate_radps": 0.0},
    {"linear_x_mps": speed * 0.6, "yaw_rate_radps": 0.20},
    {"linear_x_mps": speed,       "yaw_rate_radps": -0.12},
]
command = dict(pattern[goal_index % len(pattern)])
```

`goal_index` advances purely on an elapsed-time segment counter; the workflow
subscribes only to controller status and `/slam/odom`, never to an occupancy grid or
point cloud. The review topic publishes `"source": "bounded_lite_pattern"`, i.e. it
self-describes as a fixed pattern. This is reasonable as a control-chain smoke test,
but it cannot adapt to the environment, so coverage and path quality do not reflect a
real exploration algorithm.

**Proposal:** add an optional, map-aware strategy that selects motion by information
gain (the GBPlanner idea — Dang et al., arXiv:2201.07067), while keeping
`frontier_lite` as the default. A first ROS2-native version is in the accompanying PR
(`gbplanner_gain`): subscribe to the occupancy grid, ray-cast to count reachable
unknown cells (a 2D volumetric-gain proxy), penalise turning, steer toward the best
heading.

Happy to iterate on the API (config keys, topic names) if you'd prefer a different
shape.
