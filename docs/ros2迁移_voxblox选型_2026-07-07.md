> **[历史调研快照 · 已逐行审计(R003-E0-CORRECT-2 补正,2026-07-18)]** voxblox 选型调研(2026-07-07 时点)。
> 审计改动:①"CURRENT"降为历史快照(网络数据均为检索当日);②§6 回填执行结果(vendored voxblox
> 基底 pin d08e9d4,M2 对拍窄验收 PASS,fast-integrator/3D 分层语义未关闭)。选型结论与理由为当时判断,保留。
> 外部仓库现状未复查(逐行审计不含重新联网检索)。当前状态唯一权威 = [CURRENT_STATUS.md](../CURRENT_STATUS.md)。

# ROS2 迁移:voxblox 选型调研(2026-07-07)

> 状态:**历史调研快照**(检索日期 2026-07-07,联网 WebSearch/WebFetch + GitHub API 实查;仓库星数/push 日期均为当日数据,现已过时)
> 服务对象:任务 #15「GBPlanner ROS1→ROS2 原生移植」中的地图后端选型。
> 结论先行:**首选 = 沿用 voxblox,以 snt-arg/voxblox_ros2_minimal 为底座做 Jazzy 适配(参照 GabrieleSantangelo/voxblox-ros2 的 Jazzy Docker),并与 GBPlanner 实际依赖的 ntnu-arl/voxblox fork 做 diff 合并;ROS1 版留作 oracle 回归。备选 = OctoMap ros2 分支 + dynamicEDT3D。**

---

## 0. 选型约束:GBPlanner 依赖的两个地图 API

GBPlanner 对地图后端的硬依赖只有两条(map_manager 抽象层):

| API | 用途 | 具体需求 |
|---|---|---|
| **A. 增益计算(gain)** | 探索目标评估 | 从候选视点**光线投射**,沿射线逐体素查询三态(unknown / free / occupied),**计数未知体素**。要求:未知态可查询(voxblox 中 = block 未分配或 TSDF weight≈0)、射线遍历高效 |
| **B. 碰撞检查** | 路径/走廊安全验证 | **ESDF 距离查询**(getDistanceAtPosition)或 TSDF 距离+权重的占据盒查询 |

任何替代方案必须同时支撑 A、B,且**行为等价性优先**:gain 的数值分布、碰撞判定的保守程度直接决定探索行为(选哪个 frontier、走哪条路),换语义不同的后端 = 调参全部重来 + 与 ROS1 基线不可对比。

另注:GBPlanner 1.0(unr-arl/gbplanner_ros)README 明确写过"依赖 Voxblox **或 Octomap** 之一",即历史上存在 Octomap 后端路径;但 GBPlanner 2.0(ntnu-arl,gbplanner2 分支)默认且实测均为 voxblox,全部参数按 voxblox 语义调校。

---

## 1. voxblox 官方(ethz-asl/voxblox)ROS2 状态:**无官方移植**

