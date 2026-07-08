# M2 侦察报告③:Jazzy 构建配方(Gabriele 仓提取)

> 生成:2026-07-08,m2-voxblox-scout workflow(3 并行只读审计)。状态:ACTIVE-for-M2

## 结论

Gabriele 仓的 Jazzy 构建配方非常干净:一个 Dockerfile.base(基于 ros:jazzy,两段 apt 清单:系统级 libeigen3/gflags/glog/boost/pcl/protobuf/qtbase5 + ROS 级 backward-ros/cv-bridge/pcl-ros/rviz 全家桶/tf2 全家桶)加 CI 里一条 `colcon build --merge-install --cmake-args -DCMAKE_BUILD_TYPE=Release`,零 patch、零特殊环境变量,且 CI 徽章证明此配方在 Jazzy 上全仓构建通过。两仓严格同源:snt-arg HEAD=d08e9d4,Gabriele 恰好多 3 个 commit(b5c3911 源码修复 / c921ef6 launch 增强 / 243dc3e Docker 配方),全仓文件级 diff 仅 5 个文件。必须搬到 snt-arg 底座的只有 b5c3911 的两处改动(voxblox_ros CMake 加 INSTALL_TO_SHARE launch/cfg/mesh_results;tsdf_server_node.cc 改为先 rclcpp::init 再 gflags 解析 + automatically_declare_parameters_from_overrides(true)),并且发现 Gabriele 漏修了 esdf_server_node.cc——它仍是旧模式(gflags remove_flags=true 先吃 argv 再 rclcpp::init,且无 auto-declare),而 GBPlanner 实际依赖的正是 esdf_server,必须同款补修。m2_build.sh 草案已按 m1_build.sh 模式(挂载只读→容器内 cp 到原生 FS→colcon)给出:预构建依赖镜像 + 三段 --packages-up-to 分层构建(voxblox core→voxblox_ros→全量)+ MAKEFLAGS 控并行 + esdf_server 冒烟验收;特别注意不可跑 rosdep install(package.xml 里残留 gflags_catkin/glog_vendor/libpcl-all 等 ROS1 假 key 会炸)。

## 详情

## 一、Gabriele 仓 Jazzy 构建配方(任务 1)

### 1.1 apt 依赖清单(证据:`\\wsl.localhost\Ubuntu-22.04\home\ai4s\ros2_port_ws\ref\voxblox-ros2-gabriele\docker\Dockerfile.base`,基镜像 `ros:jazzy`)

**系统包**(第一段 RUN):
```
build-essential cmake git libdw-dev libeigen3-dev libelf-dev libgflags-dev
libgoogle-glog-dev libboost-all-dev libpcap-dev libpcl-dev libprotobuf-dev
pkg-config protobuf-compiler qtbase5-dev
```
**ROS 包**(第二段 RUN,`ros-jazzy-` 前缀):
```
backward-ros cv-bridge geometry-msgs interactive-markers pcl-conversions pcl-ros
pluginlib rclcpp rviz-common rviz-default-plugins rviz-ogre-vendor rviz-rendering
sensor-msgs std-srvs tf2 tf2-eigen tf2-geometry-msgs tf2-ros rviz2
```
说明:`libdw-dev/libelf-dev` 是 backward_ros 栈回溯用;`qtbase5-dev + rviz-common/rendering/default-plugins/ogre-vendor` 是编 voxblox_rviz_plugin 的硬需求(voxblox_ros 的 package.xml `<depend>voxblox_rviz_plugin</depend>`,绕不开);`rviz2` 本体仅运行时可视化需要,headless 构建容器可省。

### 1.2 colcon 命令(证据:`...\voxblox-ros2-gabriele\.github\workflows\build_test.yml` L25-35)
```
source /opt/ros/jazzy/setup.bash
colcon build --merge-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```
CI 在 jazzy 容器里全仓(9 包)一次构建通过 → 这是**已验证配方**。

### 1.3 Jazzy 专用 patch / 环境变量
**没有**。Dockerfile 无 ENV、无源码 patch、无 colcon mixin;Makefile(`...\voxblox-ros2-gabriele\Makefile`)只是开发容器便利目标(`docker build -t voxblox:jazzy` + 带 X11/GPU 的 `docker run`),对构建无额外输入。注意 CMakeLists 里 voxblox_ros 自己 `set(CMAKE_BUILD_TYPE RelWithDebInfo)` 会覆盖命令行 Release,无需干预。

## 二、Gabriele vs snt-arg 底座差异(任务 2)

git 确认同源:snt-arg HEAD = `d08e9d4`,Gabriele = d08e9d4 + 3 commit(`b5c3911` → `c921ef6` → `243dc3e`)。全树 `diff -qr` 仅 5 个文件不同:

