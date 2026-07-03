# 🔄 恢复文档 · 新窗口无损接管本任务

> 用途:本会话上下文将满。在**新窗口/新对话**里,让新的 Claude 读本文件 + `MEMORY.md`(自动加载)+ `README.md`(蓝图)+ `TASKS.md`(任务台账),即可**基本无损接管**。最后更新 2026-07-03。

## ⚙️ AGENT DIRECTIVES（下一个 Claude 先读这段，机器友好）
```yaml
role: 接管本任务的 Claude Code（运行在用户 Windows + WSL2 上）
language_to_user: 中文
task: 把 GBPlanner(ROS1,图搜索体积增益探索) 集成进 world-model(ROS2 无人机仿真平台)，替换占位探索 frontier_lite，论证其缺陷并量化对比突出 GBPlanner 优势
decision_locked: 桥接方案(ros1_bridge)  # 不是 gbplanner_core 重写
key_finding_2026_06_30: |
  frontier_lite 经查证是"脚本预设动作"(exploration_workflow_runtime.py.tmpl:142-147,pattern[goal_index%len(pattern)]按计时器循环 前进/左扭/右扭,且只订阅 /slam/odom+控制器状态、不订阅地图)，不是探索算法。
  GBPlanner 集成的精确插入点 = 这个探索决策节点(navlab_exploration_workflow,输出 /navlab/fcu/setpoint/intent + /navlab/exploration/*)。
  加法三步:①给仿真无人机加3D雷达(对齐OS064)+3D建图(octomap/voxblox) ②ros1_bridge把3D地图+位姿喂GBPlanner、回收航点 ③航点转 /navlab/fcu/setpoint/intent 替换脚本决策。
  详见 docs/集成机制与frontier_lite缺陷_核心发现.md(任务准星,对应 mentor md)。frontier_lite 决策代码证据已存 artifacts_sample/。
authoritative_sources_only:
  - github.com/SZ-surveying/world-model        # 注意:名字不是"世界模型"，只是项目名
  - github.com/ntnu-arl/gbplanner_ros @ gbplanner2 分支 + arXiv:2201.07067
  - 桌面 "自主探索决策(GBPlanner算法).md"(mentor 发)
hard_rules:  # 用户反复强调，违反会被追责
  - 只信真实产物(docker images / 文件 / 测试通过)，绝不信退出码或"completed"；已抓出 6+ 次假成功
  - 每完成一步：①更新文档(尤其主报告 README 全景) ②git commit+push ③刷桌面 md 副本 —— 四处同步(权威源/桌面junction/桌面md/GitHub)
  - 每个里程碑给用户全景报告：现在到哪/做了什么/下一步/用户怎么检查与演示(可视化)
  - 桌面 md 禁用 base64 内嵌图(Typora 不渲染)；用绝对路径引 PNG；图用 SVG→rsvg-convert 转 PNG(已装 fonts-noto-cjk)
  - 命名无歧义：预研A/预研B=复现任务；桥接/重写=集成方案(不用字母 A/B 指方案)
  - 留痕：仿真截图、图、表存 images/，文档写清做了什么
  - 重活(长构建)动手前简述；被打断后读 TASKS.md 自动接续，不再问"要不要继续"
  - GUI/实操优先：用户不仅要看懂，还要能亲自打开仿真验证、用于组会演示
key_env:
  wsl: Ubuntu-22.04, user=ai4s
  go: /usr/local/go/bin/go   # 裸 go 是旧1.18
  proxy: clash 127.0.0.1:7897 (.wslconfig mirrored; docker daemon 也配了代理)
  git_push: Windows端 http.sslBackend=openssl + local http(s).proxy=7897；偶发TLS瞬断→重试
  repo_wsl: ~/ws/world-model    # distro 已改 humble
  authoritative_src: C:\CCproject\GBPlanner-WorldModel-Integration  (= /mnt/c/CCproject/...)
  github: ai4sci-z/GBPlanner-WorldModel-Integration (private, gh已登录)
state_2026_06_30:
  images: 9/9 全部构建成功(实测)  # 预研A 镜像阶段完成
  blocker: exploration 能启动9服务但运行时未健康(slam_runtime_unhealthy, probe rc=20, rosbag无mcap)
  INTEGRATION_DONE: |
    ✅ 真集成代码已接进 world-model 真实结构(不再是 integration/ 独立文件)。
    WSL ~/ws/world-model 分支 feat/gbplanner-gain-exploration-strategy,2 个 commit:
      ① fix: exploration_workflow_runtime.py.tmpl 的 %% → %(真 bug,见下)
      ② feat: 新增可选策略 gbplanner_gain —— 读 /map(OccupancyGrid)、24方向光线投射数未知栅格(体积增益)、
         减转向惩罚选向,替代脚本式 frontier_lite;加 ExplorationWorkflowSpec.MapTopic 透传 map_topic。
    验证(实测):go build/vet/test ./internal/tasks/helpers/ 全过;两策略渲染脚本 py_compile 均过。
    PR/Issue 物料全在 integration/world-model-PR/(含手动提交指南、纯正文 *_BODY.md、补丁、渲染证据)。
  REAL_BUG_FOUND: |
    world-model 的 exploration 生成脚本本来就**无法编译**:模板用 text/template 渲染(无 Sprintf),
    pattern[goal_index %% len(pattern)] 的 %% 原样落盘 → python3 -m py_compile 报 SyntaxError(line147)。
    sed 改单 % 后 py_compile 通过 = 根因确证。是给作者的有价值贡献(但**不是**运行时头号根因,见下)。
  RUNTIME_ROOT_CAUSE_tomllib: |
    🔴 头号根因(读 artifacts_sample/exploration_summary.json L404 实锤):SLAM 后端崩于
    "ModuleNotFoundError: No module named 'tomllib'"。tomllib 是 Py3.11+ 标准库,humble=Ubuntu22.04=Py3.10 没有
    (此栈原为 jazzy/Py3.12 写)。SLAM 死 → 无 /slam/odom、/tf、/scan → 飞控永远 waiting_for_pose、探针全 rc=20。
    修法:SLAM CLI(navlab.common.slam.cli)的 import tomllib 加 try/except 兜底用 tomli;humble pip install tomli。
    ⚠️ 订正:之前把 %% 说成"运行时根因之一"夸大了权重——tomllib 在其上游,才是头号。PR/Issue 措辞待改。
  STAGE4_BRIDGE_STARTED: |
    用户拍板"直接上阶段4真版GBPlanner(ros1_bridge)"。已从 gbplanner-ref 镜像源码逐条证实真版 I/O 契约:
    进=/pointcloud(sensor_msgs/PointCloud2,3D)+odometry(nav_msgs/Odometry)+TF world→navigation;
    出=<robot>/command/trajectory(trajectory_msgs/MultiDOFJointTrajectory,PCI 发,pci_general.cpp:8)。
    去风险关键:自定义 planner_msgs(13msg+24srv)只在 ROS1 内用、不跨桥 → ros1_bridge 只桥 4 类标准消息,开箱即用。
    产物 integration/ros1_bridge/:bridge_topics.yaml + trajectory_to_intent.py(ROS2出口适配器,py_compile过)+ README。
    剩余:①iq_quad加3D雷达出/pointcloud ②编译起ros1_bridge ③ROS1侧跑gbplanner_node+PCI ④端到端(受 tomllib 运行时阻塞)。
progress_2026_06_30_evening: |
  运行时连修 2 个 humble 真 bug(均实测验证,world-model 分支 commit 0b85cea/49d3551):
    坑#1 tomllib:Py3.10 无此库 → SLAM 一启动就崩(头号根因)。回退 tomli。重跑后 SLAM 日志 tomllib=0,越过。
    坑#2 空 launch 参数:humble 拒绝 name:= 空值 → backends.py 跳过空参。重跑后 cartographer_node 真正运行。
    现 world-model 分支共 4 commit(3 fix:tomllib/空参/%% + 1 feat:gbplanner_gain)。
    下一个坑#3:cartographer 收不到 /scan(传感器链路,待续)。详见 docs/运行时排错记录_humble.md。
  阶段4 桥接地基已落:从 gbplanner-ref 源码逐条证实真版 GBPlanner I/O 契约(点云/里程计进、command/trajectory
    MultiDOFJointTrajectory 出、自定义 planner_msgs 留 ROS1 不跨桥=去风险),已写 ros1_bridge 话题映射 +
    ROS2 出口适配器 trajectory_to_intent.py(py_compile 过)。见 integration/ros1_bridge/。
  本机 tomli 已 vendor 到 /workspace 根(供挂载运行时 import;PR 里则是给镜像加 tomli 依赖)。
  PPT(11页)与实操手册已结合最新工作更新;桌面同步。
progress_2026_07_02_GUI实操: |
  预研B·GBPlanner 官方仿真在 WSLg 上真跑起来了,链路通到 voxblox 3D 建图(实测):
    激光点云 27876点/帧 10Hz → odometry 252Hz → voxblox TSDF 地图 4.5Hz → RViz+GbPlanner Control 面板弹窗在桌面。
  连排 6 个坑(A~F,证据+修复全记在 docs/预研B_仿真实跑排错记录.md;一键复现 runbooks/gbplanner_ref/run_light.sh):
    A bash -c 不读.bashrc→显式source;B 容器hostname只解析IPv6→ROS_HOSTNAME=localhost;
    C 上游xacro真bug(OS0-128不接受gpu/organize_cloud)→sed删;D DARPA网格场景压垮llvmpipe软件渲染segfault
    →手搓纯box图元 light_boxes.world;E 自制世界缺 ros_interface_plugin→RotorS里程计不转ROS、voxblox丢光点云
    →补一行插件(官方7个世界都带);F WSL空闲自动关机杀docker(容器255)→挂keepalive常驻进程。
  ✅✅ 临门一脚已进(同日):向 /rmf_obelix/command/pose 发 z=1.2 位姿→起飞(实测z 0.056→1.201)
  →调 automatic_planning→**自主探索闭环**(轨迹实测 (5.7,-1.3)→(4.6,1.0)→(6.2,3.9)→(4.4,6.4) 持续巡飞覆盖)。
  复现:run_light.sh 起仿真 → takeoff_and_explore.sh 起飞+触发。预研B 完成。
  ✅ 全任务周期+量化(第三轮全程采集,70采样点):总路径 291.3m,地图峰值 132,091 体素点,
  t=435s 时间预算(480s)触发 HOMING ENGAGED 自动返航;曲线/CSV images/exploration_metrics_full.*;
  voxblox 地图落盘 images/explored_map_lightboxes.vxblx(4MB,可 load_map 复用)。
  GBPlanner 侧对比数据已到手(填进 docs/对比实验与缺陷论证设计.md §3,口径=预研B独立环境,已诚实标注)。
  ⚠️ WSL keepalive 铁律:跑容器前必须有常驻WSL进程,否则发行版空闲关机、docker被优雅停掉、容器全死255。
progress_2026_07_03_预研A剥洋葱: |
  运行时 9 坑已修 8(全部实锤+固化,详见 docs/运行时排错记录_humble.md):
    ④gazebo-sensor venv 悬空软链(uv python 没拷进镜像)⑤install/setup.bash 缺失(跳过的 ydlidar colcon 生成它)
    ⑥venv Py3.14 无法 import humble rclpy→改系统 Py3.10+system-site-packages
    ⑦X2 管线运行时必需 ydlidar 驱动(推翻 6/29 假设)→declare_parameter 26 处最小补丁在 humble 编译成功
    ⑧emulator 订阅 QoS 不兼容→改 sensor-data
    ⑨【总根因】humble sdformat_urdf 不认 gpu_lidar→RSP 崩→/robot_description 没了→create -topic 生成不了 iris
      →gz 里从来没有机器人(传感器/ArduPilotPlugin JSON/TF 全是它下游)。
      修复=薄层衍生镜像 patch robot.launch.py:spawn 改 -file 直读完整 SDF;RSP 描述先 gz sdf -p 展平再剥 <sensor>。
      验证:手动常驻 baseline 四连全绿(RSP活/iris在gz/lidar出数据/SITL JSON接通)。
  当前卡点:编排环境 run#12/13 血相未变——嫌疑=baseline 的 ROS 话题对其他容器不可见(DDS 隔离:
    ROS_LOCALHOST_ONLY/RMW 不一致/域号类),活体探针 v7(对比各容器 pid1 的 DDS env)已写好待下轮 run 验证。
  方法论(好用,沉淀):①手动常驻容器从容取证(gz model --list 一锤定音)②逐段模拟启动命令冒烟③活体探针(容器活着时抓)。
  镜像注意:navlab/official-baseline:humble-latest 已被薄层补丁覆盖(含 navlab-humble-fix 标记,grep 可验)。
decision_2026_07_02: 【用户拍板】不向 world-model 作者仓库提交 PR/Issue;成果只留自己账号(ai4sci-z)。
  integration/world-model-PR/ 物料转为留档证据;world-model 4个commit留本地分支(可选推自己账号私有镜像仓)。
next_actions:
  - 截真图:用户在 RViz 看自主探索,Win+Shift+S 截图存 images/,补进实操手册与 PPT(组会硬料)
  - 预研A运行时:接着剥 /scan 链路坑(gazebo-sensor venv 修复已写好,需重建该镜像验证)
  - 量化对比:预研B跑通后可录制探索指标,与 frontier_lite 对照(docs/对比实验与缺陷论证设计.md)
  - 调运行时让 exploration 真探起来 → 取 summary.json 的 coverage/path/goals 真实指标(注:先确认是否因这个编译bug)
  - 跑 GUI(先 gbplanner_ref/build_and_run.sh 看 GBPlanner)截真图补 docs/实跑操作手册_图文版.md
  - 量化对比填 docs/对比实验与缺陷论证设计.md
read_next: [README.md, TASKS.md, integration/world-model-PR/README.md, docs/集成机制与frontier_lite缺陷_核心发现.md, docs/对比实验与缺陷论证设计.md]
```

