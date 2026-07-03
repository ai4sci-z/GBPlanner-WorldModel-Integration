# 核心发现:frontier_lite 是脚本占位 + GBPlanner 精确集成机制

> 本文是整个任务的"准星",对应 mentor 的《自主探索决策(GBPlanner算法).md》。全部基于**真实源码**(`orchestration/sim/internal/tasks/helpers/templates/python/exploration_workflow_runtime.py.tmpl`),非臆造。最后更新 2026-07-03。

## 一、核心发现①:world-model 现有的 `frontier_lite` 不是探索算法,是"脚本预设动作"
读它的真实决策代码,核心只有这几行:
```python
def exploration_intent(goal_index, speed, state):
    pattern = [
        {"linear_x_mps": speed,     "yaw_rate_radps": 0.0 },  # 前进
        {"linear_x_mps": speed*0.6, "yaw_rate_radps": 0.20},  # 前进+左扭
        {"linear_x_mps": speed,     "yaw_rate_radps": -0.12}, # 前进+右扭
    ]
    command = pattern[goal_index % len(pattern)]   # 按"计时器"循环这 3 个写死的动作
    ...
```
**铁证级事实:**
1. **它根本不订阅地图**——节点的订阅只有 `/slam/odom`(量走了多远)和控制器状态(`exploration_workflow_runtime.py.tmpl:67-68`)。**没有任何地图输入。**
2. **决策 = 按时间循环 3 个写死的速度指令**(前进/左扭/右扭),`goal_index = ready_elapsed / segment_sec`(行106)。
3. **"通过"门槛极低**:凑够 3 段动作 + 走够 0.35 米(`exploration_status` 行176-190),26 秒内完成即算 ok。
4. 连它发布的 `frontiers` 都明写 `"source": "bounded_lite_pattern"`(预设模式,行224);coverage 只是"走了多远"的代理值(行217)。

→ **结论(可写进报告):frontier_lite 是一个"控制链路冒烟测试"——证明无人机能动、能被指挥,完全不看地图、不做探索决策。这不是探索算法。**

## 二、核心发现②:GBPlanner 的精确插入点(对应 mentor md)
mentor md:GBPlanner = **自主探索决策模块**,输入【位姿 + 3D 占据地图 + 可通行性】,输出【目标航点】。
world-model 里"做探索决策"的就是上面那个 Python 节点 `navlab_exploration_workflow`:
- 输入:`/slam/odom` + 控制器状态(**当前没接地图**)
- 输出:`/navlab/fcu/setpoint/intent`(运动意图)+ `/navlab/exploration/{status,goal,coverage,frontiers,path,markers}`

**"加入 GBPlanner" = 把这个节点的"死循环预设动作"换成 GBPlanner 的"读地图→算体积增益→选航点"。** 插入点就在这里。

## 三、完整的"加法"(三步,基于两道真实鸿沟)
两道鸿沟(代码确认):① GBPlanner 要 **3D 占据地图**,world-model 只有 **2D**(Cartographer)且决策节点没接地图;② GBPlanner 是 **ROS1**,world-model 是 **ROS2**。

| 步 | 做什么 | 为什么 |
|---|---|---|
| ① 装"3D 的眼睛" | 给仿真无人机加 3D 雷达(对齐 GBPlanner 的 OS064:360°×90°/20m)+ 3D 建图(octomap/voxblox)产出 occ/free/unknown 体素图 | GBPlanner 要 3D 占据地图,现仅 2D |
| ② 接"大脑" | `ros1_bridge`:把【3D 占据图 + 位姿】喂给 ROS1 的 GBPlanner;把它输出的【航点】接回 ROS2 | GBPlanner 是 ROS1,跨框架 |
| ③ 换"决策" | 把航点转成 `/navlab/fcu/setpoint/intent`,替换 `exploration_intent` 里那段预设动作;`strategy` 标为 `gbplanner` | 让无人机真按 GBPlanner 决策飞,沿用现有验收闸门 |

## 三·五、进展实证(2026-07-03 补)
- **GBPlanner 侧已从"纸面"变"实证"**:官方仿真在本机自主探索全闭环(起飞→voxblox 建图→RRG→巡飞→时间预算自动返航→地图落盘),全程量化 291.3m/132,091 体素点(见 [预研B_复现GBPlanner.md](预研B_复现GBPlanner.md))。
- **frontier_lite 侧**:代码级铁证已齐(上文);量化实跑等 world-model 运行时最后一层修通(9 坑已修 8,见 [运行时排错记录_humble.md](运行时排错记录_humble.md))。
- 决策层原型 `gbplanner_gain` 与真版桥接地基(I/O 契约+适配器)已落地,见 `integration/`。

## 四、一句话总结(报告可直接用)
> **frontier_lite = 闭着眼睛按脚本"前进+扭头";GBPlanner = 睁开 3D 的眼睛,看哪里没探过就往哪里去。**
> **集成 = 给无人机装 3D 的眼睛(雷达+建图)+ 把决策大脑从脚本换成 GBPlanner(经 ros1_bridge),输出航点驱动飞行。** 插口(/navlab/exploration/* 与 setpoint/intent)不变,只换决策内核。

## 五、对比实验由此精确化
- 对照不再是"两个探索算法",而是**"脚本预设动作 vs 真实地图驱动探索"**——优势对比天然成立。
- 指标:覆盖率/探索面积(frontier_lite 几乎为 0 的"地图覆盖",因为它不建图决策)、是否能探到 3D/垂直空间、对未知区域的有效追逐。

## 六、GBPlanner 是实时导航还是"探完再按图飞"?(2026-07-02 实跑亲验后的精确回答)

**主模式 = 实时在线探索**(边飞边建图边决策),不是先探完再飞。滚动闭环:

```
激光扫描 → voxblox 地图更新(未知→已知) → 在当前地图的已知安全区撒点建 RRG
  → 光线投射算每条候选路径的体积增益 → 选最优的一小段(几米)飞过去
  → 飞行中继续扫描 → 地图又长大 → 用【新地图】规划下一段(循环)
```
要点:①起飞时对世界认知≈0,没有先验地图;②每次只规划一小段,"走一步看一步";③每一秒的决策都基于**到此刻为止**探出的地图。

**副模式 = 在已知图上导航**,只用在两处:
- **返航(homing)**:时间预算到(`time_budget=480s`,实测日志 `REACHED TIME LIMIT: HOMING ENGAGED`),在自己建好的全局图里搜安全路径回起飞点——实跑亲验:442.6s 触发,利索飞回原点悬停;
- **全局转场**:局部无增益时,在已知图上导航到远处的边界(frontier)再继续探。

**停止探索的三种情况**:①时间预算到(→返航)②全局也找不到任何 frontier(真探完→返航)③手动 Stop。
**地图是边飞边记的**:每帧点云实时融合进 voxblox;"探索完成"的定义恰是"地图上无值得看的未知区"。地图可存盘复用
(`save_map` 服务;实跑产物 `images/explored_map_lightboxes.vxblx`,4MB)。

> 汇报一句话:**frontier_lite 连地图都不订阅、按脚本转圈;GBPlanner 每一秒的选择都是看着实时地图算出来的。**
