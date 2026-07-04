from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params = PathJoinSubstitution([FindPackageShare("navlab_fake_odom"), "config", "navlab_fake_odom.params.yaml"])

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "mode",
                default_value="static",
                description="Fake odom mode: static, line, or yaw",
            ),
            DeclareLaunchArgument(
                "publish_rate_hz",
                default_value="20.0",
                description="Fake odom publish rate",
            ),
            Node(
                package="navlab_fake_odom",
                executable="navlab_fake_odom_node",
                name="navlab_fake_odom_node",
                output="screen",
                parameters=[
                    params,
                    {
                        "mode": LaunchConfiguration("mode"),
                        "publish_rate_hz": LaunchConfiguration("publish_rate_hz"),
                    },
                ],
            ),
        ]
    )
