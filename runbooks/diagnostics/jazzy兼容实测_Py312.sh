#!/bin/bash
# 在真 jazzy(ros:jazzy-ros-base,Python3.12)上实测我给 world-model 的改动是否兼容
set -u
PR=/mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/world-model-PR
docker run --rm \
  -v /home/ai4s/ws/world-model:/ws \
  -v "$PR:/pr" \
  ros:jazzy-ros-base bash -c '
set -e
source /opt/ros/jazzy/setup.bash
echo "=== 环境 ==="; python3 --version; echo "ROS_DISTRO=$ROS_DISTRO"
echo
echo "=== 1. tomllib 修改对 jazzy 的影响(jazzy=Py3.12 有原生 tomllib) ==="
python3 - <<PYEOF
try:
    import tomllib
    print("[OK] jazzy: import tomllib 原生成功 → except(import tomli) 分支根本不执行 → 我的改动对 jazzy 零影响")
except ModuleNotFoundError:
    import tomli as tomllib  # noqa
    print("[!!] jazzy 竟走了 tomli 分支(不应发生)")
PYEOF
echo
echo "=== 2. 我改的 toml_values.py 在 jazzy 能否 import(走原生 tomllib) ==="
cd /ws && python3 -c "import ast; ast.parse(open(\"navlab/common/toml_values.py\").read()); print(\"[OK] toml_values.py 语法在 Py3.12 合法\")"
cd /ws && python3 -c "
import sys; sys.path.insert(0,\".\")
import navlab.common.toml_values as m
print(\"[OK] jazzy: import navlab.common.toml_values 成功(用原生 tomllib,无需 tomli)\")
" 2>&1 | tail -1
echo
echo "=== 3. gbplanner_gain 渲染脚本在 Py3.12 py_compile ==="
python3 -m py_compile /pr/rendered_gbplanner_gain.py && echo "[OK] gbplanner_gain py_compile 通过(jazzy Py3.12)"
python3 -m py_compile /pr/rendered_frontier_lite.py && echo "[OK] frontier_lite py_compile 通过(jazzy Py3.12)"
echo
echo "=== 4. gbplanner_gain 依赖的 ROS2 消息在 jazzy 可用 ==="
python3 -c "import rclpy; from nav_msgs.msg import OccupancyGrid, Odometry; from std_msgs.msg import String; print(\"[OK] jazzy: rclpy + nav_msgs(OccupancyGrid/Odometry) + std_msgs(String) 全部可 import\")"
echo
echo "=== ALL_JAZZY_CHECKS_DONE ==="
'
