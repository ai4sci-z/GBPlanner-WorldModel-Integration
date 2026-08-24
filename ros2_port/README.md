# ros2_port — GBPlanner ROS 2 原生迁移(隔离工作区)

> 路线切换后新增(2026-07-08)。**桥接历史资产不动**,ROS 2 port 全部落在本目录隔离。
> 主线任务书:[../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md](../docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md)。
>
> **当前 M5-c 证据快照（2026-08-24）**：M5 仍为进行中，不能进入 P2。GBPlanner
> `32f269f` + WorldModel `6e48597` 的最终同 SHA external 样本只有 2/2 PASS，不足以
> 构成冻结分母；WorldModel `6e48597` 的 `frontier_lite` cohort 为 4/6 PASS，随后
> `dc41bc3` 修复了其中一个完成状态未闩锁问题，但未消除真实返航失败。两种策略的
> `accepted_goals` 语义不同，不能直接比较该数值；所有成功降落样本的下降曲线审计仍
> 失败，AP LAND 当前只把它当审计项，不能宣称下降率安全已验证。完整样本、失败和硬门见
> [M5-c cohort 证据](../docs/M5c_cohort_2026-08-24.md)。下一步必须固定
> `32f269f` + `dc41bc3` 重建分母、实跑 terminal failure 安全收尾，并解决下降曲线证据。
>
> **历史施工流水（截至 P1-2 首次 PASS；以下“当前候选”等仅指当时停点）**：
> M1 msgs ✅ / M2 voxblox ✅(五切片全过)/ M3 core 剥离 ✅(12k 行,单测 4/4;
> "3D 行为等价"未证,Review 002 判 NOT PROVEN)/ M4a 合成冒烟 ✅(M4b 真场景 open-loop 未测)/
> **M5 P1-2 ✅ 直连闭环已通过;M5-c 多 run oracle/同口径对比仍未完成**。首次固定 SHA run
> `20260824T033655.765292080Z` 因误接旧 2D `/cloud_in` 仅形成 1 顶点/0 边。
> 第二次 run `20260824T035607.451295836Z` 已用 `/wm/cloud3d` 恢复真实 3D 建图与规划
> (RRG 最大 489 顶点/2944 边、轨迹最大 23 点),但同一任务窗口内
> `accepted_goals=0`、summary/probe/返航降落均未通过,所以仍是 FAIL。唯一一次
> `WP REACHED` 出现在 rosbag/任务窗口结束约 25 秒后,不得计入验收。现场证据还表明
> PCI 在 `/gbp/enable` 前发布路径且周期刷新路径,反复重置 adapter 的航点索引。
> 当前工作树候选修复改为:规划里程计和 `map -> base_link` 统一取
> `/external_nav/odom` 的 x/y/orientation 与 fresh FCU EKF z、PCI 等待 enable 并在首条非空路径后停止、任务结束
> 立即停止宿主栈。候选补丁已通过 Python 27/27、11 包 Jazzy 构建、core 4/4、node
> 3/3 和 M4 `TRAJ_POINTS=11`(`VERIFY_RC=0`)。第三次 run
> `20260824T043724.213476420Z` 使用可复现镜像 `e7d28dd...`,实证 3D topic、enable
> 门控、21 点 one-shot 路径均生效,但仍为 `accepted_goals=0`。MCAP 对拍定位到两个新根因:
> adapter 在 0.35m 才校准坐标旋转,而首航点仅 0.32m,错误 fallback 造成校准死锁;
> one-shot 路径又在 30s 被主动判超龄。MCAP 同时推翻了 external-nav 已带高度的假设:
> 首个运动 intent 时 `/external_nav/odom.z=0`,而非真值 FCU EKF 高度为 0.4529m。
> 该轮候选改为 0.10m 起持续校准/0.35m 冻结、active path 寿命覆盖 90s 验收窗,
> 并用 fresh FCU EKF z 显式融合 planning odom/TF。第四次 run
> `20260824T045937.266250321Z` 证明 3D planning 高度成立(`planning_z_max=0.529m`),
> 但仍为 `accepted_goals=0`、路径 0.865m、未返航降落。MCAP 同步证据为
> 单向量旋转估计=`-171.13°`、FCU yaw=`+89.95°`;当前 WorldModel controller 把 intent
> 当机体系 FRD 后再按 yaw 旋到 NED,旧 adapter 又把世界系结果直接当 intent。
> 第五次 run `20260824T052332.574642383Z` 使用镜像 `92898e6f...`,3D 高度、
> voxblox、RRG(411 顶点/2326 边)、16 点 one-shot 与 1.3911m 运动均成立,但仍为
> `accepted_goals=0`。两次 MCAP 共同证明 map/NED 位置数值含轴交换反射(det=-1),
> 强制 det=+1 的单向量“旋转标定”会随运动方向漂移。当前候选已删除该控制路径,
> 改用 `/slam/odom` 的 map→base_link yaw 直接把 map 速度表达成 body FRD,并在 FCU yaw
> 缺失/过期时 fail-closed;新鲜度由 `/mavlink_external_nav/status` 的真实
> `fcu_attitude_age_ms` 与状态消息年龄共同核算,不能用持续更新的 LOCAL_POSITION
> 消息替陈旧 ATTITUDE 续命。第六次 run `20260824T055032.238341323Z`
> 首次达到 1 个真实航点(`path=1.0199m`),证明 body 方向修复有效;但仍未达 3 个航点。
> MCAP 证明 adapter 2Hz 低于 controller 的 `dt<=0.25s` 积分契约,使目标推进速度折半;
> 同时旧 1.5s/2cm `slam_frozen` 在真实低速推进上三次误触发。当前候选改为
> 4Hz 控制节拍和“当前航点连续命令 8s/2cm”停滞闩锁。
> `20260824T074701.195741657Z` 证明窗口首尾净位移仍会把换航点后
> 的制动回撤误判为冻结:窗口内最大位移约 8cm,但首尾仅 1.2cm。
> `887a420` 改为 epoch 起点到窗口内任一样本的最大位移,真正静止仍按
> 8s/2cm fail-closed。随后同一实跑 `20260824T075515.387084602Z`
> (`FEAT_HEAD=887a420`,`WM_HEAD=fd4296f`) 完成 3 个真实航点、4.0871m 路径、
> 0.32648m 返航半径、LAND ACK/mode、touchdown、disarm 和 motors-safe;
> summary=`TASK_STATUS_OK`,acceptance rc=0,因此 P1-2 记 PASS。
> `navlab/official-baseline:jazzy-latest` 是运行镜像,不含
> `ros-jazzy-pcl-ros`,不得用它编译 voxblox/GBPlanner。统一验证入口为
> `runbooks/ros2_port/verify_current_ros2.sh`;M5 运行镜像必须用
> `runbooks/ros2_port/build_m5_stack.sh` 从固定基镜像重建,不得再用 `docker commit`。
> 下文 M1/M2 段落为历史施工记录,保留不动。

