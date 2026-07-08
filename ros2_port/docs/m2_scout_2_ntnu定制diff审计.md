# M2 侦察报告②:ntnu-arl 定制 diff 审计(行为等价命门)

> 生成:2026-07-08,m2-voxblox-scout workflow(3 并行只读审计)。状态:ACTIVE-for-M2

## 结论

GBPlanner 实际 pin 的是 ntnu-arl/voxblox @ dev/noetic 分支(packages_https.rosinstall L44-47),ref 克隆原 HEAD(master@3346747)确实不对,已 fetch 并 checkout 为本地分支 dev-noetic(HEAD 0ee88c2)。ntnu 定制与 ethz 官方的 merge-base 为 8d1b843,定制面高度集中:只改了 TSDF integrator 的权重语义与 Fast integrator 提前终止准则(新增 clearing_ray_weight_factor / weight_ray_by_range / use_symmetric_weight_dropoff 三参数、删除 sparsity_compensation、updateTsdfVoxel 签名 void→bool 并引入 shouldAbortIntegration 虚函数、max_consecutive_ray_collisions 默认 2→0),外加 ros_params 读参和一处纯可视化改动;ESDF/utils/core 完全未动。关键结论:snt-arg voxblox_ros2_minimal 底座是 ethz 血统(仍有 sparsity_compensation 旧语义、无 ntnu 三参数),而 GBPlanner 配置 method="fast" + clearing_ray_weight_factor=0.01 恰好踩在 ntnu 改动的热路径上——不移植该 patch,逐体素对拍必然失败;且 GBPlanner yaml 里残留的 use_sparsity_compensation_factor=True + factor=100(在 ntnu fork 中是死参数)在 ethz 血统底座上会被激活,造成 ×100 权重的二次发散,是最大的坑。

## 详情

## 1. Pin 确认

- 证据:`C:\CCproject\GBPlanner-WorldModel-Integration\sources\gbplanner_ros-源码\packages_https.rosinstall` L44-47:`uri: https://github.com/ntnu-arl/voxblox.git, version: dev/noetic`(packages_ssh.rosinstall 同构)。
- ref 克隆已修正:`/home/ai4s/ros2_port_ws/ref/voxblox-ntnu` 现在在本地分支 `dev-noetic`(HEAD **0ee88c2** "Changed to c++ 14")。原 master@3346747 不是 GBPlanner 用的分支。
- 与 ethz 官方(`/home/ai4s/ros2_port_ws/ref/voxblox-ethz` master **c8066b0**)的 merge-base = **8d1b843**(已把 ethz master 本地 fetch 进 ntnu 克隆便于 diff;注意该克隆里 FETCH_HEAD 引用不稳定,复现 diff 请用显式 hash `8d1b843` / `c8066b0` / `dev-noetic`)。
- ntnu-only 提交 = `feature/new_abort_criterion_for_fast_integrator` 一条线(9d40660→2cefc8f→d1a96d8→1487890→f9410d1→0ee88c2)。

## 2. ntnu 定制逐文件清单(git diff 8d1b843..dev-noetic)

### 必须移植(核心行为)
- **voxblox/include/voxblox/integrator/tsdf_integrator.h**(+106):Config 新增 `clearing_ray_weight_factor`(默认1.0)、`weight_ray_by_range`(默认false)、`use_symmetric_weight_dropoff`(默认false);**删除** `use_sparsity_compensation_factor`/`sparsity_compensation_factor`;`max_consecutive_ray_collisions` 默认 2→**0**;TsdfIntegratorBase 新增纯虚 `shouldAbortIntegration(global_voxel_idx, is_in_truncation_distance)`(Simple/Merged 返回 false,Fast 实现);`updateTsdfVoxel` 签名 void→**bool**,参数 `(weight)`→`(ray_weight, clearing_ray_weight)`。
- **voxblox/src/integrator/tsdf_integrator.cc**(+158):三层语义改动——①`getVoxelWeight` 判据从 `use_const_weight` 改为 `!weight_ray_by_range`(即默认恒1.0,开了才 1/z²);②`updateTsdfVoxel`:截断距离**外**统一用 `clearing_ray_weight = factor × ray_weight`,截断距离**内**三选一(symmetric dropoff / const / weight_dropoff 且下限从 0 改为 clearing_ray_weight);③Fast integrator 的碰撞终止逻辑移入 updateTsdfVoxel 返回值,**截断距离内永不提前终止**(旧版在表面附近也可能弃射线)。另有构造函数 CHECK 与 Config::print 更新。
- **voxblox_ros/include/voxblox_ros/ros_params.h**(+16):读取上述 3 个新参数、删除 sparsity 两参数的读取。需按底座的 rclcpp declare/get_parameter 风格改写。

