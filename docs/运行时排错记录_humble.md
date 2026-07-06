> 📌 **状态戳(2026-07-06 晚·全绿后)**:本文含历史阶段内容。**当前权威状态**以 [RESUME_新窗口接管_2026-07-06.md](../RESUME_新窗口接管_2026-07-06.md) + [Bug 台账](../docs/world-model端到端Bug台账_给作者PR.md) 为准。要点:jazzy 9/9 已验真;**run `20260706T130626` 已端到端全绿**(TASK_STATUS_OK/4探针全ok/3目标/SIM+0.72m,无hack,B15+B16 已修);但 frontier_lite 多跑基线**稳定性差**(6次全绿2/6,达标率40%,根因=启动耗时蚕食探索窗口);当前主线=**B2.5 自写薄桥接真 GBPlanner**(官方 ros1_bridge 与 zenoh 均已实验判死)→3D lidar(官方 lidar_3d 组件)→同口径对比;**PR 延后**(用户指示:等最终桥接跑通后统一定稿)。

# world-model exploration 运行时排错记录(jazzy→humble 迁移坑,逐个剥)

> 背景:world-model 这套栈原为 jazzy(Ubuntu 24.04 / Python 3.12)写,本机搬到 humble(Ubuntu 22.04 / Python 3.10)。
> 9 个镜像已全部构建成功(预研A),但**运行时**还有一连串版本坑。本文按"只信真实产物"的铁律,逐个记录:
> 每个坑都给【真实证据(日志原文)】+【根因】+【修复】+【验证】。证据来自 `artifacts/sim/exploration/<run_id>/`。
> 最后更新 2026-07-05。

## 坑 #1(头号):SLAM 崩于 `ModuleNotFoundError: No module named 'tomllib'`

- **证据**:`artifacts_sample/exploration_summary.json` L404 `slam_runtime_log.last_problem_lines`;
  run `20260630T004434Z` 的 `slam_backend.runtime.log`。
- **根因**:`tomllib` 是 Python **3.11+** 标准库;humble=Py3.10 没有。
  `navlab/common/toml_values.py` 与 `navlab/sim/companion/runtime/config.py` 顶层 `import tomllib` →
  `navlab.common.slam.config` 导入 `toml_values` → SLAM 节点启动即崩 → 无 `/slam/odom`、`/tf`、`/scan` →
  飞控永远 `waiting_for_pose`、所有探针 rc=20。**这是 exploration 在 humble 上起不来的头号原因。**
- **修复**(world-model 分支 commit `0b85cea`):两个文件 `import tomllib` 改为
  `try: import tomllib / except ModuleNotFoundError: import tomli as tomllib`(API 一致,drop-in);
  humble 环境装 `tomli`。本机为让挂载运行时取到 tomli,把 `tomli` vendor 到 `/workspace` 根(PYTHONPATH)。
- **验证(实测)**:① SLAM 容器内挂载改后代码 + 装 tomli → `import navlab.common.toml_values` / `navlab.common.slam.config` 均 OK;
  ② 重跑 run `20260630T075024Z`,其 `slam_backend.runtime.log` 中 `tomllib` 出现 **0 次** → 已越过此坑。✅

## 坑 #2:SLAM launch 报 `malformed launch argument 'cartographer_configuration_directory:='`

- **证据**:run `20260630T075024Z` 的 `slam_backend.runtime.log` 尾:
  `malformed launch argument 'cartographer_configuration_directory:=', expected format '<name>:=<value>'`。
- **根因**:`navlab/common/slam/backends.py` 的 `CartographerBackend.command` 把**所有** launch 参数
  (含空串值,如未设置的 `cartographer_configuration_directory`)都拼成 `key:=value`;
  ROS2 humble 的 launch **拒绝空值** `name:=`。
- **修复**(world-model 分支 commit `49d3551`):构造参数时**跳过渲染为空串的参数**,让 launch 文件用自身默认值。
  (`launch_value`:bool→true/false 非空,故只有值为 `""` 才被跳过,安全。)
