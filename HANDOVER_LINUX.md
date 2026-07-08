# HANDOVER_LINUX — 原生 Linux 环境无损接管引导

> **读者 = 新环境里的 Claude Code。** 用户在原生 Ubuntu 24.04(双系统新盘)上 clone 本仓后,会让你读本文件接管。
> 本文件自带全部上下文快照 + 环境适配规则;按 §0 顺序执行,不要跳步。
> 生成:2026-07-08 深夜(WSL 侧干净断点);作者:上一环境的 Claude Code。

---

## §0 接管协议(按序执行)

```text
STEP 0: 探测环境,填出下表(本文件所有 ${VAR} 按此代换)
  ${REPO}   = 本仓 clone 路径(pwd 所在)
  ${WM}     = world-model 仓 clone 路径(§3 恢复后填)
  ${HOME}   = Linux 用户家目录
  探测: go version(须 ≥1.24)/ docker info / nproc / df -h
STEP 1: 通读入口四件套(顺序): CURRENT_STATUS.md → TASKS.md → 接力棒_当前值班.md
        → docs/GBPlanner_ROS2原生迁移可行性与任务拆解_2026-07-08.md(任务书)
STEP 2: 若做 ROS2 迁移主线,再读: ros2_port/README.md(feat 分支)
        + ros2_port/docs/m2_scout_{1,2,3}(侦察报告)
STEP 3: 按 §4 重建环境,每步过验收门才继续
STEP 4: 按 §7 把本文件的关键事实写入你的记忆系统(新机器记忆为空)
STEP 5: 从 §6 任务队列顶端继续干;干活纪律见 §8
```

---

## §1 项目身份(30 秒版)

给 **world-model**(ROS2 jazzy 无人机仿真平台,Go 编排+容器化 ROS 栈)换探索脑子:
用 **GBPlanner**(DARPA SubT 冠军队的 3D 探索规划器,ROS1)替换其占位策略 frontier_lite。
**当前主线 = GBPlanner ROS2 原生迁移(M0-M5)**;此前的 ROS1↔ROS2 桥接线已完成使命
(公平对比 **50% vs 0%** 显著占优)并冻结为 oracle/科研素材,**不再演进**。
导师最高指示(2026-07-07):放弃桥接,原生迁移。

## §2 状态快照(machine-readable)

```yaml
snapshot_date: 2026-07-08T23:59+08
milestones:
  bridge_line:   {status: FROZEN_ORACLE, headline: "50% vs 0% 公平对比,全证据在库"}
  M0_recon_docs: {status: DONE}
  M1_planner_msgs:
    status: DONE
    commit: e343421            # feat 分支
    what: "ros2_port/src/planner_msgs 最小 8 接口;jazzy colcon rc=0;interface show 8/8"
  M2_voxblox:
    status: SLICE_1-4_DONE__SLICE_5_PENDING
    commits: [d8b4ee1, "3018307", aa66fcc, 1f61ff1]   # feat 分支四切片
    slice1: "vendor snt-arg/voxblox_ros2_minimal@d08e9d4 → ros2_port/src/;9包 Jazzy 构建 rc=0"
    slice2: "维护补丁:删幽灵依赖 rviz_plugin(7包最小集);修 gflags 吃 --ros-args;param E2E 实证"
    slice3: "ntnu dev/noetic tsdf_integrator 行为补丁(补丁原件 runbooks/ros2_port/ntnu_tsdf_integrator.patch);gtest 10/10"
    slice4: "oracle 逐体素对拍双积分器 PASS: simple=35323/35323 零差 RMS 1e-4;fast mismatch 2/34506;
             路上修真 bug=min_time 节流 1s 无操作(from_seconds 静态工厂误用)"
    slice5_TODO: "ESDF 对拍 + world-model 场景建图 + RViz2 可见(=M2 收口)"
  M3_core_strip:  {status: TODO, note: "GBPlanner 是进程内实例化 TsdfServer,构造签名 (nh,nh_private)→(rclcpp::Node*) 要适配"}
  M4_node_shell:  {status: TODO, note: "PCI 先用最小定时 trigger 替代,勿复刻全家桶"}
  M5_integration: {status: TODO, note: "接入契约=external strategy 发 intent+status;适配器 trajectory_to_intent_stage4.py 直接复用"}
world_model_side:
  stage6_probe_fixes: "全收口:修⑥ ff24087(frame_contract 采样消费链路 pose)+ 修⑦ 050ee94(rosbag required 集合同口径);
                       live 复跑 20260708T101402 = TASK_STATUS_OK 全绿"
  clean_branch: fix/world-model-e2e-takeoff   # 9 commits: 09a5aa4→79643b9→77d951a→dada2db→99bcfa1→e7ca9fc→30e0f6d→ff24087→050ee94
git:
  this_repo:   {remote: "github.com/ai4sci-z/GBPlanner-WorldModel-Integration(私有)", branches: [main, feat/gbplanner-ros2-port]}
  world_model: {upstream: "github.com/SZ-surveying/world-model", local_work_branch: fix/world-model-e2e-takeoff,
                bundle_backup: "Windows 盘 C:\\CCproject\\backups\\world-model-clean-050ee94.bundle(含 main+clean 分支完整历史)"}
```

