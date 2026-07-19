# 宿主 ROS2 环境 pins(方案 A,负责人批准 2026-07-20;governance/README §2 同族)
# 回滚:sudo apt-get remove --purge 'ros-jazzy-*' && sudo rm /etc/apt/sources.list.d/ros2.list
# 激活:source /opt/ros/jazzy/setup.bash(run_batch 操作员在 A/A 前须 source;sidecar 继承 env)

ros-jazzy-rclpy 7.1.11-1noble.20260615.133206
ros-jazzy-rmw-cyclonedds-cpp 2.2.3-1noble.20260615.123728
ros-jazzy-ros-base 0.11.0-1noble.20260616.084325
ros-jazzy-std-msgs 5.3.8-1noble.20260615.102930

验证:source /opt/ros/jazzy/setup.bash && python3 -c 'import rclpy; from std_msgs.msg import String'  → rc=0(2026-07-20 实测)