- **验证(实测)**:重跑 run `20260630T075417Z`,`malformed launch argument` 出现 **0 次**,
  且 `slam_backend.runtime.log` 显示 **`cartographer_node` 真正启动并运行**(日志停在
  `Queue waiting for data: (0, scan)` = 等激光数据)。✅ SLAM 节点已能起来。

## 坑 #3:cartographer 收不到 `/scan` → 根因已锁定:gazebo-sensor 镜像 venv 悬空软链

- **证据链**(2026-07-01 实测):
  1. run `20260630T075417Z` SLAM 日志反复 `Queue waiting for data: (0, scan)`;
  2. 该 run **没有任何 gazebo_sensor 日志** = 发 `/scan` 的服务根本没起来;
  3. 进容器直接跑服务用的解释器:`/opt/gazebo-sensor-venv/bin/python` → **"No such file or directory"**;
  4. `ls -l` 实锤:venv 的 python 是软链 → `/root/.local/share/uv/python/cpython-3.14-.../python3.14`,
     **而 uv 托管的这个 Python 没被拷进最终镜像**(builder 阶段只 `COPY` 了 venv 目录)→ 悬空软链。
- **因果**:gazebo_sensor 服务启动即"解释器不存在"→ 崩、无日志 → `/scan`/`/sim/x2/*` 全无 → cartographer 干等。
- **修复**(已写入 `runbooks/world-model-humble-fixes/gazebo-sensor-humble.Dockerfile`):
  最终阶段补 `COPY --from=builder /root/.local/share/uv/python /root/.local/share/uv/python`。
- **验证**:重建脚本 `build_gazebo_sensor2.sh`(含真实产物自检)——✅ **重建成功(2026-07-02 实测)**:
  新镜像 `navlab/gazebo-sensor:humble-latest` 生成,`VENV_PYTHON=OK`(镜像内 `/opt/gazebo-sensor-venv/bin/python --version` 真能执行,输出 Python 3.14.5)。**镜像级修复完成;端到端重跑 exploration 验证 `/scan` 待做**(需等 GBPlanner 演示容器空出资源)。

## 坑 #4:venv 修好后 gazebo_sensor 仍秒退 → 同一命令里的第二死点

- **证据**(2026-07-03 run `20260703T004145Z`):镜像 venv 已修(`VENV_PYTHON=OK`),但该 run 仍无
  gazebo_sensor 日志、`/scan` 仍缺、blockers 与上次相同 → 服务还是没起来。
- **根因**:启动命令为 `source /opt/navlab_sensor_ws/install/setup.bash && exec venv/python -m ...`;
  `install/` 目录由 **ydlidar 的 colcon 构建**生成——而 humble 版镜像**故意跳过了**该构建(humble 编不过)
  → `source` 失败 → `&&` 链中断 → 容器秒退无日志。**与坑#3(venv)是同一命令里两个独立死点,修掉第一个才暴露第二个。**
- **修复**:Dockerfile 补一个 no-op `install/setup.bash` 占位(仿真走 gz gpu_lidar→ros-gz-bridge,不需要 ydlidar 驱动)。
- **验证(实测)**:重建后**逐段冒烟测试 4/4 全通**(source ros → source 占位 → venv import cli → cli --help),
  启动链首次完全打通。端到端 run#4 验证中。
- **方法教训**:修"启动即死"类 bug,应**先在容器里逐段模拟完整启动命令**再烧整轮 e2e——本次已按此法执行。

## 坑 #5:venv Python 3.14 无法 import humble 的 rclpy(第三死点)

- **证据**(2026-07-03,1:1 复刻编排器命令实测):坑#4 修后服务**真正启动**了(X2 runtime、双 ros_gz_bridge、
  投影/串口仿真子进程全拉起),随后三个子进程齐报 `requires ROS2 Python packages` → 主进程退出。
