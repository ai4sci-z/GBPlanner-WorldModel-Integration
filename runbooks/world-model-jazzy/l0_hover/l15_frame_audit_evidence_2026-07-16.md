# L1.5 帧审计:external-nav 位置喂入 = 真值的反射(B21,ROOT_CAUSE)

日期:2026-07-16。承接 `l1_bringup_evidence_2026-07-15.md` §4 的二分矩阵封口
(L0 稳 / L1 稳 / L1.5 翻 / L2 翻 → 根因域 = external-nav→EK3 喂入路径)。
本文记录根因定案的**测量链**:未做任何新跑,直接在既有 L1.5 翻机 BIN 上判决。

## 1. 假设来源(源码内在矛盾,先于测量)

`navlab/real/companion/nodes/external_nav.py`(wm `57924c0` 时点):

- 位置转换 `ros_enu_position_to_mavlink_local_frd(x,y,z) = (y, -x, -z)`,
  注释声称 "map 契约 x=west, y=north"。
  **几何事实:x=west, y=north, z=up 是左手系**,不可能是合法右手 ROS 帧;
  `(y,-x,-z)` 对**任何**右手 z-up 源帧都产出左手(反射,det=−1)的 NED。
- yaw 路径(live 参数 `--use-fcu-roll-pitch --no-align-yaw-to-fcu`)发
  `π/2 − yaw`,系数 −1 = **真旋转**约定(标准 ENU 公式)。
- 位置=反射 + yaw=旋转 ⇒ 与 IMU 惯性基准对任何帧约定都不可调和
  ⇒ EK3 创新反馈闭环正反馈发散 ⇒ 起飞后确定性翻机。
  与二分矩阵完全自洽:L0/L1(GPS,不融合 vision)稳;L1.5/L2(融合)确定性翻。
- git 考古:`(y,-x)` 由上游 `e8969cf`(feat(hover): harden SLAM hover validation)
  引入,"x=west" 注释是上游 `869dcd8` 加的——**上游真 bug,非迁移引入**。入台账 B21。

## 2. 测量方法(工具 `l15_frame_audit.py`,本目录)

对 L1.5 翻机 run 的 dataflash BIN 全重放:

- `VISP.PX/PY` = AP_VisualOdom 收到的 vision 位置(喂入端,NED 语义)
- `SIM2.PN/PE` = SITL 自身真值(NED)
- 取**翻机前窗口**(真值 XY 离起点 >1.5m 截断,避开翻机滑撬与 0.25m/s 限幅钳制段),
  以 VISP 时刻线性插值 SIM2,中心化最小二乘拟合 2×2 矩阵 `fed = M @ truth_NE`。
- 判据:det(M) ≈ +1 → 真旋转(假设 REFUTED);det(M) ≈ −1 → 反射(CONFIRMED)。
- 另附 8 候选轴映射残差 RMS 与步进方向测试(对径向限幅免疫)。

首版教训:全窗口拟合被翻机滑撬(truth E 位移 9.8m)+ 限幅钳制污染,det=−0.09
不可判;截前窗后信号干净。

## 3. 判决(3/3 CONFIRMED = REFLECTION)

wm `57924c0`,L1.5 正式批三跑(`l1_bringup_evidence_2026-07-15.md` §4.4 同源 BIN):

| run | 窗口 | M(fed = M @ truth_NE) | det | 最优候选(RMS) | 次优 |
|---|---|---|---|---|---|
| 20260715T191629 | 8.0–23.2s, 765 样本 | [[+1.005, −0.000], [−1.509, −0.918]] | **−0.923** | reflectN (n,−e) 0.0179m | 其余 ≥0.335m |
| 20260715T192023 | 8.0–30.7s, 1137 样本 | [[+0.999, +0.000], [−0.137, −0.951]] | **−0.950** | reflectN (n,−e) 0.0135m | 其余 ≥0.296m |
| 20260715T192423 | 7.0–23.6s, 833 样本 | [[+0.996, +0.000], [−0.789, −0.935]] | **−0.932** | reflectN (n,−e) 0.0179m | 其余 ≥0.330m |

读数:

- **VISP.PN = +truth_N**(m00 = +1.005/+0.999/+0.996,三跑一致到千分位)
- **VISP.PE = −truth_E**(m11 ≈ −0.93,幅值差 = 限幅压缩;m10 列由 N 跨度仅 1–2cm
  支撑,不可判读)
- ⇒ 喂入 = 真值绕北轴反射,**东轴镜像**。
- ⇒ 反推:真值/odom 源帧 = **标准 ENU(x=east, y=north)**;上游注释 "x=west,
  y=north" 被同一测量证伪。yaw 公式对标准 ENU 恰好正确 → 位置修好后整条喂入自洽。
- 步进方向测试在本数据集不可判(运动近 1 维,rot180 与 reflectN 方向简并),
  判决权在双轴 LS 拟合;N 轴 m00=+1 排除 rot180(rot180 要求 m00=−1)。

## 4. 修复与验证

- **修复 = wm `908a95a`**:`(y, -x, -z)` → `(y, x, -z)`(标准 ENU→NED),
  status field_map 自述同步,单测改为断言右手性。B21 入账。
  targeted 单测 11/11;容器全套 409 passed / 5 failed / 1 xfailed——
  **5 失败在干净 HEAD `57924c0` 同样失败**(official-baseline 容器缺 `loguru`,
  环境性,与本修复无关;07-15 记录的 "414 passed" 环境待考)。
