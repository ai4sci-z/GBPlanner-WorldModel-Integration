"""
ROS2 launch file for Voxblox KITTI evaluation.

This launch file starts the voxblox_eval node for evaluating reconstruction
quality against KITTI ground truth point clouds.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for KITTI evaluation."""

    # Declare launch arguments
    voxblox_file_path_arg = DeclareLaunchArgument(
        'voxblox_file_path',
        default_value='/Users/helen/data/kitti/voxblox/const_0_50.vxblx',
        description='Path to the voxblox reconstruction file'
    )

    gt_file_path_arg = DeclareLaunchArgument(
        'gt_file_path',
        default_value='/Users/helen/data/kitti/voxblox/velodyne_ptcloud_0_10_subsampled.ply',
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
            'color_mode': 'colors',
            'frame_id': 'world',
            'verbose': True,
            'visualize': False,
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
