#!/usr/bin/env python3
"""
ROS2 Jazzy launch file for KITTI dataset processing with Voxblox.

This launch file supports both laser and stereo-based mapping from KITTI datasets.
These datasets can be created with the KITTI raw datasets:
http://www.cvlibs.net/datasets/kitti/raw_data.php
and kitti_to_rosbag: https://github.com/ethz-asl/kitti_to_rosbag
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
    PythonExpression,
    TextSubstitution,
)
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    """Generate launch description for KITTI dataset processing."""

    # Declare launch arguments
    play_bag_arg = DeclareLaunchArgument(
        'play_bag',
        default_value='true',
        description='Whether to play the bag file automatically'
    )

    process_every_nth_frame_arg = DeclareLaunchArgument(
        'process_every_nth_frame',
        default_value='1',
        description='Process every Nth frame from the dataset'
    )

    voxel_size_arg = DeclareLaunchArgument(
        'voxel_size',
        default_value='0.25',
        description='Voxel size for TSDF map (in meters)'
    )

    scale_arg = DeclareLaunchArgument(
        'scale',
        default_value='0.25',
        description='Scale parameter for stereo processing'
    )

    use_laser_arg = DeclareLaunchArgument(
        'use_laser',
        default_value='true',
        description='Whether to use laser (true) or stereo (false) for the map'
    )

    # Note: bag_file argument is commented out in the original launch file
    # If needed, uncomment and add to the launch description
    # bag_file_arg = DeclareLaunchArgument(
    #     'bag_file',
    #     default_value='/path/to/drive35.bag',
    #     description='Path to the KITTI bag file'
    # )

    # Launch configurations
    play_bag = LaunchConfiguration('play_bag')
    process_every_nth_frame = LaunchConfiguration('process_every_nth_frame')
    voxel_size = LaunchConfiguration('voxel_size')
    scale = LaunchConfiguration('scale')
    use_laser = LaunchConfiguration('use_laser')
    # bag_file = LaunchConfiguration('bag_file')

    # Get package share directory for config files
    voxblox_ros_share = FindPackageShare('voxblox_ros')

    # Stereo config file path
    stereo_config_file = PathJoinSubstitution([
        voxblox_ros_share,
        'cfg', 'stereo', 'kitti_stereo_jager.yaml'
    ])

    # Mesh output file path with anonymous suffix
    mesh_output_file = PathJoinSubstitution([
        voxblox_ros_share,
        'mesh_results', 'kitti.ply'  # Note: $(anon kitti) not directly supported, using fixed name
    ])

    # Bag player node (conditional execution based on play_bag argument)
    # Note: In the original, bag_file was commented out. If you need to use it,
    # uncomment the bag_file_arg above and replace the placeholder path below
    bag_player = ExecuteProcess(
        condition=IfCondition(play_bag),
        cmd=[
            'ros2', 'bag', 'play',
            # '/path/to/drive35.bag',  # Replace with actual bag file path or use LaunchConfiguration
            '-r', '0.2',
            '--clock'
        ],
        name='player',
        output='screen'
    )

    # Stereo image processing node with namespace and remappings
    stereo_image_proc_node = Node(
        package='stereo_image_proc',
        executable='stereo_image_proc',
        name='stereo_image_proc',
        namespace='stereo_gray',
        output='screen',
        parameters=[
            stereo_config_file,
            {
                'approximate_sync': True,
            }
        ],
        remappings=[
            ('left/image_raw', '/cam02/image_raw'),
            ('left/camera_info', '/cam02/camera_info'),
            ('right/image_raw', '/cam03/image_raw'),
            ('right/camera_info', '/cam03/camera_info'),
        ],
        # clear_params is handled by ROS2 parameter system automatically
    )

    # Voxblox TSDF server node with conditional remappings and parameters
    # Using OpaqueFunction to handle conditional logic properly
    def create_voxblox_node(context):
        """Create voxblox node with conditional remappings and parameters."""
        # Evaluate use_laser to determine remappings and color mode
        use_laser_value = context.launch_configurations.get('use_laser', 'true')
        use_laser_bool = use_laser_value.lower() in ('true', '1', 'yes')

        # Conditional remapping based on use_laser
        if use_laser_bool:
            pointcloud_remap = ('pointcloud', '/velodyne_points')
            color_mode_value = 'normals'
        else:
            pointcloud_remap = ('pointcloud', '/stereo_gray/points2')
            color_mode_value = 'color'

        # Get voxel size value
        voxel_size_value = context.launch_configurations.get('voxel_size', '0.25')

        # Mesh filename (note: anonymous suffix not directly available)
        mesh_file_path = os.path.join(
            get_package_share_directory('voxblox_ros'),
            'mesh_results',
            'kitti.ply'
        )

        voxblox_node = Node(
            package='voxblox_ros',
            executable='tsdf_server',
            name='voxblox_node',
            output='screen',
            arguments=['-alsologtostderr'],
            parameters=[{
                'tsdf_voxel_size': float(voxel_size_value),
                'tsdf_voxels_per_side': 16,
                'voxel_carving_enabled': True,
                'color_mode': color_mode_value,
                'use_tf_transforms': True,
                'enable_icp': True,
                'icp_iterations': 10,
                'verbose': True,
                'update_mesh_every_n_sec': 0.2,
                'max_ray_length_m': 25.0,
                'min_time_between_msgs_sec': 0.2,
                'slice_level': 1.0,
                'method': 'fast',
                'use_const_weight': True,
                'mesh_filename': mesh_file_path,
            }],
            remappings=[pointcloud_remap],
        )

        return [voxblox_node]

    # Build launch description
    return LaunchDescription([
        # Declare all arguments
        play_bag_arg,
        process_every_nth_frame_arg,
        voxel_size_arg,
        scale_arg,
        use_laser_arg,

        # Nodes and actions
        bag_player,
        stereo_image_proc_node,
        OpaqueFunction(function=create_voxblox_node),
    ])