### 建议移植(纯可视化,GBPlanner 配置值=默认,行为无差)
- **voxblox_ros/include/voxblox_ros/tsdf_server.h + src/tsdf_server.cc**:新成员 `occupancy_min_distance_voxel_size_factor_`(ros param,默认1.0)传入 createOccupancyBlocksFromTsdfLayer。
- **voxblox_ros/include/voxblox_ros/ptcloud_vis.h**:`createOccupancyBlocksFromTsdfLayer` 增加 `occupied_voxel_min_distance` 形参(原硬编码 voxel_size)。GBPlanner yaml 设 1.0 等价旧行为,占用节点 marker 可视化专用,对拍不受影响。

### 可忽略
- 4 个 CMakeLists(c++11→14、cmake 3.0.2):ROS2 底座已是 ament/C++17。
- launch(basement/cow_and_lady/euroc/kitti 删 sparsity 参数)、docs、clang-format 行。
- **voxblox/test/test_sdf_integrators.cc**(+13):随新 API 适配——不算"移植项"但建议一并带上作 M2 单测参照。

### ntnu 未动的部分(重要排除项)
esdf_integrator、esdf_server、utils/(planning_utils 等)、core/(tsdf_map/esdf_map/layer/block)、mesh、interpolator 全部无 ntnu 改动。ethz 在 fork 点之后的前进(8d1b843..c8066b0,底座已含)经抽查为 style/include-order/gcc-warning 修复 + 纯新增 API(color_maps、interpolator 等),esdf_integrator.cc 仅 include 排序——不构成行为冲突,底座无需降级。

## 3. 底座血统判定(snt-arg voxblox_ros2_minimal)

- `src\voxblox_ros2_minimal\voxblox\include\voxblox\integrator\tsdf_integrator.h` L67-68 仍有 `use_sparsity_compensation_factor`/`sparsity_compensation_factor`,L82 `max_consecutive_ray_collisions = 2`,L153 旧版 void updateTsdfVoxel,**无** shouldAbortIntegration/clearing_ray_weight/weight_ray_by_range → **ethz 血统,ntnu 定制一项都没有**。
- `voxblox_ros\include\voxblox_ros\ros_params.h` L210-250:rclcpp 路径**活跃地** declare+get `use_sparsity_compensation_factor`/`sparsity_compensation_factor`。

## 4. GBPlanner 调用面与配置面(定制是否被用到)

