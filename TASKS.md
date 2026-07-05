# 任务台账(进程调度式 · 防丢 + 自纠错 + 留痕)

> 项目"调度状态盘",仿操作系统进程表(PCB)。git 提交后永不丢。被打断后我读本表自动接续,无需提醒。

## 一、机制

### 1.1 调度 / 防丢(仿 OS 进程表)
- 本文件 = 进程表;状态:⬜就绪 / 🔵运行中 / ⏸阻塞 / ✅完成。
- **检查点**:每完成一最小步 → 写盘 + git 提交。
- **抢占**:你插入紧急任务 = 高优先级抢占;我先把当前状态写表,处理你的事,再回表续跑。
- **后台进程**:长任务(镜像构建、子模块拉取)放后台,完成通知,不阻塞前台。

### 1.2 自纠错(防止"自己出错还发现不了")
- **文档(md)**:每次更新后自检 →① 不含 base64 大块;② 引用图片都存在;③ 桌面 md 用**绝对路径**引图、README 用相对路径;④ 大小正常。
  - ⚠️ 教训1:Typora 不渲染 base64 内嵌图 → 桌面 md 严禁 base64,绝对路径引 PNG。
  - ⚠️ 教训2:WSL 无中文字体时 rsvg-convert 转出的 PNG 中文变豆腐块 → 必须先装 `fonts-noto-cjk`/`fonts-wqy-zenhei` 再转。
- **代码**:每写一段必在 WSL **编译 + 跑测试**,全绿才算完成才提交。
- **留痕(你的要求)**:每做完一件事都留证据 —— 仿真**截图**、生成的**图/表**统一存 `images/`,并在文档里写清"做了什么、结果如何"。

### 1.3 四处同步(每步收尾)
① 更新桌面 md(文字+图)②跑自检 ③git 提交推送 → 权威源 / 桌面传送门[自动] / 桌面 md / GitHub 四处一致。

## 二、命名约定(特异性 + 可读性)
- **预研 A / 预研 B** = 复现任务(A=复现 world-model,B=复现 GBPlanner)。
- **集成方案** = 「桥接方案(ros1_bridge)」(已选定)/「重写方案(gbplanner_core)」(备选)。**不用字母指代方案。**

