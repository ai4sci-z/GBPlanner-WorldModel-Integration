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
- **验证批**:`l15_batch.sh`(truth-external-nav ×3,DURATION_SEC=1500,与 07-15
  翻机批同条件)于 2026-07-15T19:55:19Z(UTC)发车,
  log = `artifacts/sim/l15_batch_20260715T195519Z.log`。判决以 BIN 为准
  (`l1_bin_full_window.py` + 本审计工具复核 det≈+1)。结果另记。

## 5. 诚实边界

- 本文只 CONFIRM"喂入位置是真值的反射 + 修复后喂入几何自洽";
  "翻机由此反射引起"在验证批 L1.5×3 全稳 + L2×3 全稳之前只是强因果假设
  (机制推理 + 二分矩阵一致,但未反事实闭环)。
- `_ros_quat_to_frd`(非 use-fcu-roll-pitch 路径)与 `pose_mirror.ned_to_gazebo_pose`
  的帧向**未在本轮审计/修改**(前者 live 不走,后者被 Procrustes 自对齐吸收),
  遗留待查,勿与 B21 混淆。
- L2(SLAM 喂入)是否还有 cartographer map 帧向问题,待 L2 复跑后用同工具审计。