- 配置 `gbplanner\config\rmf_obelix\voxblox_sim_config.yaml`(smb 同构):L16 `method: "fast"` → **FastTsdfIntegrator 是热路径**,ntnu 的 abort 准则直接生效;L18 `max_consecutive_ray_collisions: 0`;L47 `clearing_ray_weight_factor: 0.01`(自由空间更新只有 1% 权重,占用面极难被误清除——GBPlanner 探索行为的关键调参);L48 `weight_ray_by_range: False`;L42-43 `use_const_weight: False`/`use_weight_dropoff: True`;L3 `use_freespace_pointcloud: True`。
- **坑①(最高危)**:yaml L9-10 `use_sparsity_compensation_factor: True` + `sparsity_compensation_factor: 100.0` 在 ntnu fork 中是**死参数**(已被删),但在 ethz 血统底座上是**活参数**——配置原样搬到未打补丁的底座会激活 ×100 稀疏补偿,叠加 clearing_ray_weight_factor 被忽略,双重行为发散。移植时必须删除这两行(或按 ntnu 语义删掉底座里的 sparsity 代码)。
- **坑②(无害但要知道)**:yaml L44 键名 `use_symmetric_weight_drop_off` 是笔误(ntnu 参数名为 `use_symmetric_weight_dropoff`),ROS1 下从未被读到,默认 false 恰好等价;移植配置时保持 false 即可。
- API 调用面(`planner_common\include\planner_common\map_manager_voxblox_impl.h` L24-32:`#define use_tsdf` → 用 voxblox::TsdfServer;`planner_common\src\voxblox\voxblox_common_impl.cpp`):TsdfServer/EsdfServer、Layer、Interpolator、TsdfIntegratorBase::Config、EsdfIntegrator::Config、getTsdfIntegratorConfigFromRosParam/getEsdfIntegratorConfigFromRosParam、castRay、getGridIndexFromPoint、getCenterPointFromGridIndex、utils::getAndAllocateBoxAroundPoint、HierarchicalIndexMap、Block/VoxelIndex——全是两个血统共有的标准 API;GBPlanner **不直接调** updateTsdfVoxel/shouldAbortIntegration,ntnu 定制通过"地图内容 + 参数读取"影响它,编译期唯一硬约束是 Config 结构体需含新字段、ros_params 需认新参数名。

## 行动项

- 【P0】把 ntnu tsdf_integrator patch 移植进底座:在 ref 克隆生成补丁 `git -C /home/ai4s/ros2_port_ws/ref/voxblox-ntnu diff 8d1b843 dev-noetic -- voxblox/include/voxblox/integrator/tsdf_integrator.h voxblox/src/integrator/tsdf_integrator.cc` 应用到 src/voxblox_ros2_minimal/voxblox(底座该两文件接近 ethz 老版,预计基本干净套上);核心=三个新 Config 字段+删 sparsity+shouldAbortIntegration+updateTsdfVoxel 新签名+max_consecutive_ray_collisions 默认0
- 【P0】改底座 voxblox_ros/include/voxblox_ros/ros_params.h 的 rclcpp 参数路径:declare/get `clearing_ray_weight_factor`/`weight_ray_by_range`/`use_symmetric_weight_dropoff`,删除 L210-250 的 sparsity 两参数读取(与 ntnu 语义对齐,防止坑①)
- 【P0】移植 GBPlanner voxblox 配置(rmf_obelix/voxblox_sim_config.yaml)时删除 L9-10 的 use_sparsity_compensation_factor/sparsity_compensation_factor 两行(ntnu 下是死参数,底座上会激活 ×100 发散);L44 键名笔误 use_symmetric_weight_drop_off 保持 false 语义即可
- 【P1】ROS1 oracle 对拍基线用 ref/voxblox-ntnu 的 dev-noetic 分支构建(不是 master@3346747);对拍配置锁定 method=fast + max_consecutive_ray_collisions=0 + clearing_ray_weight_factor=0.01 + truncation 0.6/voxel 0.2 + use_freespace_pointcloud=True(rmf_obelix yaml 原值)
- 【P1】把 ntnu 改过的 voxblox/test/test_sdf_integrators.cc(+13 行适配)一并移植,作 M2 单测级行为校验
- 【P2】可选补齐可视化等价:tsdf_server 的 occupancy_min_distance_voxel_size_factor 参数 + ptcloud_vis.h createOccupancyBlocksFromTsdfLayer 新形参(GBPlanner 设 1.0=旧行为,不影响逐体素对拍,可后置)
- 【P2】ESDF 侧无 ntnu 定制,底座 esdf_integrator/esdf_server 原样可用;ethz fork 点后的前进(style+新增 API)无需回退——不要为『对齐 ntnu 版本』去降级底座其他文件
