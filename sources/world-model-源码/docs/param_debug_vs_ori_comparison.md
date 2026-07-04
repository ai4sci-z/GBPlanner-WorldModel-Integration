# debug.param vs ori.param 参数差异比较

生成时间：2026-06-16

比较对象：

- `docs/ori.param`
- `docs/debug.param`

备注：`docs/scenarios/indoor/ori.param` 与 `docs/ori.param` 内容完全一致。

## 总览

`debug.param` 相比 `ori.param`：

- 新增参数：26 个
- 删除参数：8 个
- 共同参数但值不同：22 个

核心差异集中在四类：

1. GPS 被关闭或弱化。
2. VISO / ExternalNav 被打开。
3. EKF source set 2 被配置成 ExternalNav。
4. arming / GPS check / 脚本开关 / 传感器校准值发生变化。

## 关键结论

`debug.param` 不是简单的调试日志参数，它明显把系统往 ExternalNav/VISO 方向推：

- `GPS1_TYPE: 1 -> 0`，关闭 GPS1。
- `VISO_TYPE: 0 -> 1`，启用视觉/外部里程计输入。
- `EK3_SRC2_POSXY/VELXY/VELZ/YAW: 0 -> 6`，把 EKF source set 2 的水平位置、速度和 yaw 都指向 ExternalNav。
- `EK3_SRC2_POSZ: 1 -> 2`，高度来源从 Baro 类默认配置改成另一路高度来源。
- `EK3_GPS_CHECK: 31 -> 0`，关闭 GPS 检查。
- `ARMING_CHECK: 1 -> 1043902`，arming check 集合被大幅改动，不是简单全开或全关。

但需要注意：`debug.param` 的 `EK3_SRC1_*` 仍然是 GPS/compass 风格：

| 参数 | ori | debug |
| --- | --- | --- |
| `EK3_SRC1_POSXY` | `3` | `3` |
| `EK3_SRC1_POSZ` | `1` | `1` |
| `EK3_SRC1_VELXY` | `3` | `3` |
| `EK3_SRC1_VELZ` | `3` | `3` |
| `EK3_SRC1_YAW` | `1` | `1` |

也就是说，`debug.param` 是“保留 source set 1，新增/启用 source set 2 ExternalNav”的形态，不是当前 NavLab `navlab-sitl-external-nav.parm` 那种直接把 source set 1 配成 ExternalNav 的形态。

## ExternalNav / EKF 相关差异

| 参数 | ori | debug | 含义 |
| --- | --- | --- | --- |
| `VISO_TYPE` | `0` | `1` | debug 启用 VISO / ExternalNav 输入。 |
| `VISO_DELAY_MS` | 不存在 | `10` | debug 设置 VISO 延迟。 |
| `VISO_ORIENT` | 不存在 | `0` | debug 设置 VISO 坐标朝向。 |
| `VISO_POS_M_NSE` | 不存在 | `0.20000000298023224` | debug 设置位置噪声。 |
| `VISO_POS_X` | 不存在 | `0` | VISO 外参 X。 |
| `VISO_POS_Y` | 不存在 | `0` | VISO 外参 Y。 |
| `VISO_POS_Z` | 不存在 | `0` | VISO 外参 Z。 |
| `VISO_QUAL_MIN` | 不存在 | `0` | debug 不要求最小 VISO quality。 |
| `VISO_SCALE` | 不存在 | `1` | VISO scale。 |
| `VISO_VEL_M_NSE` | 不存在 | `0.10000000149011612` | 速度噪声。 |
| `VISO_YAW_M_NSE` | 不存在 | `0.20000000298023224` | yaw 噪声。 |
| `EK3_SRC2_POSXY` | `0` | `6` | debug source set 2 水平位置使用 ExternalNav。 |
| `EK3_SRC2_POSZ` | `1` | `2` | debug source set 2 高度源不同于 ori。 |
| `EK3_SRC2_VELXY` | `0` | `6` | debug source set 2 水平速度使用 ExternalNav。 |
| `EK3_SRC2_VELZ` | `0` | `6` | debug source set 2 垂直速度使用 ExternalNav。 |
| `EK3_SRC2_YAW` | `0` | `6` | debug source set 2 yaw 使用 ExternalNav。 |
| `EK3_SRC_OPTIONS` | `1` | `0` | debug 关闭了原来的 source option。 |

对当前问题的含义：

- 如果 FCU 没切到 source set 2，debug 的 ExternalNav source set 2 可能不会成为主 EKF 输入。
- 如果只加载 debug 里的 `EK3_SRC2_*`，但没有明确 source set 切换策略，可能出现“VISO 在发，但 EKF 主源仍不按预期工作”的状态。
- 当前 NavLab runtime 里 `navlab-sitl-external-nav.parm` 是把 `EK3_SRC1_*` 直接设为 ExternalNav，这和 `debug.param` 的策略不同，需要单独确认哪条路线更适合 SITL hover。