## 目录

```text
ros2_port/
  src/
    planner_msgs/            # M1:planner_msgs ROS 2 最小消息/服务包
    voxblox_ros2_minimal/    # M2:voxblox ROS 2 底座(vendored,见下方来源)
  docs/
    m2_scout_1_底座移植质量审计.md   # M2 侦察报告(3 并行审计,构建/移植前必读)
    m2_scout_2_ntnu定制diff审计.md   # 行为等价命门:ntnu tsdf_integrator 定制
    m2_scout_3_jazzy构建配方.md      # Jazzy 依赖清单与构建配方来源
  (build/ install/ log/ 由 colcon 生成,已 .gitignore)
```

## M1:planner_msgs 最小集

**只迁最小闭环**(不迁 13 msg + 24 srv + 1 action 全家桶)。当前集 = 核心规划服务 `PlannerSrv` + 它依赖的模式枚举:

| ROS 2 文件 | 迁自 ROS 1 | 说明 |
|---|---|---|
| `srv/PlannerSrv.srv` | `planner_srv.srv` | 核心:请求规划、返回 `geometry_msgs/Pose[]` 路径 |
| `srv/PlannerSetPlanningMode.srv` | `planner_set_planning_mode.srv` | 设置 manual/auto 规划模式 |
| `srv/PlannerHoming.srv` | `planner_homing.srv` | 请求回家最短路径 |
| `msg/PlanningMode.msg` | `PlanningMode.msg` | basic/narrow/adaptive 探索模式枚举 |
| `msg/BoundMode.msg` | `BoundMode.msg` | 碰撞检查 bound 模式枚举 |
| `msg/TriggerMode.msg` | `TriggerMode.msg` | PCI 触发模式枚举 |
| `msg/ExecutionPathMode.msg` | `ExecutionPathMode.msg` | 执行路径模式枚举 |
| `msg/PlannerStatus.msg` | `PlannerStatus.msg` | 规划器状态(聚合以上枚举) |

