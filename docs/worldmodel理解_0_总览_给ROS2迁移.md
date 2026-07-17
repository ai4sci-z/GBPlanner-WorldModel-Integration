> **[技术参考 · 已逐行审计(R003-E0-CORRECT-2 补正,2026-07-18)]** 本文为迁移视角技术索引,不承载当前状态。
> 审计改动:①"主线任务书"降为历史设计;②"替换决策框"澄清为按 run 可切换接管、frontier_lite 并列保留;
> ③WSL/Windows 行号基准标注为历史环境,现按符号名定位;④里程碑加真实状态指针(M0-M4 窄验收,M5 BLOCKED)。
> 深层机制主张(Go 编排/让位机制)与 wm 代码的比对以理解(一)(二)(三)各篇审计为准。
> 当前状态唯一权威 = [CURRENT_STATUS.md](../CURRENT_STATUS.md)。

# worldmodel 理解(零):总览 · 给 ROS2 迁移的人

> 状态:技术参考(撰写于 2026-07-08;不承载当前状态)
> 读者:要把 GBPlanner 从 ROS1 移植成 ROS2 原生节点、并直接接进 world-model 的人。
> 定位:这是 1/2/3 三份精读报告的**入口与索引**,不重复细节。细节各归各篇。
> 关联:历史设计任务书 [GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md](GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md)(**非当前权威**)· 路线切换决策 [路线切换_ROS2迁移_2026-07-07.md](路线切换_ROS2迁移_2026-07-07.md)。

---

## 1. 五句话看懂 world-model(迁移视角)

1. **world-model 的编排层是 Go 控制平面**(单一二进制 `navlab-sim`,cobra CLI),它**本身不是 ROS 节点、不参与实时控制**;它只做四件事:规划 → 渲染 → 起容器执行 → 离线裁决 gate。详见 [理解(一)](worldmodel理解_1_编排与任务生命周期.md)。
2. **真正跑在 ROS 里的全部是"渲染出来的 Python 脚本"**(Gazebo/SITL、SLAM、fcu_controller、exploration_workflow、探针、rosbag),Go 层只通过文件产物与它们交互。→ **你的 ROS2 planner 不需要动 Go 层任何执行逻辑,只要满足它的 topic/JSON 契约。**
3. **数据流一句话**:Gazebo 出传感 → ROS2 → cartographer 2D 出 `map→base_link` → 适配器变 `/slam/odom` → 兵分两路:①回灌 MAVLink ODOMETRY 给 ArduPilot EKF;②`exploration_workflow` 读 `/slam/odom` 出 intent(JSON)→ `fcu_controller` 下发 → SITL 动 → Gazebo 动 → 闭环。详见 [理解(二)](worldmodel理解_2_ROS图与数据流.md)。
4. **GBPlanner 的落点 = 运行时接管"决策框"(intent 的生产者)**,其余链路原样复用。插拔靠 `strategy` 字段:原版只是标签,真正的让位机制是 clean 分支加的 **`strategy=external` 分支**——选 external 时内建 workflow 整段让位,把 intent 总线与 status 话题所有权交给外部进程。**注意口径:这是"按 run 可切换选择",frontier_lite 保留并列可选,不是把它删掉替换**(项目最终目标=独立、可配置选择、可切换、可回滚,见 CURRENT_STATUS)。详见 [理解(三)](worldmodel理解_3_探索策略接口_GBPlanner接入点.md)。
5. **迁移不是重写算法**:保留 GBPlanner 算法核心,替换 ROS1 外壳与运行时依赖,行为尽量对齐 ROS1 原版 oracle。

---

## 2. ROS2 GBPlanner 的接入契约(M5 用,先记住)

外部 planner(= 未来的 ROS2 GBPlanner + `trajectory_to_intent` 适配器)必须:

- **订阅**:`/slam/odom`(odom)、`/wm/cloud3d` 或 `/lidar3d/points`(3D 点云)、TF;
- **发布**:`/navlab/fcu/setpoint/intent`(运动意图,fcu_controller 消费)、`/navlab/exploration/status`(gate 靠它裁决);
- ⚠️ **`status.ok=true` 会触发 landing**——探索"完成"信号,别乱发;
- 现成资产:`trajectory_to_intent_stage4.py`(桥接期适配器,ROS2 迁移**直接复用**);Stage5c probe/harness 口径可改成 M5 harness。

---

## 3. 迁移前置检查(踩坑预防)

- ⚠️ **TF 不是标准 `map→odom→base_link`**:world-model 是 cartographer 直接给 `map→base_link`,`odom` 在很多地方只是 legacy 名字。GBPlanner ROS2 的 `world_frame`/`robot_frame`/TF lookup **必须按 world-model 实际 TF 设计,不要默认存在 `map→odom`**(理解(二) 明确指出)。
- **行号基准差异(历史环境)**:理解(一)以 **WSL** `~/ws-clean/world-model` @ `e7ca9fc` 为准(含 B16 探针修复+预算调整);理解(二)/(三) 部分以 **Windows** `sources/world-model-源码/` 上游快照为准(**原版无 external 分支**)。凡涉及 clean 分支修复处各篇已显式标注。⚠️ **现环境已迁至原生 Ubuntu,当前事实源 = `/home/ai4s/projects/world-model`@fix/world-model-e2e-takeoff;各篇行号相对现 HEAD 可能漂移,使用前须按符号名重新定位,不要按行号盲跳。**
- **world-model 侧资产迁移后继续受益**:EKF 参考系修复(clean 99bcfa1)、探针预算修复、lidar3d 净增量、评测口径——都是 world-model 侧,不随桥接废弃。

---

## 4. 迁移优先级(为什么按这个序)

```text
M0 入口文档收口  →  M1 planner_msgs 最小消息层  →  M2 voxblox ROS2 后端
   →  M3 算法核心 ROS-free 剥离  →  M4 ROS2 planner 节点壳  →  M5 world-model 直连联跑 + oracle 回归
```

(真实进度以 CURRENT_STATUS 为准:M0-M4 窄验收〔行为等价与 3D 无损未证〕,M5 BLOCKED 于平台稳定门。)

- **先地基后上层**:M1 消息层不通,后面 rrg/voxblox 全都编译不了;
- **voxblox = 最大风险**(换地图后端≈换 gain 分布/碰撞边界/路径偏好),所以第一版沿用 voxblox core、用 ROS1 oracle 逐体素对拍,**不用 nvblox**;
- **M5 才碰 external 联跑**——M1-M3 别急着接 world-model,先把消息层和地图层骨架做出来。

一句话:**先把消息层地基打稳,再逐层往上,每层拿 ROS1 GBPlanner 当 oracle 对照。**