## 0. 新会话第一步(必做)
1. 在**同一项目目录 `C:\CCproject`** 打开新 Claude Code 对话(记忆会自动加载)。
2. ⚠️ **后台构建任务不跨会话**——新会话**先用 `docker images` 核对真实状态**,别信任何"之前说成功"。核对命令见 §6。
3. **铁律**:退出码/任务"completed"≠成功,**只认 `docker images` 真实镜像**(本任务已抓出 6 次假成功)。

## 1. 任务 + 权威资料
- **任务**:把 **GBPlanner**(ROS1 图搜索体积增益探索)集成进 **world-model**(ROS2 无人机仿真平台),替换其占位探索 `frontier_lite`,并论证缺陷 + 对比突出 GBPlanner 优势。
- ⚠️ "world-model" 只是维护者起的项目名,**不是具身智能"世界模型"**。
- **权威资料仅 3 个**:world-model 仓库(github.com/SZ-surveying/world-model)、GBPlanner(arXiv:2201.07067 + github.com/ntnu-arl/gbplanner_ros 的 `gbplanner2` 分支)、桌面 `自主探索决策(GBPlanner算法).md`(mentor 发)。

## 2. 已定决策:**桥接方案(ros1_bridge)**
GBPlanner=ROS1,world-model=ROS2;作者官方栈(Unified Autonomy Stack)就用 `ros1_bridge` 接。**原 P1(抽 gbplanner_core 重写)降为备选**。路线:跑通 gbplanner-ref → 搭 ros1_bridge 把 world-model 的点云/里程计喂给 GBPlanner、航点回流 `/navlab/exploration/*` → 给无人机加 3D 雷达 → 替换 frontier_lite → 对比。

