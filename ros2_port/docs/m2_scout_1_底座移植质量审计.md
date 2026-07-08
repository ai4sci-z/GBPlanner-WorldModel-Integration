# M2 侦察报告①:snt-arg 底座移植质量审计

> 生成:2026-07-08,m2-voxblox-scout workflow(3 并行只读审计)。状态:ACTIVE-for-M2

## 结论

snt-arg/voxblox_ros2_minimal 移植质量整体合格:9 包全部 ament 化,无存活的 roscpp/ROS1 代码(残留全是注释),tsdf/esdf server 的 pub/sub/service/timer 与 ROS1 逐项对齐(6 个服务含 save/load map 齐全),Gabriele 分叉(=snt-arg+3 个 commit)带 Jazzy Docker CI 做全量 colcon build,可构建性有背书。两个真坑:① voxblox_ros/package.xml 声明了代码根本不用的 voxblox_rviz_plugin 依赖,会把 Qt5/rviz 拖进 headless 容器,须删 1 行;② rosdep 键大量失效(gflags_catkin/glog_catkin/glog_vendor/libpcl-all),且 CMake 必需的 backward_ros/glog/protobuf 未在 package.xml 声明——系统依赖只能按 Gabriele Dockerfile.base 的 apt 清单装。行为等价方面:GBPlanner 实际 pin 的 ntnu-arl/voxblox@dev/noetic(ref 克隆已在该分支 0ee88c2)与本底座唯一实质分歧集中在 tsdf_integrator(NTNU 的 new-abort-criterion+clearing_ray_weight_factor/weight_ray_by_range/use_symmetric_weight_dropoff vs 港版 ethz 的 sparsity_compensation_factor,~162 行差异);GBPlanner 的 voxblox_sim_config.yaml 两族参数都写了("OVERLAP BETWEEN VERSIONS" 段),直接跑港版会静默走 ethz 权重路径,逐体素对拍必然不等价,须把 NTNU integrator 差异移植进来。最小构建集=7 包(xmlrpcpp, eigen_checks, minkindr, minkindr_conversions, voxblox_msgs, voxblox, voxblox_ros),skeleton 和 rviz_plugin 第一版都可跳过。

## 详情

## 一、逐包依赖与 ament 化状态(9 包)

底座根:`\\wsl.localhost\Ubuntu-22.04\home\ai4s\ros2_port_ws\src\voxblox_ros2_minimal`

| 包 | ament 化 | ROS 依赖 | 系统依赖 | 问题 |
|---|---|---|---|---|
| voxblox(core) | ament_cmake_auto,C++17 | eigen_checks, minkindr | **Protobuf**(`protobuf_generate` TARGET 模式,需 protobuf-compiler)、Eigen3、**glog**(glog::glog imported target) | package.xml 未声明 protobuf/glog → rosdep 装不出来 |
| voxblox_msgs | rosidl,完全 ament | std_msgs, geometry_msgs, builtin_interfaces | — | msg/srv 集合与 ROS1 ntnu 完全一致(Block/Layer/Mesh/MeshBlock/VoxelEvaluationDetails + FilePath.srv) |
| voxblox_ros | ament_cmake_auto | rclcpp, pcl_ros, pcl_conversions, cv_bridge, interactive_markers, std_srvs, sensor_msgs, tf2/tf2_ros, minkindr_conversions, voxblox, voxblox_msgs, xmlrpcpp, **voxblox_rviz_plugin(代码零使用!)** | PCL, glog, Protobuf, **backward_ros(CMake REQUIRED 但 package.xml 未声明)** | package.xml 残留 ROS1 键 `gflags_catkin`、`libpcl-all`(ament_auto QUIET 静默跳过,不阻塞 colcon,但 rosdep 报错) |
| voxblox_rviz_plugin | 已按 RViz2 重写(pluginlib+AUTOMOC) | rviz_common/rendering/default_plugins/ogre_vendor, Qt5 | qtbase5-dev | 仅 mesh 可视化用;headless 不需要 |
| voxblox_skeleton | ament_cmake_auto | voxblox, voxblox_ros, backward_ros | Protobuf, glog | GBPlanner 全源码 0 引用,可跳过 |
| eigen_checks | ament_cmake_auto | ament_cmake_gtest | Eigen3, glog | 残留键 `glog_vendor`;gtest 无 BUILD_TESTING 保护(恒编译测试) |
| minkindr(目录 minikindr_ament) | INTERFACE header-only | — | Eigen3 | 干净 |
| minkindr_conversions | INTERFACE | rclcpp, tf2/tf2_ros/tf2_geometry_msgs/tf2_eigen, geometry_msgs, minkindr, xmlrpcpp | glog | 残留键 `gflags_catkin`/`glog_catkin`/`Eigen3`(非标准 rosdep 键) |
| xmlrpcpp | ament 化的 ROS1 vendored 库 | — | — | `XmlRpcDispatch.cpp` 被注释未移植(TODO bpwilcox);LGPL-2.1 |