| 文件 | 来源 commit | 内容 | 是否搬 |
|---|---|---|---|
| `voxblox_ros/CMakeLists.txt` | b5c3911 | `ament_auto_package()` → `ament_auto_package(INSTALL_TO_SHARE launch cfg mesh_results)`(三个目录底座里都已存在) | **必搬**(否则 launch/cfg 不装进 share,下游 launch 找不到) |
| `voxblox_ros/src/tsdf_server_node.cc` | b5c3911 | 初始化顺序修复:先 `rclcpp::init(argc,argv)` 让 `--ros-args/--params-file` 先被 ROS 吃掉,再 `gflags::ParseCommandLineNonHelpFlags(remove_flags=false)`;并加 `NodeOptions.automatically_declare_parameters_from_overrides(true)`(YAML 参数不用逐个 declare 就能进节点) | **必搬** |
| `voxblox_ros/launch/cow_and_lady_dataset.launch.py` | c921ef6 | 加 world→kinect、kinect→camera_rgb_optical_frame 两个 static TF;`use_sim_time:=true`、`timestamp_tolerance_sec:=0.2`、publish_pointclouds 参数;附 ROS1 bag 转换命令(`pip install rosbags` + `rosbags-convert`) | **选搬**——对 GBPlanner 集成非必需,但对 M2「ROS1 oracle 对拍」极有用(cow_and_lady 是确定性数据集,bag 转换命令直接可用) |
| `.github/workflows/build_test.yml` | 243dc3e | snt-arg 里还是 ROS1 melodic/noetic catkin 的**陈旧 CI**(意味着 snt-arg 自己从未在 CI 上验证过 ROS2 构建!);Gabriele 换成 jazzy docker colcon | 若保留 CI 则搬,否则删 |
| `Makefile` + `docker/`(仅 Gabriele 有) | 243dc3e | 构建配方本体 | 以 m2_build.sh 形式复刻,不必逐字搬 |

### ⚠️ 额外发现(Gabriele 没修完的坑)
`voxblox_ros/src/esdf_server_node.cc`(底座与 Gabriele 一致,均未修)仍是旧模式:`gflags::ParseCommandLineNonHelpFlags(&argc,&argv,remove_flags=true)` 在 `rclcpp::init` **之前**执行,会吞/挪 `--ros-args` 相关 argv,且无 `automatically_declare_parameters_from_overrides` → 用 `--params-file` 喂 GBPlanner 的 voxblox 参数会大面积失效。**GBPlanner 依赖的正是 esdf_server**,必须把 b5c3911 的同款修复移植到 esdf_server_node.cc(以及 intensity_server_node.cc/skeleton 节点如后续用到)。同款旧模式还存在于 `voxblox_eval.cc` L307、`simulation_eval.cc` L48、`voxblox_skeleton/src/skeleton_eval.cpp` L412(离线工具,优先级低)。

### 依赖解析方式确认(为什么 apt 清单即可、禁止 rosdep)
package.xml 残留 ROS1 假 key:`gflags_catkin`、`glog_catkin`、`glog_vendor`、`libpcl-all`、`Eigen3`(见 `voxblox_ros/package.xml`、`minkindr_conversions/package.xml`、`eigen_checks/package.xml`)。colcon 只用它们排包序,但 `rosdep install --from-paths` 会解析失败直接报错——**M2 构建不要跑 rosdep**,依赖全靠 Dockerfile 的显式 apt 清单(CMake 侧实际走 `find_package(glog/Protobuf/PCL/Eigen3/Qt5)` 系统查找,已被 Gabriele CI 验证)。

### 包清单与依赖序(9 包,证据:各 package.xml)
`xmlrpcpp`(vendored,无依赖)、`eigen_checks`、`minkindr`(目录名 minikindr_ament)、`minkindr_conversions`(依赖 minkindr+xmlrpcpp+tf2 系)、`voxblox_msgs`(仅 std_msgs+rosidl)、`voxblox`(core,依赖 eigen_checks+minkindr+Protobuf)、`voxblox_rviz_plugin`(依赖 voxblox+voxblox_msgs+rviz 系+Qt5)、`voxblox_ros`(依赖上述全部+pcl_ros+backward_ros)、`voxblox_skeleton`(依赖 voxblox_ros)。

## 三、m2_build.sh 完整草案(任务 3)

