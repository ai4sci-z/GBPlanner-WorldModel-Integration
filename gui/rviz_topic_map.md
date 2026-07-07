# RViz 配置「显示项 → topic」完整映射

- **状态**:REFERENCE(提取自容器内原始文件,逐字段核对,未编造)
- **提取日期**:2026-07-07
- **数据来源**(均为 `gbplanner-ref:latest` 镜像内文件,`docker run --rm` 读取,未触碰运行中容器):
  1. `/root/gbp_ws/src/exploration/gbplanner_ros/gbplanner/config/rviz/smb.rviz`(融合C 用)
  2. `/root/gbp_ws/src/exploration/gbplanner_ros/gbplanner/config/rviz/rmf_obelix.rviz`(原版A 用)
  3. marker 语义佐证:`gbplanner/src/gbplanner_rviz.cpp`(publisher 声明 L11-64,各 `ns=`/`color=` 赋值)+ `planner_control_interface/include/planner_control_interface/pci_manager.h`(L21-22)
- **铁律**:颜色/形状只是显示样式,**语义一律以 topic + marker namespace 为准**(见表3)。

两份配置公共项:`Fixed Frame: world`,背景黑色,带 `gbplanner_ui/GbPlanner Control` 面板(Go/Stop 等按钮)。

---

## 表1:smb.rviz(融合C 用配置)

| 显示项名称 | 类型 | topic | 语义(按 topic/namespace) | 备注 |
|---|---|---|---|---|
| Grid | rviz/Grid | (无 topic,Reference Frame=`<Fixed Frame>`) | 参考网格 | 默认关闭 |
| Axes/TF | rviz/TF | (订阅 /tf,无 Topic 字段) | TF 树 | 默认关闭 |
| Axes/BaseLink | rviz/Axes | (无 topic,Reference Frame=`base_link`) | 机体坐标轴,长3m | 开启 |
| Axes/World | rviz/Axes | (无 topic,Reference Frame=`world`) | 世界原点坐标轴,长2m | 开启 |
| Odometry | rviz/Odometry | `/ground_truth/state` | 真值里程计(红色箭头,Keep=1) | 默认关闭 |
| PlannerViz/PlanningFailed | rviz/MarkerArray | `/vis/planning_failed` | 采样失败的边(cpp ns=`failed_edges`) | 默认关闭 |
| PlannerViz/VolumetricGain | rviz/MarkerArray | `/vis/volumetric_gains` | 体积增益评估体素(cpp ns=`bound`/`unknown_voxels`/`free_voxels`/`occupied_voxels`) | 默认关闭 |
| PlannerViz/SensorFOV | rviz/MarkerArray | `/vis/sensor_fov` | 传感器视场(cpp ns=传感器名) | 默认关闭 |
| PlannerViz/BestPaths | rviz/MarkerArray | `/vis/best_planning_paths` | 局部规划最优路径(ns `best_path`/`vertices` 均勾选) | 开启 |
| PlannerViz/ShortestPaths | rviz/MarkerArray | `/vis/shortest_paths` | 局部图最短路径树;**该配置只勾选 ns `frontiers`**(frontier 红球),`vertices`/`shortest_edges`/`gain`/`heading`/`leaf_vertices`/`best_leaf_vertices` 均为 false | 开启 |
| PlannerViz/RobotState | rviz/MarkerArray | `/vis/robot_state` | 机器人状态盒(ns `size`/`extension`/`extension_aligned`/`heading` 全勾) | 开启 |
| PlannerViz/PlanningWorkspace | rviz/MarkerArray | `/vis/planning_workspace` | 规划工作空间盒(cpp ns=`global`/`local`) | 默认关闭 |
| PlannerViz/GlobalGraph | rviz/MarkerArray | `/vis/planning_global_graph` | 全局图(ns `edges`/`frontier`/`gain`/`vertices` 全勾) | 开启 |
| PlannerViz/HomingPath | rviz/MarkerArray | `/vis/planning_homing_path` | 回家(homing)路径(cpp ns=`best_path`,亮绿) | 默认关闭 |
| PlannerViz/PlanningGraph | rviz/MarkerArray | `/vis/planning_graph` | 局部采样图(ns `vertices`/`hanging_vertices` 勾选,`edges`=false) | 开启 |
| PlannerViz/Sampler | rviz/MarkerArray | `/vis/sampler` | 采样器采样点(cpp ns=`valid_samples`/`invalid_samples`) | 默认关闭 |
| PlannerViz/RefPath | rviz/MarkerArray | `/vis/ref_path` | **下发执行的参考路径**(ns `ref_path`/`vertices` 均勾选) | 开启 |
| PlannerViz/RayCasting | rviz/MarkerArray | `/vis/ray_casting` | 增益计算的射线投射(cpp ns=`rays`) | 默认关闭 |
| PlannerViz/ShortestPathsClustering | rviz/MarkerArray | `/vis/shortest_path_clustering` | 最短路径聚类(cpp ns=`cluster{i}`) | 默认关闭 |
| PlannerViz/StateHist | rviz/MarkerArray | `/vis/state_history` | 机器人状态历史(cpp ns=`state`/`state_range`) | 默认关闭 |
| PlannerViz/PlanningGlobalPath | rviz/MarkerArray | `/vis/planning_global_path` | 全局路径(cpp ns=`current2frontier` 亮绿 / `frontier2home` 暗红) | 开启 |
| PlannerViz/NoGainZones | rviz/MarkerArray | `/vis/no_gain_zone` | 无增益区(ns `no_gain_zone_0` 勾选;cpp ns=`no_gain_zone_{i}`) | 开启 |
| PlannerViz/CarrotPose | rviz/Pose | `/carrot_point` | 跟踪控制的 carrot 目标位姿(Axes 形状) | 开启;rmf_obelix.rviz 无此项 |
| PlannerViz/GoToWaypointVis | rviz/Marker | `/gbplanner/go_to_waypoint_pose_visualization` | 手动 Go-to-waypoint 目标可视化 | 开启 |
| PlannerViz/Geofence | rviz/MarkerArray | `/vis/geofence` | 电子围栏(ns `geofence`/`ID` 勾选) | 开启;rmf_obelix.rviz 无此项 |
| Sensors/Image | rviz/Image | `/m100/camera_blackfly/image_raw` | 相机图像 | 组整体关闭 |
| Sensors/InputPointcloud | rviz/PointCloud2 | `/input_pointcloud` | 规划输入点云(AxisColor 按 Z 染色,Decay 100s) | 组整体关闭(Sensors Enabled: false) |
| Voxblox/VoxbloxMesh | voxblox_rviz_plugin/VoxbloxMesh | `/gbplanner_node/mesh` | voxblox 表面网格 | 默认关闭 |
| Voxblox/Occupied | rviz/MarkerArray | `/gbplanner_node/occupied_nodes` | voxblox 占据体素(ns `occupied_voxels` 勾选;发布方=voxblox,非 gbplanner_rviz.cpp) | **开启**(smb 配置里体素地图主显示) |
| Voxblox/Tsdf | rviz/PointCloud2 | `/gbplanner_node/tsdf_pointcloud` | TSDF 点云(Intensity 染色) | 默认关闭 |
| Voxblox/SurfacePCL | rviz/PointCloud2 | `/gbplanner_node/surface_pointcloud` | voxblox 表面点云(AxisColor 按 Z) | 默认关闭(但为 Time 面板 SyncSource) |
| CommandTraj | rviz/MarkerArray | `/pci_command_trajectory_vis` | PCI 下发轨迹可视化(pci_manager.h L21-22 advertise) | 默认关闭;**全仓 grep 仅见 advertise、未见 publish 调用**,参考栈里此 topic 实际不出数据 |
| RobotModel | rviz/RobotModel | (param `robot_description`,非 topic) | SMB 地面车 URDF 模型(含 velodyne/os1 链节) | 开启;rmf_obelix.rviz 无此项 |