## 3. 当前总状态(2026-06-30)
| 阶段 | 状态 |
|---|---|
| 预研B·GBPlanner 官方仿真复现 | ✅ 镜像 `gbplanner-ref` 已建(10.7GB) |
| 调研·ros1_bridge | ✅ 确认 |
| P1·gbplanner_core 核心(光线投射+体积增益) | ✅ 编译+ctest 通过(`code/gbplanner_core/`) |
| 桥接接口规格 | ✅ 精确锁定(`docs/桥接接口规格.md`) |
| 对比实验设计 | ✅ (`docs/对比实验与缺陷论证设计.md`) |
| 图文实跑手册 | ✅ (`docs/实跑操作手册_图文版.md`,真截图待补) |
| **预研A·world-model 9 镜像** | 🔵 **8/9**,official-baseline 未建(见 §5) |
| GUI 实操 / 跑 exploration / 对比 | ⬜ 待 9/9 或走预研B |

## 4. 环境关键事实(照抄即用)
- WSL2:`Ubuntu-22.04`,用户 **`ai4s`**(可用 docker)。Win11 家庭版。
- **Go 1.24 在 `/usr/local/go/bin`**(apt 旧 1.18 会盖住,PATH 要前置):`export PATH=/usr/local/go/bin:$PATH`。
- **代理**:Windows clash 在 `127.0.0.1:7897`;`.wslconfig` 已设 mirrored networking + autoProxy。
- **Docker 守护进程代理**已配(`/etc/systemd/system/docker.service.d/http-proxy.conf`→7897),否则拉不动 Docker Hub。
- **git push**:Windows 端用 `git config http.sslBackend openssl` + local `http(s).proxy=127.0.0.1:7897`(schannel 走代理会握手失败)。
- 项目仓库克隆在 WSL:`~/ws/world-model`(子模块已拉全)。distro 已在 `orchestration/sim/config.toml` 改为 **humble**。
- GitHub 私有仓:`ai4sci-z/GBPlanner-WorldModel-Integration`(gh 已登录)。本机权威源:`C:\CCproject\GBPlanner-WorldModel-Integration`。