- companion 已 retag `jazzy-908a95a30561`(external_nav.py 由 official-baseline
  容器挂载 /workspace 直跑,改 host 文件即生效;retag 仅满足 tag_policy)。
- **验证批判决:L1.5×3 修复后全稳(3/3,与翻机批同条件反事实闭环)**。
  `l15_batch.sh`(truth-external-nav ×3,DURATION_SEC=1500),
  log = `artifacts/sim/l15_batch_20260715T195519Z.log`:

  | run(修复后) | armed | roll/pitch 峰(°) | 结局 | 喂入帧审计 |
  |---|---|---|---|---|
  | 20260715T195519 | 14.7s | 0.5 / 0.0 | EV17 正常降落,零 crash | det=+0.999,identity RMS 0.0001m |
  | 20260715T195844 | 14.8s | 0.5 / 0.0 | EV17 正常降落,零 crash | det=+1.000 |
  | 20260715T200206 | 15.4s | 0.5 / 0.1 | EV17+EV18 正常降落,零 crash | det=+1.000 |

  对照修复前同臂 3/3:armed 21.9–29.9s 全 AngErr 129–152° CrashCheck 翻机。
  修复前确定性失稳 ↔ 修复后逐秒级复刻的确定性稳定,真值 XY 漂移 ≤4cm。
  **这是 external-nav 喂入系(L1.5/L2)首次出现完整"起飞→悬停→降落"闭环。**
  三跑 rc=1 均为诊断臂设计上的 purpose 烙印 blockers
  (`external_nav_uses_diagnostic_truth_input` 等),非故障。
- **L2×3 主线批判决:3/3 仍翻**(`l2_batch.sh`,
  log = `artifacts/sim/l2_batch_20260715T200618Z.log`):

  | run(B21 修复后主线) | armed | roll/pitch 峰(°) | crash |
  |---|---|---|---|
  | 20260715T200619 | 14.6s | 61.4 / 70.8 | AngErr=56>30 @27.6 |
  | 20260715T200937 | 14.9s | 78.4 / 83.6 | AngErr=52>30 @27.8 |
  | 20260715T201311 | 14.4s | 59.0 / 88.8 | (侧翻上锁,无 crash msg) |

  ⇒ **B21 状态:L1.5 臂 FIXED;L2 臂非充分——SLAM 喂入链还有第二层根因。**

## 6. 第二层根因(L2 残余):喂入 yaw ≡ 真值 − 180°,位置却与真值同向

L2 run `20260715T200619` 测量(数据源 = summary `hover_xy_alignment` pairwise
+ BIN VISP/SIM 对比):

- **位置方向**:`gazebo_model_odometry ↔ /external_nav/odom` 方向余弦 **+1.0000**
  (喂入位置与真值完全同向);`/external_nav/odom ↔ /slam/odom_corrected` 也 +1.0000。
  EKF 跟随喂入(fcu ↔ feed 余弦 +0.998)。
- **yaw**:VISP.Y 初值 **−91.4°** vs SIM.Yaw 初值 **+90.0°**(spawn 朝东,与 §3
  真值帧=标准 ENU 互证);发散段 SIM 161.9° ↔ VISP −24°≈161.9−180(差=SLAM 滞后)。
  **喂入 yaw = 真值 yaw − 180°,恒差且动态跟踪。**
- 机制:位置对 + yaw 反 180° = 非刚体不一致(B21 同类):EKF 初始 yaw 对齐到反向,
  控制器世界系修正方向全反 → 正反馈跑飞(真值实测漂移 3.56m)→ AngErr 翻机。
  (刚体旋转偏移不可能致翻——L0/L1.5 已证;必须是位置与 yaw 帧不一致。)
- **嫌疑机制(与 `imu_frame_corrector.py` 文档自洽)**:官方 iris 模型 IMU
  `roll-180` 倒装,ros_gz 桥不修数据、TF 声称 identity → Cartographer 吃倒置 IMU
  (静止 z 加速度 −9.8)→ 重力对齐反 → 平面位置照常、朝向 180° 反。
- **反事实批**:`l2fix_batch.sh`(imu-flu-correction ×3,单变量叠在 B21 上)
  2026-07-15T20:23:08Z 发车,log = `artifacts/sim/l2fix_batch_20260715T202308Z.log`。
  预测:修正后 VISP.Y 初值 ≈ +90°,3/3 稳。结果另记。
- 另записано:candidate 流(`/external_nav/odom_candidate`,selector 输出)与
  一切都反平行且幅值只有 0.24m,主线没人消费它——审计 blocker
  `external_nav_odom_candidate__*` 是接线审计告警,与稳定性问题分案处理。

## 5. 诚实边界

- 本文只 CONFIRM"喂入位置是真值的反射 + 修复后喂入几何自洽";
  "翻机由此反射引起"在验证批 L1.5×3 全稳 + L2×3 全稳之前只是强因果假设
  (机制推理 + 二分矩阵一致,但未反事实闭环)。
- `_ros_quat_to_frd`(非 use-fcu-roll-pitch 路径)与 `pose_mirror.ned_to_gazebo_pose`
  的帧向**未在本轮审计/修改**(前者 live 不走,后者被 Procrustes 自对齐吸收),
  遗留待查,勿与 B21 混淆。
- L2(SLAM 喂入)是否还有 cartographer map 帧向问题,待 L2 复跑后用同工具审计。