视角:Orbit,Target Frame=`base_link`。

---

## 表2:rmf_obelix.rviz(原版A 用配置)

| 显示项名称 | 类型 | topic | 语义(按 topic/namespace) | 备注 |
|---|---|---|---|---|
| Grid | rviz/Grid | (无 topic) | 参考网格 | 默认关闭 |
| Axes/TF | rviz/TF | (订阅 /tf) | TF 树 | 默认关闭 |
| Axes/BaseLink | rviz/Axes | (无 topic,Reference Frame=`rmf_obelix/base_link`) | 机体坐标轴 | 开启;注意带 `rmf_obelix/` 前缀 |
| Axes/World | rviz/Axes | (无 topic,Reference Frame=`world`) | 世界坐标轴 | **默认关闭**(与 smb 不同) |
| Odometry | rviz/Odometry | `/ground_truth/odometry_throttled` | 真值里程计(红箭头,Keep=1) | **开启**(与 smb 不同:topic 不同且启用) |
| PlannerViz/PlanningFailed | rviz/MarkerArray | `/vis/planning_failed` | 采样失败边 | 默认关闭 |
| PlannerViz/VolumetricGain | rviz/MarkerArray | `/vis/volumetric_gains` | 体积增益体素 | 默认关闭 |
| PlannerViz/SensorFOV | rviz/MarkerArray | `/vis/sensor_fov` | 传感器视场 | 默认关闭 |
| PlannerViz/BestPaths | rviz/MarkerArray | `/vis/best_planning_paths` | 局部最优路径(ns `best_path`/`vertices` 勾选) | 开启 |
| PlannerViz/ShortestPaths | rviz/MarkerArray | `/vis/shortest_paths` | 局部最短路径树;只勾 ns `frontiers`(红球),其余 false | 开启 |
| PlannerViz/RobotState | rviz/MarkerArray | `/vis/robot_state` | 机器人状态盒(4 个 ns 全勾) | 开启 |
| PlannerViz/PlanningWorkspace | rviz/MarkerArray | `/vis/planning_workspace` | 规划工作空间盒 | 默认关闭 |
| PlannerViz/GlobalGraph | rviz/MarkerArray | `/vis/planning_global_graph` | 全局图 | **默认关闭**(与 smb 不同),Namespaces 为空 `{}` |
| PlannerViz/HomingPath | rviz/MarkerArray | `/vis/planning_homing_path` | 回家路径 | 默认关闭 |
| PlannerViz/PlanningGraph | rviz/MarkerArray | `/vis/planning_graph` | 局部采样图(ns `vertices` 勾选,`edges`=false;**无 `hanging_vertices` 条目**) | 开启 |
| PlannerViz/Sampler | rviz/MarkerArray | `/vis/sampler` | 采样点 | 默认关闭 |
| PlannerViz/RefPath | rviz/MarkerArray | `/vis/ref_path` | 下发执行的参考路径(ns `ref_path`/`vertices` 勾选) | 开启 |
| PlannerViz/RayCasting | rviz/MarkerArray | `/vis/ray_casting` | 射线投射 | 默认关闭 |
| PlannerViz/ShortestPathsClustering | rviz/MarkerArray | `/vis/shortest_path_clustering` | 路径聚类 | 默认关闭 |
| PlannerViz/StateHist | rviz/MarkerArray | `/vis/state_history` | 状态历史 | 默认关闭 |
| PlannerViz/PlanningGlobalPath | rviz/MarkerArray | `/vis/planning_global_path` | 全局路径(current2frontier / frontier2home) | 开启 |
| PlannerViz/NoGainZone | rviz/MarkerArray | `/vis/no_gain_zone` | 无增益区 | 开启(Namespaces 空 `{}`) |
| PlannerViz/GoToWaypointVis | rviz/Marker | `/gbplanner/go_to_waypoint_pose_visualization` | 手动 waypoint 可视化 | 开启 |
| PlannerViz/CarrotPose | — | — | — | **该配置未包含** |
| PlannerViz/Geofence | — | — | — | **该配置未包含** |
| Sensors/Image | rviz/Image | `/m100/camera_blackfly/image_raw` | 相机图像 | 组整体关闭 |
| Sensors/VLP | rviz/PointCloud2 | `/rmf_obelix/velodyne_points` | Velodyne 原始点云(AxisColor 按 Z) | 组整体关闭(Sensors Enabled: false) |
| Voxblox/VoxbloxMesh | voxblox_rviz_plugin/VoxbloxMesh | `/gbplanner_node/mesh` | voxblox 网格 | 默认关闭 |
| Voxblox/Occupied | rviz/MarkerArray | `/gbplanner_node/occupied_nodes` | voxblox 占据体素 | **默认关闭**(与 smb 相反) |
| Voxblox/Tsdf | rviz/PointCloud2 | `/gbplanner_node/tsdf_pointcloud` | TSDF 点云 | 默认关闭 |
| Voxblox/SurfacePCL | rviz/PointCloud2 | `/gbplanner_node/surface_pointcloud` | voxblox 表面点云(AxisColor 按 Z,Alpha 0.8) | **开启**(rmf_obelix 配置里体素地图主显示;与 smb 相反) |
| CommandTraj | rviz/MarkerArray | `/pci_command_trajectory_vis` | PCI 下发轨迹可视化 | 默认关闭;同表1 备注(仅 advertise) |
| RobotModel | — | — | — | **该配置未包含** |

