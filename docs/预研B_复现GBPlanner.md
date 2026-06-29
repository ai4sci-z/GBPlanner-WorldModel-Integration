# 预研 B · 复现 GBPlanner 官方仿真(ROS1)

> 目的:在本机**独立复现**官方 GBPlanner,看懂算法真实行为与 I/O,作为「桥接方案」的运行件。
> 状态:**镜像已构建成功 ✅**;实际 roslaunch 跑动画为下一步(需 WSLg GUI,截图留证)。最后更新 2026-06-29。

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
| 结论 | **GBPlanner 的 ROS1 环境在本机可复现** |

> 📸 截图待补:`docker images` 输出、后续 `roslaunch gbplanner rmf_sim.launch` 的 RViz 画面 → 存 `images/预研B_*.png`。

## 四、算法真实 I/O(供桥接对接)
- 输入:点云 `/pointcloud`←`/<robot>/velodyne_points`(**3D**);里程计 `odometry`←`ground_truth/odometry_throttled`;TF `world→navigation`。
- 输出:经 **PCI**(`pci_general_ros_node`)下发路径/航点;由 service 触发(`std_srvs/Trigger`、`pci_search`、`pci_global`)。
- 建图:voxblox(编译进 gbplanner)。

## 五、下一步
1. `roslaunch gbplanner rmf_sim.launch`(WSLg)→ 录 RViz 探索过程截图。
2. 抄 `gbplanner_config.yaml` / `voxblox_sim_config.yaml` 关键参数。
3. 作为桥接方案的 ROS1 运行件,接 ros1_bridge。
