# L0 悬停硬门 · 配对批证据(2026-07-14)

> 版本基线:pins_2026-07-14.yaml(world-model `13b11e0`,ArduPilot `e0fa4a47`,
> official-baseline `e13af8bbf517`,模型 overlay sha256 `11715865…e4e8` = 翻机 run 同款冻结)
> harness:`l0_hover_gate.sh`(main `4dfb9e7`);判决 = 落地后全窗口 BIN,业务结果=退出码。

## 1. 实验设计

L0 = 与翻机 hover run **同容器/同 launch/同世界/同冻结模型**,仅两处变量:
①EKF 用官方 GPS+罗盘基线(不挂 external-nav parm 覆盖层)②不起任何 SLAM/companion 服务。
剖面:GUIDED 起飞 → 悬停 60 仿真秒 → LAND。观察式驱动,飞行中零干预。

## 2. 结果:6/6 PASS(两高度配对,各 3 次)

| run | alt | armed(sim s) | roll峰(°) | pitch峰(°) | 带内悬停(s) | XY span(m) | crash | 判决 |
|---|---|---|---|---|---|---|---|---|
| 20260714T133858Z | 0.5 | 88.47 | 0.3 | 0.0 | 83.1 | 0.080 | 无 | PASS |
| 20260714T134508Z | 0.5 | 88.47 | 0.4 | 0.0 | 83.1 | 0.061 | 无 | PASS |
| 20260714T135114Z | 0.5 | 88.47 | 0.3 | 0.0 | 83.1 | 0.100 | 无 | PASS |
| 20260714T135721Z | 1.2 | 89.88 | 0.4 | 0.0 | 81.9 | 0.082 | 无 | PASS |
| 20260714T140327Z | 1.2 | 89.88 | 0.3 | 0.0 | 81.9 | 0.110 | 无 | PASS |
| 20260714T140933Z | 1.2 | 89.88 | 0.4 | 0.0 | 81.9 | 0.056 | 无 | PASS |

每跑仅 1 次解锁事件(落地后),armed 全程连续;RTF≈0.33(mission.json 有记录)。
artifacts:`world-model/artifacts/sim/l0_hover/<run-id>/`(config_manifest/mission.json/verdict.json/BIN)。

## 3. 同尺对照:L2 全栈 hover(翻机组,同一判决脚本)

| run | armed(s) | roll峰(°) | pitch峰(°) | EKF XY 估计跨度(m) | crash_check |
|---|---|---|---|---|---|
| 20260714T092022(L2) | 14.0 | **142.4** | 86.0 | **1345.9** | 触发 |
| 20260714T093122(L2) | 18.4 | **138.5** | 89.5 | **1275.4** | 触发 |
| L0 六跑 | 88-90 | ≤0.4 | ≤0.1 | ≤0.11 | 无 |

注:L2 的 EKF XY 估计在"悬停"中跑出 >1.2 公里(XKF1 全 armed 窗口跨度;
跑飞的时间分辨——翻覆前 or 翻覆后——尚未拆分,列为下一步)。

## 4. 结论与状态词

- **CONFIRMED:刚体物理 / ArduPilotPlugin / 电机 / lockstep / GPS-EKF 在 0.5m 与 1.2m 均稳定**
  (6/6,单变量 = 定位链;高度配对显示无贴地敏感性)。
- **REFUTED:"翻覆 = Gazebo 物理层真实外力矩"假设**——同物理、同模型、同高度,
  仅移除 SLAM/external-nav 定位链即完全稳定;物理外力矩无法解释 EKF 估计公里级瞬移。
- **收敛后的嫌疑域:external-nav/SLAM → EKF 喂入链**(内容、时序或其伴随服务)。
- **尚不能宣称**:具体根因(feed 内容 vs 服务负载/DDS vs 融合参数);L0 的两处变量
  (parm 覆盖层 + 服务集)还需 L1/L1.5 拆分;GATE-4b 本体(全栈 60s 悬停)仍 FAIL。

## 5. 下一层

1. **L2r**:原 hover 任务同 pin 重跑 ×3(固定失败臂;三修复已在码内,若仍翻 = 修复不充分的再证)
2. **L1**:全服务在场但 EKF 留在 GPS 源(拆"服务在场"vs"喂入被融合")——做正式 profile,不 sed
3. L2 BIN 时间分辨:EKF 跑飞 vs 翻覆的先后次序(XKF1/ATT 按时间轴拆)
