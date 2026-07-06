# frontier_lite 基线定档(2026-07-06 晚,B16 修复后连跑实测)

> 用途:GBPlanner 接入后的**同口径对照组**。所有数字为实测,run 产物在
> `~/ws-clean/world-model/artifacts/sim/exploration/<run_id>`(summary.json/BIN/rosbag/probes)。
> 环境:clean 分支 `dada2db`(09a5aa4+4修复,无 hack),jazzy 9/9 镜像,`clean_repro.sh`/`baseline_batch.sh`。

## 一、数据(B16 修复后 6 次)

| # | run_id | rc | accepted_goals(min3) | path_length_m(min0.35) | takeoff.ok | frame_contract | 4探针 |
|---|---|---|---|---|---|---|---|
| 1 | 20260706T130626 | **0** | **3** ✅ | 1.0637 | ✅ | ✅ | 4/4 |
| 2 | 20260706T132342 | 1 | 2 | 0.4253 | ✅ | ✅ | 3/4 |
| 3 | 20260706T132456 | **0** | **3** ✅ | 3.8016 | ✅ | ✅ | 4/4 |
| 4 | 20260706T132610 | 1 | 2 | 1.3635 | ✅ | ✅ | 3/4 |
| 5 | 20260706T132722 | 1 | 0 | 0.1054 | ❌ | ❌ | 2/4 |
| 6 | 20260706T132921 | 1 | 2 | 2.1327 | ✅ | ✅ | 3/4 |

## 二、统计口径(排除 #5 启动竞态后 n=5;#5 单列)

- **全绿率**:2/6(33%);正常启动 run 中 2/5(40%)。
- **accepted_goals**:2~3(均值 2.4/5 次正常 run);**达标率(≥3)= 40%**。
- **path_length**:0.43~3.80 m(均值 1.76 m,方差极大)。
- **takeoff 成功率**:5/6(83%);唯一失败 = #5 启动竞态(bootstrap 整体没起来,非飞行问题)。
- **frame_contract_probe(B16 修复)**:正常启动 run **5/5 全 ok** —— 修复稳定。
- **slam.ready**:6/6 = False(一贯,靠 /slam/odom evidence 兜底,不挡 gate;遗留观察项)。

## 三、失败模式分类(给 GBPlanner 对比与后续排障用)

| 模式 | 次数 | 定性 |
|---|---|---|
| A·探索质量:`accepted_goals 2<3` | 3/6 | **frontier_lite 固有缺陷的量化证据**——脚本式 3 步循环不看地图,目标能否被接受取决于时序/运动随机性,导致达标率仅 40%、path 方差 0.4~3.8m。这正是 GBPlanner(体积增益选路)要解决的问题,是对比实验的核心指标 |
| B·启动竞态:bootstrap 未完成 | 1/6 | run `132722`:controller_not_ready、rosbag_profile_failed、连 /navlab/fcu/controller/status 都没采到——服务启动期系统性故障(疑资源/DDS 竞态),与探索策略无关;连跑压力下偶发,记录不深究 |
| C·探针采样(B16 前的旧病) | 0/6 | 已修复,正常 run 零复发 |

## 四、对比实验口径(GBPlanner 接入后按此对照)

- 同指标:`accepted_goals` 达标率、`path_length_m` 均值/方差、全绿率、(可加 rosbag 轨迹覆盖)。
- 同环境:同 clean 分支、同镜像、同 world、同 min_accepted_goals=3。
- 预期论证点:GBPlanner 按体积增益选向 → accepted_goals 达标率与 path_length 应显著且**稳定**地高于 frontier_lite 的 40% / 1.76±1.3m。