模式沿用 `\\wsl.localhost\Ubuntu-22.04\home\ai4s\ws-clean\m1_build.sh`(注意:m1_build.sh 实际在 ws-clean/ 下,不在 runbooks/ros2_port/)。与 M1 的差别:①voxblox 编译重(PCL 模板+6 个可执行文件),依赖 apt 装一次 ~2GB,故先固化依赖镜像再复用;②分三段 `--packages-up-to` 定位失败层;③源码在 WSL 原生 ext4(/home/ai4s/ros2_port_ws),仍挂只读+容器内 cp,保证不污染底座。建议入库路径 `runbooks/ros2_port/m2_build.sh`(feat/gbplanner-ros2-port 分支)。

```bash
#!/usr/bin/env bash
# M2: build voxblox ROS2 (snt-arg base + Gabriele jazzy patches) in a Jazzy container.
# Recipe source: ref/voxblox-ros2-gabriele docker/Dockerfile.base + .github/workflows/build_test.yml (CI-proven).
# Pattern: same as m1_build.sh — mount ro, cp into container FS, colcon there.
# DO NOT run rosdep install: package.xml still has ROS1 keys (gflags_catkin/glog_vendor/libpcl-all).
set -uo pipefail
SRC=/home/ai4s/ros2_port_ws/src/voxblox_ros2_minimal
IMG=voxblox_ros2_deps:jazzy
EVID=/home/ai4s/ros2_port_ws/m2_build_evidence.txt

# --- 1. dependency image (built once, cached; ~2 GB apt layer) ---
docker build -t "$IMG" - <<'DOCKERFILE'
FROM ros:jazzy-ros-base
SHELL ["/bin/bash","-c"]
RUN apt-get update && apt-get install -y \
    build-essential cmake git libdw-dev libeigen3-dev libelf-dev \
    libgflags-dev libgoogle-glog-dev libboost-all-dev libpcap-dev \
    libpcl-dev libprotobuf-dev pkg-config protobuf-compiler qtbase5-dev \
 && apt-get install -y \
    ros-jazzy-backward-ros ros-jazzy-cv-bridge ros-jazzy-geometry-msgs \
    ros-jazzy-interactive-markers ros-jazzy-pcl-conversions ros-jazzy-pcl-ros \
    ros-jazzy-pluginlib ros-jazzy-rclcpp \
    ros-jazzy-rviz-common ros-jazzy-rviz-default-plugins \
    ros-jazzy-rviz-ogre-vendor ros-jazzy-rviz-rendering \
    ros-jazzy-sensor-msgs ros-jazzy-std-srvs \
    ros-jazzy-tf2 ros-jazzy-tf2-eigen ros-jazzy-tf2-geometry-msgs ros-jazzy-tf2-ros \
 && rm -rf /var/lib/apt/lists/*
DOCKERFILE
echo "IMAGE_RC=$?"

# --- 2. staged colcon build + acceptance, all inside container ---
docker run --rm -v "$SRC":/src:ro "$IMG" bash -c '
  set -eo pipefail
  source /opt/ros/jazzy/setup.bash
  mkdir -p /root/ws/src/voxblox_ros2_minimal
  cp -r /src/. /root/ws/src/voxblox_ros2_minimal/
  rm -rf /root/ws/src/voxblox_ros2_minimal/.git
  cd /root/ws
  # voxblox_ros TUs pull full PCL headers (~1-2 GB RSS each): cap parallelism.
  export MAKEFLAGS="-j8"
  echo "=== stage 1: core (xmlrpcpp/eigen_checks/minkindr/voxblox) ==="
  colcon build --merge-install --executor sequential \
    --packages-up-to voxblox \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -15
  echo "=== stage 2: ROS layer (msgs/minkindr_conversions/rviz_plugin/voxblox_ros) ==="
  colcon build --merge-install --executor sequential \
    --packages-up-to voxblox_ros \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -15
  echo "=== stage 3: rest (voxblox_skeleton) ==="
  colcon build --merge-install --executor sequential \
    --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -15
  echo "COLCON_ALL_STAGES=OK"
  source install/setup.bash
  echo "=== accept 1: packages ==="
  ros2 pkg list | grep -E "voxblox|minkindr|eigen_checks|xmlrpcpp"
  echo "=== accept 2: executables ==="
  ros2 pkg executables voxblox_ros    # expect: esdf_server tsdf_server intensity_server voxblox_eval simulation_eval visualize_tsdf
  echo "=== accept 3: msg interfaces ==="
  ros2 interface show voxblox_msgs/msg/Layer | head -8
  echo "=== accept 4: esdf_server smoke (node up + topics) ==="
  ros2 run voxblox_ros esdf_server --ros-args -p tsdf_voxel_size:=0.2 -p update_mesh_every_n_sec:=0.0 &
  SRV_PID=$!
  sleep 6
  ros2 node list
  ros2 topic list | grep -Ei "esdf|tsdf|mesh|pointcloud" || echo "WARN: no voxblox topics visible"
  kill $SRV_PID 2>/dev/null || true
  echo "SMOKE=done"
' 2>&1 | tee "$EVID"
echo "DOCKER_RC=$?"
echo "=== DONE, evidence: $EVID ==="
```

