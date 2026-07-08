# oracle_cmp — ROS1 ↔ ROS2 voxblox 逐体素对拍 harness(M2 切片4)

> 目的:锤死"移植没改行为"。ROS1 侧 = GBPlanner 实际 pin 的 ntnu-arl/voxblox
> @ dev/noetic(gbplanner-ref 容器内 0ee88c2);ROS2 侧 = 本仓 vendored 移植版。

## 原理

1. `frames_common.py` — 确定性合成场景(房间+方柱,12 个环形位姿)。两侧跑的是
   **同一份文件**,payload 逐字节一致(位姿量化到 1/1024 防 noetic/jazzy libm
   1ulp 漂移;脚本自带 SHA 自证)。
2. `pub_ros1.py` / `pub_ros2.py` — 各自容器内喂 TF+PointCloud2,结束调 save_map。
   ⚠️ ROS2 订阅名是**私有名** `/voxblox_node/pointcloud`;ROS1 是公共名 `/pointcloud`。
3. `compare_layers.py` — 零依赖解析 .voxblox(varint 计数+定界 proto2;TSDF 体素
   = 3×uint32:distance/weight float 位模式+color),逐块逐体素比对。
   判据:块集合零差 + 观测体素集合零差(<0.1%)+ 距离场 RMS<1e-3、max<5e-2
   (线程数不可锁 → 容差=浮点合并次序噪声,非逐位)。

## 跑法(WSL)

```bash
bash run_oracle_ros1.sh simple   # -> ~/cmp_out/oracle_tsdf_simple.voxblox
bash run_port_ros2.sh  simple    # -> ~/cmp_out/port_tsdf_simple.voxblox
python3 compare_layers.py ~/cmp_out/oracle_tsdf_simple.voxblox ~/cmp_out/port_tsdf_simple.voxblox
```

method 参数:`simple`(主对拍,体素集合确定)/ `fast`(GBPlanner 实际积分器,
早终止有竞态 → 统计口径,阈值放宽)。

## 已定档结果(2026-07-08)

- **simple:PASS** — 46/46 块、35,323/35,323 观测体素零差、近表面 6,851/6,851、
  距离场 RMS=1.0e-4 max=0.010(噪声量级)。证据:
  [../../runbooks/ros2_port/m2_oracle_cmp_evidence.txt](../../runbooks/ros2_port/m2_oracle_cmp_evidence.txt)
- 对拍路上抓到真移植 bug:min_time 节流 1s 无操作(已修,见 evidence §)。
