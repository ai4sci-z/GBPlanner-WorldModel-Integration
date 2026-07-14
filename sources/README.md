# sources/ 源码归档

> 来源、pin、许可证、恢复方法一律以 **[MANIFEST.yaml](MANIFEST.yaml)** 为准(机器可读,2026-07-14 建)。

| 目录/文件 | 性质 | 说明 |
|---|---|---|
| `gbplanner_ros-源码/` | 本地未跟踪克隆 | GBPlanner 官方 @7301b535;曾是损坏 gitlink,已按 P0-6 整改为不入库,恢复方法见 MANIFEST |
| `adaptive_obb_ros-源码/` | 本地未跟踪克隆 | @7dc24c97;同上 |
| `world-model-源码/` | 入库浏览快照 | 588 文件、无 .git、不含 third_party;**开发历史在 github.com/ai4sci-z/world-model 私有镜像**(上游 SZ-surveying,红线勿 push/PR) |
| `GBPlanner原始论文_...pdf` | 文档 | JFR 2020 |
| `mentor原始任务_...md` | 文档 | 任务准星 |

可运行的完整 world-model 副本在 `/home/ai4s/projects/world-model`(分支 `fix/world-model-e2e-takeoff`,
含子模块);修复 commit 只进那里并推 `ai4sci-z/world-model` 备份,不改本目录快照。
(旧说明中的 WSL 路径 `~/ws/world-model` 已随 2026-07-13 原生 Linux 迁移作废。)
