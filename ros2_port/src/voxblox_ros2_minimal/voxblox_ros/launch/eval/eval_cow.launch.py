"""
ROS2 launch file for Voxblox evaluation on cow dataset.

This launch file runs the voxblox_eval node to evaluate a Voxblox reconstruction
against ground truth mesh data for the cow dataset.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """
    Generate launch description for Voxblox cow dataset evaluation.

    Returns:
        LaunchDescription: The launch description containing all launch arguments and nodes.
    """

    # Declare launch arguments
    voxblox_file_path_arg = DeclareLaunchArgument(
        'voxblox_file_path',
        default_value='/Users/helen/data/cow/voxblox/merged_weight_nc_0_02.vxblx',
        description='Path to the Voxblox reconstruction file (.vxblx)'
    )

    gt_file_path_arg = DeclareLaunchArgument(
        'gt_file_path',
        default_value='/Users/helen/data/cow/gt_just_cow.ply',
        description='Path to the ground truth mesh file (.ply)'
    )

    # Get configuration file path
    cow_dataset_config = PathJoinSubstitution([
        FindPackageShare('voxblox_ros'),
        'cfg',
        'cow_dataset.yaml'
    ])

    # Define the voxblox_eval node
    voxblox_eval_node = Node(
        package='voxblox_ros',
        executable='voxblox_eval',
        name='voxblox_eval',
        output='screen',
        arguments=['-alsologtostderr'],
        parameters=[
            {
                'color_mode': 'normals',
                'frame_id': 'world',
                'verbose': True,
                'visualize': True,
                'recolor_by_error': False,
                'voxblox_file_path': LaunchConfiguration('voxblox_file_path'),
                'gt_file_path': LaunchConfiguration('gt_file_path'),
            },
            cow_dataset_config,  # Load parameters from YAML file
        ],
    )

    return LaunchDescription([
        # Launch arguments
        voxblox_file_path_arg,
        gt_file_path_arg,
        # Nodes
        voxblox_eval_node,
    ])
