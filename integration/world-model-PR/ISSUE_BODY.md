> 🚧 **DRAFT — 请勿提交(2026-07-06 重写)**
>
> 待 exploration 端到端全绿后再定稿提交。**事实源** = [`docs/world-model端到端Bug台账_给作者PR.md`](../../docs/world-model端到端Bug台账_给作者PR.md)。
> 旧版(只讲 tomllib/%%/frontier_lite)已作废——那不是作者 jazzy 仓库的核心问题。

---

## Title (draft): `exploration` task cannot reach takeoff end-to-end on a fresh clone (jazzy)

Reproduced from a fresh upstream clone (`09a5aa4`) on ROS 2 jazzy. Running
`navlab-sim run exploration --live-preflight` hits a chain of blockers that stop the
run cold for **any** user on **any** OS — i.e. these look like the `exploration` path
has never been run end-to-end, not an environment problem. Each is small and
fixable (patches available); listed most-fundamental first.

### 1. Generated exploration runtime script does not compile (`%%`)
`templates/python/exploration_workflow_runtime.py.tmpl` renders
`pattern[goal_index %% len(pattern)]`. It is rendered by `text/template` and written
straight to disk (no `fmt.Sprintf`), so `%%` reaches the file verbatim and
`python3 -m py_compile` raises SyntaxError. → single `%`.

### 2. ROS 2 rejects empty `name:=` launch args
The SLAM backend command builder emits every launch arg including empty values; ROS 2
launch rejects an empty `name:=` (e.g. an unset cartographer config dir). → skip empties.

### 3. SLAM IMU self-echo aborts cartographer
The IMU sanitising bridge's `output` topic defaults to `/imu`, identical to its
`source` → it re-feeds itself → cartographer aborts with "Non-sorted data". → the
bridge output must be a distinct topic (e.g. `/navlab/slam/imu`).

### 4. Rangefinder param-name drift silently disables the height source
The external-nav profile/templates set `RNGFND1_MIN_CM / MAX_CM / GNDCLEAR`. ArduPilot
4.5 renamed these to `RNGFND1_MIN / MAX / GNDCLR` (cm→m); current firmware **silently
ignores** the old names, so `MIN` falls back to 0.20 m and the ~0.095 m ground reading
is rejected ("Rangefinder: No Data"). With `EK3_SRC1_POSZ=2` (rangefinder) the vertical
source then never initialises. → use the new names.

### 5. Takeoff deadlock: exploration intent overrides the GUIDED climb
`fcu_controller_runtime.py.tmpl` forwards the exploration `setpoint/intent` to the FCU
(cmd_vel + local-position setpoint) **unconditionally**. Before takeoff that intent is a
stationary "hold"; under GUIDED it overrides the takeoff climb (CTUN.DAlt pinned to the
current altitude), so the vehicle never leaves the ground → takeoff never reports ok →
controller never becomes ready → the workflow keeps emitting hold → **deadlock**. This is
a classic critical-section / phase-ordering race. → gate forwarding on takeoff completion
(`bootstrap_ready`).

With 1–5 fixed (and no parameter hacks) the vehicle physically lifts off on jazzy:
run `20260706T110405`, BIN ground-truth SIM altitude +0.760 m, motor PWM peak 1950.

### Still open (probe/tuning, may be filed separately)
- `frame_contract_probe` misses `/tf_static` (published **transient_local/latched**; the
  probe subscribes with `qos_profile_sensor_data` = VOLATILE, so it never sees the
  retained sample) and `/ap/v1/pose/filtered` (published volatile/best_effort — QoS is
  already compatible, so this is a timing/type issue, not durability).
- `accepted_goals` = 2 (< min 3) in that run — exploration-quality variance.