## §3 仓库与代码恢复

```bash
# 1. 本仓(读到这里说明已 clone)。两个分支都要:
git fetch origin && git branch -a          # 确认 main + feat/gbplanner-ros2-port

# 2. world-model(clean 分支含全部修复,必须恢复):
#    路线 A(推荐): 挂载 Windows 盘取 bundle(双系统可 mount NTFS)
sudo mount /dev/<win盘分区> /mnt/win       # 或文件管理器挂载
git clone /mnt/win/CCproject/backups/world-model-clean-050ee94.bundle ${WM}
cd ${WM} && git checkout fix/world-model-e2e-takeoff
git remote set-url origin https://github.com/SZ-surveying/world-model.git
#    路线 B: 旧 WSL 还活着 → 从 WSL 侧 push 到用户自己 fork 再 clone
# ⚠️ 勿向 SZ-surveying 上游 push;PR 政策见 §8

# 3. voxblox 参照仓(oracle 对拍/后续 diff 用,可选,一键):
#    参考 runbooks/ros2_port/m2_clone.sh(路径按新机改)——
#    注意 ref/voxblox-ntnu 必须 fetch + checkout **dev/noetic** 分支(GBPlanner 实 pin,非默认 master)
```

## §4 环境重建(每步有验收门)

```text
GATE-0 宿主: docker engine + go ≥1.24(装 /usr/local/go,勿用发行版旧包)+ git
        宿主不装 ROS——全部容器化。国内网络:docker registry mirror + apt 清华源。
GATE-1 拉底图: docker pull ros:jazzy-ros-base
GATE-2 navlab 九镜像: bash ${REPO}/runbooks/world-model-jazzy/build_jazzy.sh
        (脚本可能含 WSL 路径,先通读改路径;坑全记录在 docs/jazzy全栈重建_施工指引.md)
        验收: docker images | grep navlab → jazzy 系 5-6 个镜像齐(humble 系不用建)
GATE-3 go test: cd ${WM}/orchestration/sim && go build ./... &&
        go test -count=1 ./internal/config/... ./internal/tasks/helpers/... ./internal/tasks/
        (tasks 包偶发 flaky FAIL,重跑即过——已知,记录在案)
GATE-4 live 全绿: 参照 runbooks/world-model-jazzy/stage6_live2.sh(把 /home/ai4s/ws-clean 改 ${WM})
        验收: summary.json → task_status=TASK_STATUS_OK 且 blockers=[]
        对照证据: runbooks/world-model-jazzy/stage6_live_evidence.txt
GATE-5 voxblox deps 镜像: docker build -t voxblox_ros2_deps:jazzy \
        -f ${REPO}/runbooks/ros2_port/m2_deps.Dockerfile ${REPO}/runbooks/ros2_port
GATE-6 M2 复验: 跑 m2_build3.sh 口径(SRC 改 ${REPO}/ros2_port/src/voxblox_ros2_minimal)
        验收: COLCON_RC=0 + test_sdf_integrators 10/10 PASSED
GATE-7 gbplanner-ref oracle 镜像(切片5 的 ESDF 对拍要用):
        入口 runbooks/gbplanner_ref/(Dockerfile + build_and_run.sh);或从旧 WSL
        docker save gbplanner-ref:latest | gzip 导出再 load(10.7GB,ROS1 栈编译较久,save/load 更稳)
```

**硬编码路径清单(新机首次用前必改,均在 feat 分支)**:

