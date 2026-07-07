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
- **预研 A / 预研 B** = 复现任务(A=复现 world-model,B=复现 GBPlanner)。均已完成。
- **集成方案** = **「B2.5 自写薄桥」(现行,实测选型)**;历史名称曾为「桥接方案(ros1_bridge)」——官方 ros1_bridge 与 zenoh 均已实验判死(stage2a-2d);「重写方案(gbplanner_core)」为备选/理解材料。

## 三、当前任务表(2026-07-06 更新)
| ID | 任务 | 状态 | 备注 |
|---|---|---|---|
| 1 | 预研B·复现 GBPlanner 官方 ROS1 仿真 | ✅ **完成:自主探索全闭环(2026-07-02 实测)** | 排 6 坑后:起飞→voxblox 3D建图→RRG规划→**无人机自主巡飞覆盖迷宫**(轨迹实测 (5.7,-1.3)→(4.4,6.4),RViz 可视化在桌面)。复现:`run_light.sh` + `takeoff_and_explore.sh`;全记录 docs/预研B_仿真实跑排错记录.md |
| 2 | 调研·确认 ros1_bridge 官方接入做法 | ✅ 完成 | 你已选「桥接方案」 |
| 3 | 预研A·完整复现并**实际运行** world-model | 🏁 **端到端全绿(07-06 晚)** | run `20260706T130626`:TASK_STATUS_OK、blockers 空、4 探针全 ok、accepted_goals=3/3、path 1.06m、takeoff.ok=True、物理起飞 SIM+0.72m/电机1950,**无 hack**,clean_repro 首次 rc=0。关键=B15 死锁修复+B16 探针双根因(tf_static latched QoS+pose_filtered DDS慢发现28.97s实测)。clean分支 fix/world-model-e2e-takeoff(79643b9→77d951a→dada2db) |
| 4 | 集成落地·`gbplanner_gain` 2D 原型 | ✅ 代码完成(**历史 2D 原型,非当前主线;PR 延后**) | ROS2-native 决策层原型:读图选向替代 frontier_lite 脚本。分支 `feat/gbplanner-gain-exploration-strategy`。**当前主线=B2.5 薄桥接真 GBPlanner(#9)**;本原型作为诚实标注的 PR-B 素材 |
| 4.5 | **真 bug 发现**:exploration 生成脚本无法编译 | ✅ 已修并入PR | `%%` 经 text/template 原样落盘 → SyntaxError;`py_compile` 实测复现,改单 `%` 后通过。疑似 exploration 运行时起不来根因之一 |
| 5 | 论证·跑 frontier_lite + 小 demo 证明其不足 | ✅ **量化证据到手(07-06 晚)** | 代码层铁证(时间驱动 goal_index=ready_elapsed/8.67s,不订阅地图)+ **基线实测**(6 run:达标率 40%、path 0.43~3.80m 方差大,根因=启动耗时蚕食 26s 窗口,docs/基线定档);GBPlanner 侧实测(291.3m/132,091点)早已入库 |
| 6 | 对比·GBPlanner vs frontier_lite 量化对照 | ✅ **公平对比定档(07-07 下午)** | **修复后同口径:GBPlanner 达标 3/6=50% vs frontier_lite 0/6=0%,显著占优**(基线 accepted 恒=2 零方差=窗口结构性失败;修复前的 2/6 全绿实为 EKF 跑飞馈赠);且我方 accepted=真实运动到达,口径更严。GBPlanner 全绿 1/6(runA),v5(PD)后全绿率待 v2 批跑。stage5c_summary_evidence + baseline_postfix_evidence |
| 7 | 文档·预研A/B 独立报告 | ⬜ 降级(文档完善类,非主线) | 预研A/B 均已完成,报告素材齐(Bug台账/基线/预研B成果);等主线跑通后统一出报告 |
| 8 | 提交 PR + Issue 给 world-model 作者 | ⏸ **延后(你 2026-07-06 晚指示)** | 源码改动**先保存**(clean 分支 4 commit+净diff 286行零hack✅,全绿✅);**等最终集成任务(真 GBPlanner 桥接)跑通后再准备完整 PR 物料一并定稿**。硬约束不变=作者 jazzy 环境能跑 |
| 9 | **⭐ B2.5 自写薄桥接真版 GBPlanner(当前主线)** | 🔵 **Stage2~5 主链全实证:4c✅ 5a✅(3次重现)5b✅ 5c 首批✅;runA=首个完整全绿;当前=成功率提升+基线重跑+GUI/PR** | 4c 去混流可归因(签名窗口 path 0.99m);5a gate 机制(run8 accepted=4 全运动到达);**5b 3D 对照成立**(FOV ±30°→±5°:输入 zspan 19× 压缩→TSDF 点数减半→trajectory z 收缩一个量级);**5c 六样本**:gate 达标 50% vs 基线 40%、全绿 1/6(runA=TASK_STATUS_OK)、失败分类 A类探索质量/B类探针波动;失真补证表=cmd_vel↔intent 0~14°(FCU 转发忠实)。上游 EKF 真 bug 根治(clean 99bcfa1,stage5a_diagnosis 必读);**ROS2 复核:无官方 ROS2 版 GBPlanner(16 分支全 ROS1/0 tag),短期维持薄桥**。入口 docs/桥接查证与执行计划 |
| 10 | 修运行时头号根因 tomllib | ✅ 完成(0b85cea) | `try: tomllib / except: tomli` 兜底;jazzy 实测零影响(原生 tomllib,兜底分支不执行) |
| 11 | **⭐ jazzy 全栈重建(用户硬指令)** | ✅ **镜像阶段 9/9 收官(07-05 晚)** | 4 缺镜像全建成+开箱验真(坑全解:BuildKit 假成功/Livox cstdint/ydlidar declare_parameter;official-baseline **原版零补丁一次过**,micro_ros_agent 58.4s=humble 最狠坑 jazzy 天然没有)。施工指引 docs/jazzy全栈重建_施工指引.md;脚本 runbooks/world-model-jazzy/ |
| 12 | **⭐ jazzy 跑通 exploration** | 🏁 **端到端全绿(07-06 晚)** | clean_repro.sh 首次 rc=0(run `20260706T130626`)。修复链:5类真bug(%%/空launch/IMU回声/RNGFND参数名)+ **B15 死锁** + **B16 探针双根因**(/tf_static latched→publisher QoS 内省;/ap/v1/pose/filtered→DDS 慢发现 28.97s 受控实验锤死→预算45s/容器90s)+ 测试断言遗留清理,go test 全绿。✅hack已撤(77d951a),净diff 286行(dada2db)。接管文档 RESUME_新窗口接管_2026-07-06.md + Bug台账 |
| 13 | **frontier_lite 基线定档** | ✅ **两批完成:修复前(07-06)+修复后复档(07-07)** | 修复前:全绿 2/6、达标 40%、path 0.43~3.80(**已判定被 EKF 跑飞污染**);**修复后(公平口径):全绿 0/6、达标 0/6、accepted 恒=2 零方差、path 0.15~2.63**——"启动耗时蚕食 26s 窗口"从源码判断升级为实测确定性结论(时间片只装得下 2 个 goal)。baseline_postfix_evidence.txt |

## 四、决策 & 桥接路线(你已拍板;2026-07-07 更新为实测路线)
集成采用「**B2.5 自写薄桥**」(历史名 ros1_bridge 方案;官方桥/zenoh 实验判死后确立)= **GBPlanner-in-world-model 桥接式融合**(非 ROS2 原生移植,联网复核无官方 ROS2 版)。实测进度:① gbplanner-ref 单侧 ✅ ② 薄桥数据链+3D 雷达 ✅(stage2~3.5)③ Stage4 FCU 闭环+去混流归因 ✅ ④ Stage5a gate 机制 ✅(3 次重现)⑤ Stage5b 3D 行为对照 ✅ ⑥ Stage5c 首批+**公平对比定档 ✅(50% vs 0%)**⑦ v2 批证伪 kp0.45 ⑧ **成功率战役 ✅**(探针预算 C/B 类根因全修+适配器 v6b;final2 再次全绿)⑨ **GUI 三演示 ✅ 交付** ⑩ **当前=组会后 full 批定档+基线复跑+PR 定稿**。`gbplanner_core` 转备选/加深理解。

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
