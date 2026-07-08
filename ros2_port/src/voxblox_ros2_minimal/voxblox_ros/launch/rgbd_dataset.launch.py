"""
ROS2 launch file for Voxblox RGBD dataset processing.

This launch file replays a rosbag and runs the Voxblox TSDF server for dense reconstruction
using RGBD camera data from the V4RL Dense Reconstruction Dataset.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import os


def generate_launch_description():
    """Generate launch description for RGBD dataset processing with Voxblox."""

    # Declare launch arguments
    play_bag_arg = DeclareLaunchArgument(
        'play_bag',
        default_value='true',
        description='Whether to play the rosbag file automatically'
    )

    bag_file_arg = DeclareLaunchArgument(
        'bag_file',
        default_value='/path/to/RS_d1_30Hz.bag',
        description='Path to the rosbag file to play'
    )

    voxel_size_arg = DeclareLaunchArgument(
        'voxel_size',
        default_value='0.20',
        description='Size of TSDF voxels in meters'
    )

    # Get launch configurations
    play_bag = LaunchConfiguration('play_bag')
    bag_file = LaunchConfiguration('bag_file')
    voxel_size = LaunchConfiguration('voxel_size')

    # Find package share directory for voxblox_ros
    voxblox_share = FindPackageShare('voxblox_ros')

    # Path to config file
    config_file = PathJoinSubstitution([
        voxblox_share,
        'cfg',
        'rgbd_dataset.yaml'
    ])

    # Path for mesh output (using timestamp-based naming instead of anon)
    mesh_output_path = PathJoinSubstitution([
        voxblox_share,
        'mesh_results',
        'rgbd.ply'
    ])

    # Rosbag player node
    # Note: In ROS2, use ros2 bag play instead of rosbag play
    bag_player = ExecuteProcess(
        condition=IfCondition(play_bag),
        cmd=[
            'ros2', 'bag', 'play',
            '-r', '1.0',
            '--clock',
            bag_file
        ],
        output='screen',
        name='player'
    )

    # Voxblox TSDF server node
    voxblox_node = Node(
        package='voxblox_ros',
        executable='tsdf_server',
        name='voxblox_node',
        output='screen',
        arguments=['--alsologtostderr'],
        parameters=[
            config_file,
            {
                'tsdf_voxel_size': voxel_size,
                'tsdf_voxels_per_side': 16,
                'voxel_carving_enabled': True,
                'color_mode': 'color',
                'use_tf_transforms': False,
                'update_mesh_every_n_sec': 1.0,
                'verbose': True,
                'min_time_between_msgs_sec': 0.2,
                'max_ray_length_m': 2.0,
                'mesh_filename': mesh_output_path,
            }
        ],
        remappings=[
            ('pointcloud', 'camera/depth/points'),
            ('transform', 'camera_imu/vrpn_client/estimated_transform'),
        ]
    )

    return LaunchDescription([
        # Declare arguments first
        play_bag_arg,
        bag_file_arg,
        voxel_size_arg,

        # Launch nodes and processes
        bag_player,
        voxblox_node,
    ])
