from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("navlab_cartographer_adapter")
    params_file = PathJoinSubstitution([pkg_share, "config", "navlab_cartographer_adapter.params.yaml"])
    config_dir = PathJoinSubstitution([pkg_share, "config"])

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "launch_cartographer_backend",
                default_value="false",
                description="Launch cartographer_ros backend nodes",
            ),
            DeclareLaunchArgument(
                "publish_placeholder_odom",
                default_value="false",
                description="Fallback placeholder odometry for smoke tests only",
            ),
            DeclareLaunchArgument(
                "configuration_directory",
                default_value=config_dir,
                description="Cartographer Lua configuration directory",
            ),
            DeclareLaunchArgument(
                "configuration_basename",
                default_value="navlab_cartographer_2d_real.lua",
                description="Cartographer Lua configuration file",
            ),
            DeclareLaunchArgument(
                "scan_topic",
                default_value="/scan",
                description="LaserScan topic consumed by the SLAM backend",
            ),
            DeclareLaunchArgument(
                "imu_topic",
                default_value="/imu",
                description="IMU topic consumed by the SLAM backend",
            ),
            DeclareLaunchArgument(
                "cartographer_odometry_topic",
                default_value="/cartographer/odometry_input",
                description=(
                    "Explicit Cartographer odometry input. Leave this off /odometry; "
                    "/odometry is diagnostic truth in simulation."
                ),
            ),
            DeclareLaunchArgument(
                "cartographer_tf_topic",
                default_value="/navlab/slam/tf",
                description=(
                    "Isolated Cartographer dynamic TF topic. Keeps SLAM TF separate from AP/Gazebo diagnostic /tf."
                ),
            ),
            DeclareLaunchArgument(
                "publish_global_tf",
                default_value="false",
                description=(
                    "Publish accepted SLAM map->base_link transforms to global /tf "
                    "for consumers and replay visualization."
                ),
            ),
            DeclareLaunchArgument(
                "global_tf_topic",
                default_value="/tf",
                description="Global TF topic used only for accepted SLAM output transforms.",
            ),
            DeclareLaunchArgument(
                "cached_odom_publish_rate_hz",
                default_value="10.0",
                description=(
                    "Republish accepted fresh SLAM odometry at this rate; stale or rejected TF is not republished."
                ),
            ),
            DeclareLaunchArgument(
                "odom_source_mode",
                default_value="slam_tf",
                description=(
                    "SLAM adapter odom source: slam_tf reads Cartographer map->base_link TF; tf reads odom->base_link"
                ),
            ),
            DeclareLaunchArgument(
                "odom_topic",
                default_value="/odom",
                description="Odometry topic emitted by the SLAM adapter",
            ),
            DeclareLaunchArgument(
                "status_topic",
                default_value="/navlab/slam/status",
                description="Structured SLAM status topic",
            ),
            DeclareLaunchArgument(
                "map_frame",
                default_value="map",
                description="SLAM map frame",
            ),
            DeclareLaunchArgument(
                "odom_frame",
                default_value="odom",
                description="Legacy odom frame used only by legacy TF mode",
            ),
            DeclareLaunchArgument(
                "laser_frame",
                default_value="laser_frame",
                description="LiDAR frame used by static TF publisher",
            ),
            DeclareLaunchArgument("laser_x", default_value="0", description="LiDAR static TF x offset"),
            DeclareLaunchArgument("laser_y", default_value="0", description="LiDAR static TF y offset"),
            DeclareLaunchArgument("laser_z", default_value="0", description="LiDAR static TF z offset"),
            DeclareLaunchArgument("laser_roll", default_value="0", description="LiDAR static TF roll"),
            DeclareLaunchArgument("laser_pitch", default_value="0", description="LiDAR static TF pitch"),
            DeclareLaunchArgument("laser_yaw", default_value="0", description="LiDAR static TF yaw"),
            DeclareLaunchArgument(
                "imu_frame",
                default_value="imu_link",
                description="IMU frame used by static TF publisher",
            ),
            DeclareLaunchArgument(
                "base_frame",
                default_value="base_link",
                description="Base frame used by static TF publishers",
            ),
            DeclareLaunchArgument(
                "resolution",
                default_value="0.05",
                description="Occupancy grid resolution",
            ),
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="base_to_laser_static_tf",
                output="screen",
                arguments=[
                    "--x",
                    LaunchConfiguration("laser_x"),
                    "--y",
                    LaunchConfiguration("laser_y"),
                    "--z",
                    LaunchConfiguration("laser_z"),
                    "--roll",
                    LaunchConfiguration("laser_roll"),
                    "--pitch",
                    LaunchConfiguration("laser_pitch"),
                    "--yaw",
                    LaunchConfiguration("laser_yaw"),
                    "--frame-id",
                    LaunchConfiguration("base_frame"),
                    "--child-frame-id",
                    LaunchConfiguration("laser_frame"),
                ],
            ),
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="base_to_imu_static_tf",
                output="screen",
                arguments=[
                    "--x",
                    "0",
                    "--y",
                    "0",
                    "--z",
                    "0",
                    "--roll",
                    "0",
                    "--pitch",
                    "0",
                    "--yaw",
                    "0",
                    "--frame-id",
                    LaunchConfiguration("base_frame"),
                    "--child-frame-id",
                    LaunchConfiguration("imu_frame"),
                ],
            ),
            Node(
                package="navlab_cartographer_adapter",
                executable="navlab_cartographer_adapter_node",
                name="navlab_cartographer_adapter_node",
                output="screen",
                parameters=[
                    params_file,
                    {
                        "publish_placeholder_odom": LaunchConfiguration("publish_placeholder_odom"),
                        "odom_source_mode": LaunchConfiguration("odom_source_mode"),
                        "map_frame_id": LaunchConfiguration("map_frame"),
                        "odom_frame_id": LaunchConfiguration("odom_frame"),
                        "base_frame_id": LaunchConfiguration("base_frame"),
                        "tf_topic": LaunchConfiguration("cartographer_tf_topic"),
                        "publish_global_tf": LaunchConfiguration("publish_global_tf"),
                        "global_tf_topic": LaunchConfiguration("global_tf_topic"),
                        "cached_odom_publish_rate_hz": LaunchConfiguration("cached_odom_publish_rate_hz"),
                        "scan_topic": LaunchConfiguration("scan_topic"),
                        "imu_topic": LaunchConfiguration("imu_topic"),
                        "odom_topic": LaunchConfiguration("odom_topic"),
                        "status_topic": LaunchConfiguration("status_topic"),
                    },
                ],
            ),
            Node(
                condition=IfCondition(LaunchConfiguration("launch_cartographer_backend")),
                package="cartographer_ros",
                executable="cartographer_node",
                name="cartographer_node",
                output="screen",
                arguments=[
                    "-configuration_directory",
                    LaunchConfiguration("configuration_directory"),
                    "-configuration_basename",
                    LaunchConfiguration("configuration_basename"),
                ],
                remappings=[
                    ("scan", LaunchConfiguration("scan_topic")),
                    ("imu", LaunchConfiguration("imu_topic")),
                    ("/odom", LaunchConfiguration("cartographer_odometry_topic")),
                    ("/tf", LaunchConfiguration("cartographer_tf_topic")),
                ],
            ),
            Node(
                condition=IfCondition(LaunchConfiguration("launch_cartographer_backend")),
                package="cartographer_ros",
                executable="cartographer_occupancy_grid_node",
                name="cartographer_occupancy_grid_node",
                output="screen",
                arguments=[
                    "-resolution",
                    LaunchConfiguration("resolution"),
                ],
            ),
        ]
    )
