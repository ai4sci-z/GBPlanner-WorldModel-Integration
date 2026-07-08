#!/usr/bin/env python3
"""
ROS2 launch file for running Voxblox with EuRoC dataset.

This launch file starts the following:
- (Optional) Rosbag player for dataset playback
- dense_stereo node from image_undistort package for stereo processing
- voxblox esdf_server for 3D reconstruction

Dataset available at: https://projects.asl.ethz.ch/datasets/doku.php?id=kmavvisualinertialdatasets
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
import os


def generate_launch_description():
    # Declare launch arguments
    play_bag_arg = DeclareLaunchArgument(
        'play_bag',
        default_value='true',
        description='Whether to play the rosbag file'
    )

    bag_file_arg = DeclareLaunchArgument(
        'bag_file',
        default_value='/path/to/V1_01_easy.bag',
        description='Path to the EuRoC dataset bag file'
    )

    voxel_size_arg = DeclareLaunchArgument(
        'voxel_size',
        default_value='0.10',
        description='Voxel size for TSDF reconstruction'
    )

    process_every_nth_frame_arg = DeclareLaunchArgument(
        'process_every_nth_frame',
        default_value='5',
        description='Process every nth frame for stereo processing'
    )

    scale_arg = DeclareLaunchArgument(
        'scale',
        default_value='0.5',
        description='Scale factor for image processing'
    )

    # Get launch configurations
    play_bag = LaunchConfiguration('play_bag')
    bag_file = LaunchConfiguration('bag_file')
    voxel_size = LaunchConfiguration('voxel_size')
    process_every_nth_frame = LaunchConfiguration('process_every_nth_frame')
    scale = LaunchConfiguration('scale')

    # Define paths to config files
    voxblox_pkg_share = FindPackageShare('voxblox_ros')
    euroc_camchain_config = PathJoinSubstitution([
        voxblox_pkg_share,
        'cfg',
        'calibrations',
        'euroc_camchain.yaml'
    ])
    euroc_dataset_config = PathJoinSubstitution([
        voxblox_pkg_share,
        'cfg',
        'euroc_dataset.yaml'
    ])
    mesh_output_path = PathJoinSubstitution([
        voxblox_pkg_share,
        'mesh_results',
        'euroc_output.ply'
    ])

    # Rosbag player node (conditional on play_bag argument)
    bag_player = ExecuteProcess(
        condition=IfCondition(play_bag),
        cmd=[
            'ros2', 'bag', 'play',
            '-r', '1.0',
            '--clock',
            bag_file
        ],
        name='player',
        output='screen'
    )

    # dense_stereo node from image_undistort package
    dense_stereo_node = Node(
        package='image_undistort',
        executable='dense_stereo_node',
        name='dense_stereo',
        parameters=[
            {
                'input_camera_info_from_ros_params': True,
                'first_camera_namespace': 'cam0',
                'second_camera_namespace': 'cam1',
                'first_output_frame': 'cam0',
                'second_output_frame': 'cam1',
                'scale': scale,
                'process_every_nth_frame': process_every_nth_frame,
            },
            euroc_camchain_config
        ],
        remappings=[
            ('raw/first/image', 'cam0/image_raw'),
            ('raw/second/image', 'cam1/image_raw'),
            ('raw/first/camera_info', 'cam0/camera_info'),
            ('raw/second/camera_info', 'cam1/camera_info'),
        ],
        output='screen'
    )

    # voxblox esdf_server node
    voxblox_node = Node(
        package='voxblox_ros',
        executable='esdf_server',
        name='voxblox_node',
        parameters=[
            {
                'use_freespace_pointcloud': True,
                'tsdf_voxel_size': voxel_size,
                'tsdf_voxels_per_side': 16,
                'voxel_carving_enabled': True,
                'color_mode': 'colors',
                'use_tf_transforms': False,
                'verbose': True,
                'update_mesh_every_n_sec': 1.0,
                'slice_level': 1.0,
                'method': 'fast',
                'use_const_weight': False,
                'publish_slices': True,
                'publish_pointclouds': True,
                'mesh_filename': mesh_output_path,
            },
            euroc_dataset_config
        ],
        remappings=[
            ('pointcloud', 'dense_stereo/pointcloud'),
            ('freespace_pointcloud', 'dense_stereo/freespace_pointcloud'),
            ('transform', 'vicon/firefly_sbx/firefly_sbx'),
        ],
        arguments=['-alsologtostderr'],
        output='screen'
    )

    return LaunchDescription([
        # Declare arguments
        play_bag_arg,
        bag_file_arg,
        voxel_size_arg,
        process_every_nth_frame_arg,
        scale_arg,
        # Launch nodes and processes
        bag_player,
        dense_stereo_node,
        voxblox_node,
    ])
