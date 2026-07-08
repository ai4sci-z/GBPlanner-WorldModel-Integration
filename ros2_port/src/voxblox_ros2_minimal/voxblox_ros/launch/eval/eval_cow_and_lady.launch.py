"""
ROS2 launch file for Voxblox Cow and Lady evaluation.

This launch file starts the voxblox_eval node for evaluating reconstruction
quality against the Cow and Lady dataset ground truth.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for Cow and Lady evaluation."""

    # Declare launch arguments
    voxblox_file_path_arg = DeclareLaunchArgument(
        'voxblox_file_path',
        default_value='/Users/helen/data/lady_cow_dataset/voxblox/cow_and_lady_antigraze_0_10.vxblx',
        description='Path to the voxblox reconstruction file'
    )

    gt_file_path_arg = DeclareLaunchArgument(
        'gt_file_path',
        default_value='/Users/helen/data/lady_cow_dataset/lady_and_cow2.ply',
        description='Path to the ground truth point cloud file'
    )

    # Define the voxblox_eval node
    voxblox_eval_node = Node(
        package='voxblox_ros',
        executable='voxblox_eval',
        name='voxblox_eval',
        output='screen',
        arguments=['-alsologtostderr'],
        parameters=[{
            'color_mode': 'normals',
            'frame_id': 'world',
            'verbose': True,
            'visualize': True,
            'recolor_by_error': False,
            'voxblox_file_path': LaunchConfiguration('voxblox_file_path'),
            'gt_file_path': LaunchConfiguration('gt_file_path'),
        }],
    )

    return LaunchDescription([
        # Declare arguments
        voxblox_file_path_arg,
        gt_file_path_arg,
        # Launch nodes
        voxblox_eval_node,
    ])