- 仓库:https://github.com/ethz-asl/voxblox (BSD-3-Clause,1,649 star,未归档)
- **最后 push:2024-07-01**(GitHub API 实查)——官方已近两年无提交,处于半停维护状态,open issues 77。
- ROS2 支持请求 Issue #364(2021-04 提出)至今无官方 ROS2 分支:https://github.com/ethz-asl/voxblox/issues/364
- **PR #413「Migrated Voxblox to ROS2」**(https://github.com/ethz-asl/voxblox/pull/413):
  - 作者 @murraylouw,2024-02-29 提交,**至今 open 未合并、无 maintainer review**;
  - 目标 **Humble**(带 devcontainer);
  - 完成度:`tsdf_server_node` + rviz 插件已迁移;**`esdf_server_node` 未完成(编译错误)**,测试未迁移;
  - 作者 fork(https://github.com/murraylouw/voxblox)最后 push 2024-02-29,已停滞。

**结论:官方路线不存在,只能走社区移植或自移植。**

---

## 2. 社区 ROS2 移植 fork 逐个盘点

### 2.1 snt-arg/voxblox_ros2_minimal ⭐ 首选底座

- 仓库:https://github.com/snt-arg/voxblox_ros2_minimal (fork 自 ethz-asl/voxblox)
- 维护方:卢森堡大学 SnT ARG(vs-graphs 项目团队),maintainer = Miguel Fernandez-Cortizas(uni.lu)
- 创建 2025-10-10,**最后 commit 2025-12-01**("make private publishers and service names");关键提交链:2025-10-29 "migration complete, there are some lacking…" → launch 文件 ROS1 XML→ROS2 Python 全迁移
- **包含 tsdf_server / esdf_server 完整实现**(voxblox_ros/src 实查:tsdf_server.cc、esdf_server.cc、intensity_server.cc、simulation_server.cc 及对应 *_node.cc 均在)
- package.xml:`ament_cmake` + `rclcpp`,描述"Voxblox ROS 2 interface",未 pin 具体发行版(Humble/Jazzy 均应可编译,SnT 内部按 Humble 用)
- 许可证:BSD-3-Clause;活跃度:0 star / 5 fork(新仓库,知名度低但代码是完整迁移)
- 诚实边界:作者自述 "there are some lacking"(细节未列),**须以 ROS1 oracle 回归验证移植质量**

### 2.2 GabrieleSantangelo/voxblox-ros2 ⭐ Jazzy 适配参照

- 仓库:https://github.com/GabrieleSantangelo/voxblox-ros2
- **与 2.1 同源**:commit 历史包含 snt-arg 迁移全链(d08e9d4、34cb200 等 miferco97 提交),即"snt-arg 迁移 + 增量"
- 增量:**2026-03-17 三个 commit,含「add Dockerfile and Makefile for CI/CD setup with ROS Jazzy」**——是目前唯一明确挂 **Jazzy** 的 voxblox 移植;另补 cow_and_lady 数据集 launch + static TF
- 包组:voxblox、voxblox_ros、voxblox_msgs、voxblox_rviz_plugin、voxblox_skeleton(比 snt-arg 多 skeleton)
- 许可证 BSD-3-Clause;**最后 push 2026-03-17**;活跃度:0 star / 0 fork(个人仓,不宜直接当上游,取其 Jazzy Dockerfile/Makefile 作适配参照)

### 2.3 murraylouw/voxblox(= 官方 PR #413 源)

- https://github.com/murraylouw/voxblox — Humble;tsdf_server 完成、**esdf_server 未完成**;2024-02 后停滞。仅作迁移改法参考(minkindr 破坏性变更的处理方式有参考价值),不作底座。

### 2.4 Tail-19/Voxblox-ros2(排除)

- https://github.com/Tail-19/Voxblox-ros2 — "ros2 + python3 implementation of Voxblox plusplus"(是 **voxblox++ 语义实例建图**的 Python 复刻,非 voxblox 本体);1 star,最后 push 2024-10-14,**无许可证**。与 GBPlanner 需求不符,排除。

### 2.5 相关但非 ROS2 的 fork(基线参照)

- **ntnu-arl/voxblox**(https://github.com/ntnu-arl/voxblox):GBPlanner 实际依赖的 fork,**最后 push 2025-10-03**(仍在动)。ROS1。**迁移时必须 diff 该 fork 与 ethz-asl master 的差异**(ntnu-arl 有针对 gbplanner 的定制),把差异补丁套到 ROS2 底座上,否则行为等价无从谈起。
- HiroIshida/voxbloxpy(https://github.com/HiroIshida/voxbloxpy):ROS-free Python 封装,可作离线验证工具,非在线后端。

---

## 3. 替代方案评估(语义差异 × 两个 API 支撑度)

### 3.1 nvblox / isaac_ros_nvblox(NVIDIA)

- 核心库:https://github.com/nvidia-isaac/nvblox ;ROS2 封装:https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_nvblox (Apache-2.0,716 star,**最后 push 2026-07-07,极活跃**)
- ROS2 支持:官方文档明确 **Jazzy**,测试平台 = Jetson / x86_64+NVIDIA GPU / DGX(https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_nvblox/index.html)
- **GPU 硬依赖:需要 CUDA,无 CPU-only 模式**(官方文档无任何 CPU 运行路径)。本机 RTX 5060 8G 可跑,但 WSL2+Docker+CUDA 栈叠加到现有 sim 容器上是额外工程量
- 语义:TSDF✅ ESDF✅(2D/3D)、unknown 有追踪 → **B(碰撞)原生支撑;A(gain)无现成"未知体素计数+光线投射"接口**,数据在 GPU 层,CPU 侧逐体素 raycast 需要层拷贝或自写 CUDA kernel;输入模型偏 RGB-D/深度图(lidar 走等效深度图转换,对 FOV/线数有假设)
- 行为等价:**风险高**——积分器、权重模型、截断策略均与 voxblox 不同,gain 数值分布必变,ROS1 基线不可对比

### 3.2 OctoMap ROS2(octomap_mapping ros2 分支)

- 仓库:https://github.com/OctoMap/octomap_mapping (**默认分支已是 ros2**,最后 push 2026-01-22,440 star;octomap_server 在 **Jazzy 有官方发行包**,docs.ros.org 有 Jazzy 2.3.0 API 文档;https://index.ros.org/p/octomap_server/)
- 许可证:octomap BSD
- 语义:概率占据八叉树(log-odds)。**三态原生**(unknown = 树中无节点)✅;`castRay` 原生 ✅ → **A(gain)可支撑**,但数值语义不同(无 TSDF 截断带,表面厚度/命中判定不同,gain 分布会漂移)
- **无 TSDF、无增量 ESDF**;距离查询靠 **dynamicEDT3D**(EDT 批量重算,增量性能差)→ B(碰撞)可用但代价与保守度都变
- 加分项:GBPlanner 1.0 曾有 Octomap 后端选项 → 移植有先例可循
- 定位:**备选/保底**——若 voxblox 移植底座验证失败,这是生态最成熟(官方维护+发行包)的退路,代价是接受行为漂移+重新调参

### 3.3 Bonxai(facontidavide)

- 仓库:https://github.com/facontidavide/Bonxai (MPL-2.0,862 star,最后 push 2026-03-11,活跃;OpenVDB 式三层稀疏体素,ROSCon 2023 基准:比 OctoMap 快 ~10 倍/内存减半)
- bonxai_map 提供概率占据图,有 ROS2 示例;另有社区扩展 Rolling-Bonxai(https://github.com/mukundbala/Rolling-Bonxai)
- 语义:**纯占据格,无 TSDF、无 ESDF、无距离查询**;unknown = 未分配 cell(可查但无现成三态 raycast 工具)→ **A、B 都要自研**(gain 光线投射器 + 距离场/碰撞查询全部自己写)
- 定位:数据结构优秀但对 GBPlanner 是"换引擎+自造两套 API",移植成本最高,不选

### 3.4 其他(简评,均不入围)

- **wavemap**(ethz-asl):多分辨率占据图,质量高,但**官方无 ROS2 接口**(Discussion #41 只有意向和 hackathon 级 fork,https://github.com/ethz-asl/wavemap/discussions/41);且无 ESDF
- **voxfield**(VIS4ROB-lab):非投影 TSDF/ESDF,语义最接近 voxblox 的学术改进版,但 ROS1 only,社区更小
- **spatio_temporal_voxel_layer**(OpenVDB,nav2):是 2D costmap 层,非 3D 探索地图后端,不适用

---

## 4. 结论矩阵

| 候选 | 移植成本 | 行为等价风险 | Jazzy 兼容 | 推荐度 |
|---|---|---|---|---|
| **voxblox ROS2 底座(snt-arg minimal + Gabriele 的 Jazzy Docker + ntnu-arl diff)** | **低–中**(核心算法零改动,工作量=验证移植质量+合 ntnu-arl 补丁) | **低**(同一 C++ core,可与 ROS1 逐体素对拍) | Gabriele 衍生已有 Jazzy CI;snt-arg 为 distro 无关 ament 包 | ⭐⭐⭐⭐⭐ **首选** |
| 官方 PR #413 / murraylouw fork | 中(esdf 未完成,停滞 2 年+) | 低 | Humble,Jazzy 未验 | ⭐⭐(仅作迁移改法参考) |
| OctoMap ros2 分支 + dynamicEDT3D | 中(GBPlanner 1.0 有先例;EDT 集成要做) | **中–高**(三态/无截断带→gain 漂移;EDT 增量差→碰撞语义变;需全量调参) | ✅ 官方发行包 | ⭐⭐⭐ **备选/保底** |
| nvblox / isaac_ros_nvblox | 高(MapManager 重写 + CUDA 栈 + gain raycast 自研) | 高(积分器/权重/输入模型全不同) | ✅ 官方 Jazzy(**GPU 硬依赖,无 CPU 模式**) | ⭐⭐(长期性能路线,不适合本次等价迁移) |
| Bonxai | 最高(无 ESDF/TSDF,A、B 两 API 全自研) | 高 | ✅(库本身 ROS 无关,有 ROS2 示例) | ⭐⭐ |
| wavemap / voxfield | — | — | ❌ 无官方 ROS2 | 不入围 |

## 5. 取舍理由:行为等价性优先

1. **本次迁移的验收标准是"ROS2 版 GBPlanner 行为 ≈ ROS1 版"**,而不是"换个更快的地图库"。gain=未知体素计数+光线投射、碰撞=ESDF 查询,两者对后端语义(截断带宽度、weight 阈值、unknown 判定)极端敏感——只有继续用 voxblox 的同一份 core 代码,才能做**逐体素/逐 gain 值的 oracle 对拍回归**(ROS1 版跑同一 rosbag 出参考答案,ROS2 版必须逐位吻合),这是唯一能锤死"移植没改行为"的方法,也与本项目一贯的实证纪律一致。
2. 三个候选移植中,**snt-arg 是唯一 tsdf_server+esdf_server 双全、launch 全迁、且 2025Q4 仍在提交的**;官方 PR #413 esdf 缺失且死了两年;Gabriele 仓与 snt-arg 同源、贡献是现成的 **Jazzy** Dockerfile/CI——三者不是竞争关系,是"底座 + Jazzy 适配参照 + 改法参考"。
3. 风险与对冲:两个移植仓 star≈0、无社区背书,"there are some lacking" 自述在案 → 对冲手段就是第 1 条的 oracle 回归 + 保留 ntnu-arl/voxblox diff 审计;若底座质量不过关,退路按序为:自己按 PR #413 改法重迁 voxblox_ros 层(core 不动,成本可控)→ OctoMap 保底(接受调参重来)。
4. nvblox 明确**不作为本次迁移目标**:GPU 硬依赖 + 语义漂移双重代价,只在"等价迁移完成、有 ROS2 基线之后"作为性能升级路线另立实验。

## 6. 落地动作(撰写时计划;**后续已执行**:gbp-feat `ros2_port` vendored voxblox,基底 pin `d08e9d4`〔snt-arg 迁移链〕,M2 数值对拍窄验收 PASS〔TSDF 零失配 / ESDF RMS 2.5e-05;fast integrator 失配与 3D 分层语义未关闭,见 CURRENT_STATUS M2 口径〕)

1. clone snt-arg/voxblox_ros2_minimal,Jazzy 容器内编译(Dockerfile 抄 GabrieleSantangelo 仓 2026-03-17 提交);
2. `git diff ethz-asl/voxblox..ntnu-arl/voxblox` 审计 GBPlanner 定制点,移植到 ROS2 底座;
3. oracle 回归:同一份点云 rosbag → ROS1 esdf_server vs ROS2 esdf_server,对拍体素层(protobuf 序列化格式未变,可直接 diff 层文件);
4. GBPlanner map_manager 对接 ROS2 voxblox,gain/碰撞 API 单测对拍。

---

### 主要来源(检索于 2026-07-07)

- https://github.com/ethz-asl/voxblox · Issue #364 · PR #413
- https://github.com/snt-arg/voxblox_ros2_minimal (GitHub API:created 2025-10-10 / pushed 2025-12-01 / BSD-3)
- https://github.com/GabrieleSantangelo/voxblox-ros2 (commits API:2026-03-17 Jazzy Dockerfile)
- https://github.com/murraylouw/voxblox (pushed 2024-02-29)
- https://github.com/ntnu-arl/voxblox (pushed 2025-10-03)
- https://github.com/Tail-19/Voxblox-ros2
- https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_nvblox + https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_nvblox/index.html (Jazzy,GPU 必需)
- https://github.com/OctoMap/octomap_mapping (默认分支 ros2,pushed 2026-01-22) + https://index.ros.org/p/octomap_server/
- https://github.com/facontidavide/Bonxai (MPL-2.0,pushed 2026-03-11)
- https://github.com/ethz-asl/wavemap/discussions/41
- https://github.com/unr-arl/gbplanner_ros / https://github.com/ntnu-arl/gbplanner_ros