## 5. 预研A 构建详情(关键,8/9)
**已建 8 个**(humble):ros-base、ardupilot-sitl、mavlink-router、gazebo-headless、fast-lio、companion、slam-cartographer、gazebo-sensor。
**未建**:`official-baseline`(ArduPilot 全家桶,最重)。
**这栈是为 jazzy 写的,搬 humble 已补 6 处**(补丁脚本固化在 `runbooks/world-model-humble-fixes/`):
1. 编排器经典构建器不支持 `--mount` → 改用 `DOCKER_BUILDKIT=1 docker build` CLI。
2. fast-lio(Livox)jazzy GCC13 编不过 → humble 解决。
3. gazebo-sensor ydlidar 不兼容 → 跳过 ydlidar(`gazebo-sensor-humble.Dockerfile`)。
4. gazebo-headless 缺 Harmonic `gz sim` → 装 `gz-harmonic`+`ros-gzharmonic`(`gazebo-headless-humble.Dockerfile`)。
5. official-baseline `ros-gz`(Fortress)与 Harmonic 冲突 → 改 `ros-gzharmonic`;`--break-system-packages` humble pip 不支持 → 去掉(`build_official4.sh` 的 sed)。
6. official-baseline git 克隆 ardupilot GnuTLS 断连 → 走代理(`--network=host --build-arg HTTPS_PROXY`,见 `build_official4.sh`)。
**关键修正(重要)**:这套栈**其实支持 humble**(Dockerfile `ARG ARDUPILOT_ROS_REF=humble` 默认就是 humble,ardupilot_gz/cartographer 在 humble 已编过),**不必回退 jazzy**。colcon 唯一失败的包是 `micro_ros_agent`,因 `ARG MICRO_ROS_AGENT_REF=jazzy`(默认指 jazzy 分支,要 Fast-CDR 2;humble 自带 Fast-CDR 1)。**修法:传 `--build-arg MICRO_ROS_AGENT_REF=humble`(humble 分支配 Fast-CDR 1)。**
**最新重建命令(含全部修复)**:`bash runbooks/world-model-humble-fixes/build_official5.sh`(WSL;自动 patch ros-gz/pip + host网代理 + MICRO_ROS_AGENT_REF=humble)。后台任务 `b4zjojmcc` 正在跑此版本——新会话先 `verify_humble.sh` 看是否已 9/9,没好就看 `~/build_official5.log`。

