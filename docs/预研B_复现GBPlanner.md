> **[REFERENCE]** GBPlanner 官方仿真单侧复现(不代表 world-model 集成完成)。当前状态以 [CURRENT_STATUS.md](../CURRENT_STATUS.md) 为准。

# 预研 B · 复现 GBPlanner 官方仿真(ROS1)

> 目的:在本机**独立复现**官方 GBPlanner,看懂算法真实行为与 I/O,作为「桥接方案」的运行件。
> 状态:✅✅ **完成(2026-07-02):自主探索全任务周期在本机实测跑通**——起飞→voxblox 3D 建图→RRG 规划→
> 自主巡飞→时间预算到自动返航→地图落盘。排 6 坑全记录见 [预研B_仿真实跑排错记录.md](预研B_仿真实跑排错记录.md)。

## 一、目标
- 不依赖 world-model,单独把官方 `ntnu-arl/gbplanner_ros`(gbplanner2,ROS1 Noetic)跑起来。
- 确认输入/输出话题、参数、行为,供桥接对接。

## 二、做了什么 + 关键命令
1. 写 ROS1 Noetic 的一键 Dockerfile(`runbooks/gbplanner_ref/Dockerfile`)。
2. **踩坑并修复**:首版手动 `git clone gbplanner_ros` + rosinstall 又拉一份 → catkin 报"重复包 planner_msgs"。
   **修复**:不手动 clone,直接用官方 `packages_https.rosinstall` 在**工作区根**初始化(其 local-name 自带 `src/` 前缀):
   ```dockerfile
   WORKDIR /root/gbp_ws
   RUN wget -O /tmp/packages.rosinstall \
         https://raw.githubusercontent.com/ntnu-arl/gbplanner_ros/gbplanner2/packages_https.rosinstall && \
       wstool init . /tmp/packages.rosinstall && wstool update
   RUN source /opt/ros/noetic/setup.bash && catkin config -DCMAKE_BUILD_TYPE=Release && catkin build
   ```
3. 后台构建(容器内 github 走代理):
   ```bash
   docker build --network=host \
     --build-arg HTTPS_PROXY=http://127.0.0.1:7897 \
     -t gbplanner-ref runbooks/gbplanner_ref
   ```

## 三、结果(留痕)
| 项 | 结果 |
|---|---|
| 构建 | `BUILD_OK` |
| 镜像 | `gbplanner-ref:latest`(约 10.7GB) |
| 含包 | gbplanner、planner_common、planner_msgs、pci_general、voxblox、rotors_simulator 等 |
| **实跑(2026-07-02)** | **自主探索全闭环**:起飞(z 0.056→1.2)→自主巡飞覆盖 box 迷宫→480s 预算到 `HOMING ENGAGED` 自动返航 |
| 量化(第三轮**全程**采集,70 采样点) | 总路径 **291.3 m**;地图峰值 **132,091 点**;**t=435s 自动返航**(budget=480s);曲线+CSV:`images/exploration_metrics_full.*`(第二轮部分窗口数据:50.2m/134,557 点,`*_round2.*`) |
| 地图落盘 | `images/explored_map_lightboxes.vxblx`(4MB,`save_map` 服务) |
| 结论 | **官方 GBPlanner 在本机不仅可复现,而且真跑完整任务周期、可量化** |

![探索全程指标曲线(路径长度与地图增长随时间)](../images/exploration_metrics_full.png)

一键复现:`runbooks/gbplanner_ref/run_light.sh`(起仿真)→ `takeoff_and_explore.sh`(起飞+触发)。
> 注:原版 DARPA 大场景在 WSLg 软件渲染下段错误,实跑用自制轻量 box 迷宫世界(`light_boxes.world`);
> 6 个坑(含上游 xacro 真 bug)的完整证据链见 [预研B_仿真实跑排错记录.md](预研B_仿真实跑排错记录.md)。
> 📸 RViz 真截图:探索图/点云/轨迹画面由用户截存 `images/`。

## 四、算法真实 I/O(供桥接对接)
- 输入:点云 `/pointcloud`←`/<robot>/velodyne_points`(**3D**);里程计 `odometry`←`ground_truth/odometry_throttled`;TF `world→navigation`。
- 输出:经 **PCI**(`pci_general_ros_node`)下发路径/航点;由 service 触发(`std_srvs/Trigger`、`pci_search`、`pci_global`)。
- 建图:voxblox(编译进 gbplanner)。

## 五、下一步
1. ~~roslaunch 跑动画~~ ✅ 已完成(全闭环实测)。
2. 关键参数已实测确认:`time_budget=480s`、`unknown_voxel_gain=60`、`v_max=1.0`、体素 0.2m、OS064 360°×90°。
3. 作为桥接方案的 ROS1 运行件,接 ros1_bridge(接口契约与适配器见 `integration/ros1_bridge/`)。