- **根因**:uv 造的 venv 用**托管 Python 3.14**,而 humble 的 rclpy 是 **Python 3.10 的 C 扩展** → import 必败。
  (上游 jazzy 同理存疑,但那是上游的事。)
- **修复**(Dockerfile 第3版):venv 改用**系统 Python3.10 + `--system-site-packages`**(直接可见 rclpy),
  pip 装依赖组(numpy 钉 `<2.3`,2.3+ 要 Py3.11;补 tomli/pyserial)。彻底甩掉 uv builder 阶段。
- **验证(实测)**:`VENV_PYTHON=OK`(3.10.12)+ **`VENV_RCLPY=OK`**(rclpy+numpy+loguru+tomli+yaml+pymavlink 全 import 通)。

## 坑 #6:X2 管线运行时必须有 ydlidar_ros2_driver ——【推翻 6/29 的假设】

- **证据**(同日复刻实测):坑#5 修后管线走到最后一步:
  `Starting ydlidar_ros2_driver: ros2 run ydlidar_ros2_driver ...` → 包不存在 → 主进程退出。
- **翻案**:6/29 判断"仿真走 gz→ros-gz-bridge,不需要 ydlidar 硬件驱动"是**错的**。X2 管线的真实设计是
  **硬件级保真仿真**:gz 雷达 → `/scan_ideal` → CLI 把数据打成 X2 硬件串口协议写入虚拟串口 →
  **真 ydlidar 驱动**读串口 → `/navlab/x2/vendor_scan` → 时间归一化 → `/scan`。驱动是链路必经节点。
- **humble 编译失败根因**:上游驱动用 `declare_parameter("name")` 无默认值形式(humble 已移除该重载)。
- **修复**:构建时 sed 打最小补丁——26 处 declare 全部改为传入**前一行已赋默认值的同名变量**(语义不变;
  float 参数 `static_cast<double>`,ROS2 参数无 float 型),恢复 colcon 构建。镜像重建+自检(`YDLIDAR_PKG=OK`)进行中。
- **方法教训**:同一条启动命令里已连剥 **3 个独立死点**(venv悬空→setup.bash缺失→rclpy版本),
  每修一个才暴露下一个。"逐段模拟启动命令"的冒烟法有效,继续沿用。

## 坑 #7:模拟器订阅 `/scan_ideal` QoS 不兼容 → 收不到投影数据

- **证据**:`New publisher discovered ... offering incompatible QoS ... RELIABILITY; No messages will be received`。
- **根因**:emulator 订阅用默认 RELIABLE,cloud_scan_projection 发布用 best-effort(sensor QoS)→ 被拒。
- **修复**:`navlab/sim/gazebo_sensor/cli.py` 订阅改 `qos_profile_sensor_data`(同时兼容 reliable/best-effort 两种发布者)。

## 坑 #9(**真·总根因**):humble sdformat_urdf 不认 `gpu_lidar` → RSP 崩 → 机器人从未生成

- **发现方法**:绕开编排器**手动常驻起 baseline** 从容取证 → `gz model --list` 里**根本没有 iris**(只有 maze/floor)!
- **完整因果链(实锤)**:
  `robot.launch.py` 用 `create -topic robot_description` 生成机器人,而该话题由 robot_state_publisher 发布;
  humble 的 sdformat_urdf 解析 SDF 撞上 `gpu_lidar` sensor(urdf 只认 camera/ray)→ **RSP terminate**
  → `/robot_description` 没了 → **iris 从未 spawn** → gz 无传感器实体(`/lidar` 出现在话题列表只是桥的订阅端)、
  ArduPilotPlugin 不存在(SITL 无限刷 `No JSON sensor message received`)、TF 全无。
  **此前所有 `/scan`、`/imu`、`/tf`、`/ap/v1/pose` 缺失,全是这一个根因的下游。**
