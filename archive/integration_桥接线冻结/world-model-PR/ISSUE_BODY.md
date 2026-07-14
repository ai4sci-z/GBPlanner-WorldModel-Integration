> 🚧 **DRAFT — 请勿提交(2026-07-06 晚更新)**
>
> 阻断原因(已更新):exploration **已端到端全绿**(run `20260706T130626`);现按用户指示**等真 GBPlanner 桥接集成跑通后统一定稿提交**。定稿前需吸收 B16(探针双根因)与基线定档数据。
> **事实源** = [`docs/world-model端到端Bug台账_给作者PR.md`](../../docs/world-model端到端Bug台账_给作者PR.md)。旧版(只讲 tomllib/%%/frontier_lite)已作废。

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

### 6. Probe sampling bugs (B16, fixed; may be filed separately)
- `frame_contract_probe` missed `/tf_static` (published **transient_local/latched**; the
  probe subscribed with `qos_profile_sensor_data` = VOLATILE) → fixed by subscribing with
  the publisher's introspected QoS.
- It also missed `/ap/v1/pose/filtered`: measured with a controlled experiment, a
  late-joining subscription takes **~29 s of DDS endpoint discovery** against the
  ArduPilot micro-ROS agent before the publisher matches (data arrives within 40 ms once
  matched), while the probe's per-topic budget was ~2 s and the container timeout 30 s →
  fixed with a 45 s per-topic budget + 90 s container timeout (mirroring exploration_probe).
- With B16 the exploration task reached **TASK_STATUS_OK end-to-end** (run
  `20260706T130626`). Remaining observation: `accepted_goals` is timing-driven
  (`ready_elapsed / (window/3)`), so startup latency eats into the fixed 26 s window and
  the gate passes only ~40% of runs — worth considering for the gate design.
