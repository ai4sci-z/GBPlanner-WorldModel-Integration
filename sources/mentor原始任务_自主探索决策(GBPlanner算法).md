论文链接：[[2201.07067\] CERBERUS: Autonomous Legged and Aerial Robotic Exploration in the Tunnel and Urban Circuits of the DARPA Subterranean Challenge](https://arxiv.org/abs/2201.07067)

文中提出的GBPlanner算法依靠已经探索并建立好的地图来工作，通过计算路径能“看见”多少未知空间（体积增益）来选择路线，它无法推测被遮挡的未知区域里有什么

### 自主探索决策 (GBPlanner 算法)

根据地图决定“去哪里”。

1. **输入：** 当前机器人位姿 + 3D 占据网格图（已占据+空闲+未知这三种体素） + 可通行性分析。
2. **核心流程：**
   - **局部规划 (Local Planner)：**
     - 在机器人附近空间随机采样，构建一个图（Graph）。
     - **算法输入：** 体素地图中的“未知”区域。
     - **计算增益：** 使用光线投射算法计算每条路径能看到的“未知区域”体积（VolumeGain）。
     - **选择：** 选出增益最高且避开障碍物的路径。
   - **全局规划 (Global Planner)：**
     - 如果局部路径没有增益（周围都探完了），则从全局图中搜索未探索的边界（Frontiers）。
3. **最终输出：** 一系列**目标航点 (Waypoints)**。

体积增益分数：射线穿过的未知体素数量总和，同时引入了距离惩罚和转向惩罚

为了增益最大化，引入该模块的无人机，在理论上会在坑道内部进行垂直探索