**并行度依据**:9 包中只有 voxblox_ros 是真大户(1 lib + 6 exe,全量 include PCL);`--executor sequential` + `MAKEFLAGS=-j8` 在 32G 机器(WSL ~16G)上安全;若仍 OOM 降 `-j4`。不建议 colcon 默认并行(多包 x 多 job 会叠乘)。全量预计 5-15 分钟。
**验收升级项**(m2 后半程,不进本脚本):cow_and_lady bag 按 c921ef6 提示 `rosbags-convert` 转 ROS2 后喂 tsdf_server,与 ROS1 oracle(voxblox-ntnu)逐体素对拍——jazzy CLI echo 靠不住,对拍取数一律 rclpy 订阅(既有铁律)。

## 关键文件路径索引
- Dockerfile 配方:`\\wsl.localhost\Ubuntu-22.04\home\ai4s\ros2_port_ws\ref\voxblox-ros2-gabriele\docker\Dockerfile.base`
- CI colcon 命令:`\\wsl.localhost\Ubuntu-22.04\home\ai4s\ros2_port_ws\ref\voxblox-ros2-gabriele\.github\workflows\build_test.yml`
- 必搬修复:`ref\voxblox-ros2-gabriele\voxblox_ros\src\tsdf_server_node.cc` + `voxblox_ros\CMakeLists.txt`(对照底座同名文件)
- 待补修漏网:`\\wsl.localhost\Ubuntu-22.04\home\ai4s\ros2_port_ws\src\voxblox_ros2_minimal\voxblox_ros\src\esdf_server_node.cc`(L14-18 旧 gflags 模式)
- M1 模式参照:`\\wsl.localhost\Ubuntu-22.04\home\ai4s\ws-clean\m1_build.sh`(注意:不在 runbooks/ros2_port/)

## 行动项

- P0|把 Gabriele b5c3911 两处改动搬进我们要 vendor 的 voxblox 底座副本(建议 vendor 到 ros2_port/src/ 后再改,勿动 ~/ros2_port_ws/src 原底座):①voxblox_ros/CMakeLists.txt 末行改 ament_auto_package(INSTALL_TO_SHARE launch cfg mesh_results);②tsdf_server_node.cc 换成 rclcpp::init 先行 + gflags remove_flags=false + NodeOptions.automatically_declare_parameters_from_overrides(true)
- P0|同款修复移植到 esdf_server_node.cc(Gabriele 漏修;GBPlanner 用的就是 esdf_server,不修则 --params-file 喂参数失效)——顺手评估 intensity_server_node.cc
- P0|落地 runbooks/ros2_port/m2_build.sh(草案见 details):先 docker build 依赖镜像 voxblox_ros2_deps:jazzy(apt 清单照抄 Gabriele Dockerfile.base),再挂载只读+容器内 cp+三段 colcon(--packages-up-to voxblox → voxblox_ros → 全量,--merge-install --executor sequential,MAKEFLAGS=-j8),验收=9 包 pkg list + voxblox_ros 6 个 executables + esdf_server 冒烟起节点看 topic;证据 tee 到 m2_build_evidence.txt
- P1|铁律入库:M2 构建禁止 rosdep install(package.xml 残留 gflags_catkin/glog_vendor/libpcl-all 等 ROS1 假 key 必炸),依赖只走显式 apt 清单;CMakeLists 里 voxblox_ros 硬编码 RelWithDebInfo 会覆盖命令行 Release,属正常现象
- P1|选搬 c921ef6 的 cow_and_lady_dataset.launch.py 增强(static TF + use_sim_time + timestamp_tolerance)作为 M2 oracle 对拍的确定性数据集入口;ROS1 bag 转换命令已给:pip install rosbags --break-system-packages && rosbags-convert --src data.bag --dst <out>;对拍取数用 rclpy 订阅(CLI echo 不可靠)
- P2|若给 vendor 副本保留 CI:用 Gabriele 243dc3e 的 jazzy workflow 替换 snt-arg 里陈旧的 melodic/noetic catkin workflow(snt-arg 自己从未在 CI 验证过 ROS2 构建,Gabriele 的 CI 徽章才是 Jazzy 构建通过的证据)
- P2|后续(M2 后半程)按任务书§7-M2 验收表做 ROS1 oracle 逐体素对拍;离线工具 voxblox_eval.cc/simulation_eval.cc/skeleton_eval.cpp 里同款旧 gflags 模式暂不修,用到再说
