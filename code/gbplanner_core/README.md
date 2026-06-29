# gbplanner_core(P1 第一块)

**这是什么:** GBPlanner 算法的**纯 C++ 核心**,**不依赖任何机器人框架**(没有 ROS)。这样它既能配 ROS1 也能配 ROS2,是跨越"ROS1↔ROS2 错配"的关键设计。

**这一块实现了算法的"心脏":光线投射 + 体积增益。**

## 文件说明
| 文件 | 作用 |
|---|---|
| `include/gbplanner_core/types.hpp` | 基础类型:三维向量 `Vec3`、体素三态 `Unknown/Free/Occupied` |
| `voxel_map_interface.hpp` | **地图抽象接口**(算法只通过它查地图,不关心底层实现) |
| `traversability_interface.hpp` | 可通行性抽象接口(能否通行/路径是否碰撞) |
| `dense_voxel_map.hpp` | 一个简单稠密 3D 栅格地图,**离线测试用**(真实集成时换成 octomap/nvblox) |
| `ray_caster.hpp` | **核心**:`castRayUnknownCount`(一条射线数未知体素,遇障碍停)+ `computeVolumeGain`(向四周发射线累加可见未知体积) |
| `src/demo_main.cpp` | 离线演示:合成地图 → 算增益 → 验证"加墙后增益下降" |
| `test/test_gain.cpp` | 单元测试:验证射线遇障停、加墙增益下降等 |

## 怎么编译运行(在 WSL Ubuntu 内)
```bash
cd <本目录>
cmake -S . -B build
cmake --build build
./build/gbp_demo      # 看演示输出
ctest --test-dir build --output-on-failure   # 跑单元测试
```

## 设计意图(对应集成蓝图)
- **解耦**:算法核心 ←(抽象接口)→ 地图/传感器实现。换框架/换建图库时,只改实现,不动算法。
- **可离线验证**:不依赖仿真就能测算法逻辑对不对(这一步就是)。
- 后续会加:RRG 随机图采样、距离/转向惩罚、frontier 全局探索、ROS2 外壳节点。