| 文件 | 现值 → 改为 |
|---|---|
| runbooks/ros2_port/m1_build.sh | `/mnt/c/CCproject/...` → `${REPO}/...` |
| runbooks/ros2_port/m2_build.sh | `/home/ai4s/ros2_port_ws/...` → `${REPO}/ros2_port/src/...`(vendored 副本即真源) |
| runbooks/ros2_port/m2_build2.sh m2_build3.sh | `/mnt/c/...` → `${REPO}/...` |
| ros2_port/oracle_cmp/run_oracle_ros1.sh run_port_ros2.sh | CMP/SRC=`/mnt/c/...`→`${REPO}/...`;OUT=`/home/ai4s/cmp_out`→`${HOME}/cmp_out` |
| runbooks/world-model-jazzy/stage6_live2.sh stage6_verify3.sh | `/home/ai4s/ws-clean/world-model` → `${WM}` |

## §5 规则表(按环境适用性分三类)

**PORTABLE(新环境依然铁律)**:
- `navlab-sim --artifact-root` 只能指 workspace 内路径(docker 探针按 workspace 前缀映射,指 /tmp 必致 4 探针全挂假象)
- voxblox 工作区**禁 rosdep**(package.xml 有 ROS1 时代 key 会炸),依赖按 m2_deps.Dockerfile 显式清单
- jazzy `ros2 topic echo` CLI 对 rclpy 发布者收不到 → **验收一律 rclpy 订阅**
- rosidl:接口文件名 PascalCase + 常量 UPPER_SNAKE_CASE(kCamelCase 直接拒编)
- ROS2 voxblox 订阅名是**私有名** `/voxblox_node/pointcloud`(ROS1 是公共 /pointcloud);save_map 服务 `/voxblox_node/save_map`
- GBPlanner 配置陷阱:yaml 里 sparsity_factor=100 是 ntnu 死参数,底座已拆除该参数——移植 GBPlanner 配置时删 sparsity 两行
- SITL 参数真源头 = docker/profiles/navlab-sitl-external-nav.parm(templates 是测试 fixture,改了不生效)
- 外部驱动 yaw_rate 恒 0(持续旋转干失锁 X2 2D SLAM)
- TF 结构:**无 map→odom**,cartographer 直出 map→base_link(勿默认标准链)
- docker exec 不过 entrypoint,须显式 source
- 退出码=0 ≠ 成功,必须自检真实产物(镜像数/文件/测试/探针 json)

**OBSOLETE(WSL 专属,原生 Linux 下作废)**:
- WSL keepalive 仪式(空闲关机杀 docker)→ 不需要
- `wsl bash -lc` PATH 污染 / MSYS_NO_PATHCONV / PowerShell 调 wsl → 不存在
- UNC `\\wsl.localhost\...` 访问 / /mnt/c IO 慢、容器内 cp 避坑 → 不存在(但容器内构建到原生 FS 的习惯无害,可保留)
- /tmp 重启清空焦虑 → 常规 Linux 语义

**RE-VERIFY(新环境首次要重新确认)**:
- GUI:Gazebo GUI/RViz2 原生弹窗(替代 WSLg;应该更稳,验一次)
- 实时性:live run 成功率口径在新机重新定档后再和旧数据比(调度环境变了)
- go test tasks 包的偶发 flaky 是否仍在(记录,不阻塞)
- docker 组权限 / nvidia-container-toolkit(仅 nvblox 远期路线需要)

## §6 任务队列(从顶端继续)

```yaml
- id: M2-slice5          # ← 下一棒,从这里开工
  what: "ESDF 对拍 + world-model 场景建图 + RViz2 可见 = M2 收口"
  how:
    esdf_cmp: "复用 oracle_cmp harness:两侧起 esdf_server(参数同 tsdf 批)+ save_map 出 esdf 层;
               compare_layers.py 的 TSDF 体素=3×uint32,EsdfVoxel 序列化格式需先查
               voxblox/src/core/block.cc 的 Block<EsdfVoxel> 特化再改解析器(2×uint32?现场确认)"
    wm_mapping: "起 world-model 仿真栈(lidar3d 配置),ROS2 esdf_server 订点云建图;
                 TF 用 map→base_link 直链;RViz2 开 mesh/pointcloud 显示截图留证"
  acceptance: "esdf 对拍 PASS(判据同 tsdf 口径)+ 场景建图 zspan/点数合理 + RViz2 截图入 images/"
- id: M3
  what: "算法核心 ROS-free 剥离(rrg.cpp/planner_common/adaptive_obb/kdtree)"
  ref: "任务书 §7-M3;GBPlanner 源码在 sources/gbplanner_ros-源码;
        map_manager_voxblox_impl.h 用 #define use_tsdf 进程内实例化 TsdfServer(签名适配点)"
- id: M4
  what: "ROS2 节点壳(最小定时 trigger 替代 PCI)"
- id: M5
  what: "world-model 直连联跑 + oracle 回归 + 同口径公平对比(≥3 run)"
  ref: "接入契约见 docs/worldmodel理解_0_总览_给ROS2迁移.md;适配器零改动条件在 docs/ros2迁移_直连架构契约"
side_quests:
  - "组会汇报口径:任务书 §13 一句话汇报"
  - "PR 政策:⏸ 延后——等 ROS2 迁移联跑后统一定稿(用户 07-06 指示);目标=自己账号 ai4sci-z 的 fork;
     硬约束=作者 jazzy 环境实跑通过(代码级论证不可靠,有 d8ff119 被实测打脸前科)"
```