## GPS / Home / Origin 相关差异

| 参数 | ori | debug | 含义 |
| --- | --- | --- | --- |
| `GPS1_TYPE` | `1` | `0` | debug 关闭 GPS1。 |
| `GPS1_COM_PORT` | `1` | 不存在 | debug 删除 GPS1 串口配置。 |
| `GPS1_DELAY_MS` | `0` | 不存在 | debug 删除 GPS1 delay。 |
| `GPS1_GNSS_MODE` | `0` | 不存在 | debug 删除 GPS1 GNSS mode。 |
| `GPS1_MB_TYPE` | `0` | 不存在 | debug 删除 moving baseline 配置。 |
| `GPS1_POS_X` | `0` | 不存在 | debug 删除 GPS1 外参 X。 |
| `GPS1_POS_Y` | `0` | 不存在 | debug 删除 GPS1 外参 Y。 |
| `GPS1_POS_Z` | `0` | 不存在 | debug 删除 GPS1 外参 Z。 |
| `GPS1_RATE_MS` | `200` | 不存在 | debug 删除 GPS1 rate。 |
| `EK3_GPS_CHECK` | `31` | `0` | debug 关闭 EKF GPS check。 |
| `AHRS_ORIG_LAT` | 不存在 | `0` | debug 显式写入 AHRS origin。 |
| `AHRS_ORIG_LON` | 不存在 | `0` | debug 显式写入 AHRS origin。 |
| `AHRS_ORIG_ALT` | 不存在 | `0` | debug 显式写入 AHRS origin。 |

对当前问题的含义：

- debug 明确不依赖 GPS。
- 但是 `AHRS_ORIG_* = 0` 只是参数里存在 origin 字段，不等于运行时 home/global origin 一定被 FCU 接受。
- 当前 hover run 里出现 `Arm: AHRS: waiting for home`，所以仍需验证 MAVLink `SET_GPS_GLOBAL_ORIGIN` / `SET_HOME_POSITION` 是否被接受，而不是只看 param 是否存在。

## Arming / Prearm 相关差异

| 参数 | ori | debug | 含义 |
| --- | --- | --- | --- |
| `ARMING_CHECK` | `1` | `1043902` | debug 使用特定 bitmask，不是简单默认值。 |
| `EK3_GPS_CHECK` | `31` | `0` | debug 放宽 GPS 检查。 |

对当前问题的含义：

- 最新 hover run 的 FCU 报错是 `Need Alt Estimate`、`Accels inconsistent`、`EKF attitude is bad`、`AHRS: waiting for home`。
- 这些不是单纯 `GPS1_TYPE=0` 能解决的。
- `ARMING_CHECK=1043902` 可能是在保留部分安全检查，同时绕开部分 GPS/定位检查；需要解码 bitmask 后再决定是否采用，不能盲目照搬。

## 传感器校准 / 状态类差异

| 参数 | ori | debug | 含义 |
| --- | --- | --- | --- |
| `BARO1_GND_PRESS` | `100013.7578125` | `100271.125` | 气压地面基准变化，可能来自不同运行时校准。 |
| `INS_GYR1_CALTEMP` | `13.5` | `16.9375` | 陀螺校准温度变化。 |
| `INS_GYR2OFFS_X` | `0.004808139055967331` | `0.002947807079181075` | IMU offset 变化。 |
| `INS_GYR2OFFS_Y` | `0.0016641560941934586` | `0.003097717184573412` | IMU offset 变化。 |
| `INS_GYR2OFFS_Z` | `0.000058367917517898604` | `0.0015389827312901616` | IMU offset 变化。 |
| `INS_GYR2_CALTEMP` | `14.975000381469727` | `19.076000213623047` | 陀螺校准温度变化。 |
| `INS_GYROFFS_X` | `0.0024222121573984623` | `0.0027098464779555798` | IMU offset 变化。 |
| `INS_GYROFFS_Y` | `-0.00475391885265708` | `-0.00429177051410079` | IMU offset 变化。 |
| `INS_GYROFFS_Z` | `-0.0010626844596117735` | `0.0006311320466920733` | IMU offset 变化。 |
| `STAT_BOOTCNT` | `116` | `149` | 运行状态计数，通常不应作为配置迁移依据。 |
| `STAT_RUNTIME` | `192670` | `233742` | 运行状态计数，通常不应作为配置迁移依据。 |

这类参数大多是状态/校准结果，不建议直接作为设计配置照搬，除非目标就是复现同一块硬件/同一份 EEPROM 状态。

## Scripting 相关差异

