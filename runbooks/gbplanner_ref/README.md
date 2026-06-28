# P0-B · GBPlanner 参考环境(一键)

ROS1 Noetic 容器,构建即编译好官方 GBPlanner(gbplanner2),用于 **P0 看懂算法**。与 world-model(ROS2)隔离。

## 用法(在 WSL2 Ubuntu 内)
```bash
# 把本文件夹拷到 WSL(或直接从 /mnt/c 用):
cp -r /mnt/c/CCproject/runbooks/gbplanner_ref ~/ws/gbplanner_ref
cd ~/ws/gbplanner_ref
bash build_and_run.sh          # 构建 + 跑 rmf_sim.launch
# 或:
bash build_and_run.sh shell    # 只进容器 shell
```
> 从 `/mnt/c` 作为构建上下文没问题——catkin 编译发生在镜像层内部,不是在 /mnt/c 上,不违反"别在 /mnt/c 编译"。

## P0 观察清单(录下来给 P1 复刻)
- voxblox 分辨率/截断:容器内 `~/gbp_ws/src/gbplanner_ros/gbplanner/config/rmf/voxblox_sim_config.yaml`
- 增益权重/采样数/传感器 FOV:`.../gbplanner_config.yaml`
- 输入:`/<robot>/velodyne_points`(3D)+ `odometry`;TF `world→navigation`
- 输出:PCI 经 service 触发(`std_srvs/Trigger`、`pci_search`、`pci_global`、`pci_initialization`),发布参考轨迹(`geometry_msgs/Pose` 序列)+ `planner_msgs/PlannerStatus`

## 排错
- GUI 不显示:确认在 WSL2(WSLg)内跑,`echo $DISPLAY` 非空;或退而用 headless + 录 rosbag。
- 编译失败:多半缺某 `ros-noetic-*` 包 → 进 `bash build_and_run.sh shell`,`cd ~/gbp_ws && catkin build` 看报错,apt 装上重 build。