视角:Orbit,Target Frame=`rmf_obelix/base_link`。

两配置体素地图显示互补:**smb 用 Occupied(occupied_nodes 方块),rmf_obelix 用 SurfacePCL(surface_pointcloud 点云)**——现场看到的"地图"长相不同,数据源都是 gbplanner_node(voxblox)。

---

## 表3:样式 → topic + namespace 对照(语义以 topic+ns 为准,不以颜色为准)

所有 ns 与 RGB 均摘自 `gbplanner_rviz.cpp` 实码(行号为镜像内文件行号)。同一颜色可能出现在多个 topic 上,**现场辨认必须点开 RViz 显示项的 Namespaces 面板核对 topic**。

| 现场样式 | marker topic | namespace | 类型/尺寸 | 语义 | 代码佐证 |
|---|---|---|---|---|---|
| 红球(大,0.5m) | `/vis/shortest_paths` | `frontiers` | SPHERE_LIST 0.5 | 局部图中的 **frontier 顶点**(探索边界候选) | L1396,RGB(255,0,0) |
| 红球(大,0.5m)同款 | `/vis/planning_global_graph` | `frontier` | SPHERE_LIST 0.5 | **全局图**中的 frontier 顶点(注意 ns 是单数 `frontier`) | L643,RGB(255,0,0) |
| 紫点/紫红小球(0.3m) | `/vis/planning_graph` | `vertices` | SPHERE_LIST 0.3 | 局部采样图顶点 | L298,RGB(125,42,104) |
| 蓝紫小球(0.3m) | `/vis/planning_global_graph` | `vertices` | SPHERE_LIST 0.3 | 全局图顶点 | L611,RGB(53,49,119) |
| 橙棕小球(0.3m) | `/vis/shortest_paths` | `vertices` | SPHERE_LIST 0.3 | 最短路径树顶点 | L1236,RGB(200,100,0);两配置默认不勾选此 ns |
| 亮绿粗线(0.4) | `/vis/planning_global_path` | `current2frontier` | LINE_LIST 0.4 | 全局路径:当前位置→目标 frontier | L1590,RGB(0,255,0) |
| 亮绿粗线(0.4)同色 | `/vis/planning_homing_path` | `best_path` | LINE_LIST 0.4 | **回家路径**(与上一行同色同粗,只能靠 topic 区分) | L1544,RGB(0,255,0);两配置默认关闭 |
| 深绿细线(0.2) | `/vis/best_planning_paths` | `best_path` | LINE_LIST 0.2 | 局部规划选出的最优路径 | L1741,RGB(11,114,27) |
| **粉/品红线(0.25)** | `/vis/ref_path` | `ref_path` | LINE_LIST 0.25 | **下发给 PCI 执行的参考路径**(现场最关键的"粉线") | L1897,RGB(244,66,226) |
| 粉/品红线同色(0.4) | `/vis/alternate_path` | `best_path` | LINE_LIST 0.4 | visualizePath 输出的备选路径 | L1666,RGB(244,66,226);**两份 rviz 配置均未包含此 display** |
| 暗红线(0.4) | `/vis/planning_global_path` | `frontier2home` | LINE_LIST 0.4 | 全局路径:frontier→home 段 | L1623,RGB(128,0,0) |
| 橙棕细线(0.1) | `/vis/planning_global_graph` | `edges` | LINE_LIST 0.1 | 全局图的边 | L533,RGB(200,100,0) |
| 蓝色半透明方块 | `/vis/volumetric_gains` | `occupied_voxels` | CUBE_LIST(voxel 尺寸) | 增益评估中的占据体素 | L2101,RGB(0,0,255),a=0.4;默认关闭 |
| 体素方块阵(整张地图) | `/gbplanner_node/occupied_nodes` | `occupied_voxels` | (voxblox 发布) | voxblox 地图占据体素 | ns 来自 rviz yaml 勾选项;发布方=voxblox 包,不在本次 cpp grep 范围内,颜色由 voxblox 侧按高度/强度着色 |
| 黄线 | `/vis/mod_path` | `mod_path` | LINE_LIST | 修形(modified)路径 | L2539,RGB(244,217,66);**两份 rviz 配置均未包含此 display** |
| 机器人处的彩色盒/箭头 | `/vis/robot_state` | `size` / `extension` / `extension_aligned` / `heading` | 多种 | 机器人碰撞盒、扩展盒、朝向 | L868/L897/L926/L957 |
| PCI 轨迹(若出现) | `/pci_command_trajectory_vis` | **ns 未定位** | MarkerArray | PCI 下发轨迹可视化 | pci_manager.h L21-22 仅 advertise,全仓未见 publish 调用与 ns 赋值;以 RViz 内展开 Namespaces 面板为准 |

### 现场辨认三步法
1. 看到可疑线/球,先在 RViz Displays 面板逐个开关显示项,锁定它属于哪个 **topic**;
2. 展开该显示项的 **Namespaces** 面板,勾/去勾确认具体 ns;
3. 语义以本表 topic+ns 行为准——**同色≠同义**(亮绿线有两个来源、粉线有两个来源、红球有两个来源)。

### 与本项目粉线纪律的关系
桥/适配器只消费 `/rmf_obelix/command/trajectory`(发布者=pci,已实证),**绝不接任何 `/vis/*`**。RViz 里的粉线(`/vis/ref_path`,ns `ref_path`)只是规划器侧的可视化镜像,不是控制数据通路。
