#!/usr/bin/env python3
# 3D lidar 净增量补丁(clean 分支):
#  A) rangefinder_down_overlay.sdf.tmpl 尾部加 lidar3d link+sensor+joint
#     (独立 topic /lidar3d,不动 /lidar 与 x2/SLAM 链;参数对齐官方 lidar_3d,
#      降载:垂直 30 层/5Hz,llvmpipe 软渲染可承受)
#  B) bridge_override.yaml.tmpl 加 /lidar3d/points -> wm/cloud3d(PointCloud2)
# 幂等。
import io, sys

CLEAN = "/home/ai4s/ws-clean/world-model"
ok = True

def patch(path, old, new, tag):
    global ok
    src = io.open(path, encoding="utf-8").read()
    if "lidar3d" in src:
        print("ALREADY:", tag)
        return
    if old not in src:
        print("PATTERN_NOT_FOUND:", tag)
        ok = False
        return
    io.open(path, "w", encoding="utf-8", newline="\n").write(src.replace(old, new, 1))
    print("PATCHED:", tag)

# A) overlay 模板加 3D lidar(net-new sensor;/lidar 保持 2D 原样)
f = CLEAN + "/orchestration/sim/internal/tasks/helpers/templates/sdf/rangefinder_down_overlay.sdf.tmpl"
OLD_TAIL = (
    "    <joint name=\"rangefinder_down_joint\" type=\"fixed\">\n"
    "      <parent>base_link</parent>\n"
    "      <child>rangefinder_down_link</child>\n"
    "    </joint>\n"
)
NEW_TAIL = OLD_TAIL + """
    <!-- NavLab overlay: net-new 3D lidar for volumetric planners (e.g. GBPlanner).
         The official iris_with_lidar 3D unit is downgraded to lidar_2d for the X2
         2D SLAM chain (navlab_models.go); this ADDITIONAL sensor restores a true
         3D point source on its own topic without touching /lidar or the X2/SLAM
         pipeline. Params mirror ardupilot_gz lidar_3d (360x60 +/-30deg) with a
         reduced vertical count and rate to stay light under software rendering. -->
    <link name="lidar3d_link">
      <pose relative_to="base_link">0 0 0.10 0 0 0</pose>
      <inertial>
        <mass>0.05</mass>
        <inertia>
          <ixx>0.00004</ixx>
          <ixy>0</ixy>
          <ixz>0</ixz>
          <iyy>0.00004</iyy>
          <iyz>0</iyz>
          <izz>0.00004</izz>
        </inertia>
      </inertial>
      <sensor name="lidar3d" type="gpu_lidar">
        <gz_frame_id>lidar3d_frame</gz_frame_id>
        <pose>0 0 0 0 0 0</pose>
        <topic>/lidar3d</topic>
        <always_on>true</always_on>
        <update_rate>5</update_rate>
        <ray>
          <scan>
            <horizontal>
              <samples>360</samples>
              <resolution>1</resolution>
              <min_angle>-3.14159265</min_angle>
              <max_angle>3.14159265</max_angle>
            </horizontal>
            <vertical>
              <samples>30</samples>
              <resolution>1</resolution>
              <min_angle>-0.523599</min_angle>
              <max_angle>0.523599</max_angle>
            </vertical>
          </scan>
          <range>
            <min>0.3</min>
            <max>10</max>
            <resolution>0.05</resolution>
          </range>
        </ray>
        <visualize>false</visualize>
      </sensor>
    </link>

    <joint name="lidar3d_joint" type="fixed">
      <parent>base_link</parent>
      <child>lidar3d_link</child>
    </joint>
"""
patch(f, OLD_TAIL, NEW_TAIL, "A overlay lidar3d")

# B) bridge 模板加 points 桥
f = CLEAN + "/orchestration/sim/internal/tasks/helpers/templates/yaml/bridge_override.yaml.tmpl"
OLD_B = (
    "- ros_topic_name: \"cloud_in\"\n"
    "  gz_topic_name: \"/lidar/points\"\n"
    "  ros_type_name: \"sensor_msgs/msg/PointCloud2\"\n"
    "  gz_type_name: \"gz.msgs.PointCloudPacked\"\n"
    "  direction: GZ_TO_ROS\n"
)
NEW_B = OLD_B + (
    "- ros_topic_name: \"wm/cloud3d\"\n"
    "  gz_topic_name: \"/lidar3d/points\"\n"
    "  ros_type_name: \"sensor_msgs/msg/PointCloud2\"\n"
    "  gz_type_name: \"gz.msgs.PointCloudPacked\"\n"
    "  direction: GZ_TO_ROS\n"
)
patch(f, OLD_B, NEW_B, "B bridge wm/cloud3d")

sys.exit(0 if ok else 2)
