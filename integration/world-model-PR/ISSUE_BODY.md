## A. SLAM backend crashes on startup under ROS 2 Humble: `ModuleNotFoundError: No module named 'tomllib'`

Running the `exploration` task on Humble (Ubuntu 22.04, Python 3.10) blocks immediately.
The SLAM backend log shows:

```
ModuleNotFoundError: No module named 'tomllib'
```

`tomllib` is only in the standard library from Python **3.11**. Humble ships Python
**3.10**, so the top-level `import tomllib` in:

- `navlab/common/toml_values.py`
- `navlab/sim/companion/runtime/config.py`

raises at import time. `navlab.common.slam.config` imports `navlab.common.toml_values`,
so the SLAM node (`navlab.common.slam.cli`) dies on startup. With SLAM down there is no
`/slam/odom`, `/tf`, or `/scan`, the controller stays `waiting_for_pose`, and every probe
times out (`rc=20`). This is the **primary** reason the exploration run does not come up
on Humble.

**Fix:** fall back to `tomli` (identical `load`/`loads` API) when `tomllib` is missing,
and declare `tomli` as a dependency for Python < 3.11. (See accompanying PR.)

## B. Generated exploration runtime script does not compile (independent latent bug)

`orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl`
has a doubled percent in the modulo expression:

```python
command = dict(pattern[goal_index %% len(pattern)])
```

The template is rendered by `text/template` and written straight to disk by
`writeGeneratedScript` (no `fmt.Sprintf` pass), so `%%` reaches the generated file
verbatim and `python3 -m py_compile` raises `SyntaxError` at that line.

Note this is **separate from and downstream of** issue A: even with SLAM healthy, the
`navlab_exploration_workflow` node would fail to parse. (Other runtime templates use a
single `%` and are unaffected.) **Fix:** single `%`.

## C. `frontier_lite` is an open-loop motion pattern, not an exploration policy

Independent of the two bugs above, the default `frontier_lite` strategy makes no use of
the map. Its decision core is:

```python
pattern = [
    {"linear_x_mps": speed,       "yaw_rate_radps": 0.0},
    {"linear_x_mps": speed * 0.6, "yaw_rate_radps": 0.20},
    {"linear_x_mps": speed,       "yaw_rate_radps": -0.12},
]
command = dict(pattern[goal_index % len(pattern)])
```

`goal_index` advances on an elapsed-time counter; the workflow subscribes only to
controller status and `/slam/odom`, never to an occupancy grid. The review topic even
publishes `"source": "bounded_lite_pattern"`. This is fine as a control-chain smoke test,
but cannot adapt to the environment.

**Proposal:** add an optional, map-aware strategy that selects motion by information gain
(the GBPlanner idea — Dang et al., arXiv:2201.07067), keeping `frontier_lite` as default.
A first, intentionally simple ROS 2-native version is in the accompanying PR
(`gbplanner_gain`, a 2D occupancy-grid prototype). Happy to iterate on the shape (it is
explicitly not the full graph-based 3D planner).