### ✅✅ 重大更新(2026-06-30):9/9 镜像全部构建成功(docker images 实测,非假成功)!
`navlab/official-baseline:humble-latest` 已生成,9 个 humble 镜像齐全。**预研A 的镜像构建阶段完成。**

### 当前真正的卡点 → 运行时(不是构建了)
跑 `go run ./cmd/navlab-sim run exploration --live-preflight`(注:它会**真启动 9 个服务**)→ `status=blocked`。summary 留痕在 `artifacts_sample/exploration_summary.json`,blockers:
- `slam_runtime_error` / `slam_runtime_unhealthy`(SLAM 没起健康)
- `probe_failed: exploration/frame_contract/imu (rc=20)`、`probe_output_not_ok`
- `rosbag_profile_failed`(无 mcap/metadata.yaml)
- `runtime_execution_failed`

**即:容器能起,但 SLAM/传感器探针未就绪,没真正探起来(疑似首次运行就绪超时/配置/display)。**

### 新会话下一步(运行时调试)
1. 跑一次后 `docker ps -a` 看哪个容器退出/不健康;看 `artifacts/sim/exploration/<run_id>/` 下各服务/probe 日志。
2. 重点查 SLAM(cartographer)为何 unhealthy、probe rc=20(可能要加就绪等待时间,或缺 display/topic)。
3. 跑通后取 `coverage`/`path_length`/`accepted_goals` 真实指标 → 填 `docs/对比实验与缺陷论证设计.md`;用 Foxglove/RViz 出截图补 `docs/实跑操作手册_图文版.md`。
4. **GUI 实操**(用户最看重):可先 `bash runbooks/gbplanner_ref/build_and_run.sh` 看 GBPlanner 仿真(预研B,镜像就绪),截真图。

