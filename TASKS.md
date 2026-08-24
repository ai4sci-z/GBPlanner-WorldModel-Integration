# TASKS（未完成工作队列；最后更新 2026-08-24）

> 当前事实与已完成验证只写入 [CURRENT_STATUS.md](CURRENT_STATUS.md)。本文件只保留未完成项，
> 严格按项目章程排序，不并行跳阶段。

P0 本轮治理闭包和 P1-1 正式 exploration probe 恢复均已完成；当前只推进 P1，P2/P3/P4
继续受阶段门约束。

## 当前队列

| WP | 任务 | 依赖 | 可证伪验收条件 | 状态 |
|---|---|---|---|---|
| P1-2 | 固定 SHA 的真 GBPlanner 短闭环 | P0、P1-1 | 正常收尾；summary 完整且 `ok=true`；RRG、voxblox、trajectory、adapter、FCU 执行证据同 run 对齐 | 就绪；当前唯一施工项 |
| P1-3 | 默认路径正式 10/10 | P1-2 | 10/10 attempts 全部发起、起飞、任务成功、正常落地/收尾；所有 attempt 入分母 | 阻塞于 P1-2 |
| P1-4 | 长时间闭环稳定门 | P1-3 | 固定时长、漂移、断链、崩溃、资源和收尾阈值全部满足；保留完整 rosbag/summary | 阻塞于 P1-3 |
| P2-1 | ROS 1 / ROS 2 离线对齐准备 | P1 | 冻结 oracle、参数规范、topic/msg/frame 映射、fixture 与比较器均可复现 | 阻塞于 P1 |
| P2-2 | ROS 1 / ROS 2 正式对齐 | P1、P2-1 | 像素/体素、参数、消息、I/O、时序逐项对拍并记录容差与反例 | 阻塞于 P1 |
| P3 | 3D 无损证明 | P2 | z 路径、体积增益、立体避障、空间探索与 oracle 同表比较并满足门限 | 阻塞于 P2 |
| P4 | WorldModel 插件化集成 | P3 | 真 GBPlanner 独立注册、配置切换、回滚与运行验收；与其他策略并列且无冒名入口 | 阻塞于 P3 |

## 当前禁止项

- 禁止把 `/home/ai4s/aa_runs/gbplanner_strategy_v4.py` 的 2D 代理结果记作 GBPlanner/RRG 结果。
- 禁止用 `navlab/official-baseline:jazzy-latest` 编译 voxblox/GBPlanner；它是运行镜像。
- 禁止在没有最终 summary、`ok=true` 和正常收尾证据时把长跑改判为 PASS。
- 禁止在 P1 关闭前进入 P2 live、P3 或 P4 实现。
- 禁止把 GPS-denied 多层楼梯研究塞入当前实现排期。
