# runbooks/world-model-jazzy 目录导览

> 本目录混存**现役工具**与**冻结历史证据**(共 200+ 条目,平铺是历史欠账)。
> 分类如下;冻结件只读不改。物理重组(分子目录)已列入 P0 遗留队列,须负责人批准后
> 与 manifest 再生成、全量引用更新同批执行。

## 现役(当前施工使用)

| 条目 | 用途 |
|---|---|
| `l0_hover/` | **WP303 批生命周期**(batch_lifecycle.py / run_batch.sh / batch_common.sh / l15·l2·l2fix_batch.sh / wait_batch.sh + 三套测试)+ **WP304 open1/**(证据提取器/协议解码器/独立标注 + 测试)+ L0-L2 分层证据 md |
| `build_jazzy.sh` / `build_all_jazzy_native.sh` / `gazebo-sensor-jazzy.Dockerfile` | jazzy 镜像构建(BuildKit 直建 + 真产物核验) |
| `verify_jazzy_images.sh` | 镜像开箱验真 |
| `gate4_live_native.sh` | GATE-4 live 验收入口(WP307 复用底版) |
| `clean_repro.sh` | 历史基线复现(07-06 桥接期窄验收绿,非当前稳定结论) |
| `bin_autopsy 相关`(decode_*.py/sh、check_*.py) | BIN/rosbag 验尸工具(排障必备) |

## 冻结·桥接期(oracle 证据链,只读)

- `stage*`(126 条):桥接线 Stage1-6 的脚本+证据(thinbridge/探针/批跑/诊断)。
  其中 `stage5c_run.sh` 被 M5 直连方案列为 harness 改造底版(见 docs/worldmodel理解_3 §4)。
- `gui*`(12 条):桥接期三演示脚本(Windows/WSL 口径)。

## 冻结·修复剧本(已应用,留档可追溯)

- `patch_*`(17 条)/ `apply_*`(2 条):对 wm clean 分支与探针/模板的历史补丁脚本
  (死锁/IMU 回声/RNGFND/QoS/latejoin/lidar3d/external 让位等,对应台账 B 号)。
- `commit_*`、`bulk_*`:当时的提交与批量整理辅助。

## 冻结·平台战役证据

- `baseline_*`、`gate4_*evidence*`、`l1_bisect_*`、各 `*_evidence.txt`(57 条 txt/md):
  L0-L2 分层、GATE-4、基线批的原始证据,分母与判决以 md 证据文件为准。
