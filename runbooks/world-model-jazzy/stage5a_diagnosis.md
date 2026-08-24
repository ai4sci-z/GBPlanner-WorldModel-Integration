# Stage5a 诊断记录:EKF/external-nav 参考系打架(上游根因,2026-07-07)

> [ACTIVE] 状态:随第六跑结果更新。本文是 5a 多轮联跑的根因链与修复记录,证据全部可复现。

## 一、现象(三跑一致的"逃逸"签名)

Stage5a 前三跑(适配器 v1 固定轴换 / v2 EMA 闭环 / v3 Procrustes)全部 FAIL,共同现象:

- 飞机运动方向与命令**无关**,每 run 一个固定逃逸方向(map +y / −x / +y),速度 ~0.25-0.4 m/s;
- odom(SLAM)中途冻结或抖动 ±1cm;
- 严格 gate 诚实拒绝:`accepted_goals=0`(预到达 wp 已剔除),path 却有 1.4~2.9m(逃逸走出来的)。

## 二、BIN 飞控日志铁证(attempt-3 run `20260707T033010`)

1. t=13~24:GUIP 目标冻结原点,XKF1 估计跑离 2.8m —— **对固定目标持续背离=位置环正反馈**;
2. t=27 后:目标冻结 (−0.14,3.42),XKF1 加速跑飞至 (−33.7,+12.6),gap=34.8m(迷宫仅数米,**估计发散**);
3. `EK3_SRC1_YAW=1(罗盘)+ EK3_SRC1_POSXY=6(外部导航)`:yaw 参考=物理世界系,位置参考=SLAM map 系,**差固定偏角 δ**;
4. t=23.7 "in-flight yaw alignment"(运动使 δ 可见,EKF 强行重排)→ t=47.2 "**stopped aiding**"(拒绝外部导航)→ t=48.1 "**EKF variance: position lost**"。

结论:**上游集成缺陷——external_nav 把 SLAM map 系位置直接喂 AP,而 AP yaw 参考是罗盘世界系;静止无感,一动即发散**。这同时解释 frontier_lite 基线 path 0.43~3.80m 的巨大方差(每 run δ 不同→逃逸速度不同)。

## 三、修复链(clean 分支,PR 素材)

| # | 修复 | 文件 | 验证 |
|---|---|---|---|
| 1 | `EK3_SRC1_YAW 1→6`(yaw 与位置同源=外部导航) | `docker/profiles/navlab-sitl-external-nav.parm`(**真源头**;模板只是测试 fixture——第四跑教训:只改模板不生效,BIN 实测 YAW 仍=1) | 第五跑 BIN:YAW=6 生效 |
| 2 | `COMPASS_USE/USE2/USE3 → 0`(消除罗盘世界系参照;室内外部导航标准配置) | 同上 + fixture 同步 | 第五跑 BIN:全 0 生效 |
| 3 | `--no-align-yaw-to-fcu`(sender argparse 默认 True=把 FCU yaw 喂回自己,**yaw 循环自证**;第五跑日志实锤 `align_yaw_to_fcu=True` 删 flag 无效,须显式 no-) | `runtime_specs.go` + spec 测试 | **第六跑生效:EKF 不再发散**(漂移 0.25-0.4→0.03 m/s,无 stopped aiding/position lost) |

go build/vet/test 全绿(每步)。

## 四、第五跑(修复1+2后)结果

- 参数生效(BIN:YAW=6,COMPASS 全 0),EKF "yaw aligned"(非 MAG0);
- 但 align_yaw_to_fcu 仍 True(修复3未生效)→ yaw 无绝对参考 → t=53.1 stopped aiding → t=54.0 position lost → **EKF Failsafe 强制 Land**;
- 适配器 Rpairs=0:`/navlab/fcu/local_position_pose` 在 EKF 混乱期冻结(cal run 同款),Procrustes 无数据。

## 四·5 第六/七跑(修复 1+2+3 全生效后)

- **EKF 发散消失**:第六跑漂移仅 ~0.03 m/s;第七跑 lpp 数据流畅(Procrustes 396 对),
  **R_align 稳定收敛 = 旋转 −87°(det=+1)**——修复后系统的真实 map↔AP 映射;
- 新卡点=纯控制整定:fcu"胡萝卜"位置目标恒在 0.16m 前方,近距越过 wp,
  ~0.3m/s 追赶 + 0.15m 到达圈 → **0.5m 极限环绕 wp 打圈**(第七跑 odom 实测),
  accepted_goals 仍 0;
- 第八跑对策:目标不得越过 wp(近距按比例减速 forward=min(0.08, 0.4·dist))。

## 五、适配器侧演进(integration/ros1_bridge/trajectory_to_intent_stage4.py)

- v1 固定轴换 AXIS_SWAP:5a-1 证伪(map↔NED 偏角 per-run 不定);
- v2 运动响应 EMA 闭环:5a-2 证伪(2~3s 响应滞后×增益=延迟失稳,θ̂ 发散);
- v3 双坐标系同步观测 Procrustes(零滞后)+ yaw_rate 恒 0(旋转是 SLAM 失锁根因)+ slam_frozen 安全 blocker + 诚实 wp_done(预到达剔除)+ 严格五条件 ok 闩锁 + 混流闩锁:**逻辑已验证诚实**(三跑均正确拒绝),等 EKF 修复后复跑。

## 六、坐标系语义(Stage5cal 历史结论;当前实现见订正)

> **2026-08-24 订正:**下述“NED 直通”描述对应当时 controller。当前
> fcu_controller 已把 intent 定义为机体系 FRD,并按 FCU yaw 旋到 LOCAL_NED。
> 第四次 M5 run MCAP 已实证旧结论不能继续指导当前 adapter。
> yaw freshness 必须由 `/mavlink_external_nav/status.fcu_attitude_age_ms` 证明;
> `local_position_pose` 会在 LOCAL_POSITION 更新时重复最后一次 yaw,不能单独作新鲜度证据。

- **历史实现:**fcu MAVLink 主路曾把 intent (x,y) 不经旋转直接作 NED 位置目标;
- "胡萝卜"机制:实际速度 ~0.3 m/s 由 AP 位置控制器增益决定,**与命令幅值无关**,hold 刹车滑行 0.5~1m(上游语义问题,PR 议题);
- `ned_to_gazebo_pose` xy 恒等(只翻 z)——lpp xy=裸 NED。