## 三、当前任务表(2026-07-05 更新)
| ID | 任务 | 状态 | 备注 |
|---|---|---|---|
| 1 | 预研B·复现 GBPlanner 官方 ROS1 仿真 | ✅ **完成:自主探索全闭环(2026-07-02 实测)** | 排 6 坑后:起飞→voxblox 3D建图→RRG规划→**无人机自主巡飞覆盖迷宫**(轨迹实测 (5.7,-1.3)→(4.4,6.4),RViz 可视化在桌面)。复现:`run_light.sh` + `takeoff_and_explore.sh`;全记录 docs/预研B_仿真实跑排错记录.md |
| 2 | 调研·确认 ros1_bridge 官方接入做法 | ✅ 完成 | 你已选「桥接方案」 |
| 3 | 预研A·完整复现并**实际运行** world-model | 🔵 **~92%(07-05)** | 39轮实验修15坑;感知全通→SLAM闭环→位姿回灌→**FCU GUIDED+arm 已过**(坑#14修好 run#38/39 armed:true);卡 takeoff TEMPORARILY_REJECTED(坑#15,EKF位置源/VisOdom,humble 深水区)→**主线转 jazzy(#11),不在 humble 死磕** |
| 4 | 集成落地·把 GBPlanner 决策接进 world-model | ✅ **代码完成,待你提交PR** | ROS2-native 决策层集成:新增 `gbplanner_gain` 策略读图选向,替代脚本式 frontier_lite。已在 `~/ws/world-model` 分支 `feat/gbplanner-gain-exploration-strategy` commit(2提交:bugfix+feat),go build/vet/test + py_compile 全过。物料见 `integration/world-model-PR/` |
| 4.5 | **真 bug 发现**:exploration 生成脚本无法编译 | ✅ 已修并入PR | `%%` 经 text/template 原样落盘 → SyntaxError;`py_compile` 实测复现,改单 `%` 后通过。疑似 exploration 运行时起不来根因之一 |
| 5 | 论证·跑 frontier_lite + 小 demo 证明其不足 | 🔵 进行中 | 代码层已铁证(脚本循环、不订阅地图);**GBPlanner 侧实测数据已到手**(291.3m/132,091点/自动返航,曲线+CSV 在 images/);frontier_lite 侧量化待 #3 运行时修好 |
| 6 | 对比·GBPlanner vs frontier_lite 量化对照 | ⏸ 阻塞(依赖#3) | 覆盖率/用时/路径/卡死 → 表+图,突出优势 |
| 7 | 文档·写预研A/预研B 独立报告(桌面+三处) | 🔵 进行中 | 两份初稿已建,随复现进展补截图/数据 |
| 8 | 提交 PR + Issue 给 world-model 作者 | ⬜ **恢复(你 2026-07-05 更正:做完必须提交)** | ~~07-02 取消~~ → **必须提交**(自己账号 ai4sci-z fork);**硬约束=作者 jazzy 环境能跑**(见 docs/PR兼容性与jazzy评估.md)。前置=#11 jazzy 全栈跑通。物料 `integration/world-model-PR/`;分支现 12 提交 |
| 9 | **阶段4·ros1_bridge 接真版 GBPlanner** | 🔵 进行中 | ✅ I/O契约源码证实+ROS2出口适配器+bridge映射(`integration/ros1_bridge/`);⬜ 加3D雷达/编译起桥/ROS1侧跑/端到端(受运行时阻塞) |
| 10 | 修运行时头号根因 tomllib | ✅ 完成(0b85cea) | `try: tomllib / except: tomli` 兜底;jazzy 实测零影响(原生 tomllib,兜底分支不执行) |
| 11 | **⭐ jazzy 全栈重建(用户硬指令)** | ✅ **镜像阶段 9/9 收官(07-05 晚)** | 4 缺镜像全建成+开箱验真(坑全解:BuildKit 假成功/Livox cstdint/ydlidar declare_parameter;official-baseline **原版零补丁一次过**,micro_ros_agent 58.4s=humble 最狠坑 jazzy 天然没有)。施工指引 docs/jazzy全栈重建_施工指引.md;脚本 runbooks/world-model-jazzy/ |
| 12 | **⭐ jazzy 跑通 exploration(当前主线)** | 🔵 首跑中 | `run_exploration_jazzy.sh`(NAVLAB_SIM_DISTRO=jazzy);策略=遇坑小修作者代码不动框架、修完即提交(用户 07-05 拍板:目的是跑通+提PR,不死磕环境);humble 作对照组二分定位 |

## 四、决策 & 桥接路线(你已拍板)
集成采用「桥接方案(ros1_bridge)」。原 P1 重规划为:① 跑通 gbplanner-ref 的 rmf_sim 确认 I/O ② 搭 ros1_bridge:world-model(ROS2)点云/里程计 → 喂 GBPlanner(ROS1),航点回流 `/navlab/exploration/*` ③ 给 iq_quad 加 3D 雷达 ④ 接 exploration 替换 frontier_lite。`gbplanner_core` 转备选/加深理解。

## 五、论证与对比要求(你新增)
- **必须实据**:world-model 要在本机完整跑通;frontier_lite 的不足要用**实跑 demo + 量化数据**证明,不空口。
- **必须对比**:GBPlanner 与 frontier_lite 同场景对照,量化指标突出 GBPlanner 优势。
- **必须留痕**:截图、图、表全部存档并写进文档。

## 六、自检记录
- 2026-06-29 桌面 md base64 乱码 → 改绝对路径,自检通过。
- 2026-06-29 PNG 中文豆腐块 → 装 Noto CJK 字体重转,已修复。
- 2026-06-29 P1 代码 cmake+ctest 1/1 通过。
- 2026-06-29 预研B docker build BUILD_OK,镜像 gbplanner-ref(10.7GB)。
- 2026-06-29 ⚠️ 预研A 构建"假成功":报 BUILD_OK 但 `docker images` 只 5/9 → 自检抓出。诊断非 OOM,是 jazzy(24.04)编译不兼容(uint8_t/cstdint、declare_parameter)→ 切 humble 重建中。详见 [docs/预研A_构建排错记录.md]。
  - **铁律**:命令退出码=0 ≠ 成功,必须自检真实产物(镜像数/文件/测试)。
- 2026-06-30 集成代码接进 world-model 真结构:`go build/vet/test ./internal/tasks/helpers/` 全过;两种策略渲染脚本 `python3 -m py_compile` 均通过(实测,非退出码)。
- 2026-06-30 ⚠️ 真 bug 实证:渲染后 `exploration_workflow_runtime.py` `py_compile` **FAIL**(line147 `%%`)→ sed 改单 `%` 后 **OK**。已作为 PR 第1个 commit。
- 2026-06-30 🔴 **运行时头号根因实锤**(读 `artifacts_sample/exploration_summary.json` L404):SLAM 后端崩于 `ModuleNotFoundError: No module named 'tomllib'`(humble=Py3.10 无此库,栈为 jazzy/Py3.11+ 写)→ 无 `/slam/odom`/`/tf`/`/scan` → 全链 waiting_for_pose、探针 rc=20。**订正**:`%%` 不是"头号"根因(在它下游),之前 PR/Issue 措辞夸大了 `%%` 的权重,待改。修法:SLAM CLI `import tomllib` 加 `tomli` 兜底。
- 2026-06-30 阶段4桥接·真版GBPlanner I/O契约**从gbplanner-ref源码逐条证实**;产出 ros1_bridge 映射 + ROS2 出口适配器(trajectory_to_intent.py,py_compile过)。去风险:仅标准消息跨桥,自定义planner_msgs留ROS1内。见 `integration/ros1_bridge/`。
- 2026-07-02 预研B GUI 实跑排 6 坑(A~F),链路实测通到 **voxblox TSDF 3D 建图 4.5Hz**(点云 27876 点/odometry 252Hz,RViz 弹窗);发现上游 xacro 真 bug(OS0-128 传非法 gpu/organize_cloud 参数)。剩"起飞→探索"一步。证据:docs/预研B_仿真实跑排错记录.md;一键复现:runbooks/gbplanner_ref/run_light.sh。
  - ⚠️ **环境铁律(新)**:WSL 下跑容器必须挂常驻 keepalive 进程——发行版空闲十几秒自动关机→docker 被优雅停止→容器全死 255(journalctl 实锤)。
- 2026-07-02 预研B **自主探索全闭环**(起飞→建图→RRG→巡飞→480s 预算自动返航→地图落盘 4MB)+ 全程量化(291.3m/132,091 体素点/70 采样点曲线入库 images/)。
- 2026-07-03 预研A 运行时剥洋葱:坑④~⑨ 逐个实锤修复(venv悬空/setup.bash缺失/rclpy版本/ydlidar必需+declare_parameter/QoS/**总根因 sdformat_urdf-gpu_lidar-RSP**)。方法论沉淀:"手动常驻容器从容取证"+"逐段模拟启动命令冒烟"+"活体探针"。当前卡:编排下 baseline DDS 隔离嫌疑。
- 2026-07-05 ⚠️ 又抓一类假成功:`go run navlab-sim build` 编排 builder 无 BuildKit,遇 `RUN --mount` 失败**却报 OK/rc=0**(docker images 无镜像)→ 绕过,直用 `DOCKER_BUILDKIT=1 docker build`(runbooks/world-model-jazzy/build_jazzy.sh,内置真产物核验)。
- 2026-07-05 jazzy 镜像 7 个开箱验真(verify_jazzy_images.sh 逐个进容器查 /opt/ros):全真。副产物发现:**companion 的 humble tag 内部实为 jazzy/Py3.12**(同 ID 双标签)——解释了它从不报 tomllib。
- 2026-07-05 gazebo-sensor jazzy 原样构建**实测失败**(ydlidar declare_parameter,rclcpp jazzy 头文件四候选全不匹配)→ 26 处 sed v2 一次过;开箱 venv python(系统 Py3.12)直接能跑 → **d8ff119 悬空软链坑 jazzy 不存在**双向实锤。
