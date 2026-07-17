# TASKS(未完成工作包队列;状态以 CURRENT_STATUS 为准)

> 本文只维护**未完成**任务:优先级、依赖、验收门、解锁条件。
> 已完成历史见 git 历史,不在此堆日志。当前分母/状态不在此复制,见 CURRENT_STATUS。

## 当前队列(严格按序,不并行扩张)

| WP | 任务 | 依赖 | 验收门 | 状态 |
|---|---|---|---|---|
| **WP303** | monitor 生命周期实现:launcher + task record + 三轴状态(producer_outcome/evidence_status/cleanup_status)+ ≥20 fixture;只跑 fixture 不跑真实仿真 | P0 收口 | test_wait_batch 42/42 + test_batch_common 12/12,前后 PID/PGID 无残留 | 🟡 **实现停点:fixture 通过,真实仿真未做** |
| WP304 | OPEN-1 因果时间线:对失败/成功 run 逐层建时间线,竞争假设矩阵,单变量可证伪实验(方案停点先行) | WP303 | 时间线+假设矩阵成文,负责人放行方可跑实验 | ⛔ 阻塞 |
| WP305 | 时钟纪元契约修复(OPEN-2):测试与 pymavlink 环境解耦,补节点重启/来源生命周期反例 | WP303 | 反例矩阵全绿,独立复验通过 | ⛔ 阻塞 |
| WP306 | 三独立单元:GPU 支持矩阵 / IMU covariance(C'=RCRᵀ)+types.go 反注释 / truth audit 混合匹配 fail-closed | WP303 | 各单元反例测试通过 | ⛔ 阻塞 |
| WP307 | 默认路径连续 10/10:固定 commit/镜像/场景,全 attempts 入分母 | WP304–306 | 10/10 发起/起飞/full-pass,产物完整无残留 | ⛔ 阻塞 |
| WP308 | 长稳门 + R003 收口:固定时长/漂移/断链/崩溃阈值 | WP307 | 负责人批准的长稳指标全满足 | ⛔ 阻塞 |

## 下游阻塞任务(P0/P1 未关闭前禁止进入)

- **P2 ROS1/ROS2 前端对齐**:冻结 ROS1 oracle,像素/体素/参数/消息/时序逐项 diff。⛔
- **P3 3D 无损验证**:路径 z / 体积增益 / 立体避障 / 空间探索,与 oracle 同表比较。⛔
- **P4 WorldModel 插件化接入**:GBPlanner 与 frontier_lite 等并列注册、配置选择、运行切换、独立验收。⛔
- **架构预留**:GPS-denied 多层楼梯探索只输出接口/数据结构/模块边界清单,禁止功能代码。

## 相邻技术债(并入对应 WP,不单列)

- exploration/navigation 的 cartographer 仍读原始 `/imu`(B22 只转正 hover 族)→ M5/P4 前必补。
- world-model runner 探针完成即 SIGKILL mission(GATE-4b 本体 blocker)→ 属 world-model 改动,WP304 定位后另行方案。