**Jazzy 系统依赖权威清单** = `ref/voxblox-ros2-gabriele/docker/Dockerfile.base`:libgoogle-glog-dev, libgflags-dev, libprotobuf-dev, protobuf-compiler, libpcl-dev, libeigen3-dev, libdw-dev/libelf-dev(backward_ros), qtbase5-dev + ros-jazzy-{backward-ros, cv-bridge, pcl-ros, pcl-conversions, interactive-markers, tf2*, std-srvs, rviz-*}。**不要走 rosdep**(失效键太多)。

## 二、ROS1 残留审计

- `ros/ros.h`/`ros::NodeHandle`/roscpp:**全部只存在于注释里**(voxblox_ros/src/*.cc、voxblox_skeleton/src/*.cpp、tsdf_server.h L143-144),无存活代码。tf1 无引用(全部 tf2_ros)。
- **XmlRpc 存活使用 3 处**:`voxblox_ros/src/transformer.cc` L93-124(T_B_D/T_B_C 矩阵参数)、`voxblox_ros/src/voxblox_eval.cc`、`minkindr_ros/minkindr_conversions/include/minkindr_conversions/kindr_xml.h`(xmlRpcToKindr)——这就是 vendored xmlrpcpp 存在的唯一原因:ROS1 param server 用 XmlRpcValue 装 4x4 矩阵参数,移植时没重写。**在 ROS2 运行期是死路**(rclcpp 参数不可能装出 XmlRpc 结构体;该分支还只在 use_tf_transforms=false 时走),编译能过(Gabriele Jazzy CI 全量 colcon build 背书)。GBPlanner 配置 `use_tf_transforms: True`(gbplanner/config/rmf_obelix/voxblox_sim_config.yaml L2)→ 完全不受影响。短期保留 xmlrpcpp,后续可用 double 数组参数替换 T_B_D/T_B_C 解析后整包删除。
- snt-arg 仓自带的 `.github/workflows/build_test.yml` 是 **melodic/noetic 的 ROS1 陈旧 CI**(未更新),本仓自身无 ROS2 CI;Jazzy 可构建性证据来自 Gabriele 分叉的 Docker CI(全量 `colcon build --merge-install`,jazzy 镜像)。

## 三、tsdf/esdf server 完整度(作者自述 "lacking" 核查)

- 逐项对照 ntnu ROS1 版:**接口全齐**。tsdf_server:6 服务(generate_mesh/clear_map/save_map/load_map/publish_pointclouds/publish_map,tsdf_server.cc L220-249)、surface/tsdf pointcloud/occupied_nodes/slice/mesh 发布、pointcloud+freespace_pointcloud 订阅、tsdf_map_out/in、ICP(含 icp_corrected TF 广播,已用 tf2_ros 重写,L521 注释只是留档)、update_mesh/publish_map 双 timer。esdf_server:esdf_pointcloud/slice/traversable/esdf_map_out/in + update_esdf timer 全在。
- 作者 commit "migration complete, there are some **lacking dependencies**"(f59726d)指的是依赖,不是功能缺失;实际缺口就是上表的 package.xml 声明问题。
- ROS1 私有话题 `~topic` 用 `generate_private_name()`(tsdf_server.cc L15)映射成 `<node_name>/topic`;`pointcloud` 订阅是公共名。M5 接线时注意这个命名差异。
- snt-arg 基线的 `tsdf_server_node.cc` main 里 gflags 先于 rclcpp::init 解析并删 argv,**会吃掉 --ros-args**;Gabriele b5c3911 已修(rclcpp 先 init + `automatically_declare_parameters_from_overrides(true)`),必须采纳。

## 四、行为等价:ntnu(GBPlanner 真实依赖)vs 本底座

- **pin 已确认**:`sources\gbplanner_ros-源码\packages_https.rosinstall` L44-47 → `ntnu-arl/voxblox @ dev/noetic`。ref 克隆 `/home/ai4s/ros2_port_ws/ref/voxblox-ntnu` 本地分支 dev-noetic == origin/dev/noetic @ 0ee88c2(已 fetch 核实;之前说的 3346747/master 不是 pin 分支,已纠正)。
- dev/noetic 家谱 = ethz master(~2019-11)+ ethz 未合入 master 的 feature/new_abort_criterion_for_fast_integrator + 唯一 NTNU 自产 commit 0ee88c2(C++14)。
- **唯一实质行为分歧 = tsdf_integrator**(diff -wB ~162 行):NTNU 版 Config 有 `clearing_ray_weight_factor / weight_ray_by_range / use_symmetric_weight_dropoff`、`max_consecutive_ray_collisions` 默认 0、`updateTsdfVoxel(ray_weight, clearing_ray_weight)` 返回 bool、FastTsdfIntegrator 的 `shouldAbortIntegration`(截断距离内永不 abort);港版是 ethz 谱系的 `use_sparsity_compensation_factor / sparsity_compensation_factor`、max_consecutive_ray_collisions 默认 2。ros_params.h 参数集合 diff 精确证实:仅缺 NTNU 这 3 个键,多 sparsity 2 个键。
- **GBPlanner 配置两族参数都写了**(voxblox_sim_config.yaml 有 "OVERLAP BETWEEN VERSIONS" 段:sparsity_compensation_factor=100 和 clearing_ray_weight_factor=0.01 并存)→ 在 ROS1-NTNU 上走 clearing-ray 弱权重路径,在港版上会**静默改走 ethz sparsity 路径**,TSDF 权重/值必然不等价,逐体素对拍过不了。要么把 NTNU integrator 差异移植进港版 core+ros_params(推荐,改动面小且集中),要么接受行为漂移并记录。
- 其余 core 差异全部无害:esdf_integrator/block/layer 是注释与 include 顺序;esdf_map/interpolator 是港版超集(多 getEsdfLayerConstPtr、getWeight 族);**proto 目录字节级一致**(diff 确认)→ save_map/load_map 层文件可用于 oracle 对拍(对拍建议按体素查询比,不比原始字节,block 序列化顺序可能不稳定)。
- GBPlanner 消费面核查(`planner_common/include/planner_common/map_manager_voxblox_impl.h`):`#define use_tsdf` → 进程内实例化 `voxblox::TsdfServer`(非独立节点),用 esdf_server.h/ros_params.h/transformer.h + core 的 castRay/interpolator/planning_utils/layer_utils——全部存在于港版。M3/M4 需适配构造签名:ROS1 `TsdfServer(nh, nh_private)` → ROS2 `TsdfServer(rclcpp::Node*)`。

## 五、最小构建集合

GBPlanner gain(raycast+三态)与碰撞(TSDF/ESDF 距离)只需:**voxblox_ros + voxblox + voxblox_msgs + vendored 链(minkindr, minkindr_conversions, eigen_checks, xmlrpcpp)= 7 包**。
- `voxblox_skeleton`:跳过(GBPlanner 0 引用)。
- `voxblox_rviz_plugin`:跳过,但 **voxblox_ros/package.xml L34 的 `<depend>voxblox_rviz_plugin</depend>` 会让 `--packages-up-to voxblox_ros` 把它拖进来**(代码从未使用;ros:jazzy-ros-base 无 rviz,headless 容器直接构建失败)。删这 1 行(我们自己的 fork,合法维护补丁)后:`colcon build --packages-up-to voxblox_ros` 即得 7 包最小集。备选 `--packages-skip voxblox_rviz_plugin` 也可(ament_auto 对缺席依赖 QUIET 跳过),但删行更干净。

## 行动项

- P0|把 Gabriele Dockerfile.base 的 apt 清单固化为 M2 构建环境(jazzy 容器内 apt 装 libgoogle-glog-dev/libgflags-dev/libprotobuf-dev/protobuf-compiler/libpcl-dev/libeigen3-dev/libdw-dev/libelf-dev + ros-jazzy-backward-ros/cv-bridge/pcl-ros/pcl-conversions/interactive-markers/tf2 全家/std-srvs);禁止走 rosdep(gflags_catkin/glog_catkin/glog_vendor/libpcl-all/Eigen3 键全失效)
- P0|采纳 Gabriele 分叉 b5c3911(tsdf_server_node:rclcpp 先 init + NodeOptions automatically_declare_parameters_from_overrides(true) + gflags 不删 argv)——否则 --ros-args/--params-file 会被 gflags 吃掉;可顺带 c921ef6 launch 参数化(参考用)
- P0|删 voxblox_ros/package.xml L34 <depend>voxblox_rviz_plugin</depend>(代码零使用),然后最小集构建:colcon build --packages-up-to voxblox_ros(=xmlrpcpp, eigen_checks, minkindr, minkindr_conversions, voxblox_msgs, voxblox, voxblox_ros 共 7 包);voxblox_skeleton 一并跳过
- P1|移植 NTNU tsdf_integrator 差异到港版 core + ros_params.h(clearing_ray_weight_factor / weight_ray_by_range / use_symmetric_weight_dropoff / shouldAbortIntegration / max_consecutive_ray_collisions 默认 0 / updateTsdfVoxel 双权重签名)——GBPlanner voxblox_sim_config.yaml 显式设了这些键,不移植则港版静默走 ethz sparsity_compensation 路径,逐体素对拍必不等价;对拍 oracle 用 ref/voxblox-ntnu 本地分支 dev-noetic(=origin dev/noetic @0ee88c2,已核实)
- P1|对拍方案:proto 字节级一致已确认,save_map/load_map 层文件两边可互读;比对按体素查询(voxel value/weight/observed 三态)而非文件原始字节(block 序列化顺序不保证稳定);先用两版语义相同的参数(use_weight_dropoff=True、关 sparsity、method=fast)打通管线,再上 NTNU integrator 补丁追全等
- P2|M3/M4 预埋:MapManagerVoxblox 构造从 TsdfServer(nh,nh_private) 改 TsdfServer(rclcpp::Node*);话题名差异(ROS1 ~private → 港版 <node_name>/topic,generate_private_name;pointcloud 订阅是公共名);GBPlanner 栈 use_tf_transforms:True,transformer 的 XmlRpc T_B_D/T_B_C 死路径不影响,xmlrpcpp 先保留(后续可换 double 数组参数后整包删除,注意其 LGPL-2.1)
- P2|CI 认知纠偏:snt-arg 仓自带 workflow 是 melodic/noetic ROS1 陈旧文件,勿当 ROS2 构建证据;Jazzy 证据=Gabriele 分叉 Docker CI(全量 colcon build),我方 M2 自跑 colcon 后即自证
