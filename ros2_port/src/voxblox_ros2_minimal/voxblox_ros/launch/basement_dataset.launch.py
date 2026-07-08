#!/usr/bin/env python3
"""
ROS2 launch file for Voxblox basement dataset processing.

This launch file:
- Optionally plays a bag file using ros2 bag play
- Launches the voxblox tsdf_server node with parameters for basement dataset processing
- Remaps pointcloud topic to /velodyne_points

Download the dataset here: https://projects.asl.ethz.ch/datasets/doku.php?id=basement2018
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import uuid


def generate_launch_description():
    """Generate launch description for basement dataset processing with Voxblox."""

    # Generate anonymous name for mesh filename (equivalent to $(anon basement))
    # In ROS2, we generate a unique identifier similar to ROS1's anonymous name
    anon_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for brevity

    # Declare launch arguments
    play_bag_arg = DeclareLaunchArgument(
        'play_bag',
        default_value='true',
        description='Whether to play the bag file automatically'
    )

    bag_file_arg = DeclareLaunchArgument(
        'bag_file',
        default_value='/PATH/TO/basement_dataset.bag',
        description='Path to the basement dataset bag file'
    )

    # Bag player process (conditional execution based on play_bag argument)
    # Note: In ROS2, we use 'ros2 bag play' instead of rosbag play
    bag_player = ExecuteProcess(
        condition=IfCondition(LaunchConfiguration('play_bag')),
        cmd=[
            'ros2', 'bag', 'play',
            LaunchConfiguration('bag_file'),
            '-r', '1.0',
            '--clock'
        ],
        output='screen',
        name='player'
    )

    # Construct mesh filename path with anonymous component
    # Equivalent to: $(find voxblox_ros)/mesh_results/$(anon basement).ply
    mesh_filename = PathJoinSubstitution([
        FindPackageShare('voxblox_ros'),
        'mesh_results',
        f'basement_{anon_id}.ply'
    ])

    # Voxblox TSDF server node
    voxblox_node = Node(
        package='voxblox_ros',
        executable='tsdf_server',
        name='voxblox_node',
        output='screen',
        arguments=['-alsologtostderr'],
        parameters=[{
            'tsdf_voxel_size': 0.1,
            'truncation_distance': 0.5,
            'color_mode': 'normals',
            'enable_icp': True,
            'icp_refine_roll_pitch': False,
            'update_mesh_every_n_sec': 1.0,
            'mesh_min_weight': 2,
            'method': 'fast',
            'max_ray_length_m': 10.0,
            'use_const_weight': True,
            'world_frame': 'world',
            'verbose': True,
            'mesh_filename': mesh_filename,
        }],
        remappings=[
            ('pointcloud', '/velodyne_points'),
        ]
    )

    return LaunchDescription([
        # Declare arguments first
        play_bag_arg,
        bag_file_arg,

        # Launch processes and nodes
        bag_player,
        voxblox_node,
    ])
