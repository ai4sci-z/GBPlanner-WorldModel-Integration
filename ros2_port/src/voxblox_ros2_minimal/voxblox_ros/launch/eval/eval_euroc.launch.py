"""
ROS2 launch file for Voxblox evaluation on EuRoC dataset.

This launch file evaluates a Voxblox mesh against ground truth data
from the EuRoC dataset. It loads transformation parameters from a
YAML configuration file and allows customization of input file paths.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Generate launch description for Voxblox EuRoC evaluation."""

    # Declare launch arguments
    voxblox_file_path_arg = DeclareLaunchArgument(
        'voxblox_file_path',
        default_value='/Users/helen/data/euroc_datasets/voxblox/v1/const_0_05.vxblx',
        description='Path to the Voxblox mesh file to evaluate'
    )

    gt_file_path_arg = DeclareLaunchArgument(
        'gt_file_path',
        default_value='/Users/helen/data/euroc_datasets/v1_gt_subsampled.ply',
        description='Path to the ground truth PLY file'
    )

    # Get launch configurations
    voxblox_file_path = LaunchConfiguration('voxblox_file_path')
    gt_file_path = LaunchConfiguration('gt_file_path')

    # Path to the EuRoC dataset configuration file
    euroc_config_file = PathJoinSubstitution([
        FindPackageShare('voxblox_ros'),
        'cfg',
        'euroc_dataset.yaml'
    ])

    # Voxblox evaluation node
    voxblox_eval_node = Node(
        package='voxblox_ros',
        executable='voxblox_eval',
        name='voxblox_eval',
        output='screen',
        arguments=['-alsologtostderr'],
        parameters=[
            euroc_config_file,  # Load parameters from YAML first
            {
                'color_mode': 'normals',
                'frame_id': 'world',
                'verbose': True,
                'visualize': False,
                'recolor_by_error': False,
                'voxblox_file_path': voxblox_file_path,
                'gt_file_path': gt_file_path,
            }
        ],
        # In ROS2, clear_params is not needed as each node starts fresh
    )

    return LaunchDescription([
        # Declare arguments first
        voxblox_file_path_arg,
        gt_file_path_arg,
        # Launch the evaluation node
        voxblox_eval_node,
    ])