- **订正**:中途的"渲染引擎起不来(gpu_lidar 渲染)"假设**错误**——`Sensors.cc: Waiting for init` 只是"世界里没有渲染型传感器"的正常待机;修复后 gpu_lidar 在容器软件渲染下**真出数据**。
- **修复**(薄层衍生镜像,秒级,不重建 17.9GB):patch `robot.launch.py` 两针:
  ① spawn 改 `-file` 直读完整 SDF(传感器保留给 gz);
  ② RSP 的描述先 `gz sdf -p` 展平 include(sensor 藏在被 include 的 lidar_2d 里)再正则剥掉 `<sensor>` 块(TF 只需连杆/关节)。
- **验证(实测四连全绿)**:RSP 死亡=0;`gz model --list` 有 iris;`/lidar` gz 侧真出数据;SITL JSON 停止刷屏(接通)。

## 坑 #10:official_baseline 漏发 `CYCLONEDDS_URI` → 全容器 DDS"静音"

- **证据**(2026-07-03 活体探针 v7,对比各容器 pid1 环境):所有容器同为 host 网络/域 0/cyclonedds,
  fcu/slam 等都有 `CYCLONEDDS_URI=...MaxAutoParticipantIndex 512...`,**唯独 baseline 没有**。
- **根因**:Go 编排里其他服务都用 `baselineEnv()`(内含该配置),`officialBaselineServiceSpec` 却**手写内联 Env 漏了它**
  (上游疏漏)。CycloneDDS 默认每主机参与者索引上限很小;9 容器几十个节点挤 host 网络,baseline 的节点
  (gz 桥/RSP/DDS agent)分不到索引 → **它的所有话题(/imu、/tf、/scan 源、/ap/*)对其他容器不可见**。
- **修复**(world-model 分支 commit `c8bc866`):该 Env map 补一行 `CYCLONEDDS_URI: cycloneDDSParticipantEnv()`;`go build` 过。
- **验证**:e2e run#15 进行中(观察 blockers 中 topic_sample_missing 是否批量消失)。

## 坑 #11(已修):我的 `gz sdf -p` 展平补丁输出 SDF 1.11,humble libsdformat 只认 ≤1.9

- **证据**:`[robot_state_publisher-2] Error [Converter.cc:156] Unable to convert from SDF version 1.11 to 1.9`。
- **修复**(robot.launch.py 补丁 v3,薄层镜像):展平后把 `<sdf version=...>` 重写为 1.9(ardupilot 模型无 1.10+ 特性,安全)。
- **验证(实测 run#29)**:`/tf` 以 6.5Hz 真实流动 → RSP 解析成功。✅

## 坑 #12(**编排环境真凶,今日最大战果**):`--user 1000:1000` 无 passwd 条目 → gz 分区错乱 → 同容器发现瘫痪

- **侦破过程**(方法论教科书局):编排失败但手动全绿 → 网络四大假设(GZ_IP/GZ_RELAY/组播/接口漂移)
  逐一实验**全部排除**(自写组播自测 3/3 收包、嗅探 412 包在飞)→ 冻结兄弟容器无效 → **`docker inspect` 逐字段 diff**
  → 揪出唯一未复刻差异:**`User: 1000:1000`**。
- **复现+治愈双实锤**:
  - A 组(忠实 uid1000 复刻):iris=0,create 重试 8 次 → **完美复现编排死状**;
  - B 组(仅加 `GZ_PARTITION=navlab`):**iris 生成成功,create 一次就通**。
- **根因**:uid1000 在容器内无 passwd 条目 → gz-transport 默认分区(hostname:**username**)解析异常
  → 各进程分区不一致 → **同容器内 gz 服务发现互相隐身** → `create` 永远拿不到 `/gazebo/worlds`
  → 机器人永不生成 → 传感器/TF/SITL JSON 全链饿死。
  (附带教训:此前所有 root 身份的 exec 探针与 server 天然不同分区,全是"测量假象"。)
- **修复**(world-model commit `aa77fca`):`baselineEnv()` 与 baseline 内联 Env 显式加 `GZ_PARTITION=navlab`;`go build` 过。
- **验证**:e2e run#28 进行中。

## 坑 #13:IMU 净化桥"自吞回声"→ cartographer 崩(SIGABRT)

- **背景**:坑#12 修后 run#29 里程碑——`/scan` 7Hz、`/tf` 6.5Hz、SITL JSON 接通,**感知层全线贯通**;
  blockers 名单质变(scan/tf/rangefinder 系列全消失)。新墙:cartographer 拿到数据后 SIGABRT。
- **遗言**:`Check failed: ... Non-sorted data added to queue: '(0, imu)'`(时间倒退 10µs);且 `/imu` 实测 ~10kHz(荒谬)。
- **根因**(上游默认值自带环,`helpers/slam.go`):IMU 净化桥读 `imu_source_topic` 写 `imu_topic`,
  **两者默认都是 `/imu`** → 桥订阅自己的输出 → 回声风暴(重复+微乱序)→ cartographer 时序断言崩。
  (旁证:exploration rosbag 本来就录 `/navlab/slam/imu` = 上游本意的净化输出名。)
- **修复**:两针——helpers 默认值(`d3e73b7`)+ **config 默认值**(`80c0fa8`,`config/defaults.go` 的
  SlamBackend.IMUTopic 会覆盖 helpers 默认,run#30 因此仍崩,追到装配链才发现)。
- **验证(实测 run#31)**:✅✅ **SLAM 闭环打通**——cartographer 全程运行,`slam quality: tight`(0 错误),
  `slam_odom_missing`/`slam_runtime_*` blockers 全部消失,**`/slam/odom` 真实流动**。blockers 26→21。
- **下一段链**(新前沿):`/slam/odom` → external_nav → ArduPilot EKF → `/ap/v1/pose/filtered`(仍缺)→ 控制器就绪。

## 坑 #14(当前前沿,候选):FCU bootstrap 请求 mode 15(AUTOTUNE)而非 4(GUIDED)

- **背景**:坑#13 修后,`/slam/odom` → external_nav → ArduPilot EKF → **`/ap/v1/pose/filtered` 出来了**;
  读源码确认 `/ap/v1/` 前缀 = AP_DDS 的 sysid 命名空间(`AP_DDS_Topic_Table.h:182` topic_name="pose/filtered",名字没错);
  controller **pose_samples=153**,状态从 waiting_for_pose 推进到 `waiting_for_fcu_bootstrap`。blockers 21→19。
- **证据**(run#35):SITL 日志 `AP: Mode change to Autotune failed: init failed` + `Got COMMAND_ACK: DO_SET_MODE: FAILED`;
  fcu_controller runtime 日志 `mode_switch: {mode_id: 15, ok: false}`,而 `required_mode: 4`(GUIDED)。
  另有 `AP: PreArm: VisOdom: not healthy`。
- **疑似根因**(待读 navlab fcu 控制器源码确认):bootstrap 的模式映射把目标模式发成了 15(ArduCopter 里 15=AUTOTUNE)
  而非 4(GUIDED);或 mavlink COPTER 自定义模式号与 controller 常量表错位。
- **状态**:🔵 排查中(任务#6)。

## 坑 #14(已修好,run#38/39 实证):FCU bootstrap 请求 mode 15(AUTOTUNE)而非 4(GUIDED)

- **根因**:`fcu_controller_runtime.py.tmpl:192` 用 `mode_id = master.mode_mapping().get("GUIDED") or guided_mode`——
  pymavlink 的 `mode_mapping()` 依车型识别,SITL 早期握手可能返回 **ArduPlane 表(GUIDED=15=Copter 的 AUTOTUNE)**→ set_mode(15) 被拒。
- **修复**(commit `b13f268`):改为**优先信显式配置** `guided_mode`(config=4)。
- **验证(实测 run#38/39)**:✅ `mode_switch: {mode_id: 4, ok: true}`,SITL 不再报 Autotune failed。
  **连带 arm 也过了**:重试 4 次后 `arm: {armed: true, ok: true}`(前几次 result=4 临时拒绝,EKF/就绪未稳)。

## 坑 #15(当前前沿):GUIDED+armed 后 `takeoff` 被拒 result=4,高度不涨

- **证据**(run#39 fcu_controller 日志):`takeoff: {ack result:4(TEMPORARILY_REJECTED), accepted:false}`,
  多次重试,`guided:true armed:true` 但 `height z≈-0.009m`(target_min 0.175),无人机没离地。
- **伴随**:SITL statustext 反复 `DDS: Participant session request failure` / `DDS: Creation Requests failed, retrying`
  (AP_DDS micro-ROS participant 创建失败)。
- **疑似根因(待确认,深水区)**:ArduCopter GUIDED 下 NAV_TAKEOFF 需要**位置估计健康**;之前有 `PreArm: VisOdom not healthy`——
  external_nav(视觉里程计)喂给 EKF 的位置源不健康 → GUIDED takeoff 被临时拒绝。涉及 EKF3_SRC* 参数 / external_nav 频率/协方差门限,
  叠加 AP_DDS participant 问题。**这是比模式映射深得多的层次(飞控 EKF/外部导航调参),已止损,不盲目深挖(见战役实录的死循环告诫)。**
- **进展意义**:FCU bootstrap 已连过 GUIDED→arm 两大关,只差 takeoff 离地;端到端就差这最后一跳。

## 当前进度(用于汇报,2026-07-05)

| 坑 | 一句话 | 状态 |
|---|---|---|
| #1 tomllib | Py3.10 无此库,SLAM 启动即崩 | ✅ 修+实证 |
| #2 空 launch 参数 | humble 拒绝 `name:=` 空值 | ✅ 修+实证 |
| #3 venv 悬空软链 | uv python 没拷进镜像,sensor 服务秒退 | ✅ 修+实证 |
| #4 setup.bash 缺失 | 跳过的 ydlidar colcon 本该生成它 | ✅ 修+实证 |
| #5 rclpy 版本 | venv Py3.14 无法 import humble rclpy | ✅ 修+实证(VENV_RCLPY=OK) |
| #6 ydlidar 驱动必需 | 推翻"仿真不需要驱动"假设;declare_parameter 26 处补丁 | ✅ 修+实证(YDLIDAR_PKG=OK) |
| #7 QoS 不兼容 | emulator 订阅 RELIABLE 拒收 best-effort | ✅ 修 |
| #9 **总根因** | sdformat_urdf 不认 gpu_lidar→RSP 崩→**机器人从未生成** | ✅ 修+手动四连全绿 |
| #10 CYCLONEDDS 漏发 | baseline 缺 participant-index 配置 | ✅ 修 |
| #11 SDF 版本 | 我的展平补丁输出 1.11,humble 只认 ≤1.9 | ✅ 修 |
| #12 **编排真凶** | uid 无 passwd→gz 分区错乱→**同容器发现瘫痪** | ✅ 复现+治愈双实验定案 |
| #13 IMU 自吞回声 | 净化桥 source=output=/imu→cartographer SIGABRT | ✅ 修+实证(SLAM quality=tight) |
| ◉ #14 当前 | FCU bootstrap 请求 mode 15≠GUIDED 4;PreArm VisOdom | 🔵 排查中 |

(编号无 #8:中途的"渲染引擎起不来"假设经实证**排除**,已并入 #9 的订正。)

**一句话**:13 个 humble 真坑全实锤修复;感知层全通→SLAM 闭环(tight)→位姿回灌飞控(pose_samples=153);
端到端只差 FCU 解锁起飞(坑#14)。逐轮实验叙事见 [预研A排错战役实录_35轮实验全解.md](预研A排错战役实录_35轮实验全解.md)。

> 说明:这批修复(代码 4 项 + 镜像 4 项)都是真实、可提交级的贡献,已固化在 world-model 本地分支与
> `runbooks/world-model-humble-fixes/`;按用户拍板**不对外提交**,`integration/world-model-PR/` 物料仅留档。
