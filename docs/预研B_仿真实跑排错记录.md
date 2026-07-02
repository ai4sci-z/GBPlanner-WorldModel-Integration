# 预研B·GBPlanner 官方仿真实跑排错记录(2026-07-02,WSLg GUI)

> 目标:在本机 WSL2 上把 `gbplanner-ref` 镜像里的官方仿真(`rmf_sim.launch`)**真跑起来、亲眼看**。
> 结论先行:**链路已通到 voxblox 3D 建图**(里程计 252Hz、TSDF 地图 4.5Hz、RViz 弹窗在桌面),
> 只差"起飞→自主探索"最后一步(见 §卡点)。逐坑记录如下,全部有实测证据,修复固化在
> `runbooks/gbplanner_ref/run_light.sh` + `light_boxes.world`。

## 已排掉的 6 个坑

| # | 现象(证据) | 根因 | 修复 | 验证 |
|---|---|---|---|---|
| A | `RLException: rmf_sim.launch is neither a launch file...` | `bash -c` 非交互 shell 不读 `.bashrc`,工作区没 source | 启动命令显式 `source /opt/ros/noetic/setup.bash` + `devel/setup.bash` | roslaunch 正常解析 ✅ |
| B | roslaunch 卡死,11311 无监听、无日志,仅 pid1 | 容器 hostname `AI4S` 只解析到 IPv6 `::1`,ROS1(noetic)不吃 | `ROS_HOSTNAME=localhost ROS_MASTER_URI=http://localhost:11311 ROS_IP=127.0.0.1` | master 起来,节点全起 ✅ |
| C | `error: Invalid parameter "gpu"`,robot_description 生成失败 | **上游真 bug**:`rmf_obelix_base.xacro:56` 给 OS0-128 宏传了它未声明的 `gpu`/`organize_cloud` 参数 | 启动前 `sed` 删掉这两个参数(宏用默认值) | 模型 spawn 成功 ✅ |
| D | `[gazebo-9] process has died ... exit code 139`(段错误),DARPA 大场景与 cave_01 均崩 | WSLg 软件渲染(llvmpipe)扛不住带网格模型的场景 | **手搓纯 box 图元轻量世界** `light_boxes.world`(围墙+隔墙+柱,16×16m) | gzserver 稳跑,激光点云 27876 点 ✅ |
| E | `/rmf_obelix/ground_truth/odometry` **Publishers: None**;voxblox 报 `Input pointcloud queue getting too long! Dropping` | 自制世界缺 **`ros_interface_plugin`**(RotorS 传感器插件发 Gazebo 内部消息,必须世界级插件转 ROS;官方 7 个世界全带) | `light_boxes.world` 补 `<plugin name="ros_interface_plugin" filename="librotors_gazebo_ros_interface_plugin.so"/>` | **odometry 252Hz;voxblox 不丢帧;`/gbplanner_node/tsdf_pointcloud` 4.5Hz 建图** ✅✅ |
| F | 容器每 1–2 分钟死(255),journalctl 显示 docker 被反复**优雅**停止 | **WSL 空闲自动关机**:无常驻会话时发行版十几秒后关停→systemd 停 docker→容器连坐 | 挂常驻 keepalive 进程(`sleep 86400`)吊住 WSL | 容器跨命令存活 ✅ |

## 当前链路状态(实测)

```
Gazebo(box迷宫) → 激光点云 10Hz(27876点/帧) → ✅
RotorS ros_interface_plugin → /ground_truth/odometry 252Hz → ✅
voxblox(gbplanner_node 内) → TSDF 3D占据地图 4.5Hz → ✅
RViz(WSLg 弹窗,GbPlanner Control 面板) → ✅
PCI automatic_planning 调用 success:True → ✅
无人机起飞/出探索轨迹 → 🔵 未通(见下)
```

## 卡点(下一步)

- 无人机仍在地面(z=0.056),`/rmf_obelix/command/trajectory` 无消息 —— planner 触发成功但不出轨迹,疑因机器人未起飞/未做初始运动(PCI 配置 `init_motion_enable: false`,`trigger_mode: kManual`)。
- `pci_initialization_trigger` 服务调用报 `is not available` + `Unable to load type [planner_msgs/pci_initialization]` —— RViz 面板的 **Initialization 按钮**走的就是它,待查:是服务名/类型加载问题,还是须经 RViz UI 触发。
- **绕道方案**(若 init 服务难修):直接向 `/rmf_obelix/command/pose` 发一个升高的位姿(lee 控制器订阅它)让它起飞,再触发 automatic_planning。

## 复现方法(一键)

```bash
# WSL 内;先保证有个常驻 WSL 窗口开着(坑F)
bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref/run_light.sh
```
RViz 弹出后:勾选 `Sensors` 看点云;`Voxblox` 看 3D 地图长出来;左下面板 Initialization → Start Planner。
