# 桥接 adapter 冻结清单(Review 001 P0-7 整改)

> 2026-07-15 建。规则:本目录 `trajectory_to_intent_stage4.py` 为**桥接期冻结版(oracle)**,
> 永不再改;M5 现行版从它派生,改动只落在派生路径并在下表登记。

| 角色 | 路径 | sha256 | 状态 |
|---|---|---|---|
| 冻结 oracle(桥接期 stage4) | `integration/ros1_bridge/trajectory_to_intent_stage4.py` | `80d071b783e1dc17a31e00b6ff123bcaa58a39b4a06547dd0bd92186d78f8ea7` | FROZEN,禁改 |
| M5 派生现行版 | `ros2_port/adapter/trajectory_to_intent.py` | 同上(2026-07-15 与冻结版字节一致,尚未分叉) | ACTIVE(M5 恢复后按 Review 001 P1-1/2/3/4、Review 002 z 口径演进) |

派生版每次实质改动:在此表追加一行(日期 / commit / 相对冻结版的行为差异摘要)。
历史 runbook 引用旧路径属预期(指冻结版);现行脚本一律引用派生路径。

注意(Review 002 §13.2):冻结版**不是**经过安全审计的控制器——已知永久 readiness、
畸形轨迹崩溃、旧 stamp 复活、goal 重复计数、混流可绕过等缺陷,只作行为对照 oracle 用。