## 6. 新会话立即执行(恢复动作)
```bash
# A) 核对 9 镜像真实状态
bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-humble-fixes/verify_humble.sh
# B) 若 official-baseline 仍缺:看 colcon 真实错误
grep -aiE 'error:|Failed|did not complete' /home/ai4s/build_official4.log | tail -20
# C) 修好后重建
bash /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/world-model-humble-fixes/build_official4.sh
```

## 7. GUI 实操(用户强调:必须能亲自看/验证)
- **优先用预研B(已就绪)看 GBPlanner**:
  ```bash
  cp -r /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref ~/gbplanner_ref
  cd ~/gbplanner_ref && bash build_and_run.sh   # WSLg 弹出 Gazebo+RViz
  ```
  跑通后用 computer-use 截真图,补进 `docs/实跑操作手册_图文版.md` 的"真截图位"。
- world-model 的 exploration GUI 需 official-baseline 建成(9/9)后:`cd ~/ws/world-model/orchestration/sim && go run ./cmd/navlab-sim run exploration`。
- 注:GUI 经 WSLg 弹到 Windows 桌面;若卡用 headless + rosbag/Foxglove。

## 8. 工作铁律(用户反复强调,必须遵守)
1. **四处同步**:每步收尾 →① 改权威源 `C:\CCproject\GBPlanner-WorldModel-Integration` ②刷桌面 md(README→`桌面\GBPlanner项目_蓝图与进展.md`)③`git add/commit/push`(桌面"传送门"junction 自动跟随)。
2. **自纠错**:只信 `docker images`/文件/测试,不信退出码;每步自检。
3. **留痕**:仿真截图、图、表存 `images/`,文档写清"做了什么"。
4. **命名**:预研A/B=复现任务;桥接/重写=集成方案(不用字母)。
5. **Typora 渲染**:桌面 md 用**绝对路径**引 PNG,**禁用 base64**;图用 SVG 写→`rsvg-convert`转 PNG(WSL 已装 fonts-noto-cjk)。
6. **重活先问**;被打断后读 TASKS.md 自动接续,不再征求"要不要继续"。

## 9. 文件地图
- 权威源 `C:\CCproject\GBPlanner-WorldModel-Integration\`:`README.md`(蓝图主报告)、`TASKS.md`(任务台账)、`RESUME_恢复文档.md`(本文)、`code/gbplanner_core/`(P1代码)、`docs/`(桥接规格/对比设计/排错记录/操作手册/实跑图文/预研A·B/仓库导览/手机RemoteControl)、`images/`(图)、`runbooks/`(环境搭建、gbplanner_ref、world-model-humble-fixes 补丁)。
- 桌面:各 md 副本(绝对路径引图)+ `GBPlanner项目`(junction→权威源)+ 两个`源码浏览`夹。
- WSL:`~/ws/world-model`(仓库)、`~/gbp_core_build`(P1 build)、`~/*.log`(构建日志)。

## 10. 待办(任务台账 #3-#7)
#3 预研A(差 official-baseline)/ #4 桥接落地 / #5 论证 frontier_lite 缺陷(跑+数据)/ #6 GBPlanner vs frontier_lite 对比 / #7 预研A·B 独立报告(已建初稿)。