## §7 记忆重建(新机器 Claude Code 记忆为空,接管后立即做)

把以下条目写入你的持久记忆(格式随你的记忆系统,内容以本文件+入口四件套为准):

```text
1. 接管先读 = ${REPO}/CURRENT_STATUS.md(唯一事实源)+ TASKS.md + 接力棒 + 本 HANDOVER
2. 主线 = GBPlanner ROS2 原生迁移 M0-M5;进度快照 = 本文件 §2;桥接线冻结勿追
3. §5 的 PORTABLE 规则全文(尤其 artifact-root/rosdep 禁令/rclpy 订阅/私有 topic 名)
4. 用户画像: 科研学生,中文交流;要求=实证(每步留 evidence 文件)+诚实边界(不夸大,
   失败如实写)+四处同步(权威仓+GitHub);严厉批评过"错误变形当进展"——唯一指标=真跑通,
   找根因读源码不打补丁;别问"要不要继续",自主推进到干净断点
5. 工作节奏: 每完成一最小步→写盘+git commit(main=文档/证据,feat/gbplanner-ros2-port=代码);
   收工更新接力棒+CURRENT_STATUS+TASKS 三处状态
6. 本机环境事实(你自己探测后补): 路径表/go 版本/docker 镜像清单/首次 live 全绿 run id
```

## §8 工作纪律(用户明确要求过的)

1. **实证纪律**:不因"能编译"宣称成功;行为等价靠 oracle 对拍;每个里程碑单独 commit + evidence 文件入 runbooks/
2. **诚实边界**:结论页写清"不能宣称什么"(参照 CURRENT_STATUS §三格式)
3. **单变量施工**:勿一次碰 messages+voxblox+rrg+TF+RViz(任务书 §11);切片式推进,每片可验收
4. **文档同步**:干完活同步 CURRENT_STATUS/TASKS/接力棒;新窗口读入口即可接管(你现在就是受益者)
5. **抢占式调度**:用户插话=高优先级抢占,先把当前状态写盘再处理
6. **对外发布红线**:勿向上游仓 push/PR(政策=延后统一定稿);外发内容先经用户

## §9 证据索引(全在本仓,新环境可直接引用)

| 主题 | 位置 |
|---|---|
| M1 构建证据 | runbooks/ros2_port/m1_build_evidence.txt |
| M2 切片1/2/3 构建证据 | runbooks/ros2_port/m2_build{,2,3}_evidence.txt |
| M2 oracle 对拍(含真 bug 记录) | runbooks/ros2_port/m2_oracle_cmp_evidence.txt |
| ntnu 行为补丁原件 | runbooks/ros2_port/ntnu_tsdf_integrator.patch |
| 三路侦察报告 | ros2_port/docs/m2_scout_{1,2,3}*.md |
| stage6 收官(live 全绿+翻案) | runbooks/world-model-jazzy/stage6_live_evidence.txt |
| 桥接期全部结论(oracle) | CURRENT_STATUS §二 + runbooks/world-model-jazzy/stage*_evidence.txt |
| 迁移检查单(本文件的姊妹篇) | docs/原生Linux迁移检查单_2026-07-08.md |
| jazzy 镜像重建施工指引 | docs/jazzy全栈重建_施工指引.md |
| Bug 台账(B1-B16+EKF,PR 素材) | docs/world-model端到端Bug台账_给作者PR.md |