**依赖**:`std_msgs`(`Header`)、`geometry_msgs`(`Pose`/`Point`)。**不迁** `actionlib_msgs`(无 action)。

### ROS 1 → ROS 2 迁移记录(诚实标注)

- **文件名 PascalCase**:rosidl 要求接口文件 CamelCase,故 3 个服务由 snake_case 重命名(`planner_srv`→`PlannerSrv` 等)。**消息/服务字段内容逐字保持**,仅类型名大小写变化;桥接已废、无 ROS 1 互操作需求,采 ROS 2 惯用命名。
- **`Header` → `std_msgs/Header`**:ROS 2 不再隐式解析裸 `Header`。
- **同包引用用裸名**:`PlannerStatus.msg` 内 `TriggerMode trigger_mode` 等,rosidl 自动解析同包类型。
- **构建系统**:catkin `message_generation` → ament_cmake + `rosidl_default_generators`;`package.xml` format 2 → format 3。
- **常量改名 UPPER_SNAKE_CASE**:rosidl 强制常量命名 `[A-Z][A-Z0-9_]*`,ROS 1 的 `kManual/kAuto/kForward` 等 kCamelCase **直接报错拒编**(实测),全部改为 `K_MANUAL/K_AUTO/K_FORWARD` 等;**常量值逐字保持**,调用侧迁移时需同步改名(已在各 .msg 顶部注释标注)。

## 构建(必须在 ROS 2 Jazzy 环境)

> ⚠️ 历史记录(WSL 期)。2026-07-13 已迁移到原生 Ubuntu 24.04;容器构建方式仍有效。

本机 WSL 原生是 Ubuntu 22.04(Jammy),**无原生 Jazzy**;项目 Jazzy 只在 docker 镜像里。故 colcon build 在 jazzy 容器内进行,挂载本目录:

```bash
# 在 WSL:把 ros2_port 挂进 jazzy 容器构建
docker run --rm -v <ros2_port 绝对路径>:/ws -w /ws <jazzy镜像> \
  bash -lc "source /opt/ros/jazzy/setup.bash && colcon build && \
            source install/setup.bash && \
            ros2 interface show planner_msgs/srv/PlannerSrv"
```

验收(M1):`colcon build` 通过 + `ros2 interface show planner_msgs/srv/PlannerSrv` 可打印 + 无 ROS1/catkin/actionlib 依赖。构建证据见 [../runbooks/ros2_port/](../runbooks/ros2_port/)(若已生成)。

## M2:voxblox ROS 2 底座(✅ 已收口 2026-07-14)

