#!/usr/bin/env python3
# skeletonize_map_realtime.launch.py
#
# ROS2 Jazzy port of the ROS1 XML launch file for realtime skeletonization.
# This launch file provides realtime skeletonization of ESDF maps as they are generated.
#
# Key differences from ROS1:
#  - Uses launch_ros.actions.Node instead of <node>
#  - DeclareLaunchArgument replaces <arg>
#  - PathJoinSubstitution replaces $(arg ...) path concatenation
#  - TF static publisher now uses tf2_ros (no rate argument needed - it latches)
#  - respawn=True available in ROS2 Jazzy
#  - clear_params not needed in ROS2 (parameters are node-scoped)

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for realtime skeletonization."""

    # --- Launch Arguments (ROS1 <arg> equivalents) ---
    base_path_arg = DeclareLaunchArgument(
        "base_path",
        default_value="/home/hriday",
        description="Base directory where maps are located",
    )

    input_map_name_arg = DeclareLaunchArgument(
        "input_map_name",
        default_value="rs_esdf_0.10.voxblox",
        description="Input ESDF map filename",
    )

    output_map_name_arg = DeclareLaunchArgument(
        "output_map_name",
        default_value="rs_skeleton_0.10.voxblox",
        description="Output skeletonized map filename",
    )

    sparse_graph_name_arg = DeclareLaunchArgument(
        "sparse_graph_name",
        default_value="rs_sparse_graph_0.10.voxblox",
        description="Output sparse graph filename",
    )

    frame_id_arg = DeclareLaunchArgument(
        "frame_id",
        default_value="map",
        description="World/map frame ID",
    )

    # --- Derived paths (combining base_path with filenames) ---
    voxblox_path = PathJoinSubstitution(
        [
            LaunchConfiguration("base_path"),
            LaunchConfiguration("input_map_name"),
        ]
    )

    output_path = PathJoinSubstitution(
        [
            LaunchConfiguration("base_path"),
            LaunchConfiguration("output_map_name"),
        ]
    )

    sparse_graph_path = PathJoinSubstitution(
        [
            LaunchConfiguration("base_path"),
            LaunchConfiguration("sparse_graph_name"),
        ]
    )

    # --- Voxblox Skeletonizer Node (realtime) ---
    # ROS1: <node name="voxblox_skeletonizer" pkg="voxblox_skeleton"
    #        type="skeletonizer_realtime" output="screen" clear_params="true"
    #        respawn="true" args="-v=1">
    skeletonizer_node = Node(
        package="voxblox_skeleton",
        executable="skeletonizer_realtime",
        name="voxblox_skeletonizer",
        output="screen",
        emulate_tty=True,
        respawn=True,  # ROS2 Jazzy supports respawn
        arguments=["-v=1"],  # Verbosity flag
        remappings=[
            ("pointcloud", "/filtered_points"),
        ],
        parameters=[
            {
                # Visualization and frame settings
                "color_mode": "lambert",
                "frame_id": LaunchConfiguration("frame_id"),
                "world_frame": LaunchConfiguration("frame_id"),
                "verbose": False,

                # File paths
                "input_filepath": voxblox_path,
                "output_filepath": output_path,
                "sparse_graph_filepath": sparse_graph_path,

                # Skeletonization parameters
                "max_block_distance_from_body": 10.0,
                "generate_by_layer_neighbors": False,
                "min_gvd_distance": 0.5,

                # ICP settings
                "enable_icp": False,
                "icp_refine_roll_pitch": False,

                # Separation angle
                # If using full euclidean: 0.78 (45 degrees)
                # If using quasi-Euclidean: 1.57 (90 degrees)
                "min_separation_angle": 0.78,

                # ESDF update settings
                "update_esdf": True,
                "esdf_max_distance_m": 5.0,
                "esdf_min_diff_m": 0.0,
                "esdf_add_occupied_crust": True,

                # TSDF settings
                "tsdf_voxel_size": 0.2,

                # Publishing options
                "publish_pointclouds": True,
                # Commented out in original:
                # "publish_slices": True,
                # "slice_level": 1.0,
            }
        ],
    )

    # --- Static TF Publisher (map -> map_elevated) ---
    # ROS1: <node pkg="tf" type="static_transform_publisher" name="map_to_map_elevated"
    #        args="0 0 0.0 0 0 0 map map_elevated 100" />
    # ROS2: Uses tf2_ros, no rate argument (automatically latches)
    # Arguments: x y z yaw pitch roll parent_frame child_frame
    static_tf_node = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="map_to_map_elevated",
        arguments=["0", "0", "0.0", "0", "0", "0", "map", "map_elevated"],
        output="screen",
        emulate_tty=True,
    )

    return LaunchDescription(
        [
            # Declare all arguments first
            base_path_arg,
            input_map_name_arg,
            output_map_name_arg,
            sparse_graph_name_arg,
            frame_id_arg,
            # Launch nodes
            skeletonizer_node,
            static_tf_node,
        ]
    )