| 参数 | ori | debug |
| --- | --- | --- |
| `SCR_ENABLE` | `0` | `1` |
| `SCR_DEBUG_OPTS` | 不存在 | `0` |
| `SCR_DIR_DISABLE` | 不存在 | `0` |
| `SCR_HEAP_SIZE` | 不存在 | `204800` |
| `SCR_LD_CHECKSUM` | 不存在 | `-1` |
| `SCR_RUN_CHECKSUM` | 不存在 | `-1` |
| `SCR_THD_PRIORITY` | 不存在 | `0` |
| `SCR_USER1` - `SCR_USER6` | 不存在 | `0` |
| `SCR_VM_I_COUNT` | 不存在 | `10000` |

debug 启用了 Lua scripting。当前 NavLab sim hover 问题没有证据显示依赖 Lua script，所以这部分先记录，不应作为第一优先级。

## 完整值变化列表

| 参数 | ori | debug |
| --- | --- | --- |
| `ARMING_CHECK` | `1` | `1043902` |
| `BARO1_GND_PRESS` | `100013.7578125` | `100271.125` |
| `EK3_GPS_CHECK` | `31` | `0` |
| `EK3_SRC2_POSXY` | `0` | `6` |
| `EK3_SRC2_POSZ` | `1` | `2` |
| `EK3_SRC2_VELXY` | `0` | `6` |
| `EK3_SRC2_VELZ` | `0` | `6` |
| `EK3_SRC2_YAW` | `0` | `6` |
| `EK3_SRC_OPTIONS` | `1` | `0` |
| `GPS1_TYPE` | `1` | `0` |
| `INS_GYR1_CALTEMP` | `13.5` | `16.9375` |
| `INS_GYR2OFFS_X` | `0.004808139055967331` | `0.002947807079181075` |
| `INS_GYR2OFFS_Y` | `0.0016641560941934586` | `0.003097717184573412` |
| `INS_GYR2OFFS_Z` | `0.000058367917517898604` | `0.0015389827312901616` |
| `INS_GYR2_CALTEMP` | `14.975000381469727` | `19.076000213623047` |
| `INS_GYROFFS_X` | `0.0024222121573984623` | `0.0027098464779555798` |
| `INS_GYROFFS_Y` | `-0.00475391885265708` | `-0.00429177051410079` |
| `INS_GYROFFS_Z` | `-0.0010626844596117735` | `0.0006311320466920733` |
| `SCR_ENABLE` | `0` | `1` |
| `STAT_BOOTCNT` | `116` | `149` |
| `STAT_RUNTIME` | `192670` | `233742` |
| `VISO_TYPE` | `0` | `1` |

## 新增参数列表

`debug.param` 中存在、`ori.param` 中不存在：

- `AHRS_ORIG_ALT`
- `AHRS_ORIG_LAT`
- `AHRS_ORIG_LON`
- `SCR_DEBUG_OPTS`
- `SCR_DIR_DISABLE`
- `SCR_HEAP_SIZE`
- `SCR_LD_CHECKSUM`
- `SCR_RUN_CHECKSUM`
- `SCR_THD_PRIORITY`
- `SCR_USER1`
- `SCR_USER2`
- `SCR_USER3`
- `SCR_USER4`
- `SCR_USER5`
- `SCR_USER6`
- `SCR_VM_I_COUNT`
- `VISO_DELAY_MS`
- `VISO_ORIENT`
- `VISO_POS_M_NSE`
- `VISO_POS_X`
- `VISO_POS_Y`
- `VISO_POS_Z`
- `VISO_QUAL_MIN`
- `VISO_SCALE`
- `VISO_VEL_M_NSE`
- `VISO_YAW_M_NSE`

## 删除参数列表

`ori.param` 中存在、`debug.param` 中不存在：

- `GPS1_COM_PORT`
- `GPS1_DELAY_MS`
- `GPS1_GNSS_MODE`
- `GPS1_MB_TYPE`
- `GPS1_POS_X`
- `GPS1_POS_Y`
- `GPS1_POS_Z`
- `GPS1_RATE_MS`

## 后续建议

下一步不要直接全量套用 `debug.param`。建议只提取候选 ExternalNav 相关参数做小步验证：

1. 明确选择 EKF source set 策略：继续使用 `EK3_SRC1_* = ExternalNav`，还是复刻 debug 的 `EK3_SRC2_* = ExternalNav`。
2. 解码 `ARMING_CHECK=1043902`，确认它具体关闭/保留了哪些检查。
3. 单独验证 home/origin 命令是否被 FCU 接受，因为当前 blocker 里有 `AHRS: waiting for home`。
4. 把 VISO 参数和当前 `navlab-sitl-external-nav.parm` 对齐，尤其是 `VISO_DELAY_MS`、`VISO_QUAL_MIN`、`VISO_*_NSE`。