**vendored 来源**:[snt-arg/voxblox_ros2_minimal](https://github.com/snt-arg/voxblox_ros2_minimal) @ **d08e9d4**(2025-12-01,upstream HEAD),剥离 .git 整树收入 `src/voxblox_ros2_minimal/`(2.8MB,9 包:voxblox core / voxblox_ros / voxblox_msgs / voxblox_rviz_plugin / voxblox_skeleton + vendored eigen_checks / minkindr / minkindr_conversions / xmlrpcpp)。选型依据 [../docs/ros2迁移_voxblox选型_2026-07-07.md](../docs/ros2迁移_voxblox选型_2026-07-07.md);后续对底座的全部修改都在本仓以独立 commit 留痕(=我们的维护 fork)。

**切片计划与状态**(侦察依据 `docs/m2_scout_*.md`):

| 切片 | 内容 | 状态 |
|---|---|---|
| 1 | **纯净底座 Jazzy 全量构建**(零源码改动,复刻 Gabriele CI 口径) | ✅ 9/9 包 2min27s,COLCON_RC=0;6 executables;esdf_server 冒烟能跑(证据 [../runbooks/ros2_port/m2_build_evidence.txt](../runbooks/ros2_port/m2_build_evidence.txt)) |
| 2 | 维护补丁:删 voxblox_ros 幽灵依赖 voxblox_rviz_plugin;采纳 Gabriele b5c3911(rclcpp 先 init+auto-declare,修 gflags 吃 --ros-args,冒烟已实锤该 bug)并补齐其漏掉的 esdf/intensity server node | ✅ 最小集 7 包成立(rviz_plugin 不再被拖入);9/9 全量 rc=0;**参数管道 E2E 实证:`ros2 param get /voxblox world_frame`→`map`**,弃用警告消失(证据 [../runbooks/ros2_port/m2_build2_evidence.txt](../runbooks/ros2_port/m2_build2_evidence.txt)) |
| 3 | **行为等价补丁**:ntnu dev/noetic 的 tsdf_integrator 定制移植(3 新权重字段+删 sparsity+fast 提前终止)+ ros_params 对齐 + test_sdf_integrators 单测 | ✅ 补丁=`git diff 8d1b843 dev-noetic`(原件 [../runbooks/ros2_port/ntnu_tsdf_integrator.patch](../runbooks/ros2_port/ntnu_tsdf_integrator.patch),19/20 hunk 干净套上+1 个 header hunk 手补虚函数声明);ros_params 三参数换血(clearing_ray_weight_factor/weight_ray_by_range/use_symmetric_weight_dropoff 进,sparsity 两参数出);**gtest 10/10 PASSED**+sparsity 符号零残留(证据 [../runbooks/ros2_port/m2_build3_evidence.txt](../runbooks/ros2_port/m2_build3_evidence.txt)) |
| 4 | oracle 对拍:同点云 ROS1(ntnu dev/noetic)vs ROS2,save_map 层文件按体素查询比对 | ✅ **TSDF 双积分器全 PASS**(harness=[oracle_cmp/](oracle_cmp/),输入逐字节一致 SHA 互证):**simple=46/46 块、35,323/35,323 观测体素零差、距离场 RMS 1e-4**;fast(GBPlanner 实际用)=mismatch 2/34,506(0.0058%,竞态噪声)。路上抓到并修掉真移植 bug:min_time 节流 1s 无操作(from_seconds 静态工厂误用)+ 实测纠正订阅名为私有名 `/voxblox_node/pointcloud`。证据 [../runbooks/ros2_port/m2_oracle_cmp_evidence.txt](../runbooks/ros2_port/m2_oracle_cmp_evidence.txt) |
| 5 | M2 收尾:ESDF 对拍 + world-model 场景建图(订 /wm/cloud3d 或 lidar3d)+ RViz2 可见 | ✅ ESDF oracle 对拍 PASS(RMS 2.5e-05)+ 场景建图 3.0MB/18,202 体素 + RViz2 截图(feat `404ac67`/`8fba00a`) |

**构建配方**(禁 rosdep——package.xml 有 ROS1 时代 key):deps 镜像 [../runbooks/ros2_port/m2_deps.Dockerfile](../runbooks/ros2_port/m2_deps.Dockerfile)(镜像名 `voxblox_ros2_deps:jazzy`,apt 清单源自 Gabriele Jazzy CI),构建脚本 [../runbooks/ros2_port/m2_build.sh](../runbooks/ros2_port/m2_build.sh)。

**已知陷阱**(详见侦察报告):GBPlanner yaml 的 `sparsity_compensation_factor=100` 在 ethz 血统底座上会激活 ×100 权重发散(ntnu 下是死参数)——切片 3 前禁止直接套 GBPlanner 配置;xmlrpcpp 是 ROS1 参数残留死路(仅 `use_tf_transforms=false` 分支),GBPlanner 用 True 不受影响,暂留后除。

## M3-M5(状态见顶部横幅与 main CURRENT_STATUS)

- **M3 ✅(feat `e61052d`)**:核心 12,143 行剥离为 ament 库(`src/gbplanner_core/`),零 `ros/ros.h`,单测 4/4。
  口径纪律(Review 001 P1-6):只能说 **ROS1-free / node-wrapper-free**,不能说 "ROS-free"
  (接口仍依赖 ROS2 消息/tf2/voxblox_ros);"3D 算法行为等价"未证,需 ROS1 oracle 3D fixture 对拍。
- **M4a ✅(feat `be7d6e0`)**:节点壳 `src/gbplanner_node/` + 最小 PCI 触发,合成场景 RRG 出 12wp 轨迹。
  PCI 替身只是 smoke 工具(Review 002 §13.1),恢复 M5 前须另做 planning coordinator。
- **M5 P1-2 ✅ 直连闭环通过；M5-c 🔵 进行中**：当前证据与硬门以
  [M5-c cohort 证据](../docs/M5c_cohort_2026-08-24.md)为准。最终高度口径 external
  同 SHA 仅 2/2 PASS；`frontier_lite` 冻结 cohort 为 4/6 PASS，且存在真实返航失败。
  `accepted_goals` 语义不一致、terminal failure 安全收尾未实跑、AP LAND 下降曲线
  仅审计且所有成功样本仍为 false，因此不能宣布 M5-c 完成，也不得进入 P2。
- **P1-2 历史调试记录（截至首次 PASS）**：`ea80713` 已恢复 adapter z 闭环;首次 fixed-SHA run
  `20260824T033655.765292080Z` 证明旧 2D 点云入口错误。第二次 run
  `20260824T035607.451295836Z` 证明 `/wm/cloud3d`、SDF 外参和非平凡 3D RRG 已恢复,
  但因规划/执行时序与周期路径刷新,同一窗口仍为 `accepted_goals=0`,不得计作 PASS。
  随后候选曾尝试统一 `/external_nav/odom` 高度到 `/gbp/planning_odom` 与规划 TF,
  但第三次 run 的 MCAP 已证明该高度仍为 0;PCI 等待 enable、首条非空路径后
  one-shot 停止的修复则已实证生效。`validate_m5_run.py` 继续要求
  同一 run 的最终 summary `ok=true`、正常返航降落和 RRG/voxblox/trajectory/adapter/FCU
  五类证据全部成立,并新增 3D planning odom/TF 与 PCI one-shot 证据;任一失败仍 rc=20。
  第三次 run `20260824T043724.213476420Z` 已验证 PCI 修复但仍 0 accepted goals;
  当时 MCAP 曾被解释为 per-run map→NED 旋转需提前估计;第五次 run 已进一步证明
  该模型本身错误,因为实际数值关系含 det=-1 轴交换反射,不是 det=+1 旋转;
  exploration 的 `/external_nav/odom.z` 也实际为 0。高度候选因此使用 fresh
  `/navlab/fcu/local_position_pose` 的 FCU EKF z(非 simulator truth),并把验收升级为
  `planning_z_max>0.05m`;不得把“planning_odom 有消息”冒充 3D 高度已成立。
  第四次 run `20260824T045937.266250321Z` 已通过该高度门,但仍 0 accepted goals。
  MCAP 与当前 fcu_controller 源码共同证明 intent 已是机体系 FRD 契约:controller
  会按 FCU yaw 转到 LOCAL_NED。第五次 run `20260824T052332.574642383Z` 在真实
  3D/RRG/16点轨迹成立后仍 0 goals;在线角从 80° 漂到 172°、-150°、-75°。
  两次 bag 的 `yaw_map≈0.2°/yaw_ned≈89.95°` 与位置位移共同证明数值关系近似
  `NED=(map_y,map_x)`。当前候选直接按 map→base_link 姿态输出 body forward/right,
  删除位置标定闭环,并保留真实 FCU yaw freshness 门;验收门槛未放宽。
  最终直连实跑 `20260824T075515.387084602Z` 固定 `887a420`/`fd4296f`,
  adapter 记录 3 次真实 `WP REACHED`,gate 后 `blockers=[]`,RRG 368 顶点/
  2259 边、17 点 trajectory、4.0871m 路径;实测返航至 0.32648m < 0.35m,
  随后 LAND ACK/mode、touchdown、disarm、motors-safe 全部成立。同一 MCAP 为
  150.174s/174438 messages,summary=`TASK_STATUS_OK`,M5 acceptance rc=0。
  这只完成 P1-2 直连闭环;任务书 M5-c 要求的至少 3 run 与 oracle/
  frontier_lite 同口径对比仍未完成,不得把整个 M5 写成完成。
