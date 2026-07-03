# official-baseline 薄层补丁(坑#9 + #11)

humble 的 sdformat_urdf 不认 `gpu_lidar` → RSP 崩 → 机器人从未生成(坑#9);
补丁展平用的 `gz sdf -p` 输出 SDF 1.11,humble libsdformat 只认 ≤1.9(坑#11)。

`robot.launch.py` 三针补丁:
1. spawn 改 `-file` 直读完整 SDF(不再依赖 RSP 话题);
2. RSP 描述先 `gz sdf -p` 展平 include 再剥 `<sensor>` 块;
3. 展平输出 `<sdf version>` 重写为 1.9。

重建(秒级,在本目录):
```bash
docker build -t navlab/official-baseline:humble-latest .
```
验证:`docker run --rm navlab/official-baseline:humble-latest grep -c navlab-humble-fix \
/opt/navlab_official_ws/install/ardupilot_gz_bringup/share/ardupilot_gz_bringup/launch/robots/robot.launch.py` 应为 4。
