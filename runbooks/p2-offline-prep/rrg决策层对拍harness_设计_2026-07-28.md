# rrg 决策层对拍 harness · 设计定稿(P2-OFFLINE-PREP,2026-07-28)

> 路线图 #7(P2/P3 的门):"同地图→同采样图/同增益/同最优路径"的对拍工具**此前不存在**。
> 本文=设计定稿(离线准备,负责人已批并行;不运行 live、不作对齐结论、不改 gbp-feat 代码)。
> 模式复用已定档的 oracle_cmp(MAP 层)三件套:确定性输入 + 两侧同文件自证 + 分层判据。

## 0. 对拍对象与边界

- 对象:`gbplanner_core` 决策层 = RandomSampler 采样 → Rrg 图构建(kdtree 近邻/边碰撞)→
  体积增益(volumetric gain)→ 最优路径选择。ROS1 侧=gbplanner-ref 容器(oracle);
  ROS2 侧=ros2_port vendored 移植版。
- 不覆盖:执行层(pci_general,上游本就缺失,P3 另建)、地图层(oracle_cmp 已定档)。

## 1. 核心难点与决策:样本录制/回放(tap/replay),不是种子注入

实测(ros2_port/src/gbplanner_core/src/random_sampler.cpp:136,244):`generator_.seed(rd())`
= random_device 播种,非确定。且即使两侧同种子:`std::mt19937` 序列跨平台同(标准规定),
但 `std::uniform_real_distribution` / `std::normal_distribution` 的实现**不受标准规定**,
noetic(libstdc++/gcc9) 与 jazzy(gcc13) 可产生不同样本序列 → **种子注入不可靠,弃用**。

**决策**:在 `RandomSampler::generate` 加环境变量门控的 tap/replay(两侧打**同一份**小补丁,
补丁文本入 harness 目录,SHA 自证——同 oracle_cmp 的 frames_common 模式):
- `GBP_SAMPLE_LOG=<file>`:把每次 generate 产出的 state 追加写入(文本,定点量化 1/1024,
  同 oracle_cmp 防 1ulp 漂移);
- `GBP_SAMPLE_REPLAY=<file>`:generate 改为按序读文件返回(耗尽即报错退出,防静默漂移)。

回放消除了随机性 → 下游(kdtree/图/增益/路径)在同地图+同根状态下应**确定**。

## 2. 输入 fixture(全确定)

1. 地图:复用 oracle_cmp 的 `frames_common.py` simple 场景喂 voxblox(**已定档两侧逐体素零差**)
   → 决策层拿到的地图输入等价性已被 MAP 层对拍背书,无需重证;
2. 根状态:固定 root state(写死在 fixture,如 (0,0,1,yaw=0));
3. 参数:两侧同一份 planner config(harness 目录持有唯一副本,启动前拷入,SHA 自证);
4. 样本:ROS1 oracle 先跑一次 `GBP_SAMPLE_LOG` 录制 → 之后 ROS1(自回放 sanity)与 ROS2
   都用 `GBP_SAMPLE_REPLAY` 同一份样本文件。

## 3. 对拍产物与 dump 点(两侧各 dump 一份 JSON)

| 层 | dump 内容 | 判据 |
|---|---|---|
| S1 样本 | replay 消费计数+末样本回显 | 精确相等(自证 replay 生效) |
| S2 图 | 顶点(id,量化坐标,status)集合;边(id对,量化代价)集合 | 集合零差(回放后应确定;kdtree 平票顺序若现实测差→记录为真实分叉点,不放宽) |
| S3 增益 | 每顶点 volumetric gain(raw + 各惩罚项分解) | 相对容差 ≤1e-6(纯浮点累加序噪声);超差=真行为分叉 |
| S4 决策 | best_vertex_id + 最优路径顶点序列 + ref path 量化坐标 | 精确相等(S2/S3 等价则 S4 必等;不等=选择逻辑分叉) |

分层判据的意义:**失败自动定位到最浅分叉层**(样本/图/增益/选择),不用整段猜。

## 4. 实施清单(待排期;估算 2-3 个工作日)

1. tap/replay 补丁(random_sampler.cpp,~30 行,ROS1/ROS2 同文本)+ 两侧构建脚本;
2. dump 点补丁(rrg.cpp:采样循环、增益计算、getBestPath;~60 行,同文本);
3. fixture(根状态+参数副本+地图复用 oracle_cmp);
4. `compare_rrg.py`(零依赖,同 compare_layers.py 风格,S1-S4 分层报告);
5. 定档跑:simple 场景 ×3 重复(回放下应逐次相同=确定性自证)→ 判读入档。

## 5. 风险与诚实边界

- kdtree.c(C 实现)近邻平票顺序、`std::sort` 稳定性差异 → 可能是真实分叉点;设计选择=
  **暴露它而非容差掩盖**(S2 集合判据 + 平票时记录候选集);
- 增益射线投射若依赖 voxblox 查询顺序/线程 → 强制单线程跑(同 oracle_cmp 的教训:
  线程数不可锁=浮点合并噪声,decision 层必须单线程消掉);
- 本设计未运行任何 live、未改 gbp-feat(补丁文本只存 harness 目录待实现期应用);
  实现与跑批须负责人排期(P2 正式启动或 OFFLINE-PREP 扩权后)。

## 6. 与现有资产的关系

- oracle_cmp(MAP 层,已定档零差)= 地图输入等价性的前置背书,本 harness 直接站上去;
- 样本 tap/replay 思路 = frames_common"两侧同文件+SHA 自证"哲学在随机性上的推广;
- 完成后,路线图 #7 从 ⛔ 变为可执行,#6(行为等价)与 #9(3D 无损 rrg 部分)获得工具。
