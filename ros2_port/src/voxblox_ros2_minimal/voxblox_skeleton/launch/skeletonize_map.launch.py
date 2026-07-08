#!/usr/bin/env python3
# skeletonize_map.launch.py
#
# ROS2 Jazzy port of the ROS1 skeletonize_map.launch file.
# Provides basic skeletonization of ESDF maps for planning support.
#
# This launch file loads an existing ESDF map, skeletonizes it, and saves
# the output skeleton and sparse graph to disk.

from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node

from launch import LaunchDescription


def generate_launch_description():
    """
    Generate launch description for offline ESDF map skeletonization.

    This launch file is intended for batch processing of existing voxblox maps,
    where the skeletonizer node processes a saved ESDF and exits.
    """

    # --- Arguments (equivalents to <arg> in ROS1) ---
    base_path_arg = DeclareLaunchArgument(
        "base_path",
        default_value="/home/hriday",
        description="Base directory where maps are located",
    )

    input_map_name_arg = DeclareLaunchArgument(
        "input_map_name",
        default_value="rs_esdf_0.10.voxblox",
        description="Input ESDF/TSDF Voxblox map filename",
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
        description="World / map frame ID",
    )

    # --- Derived paths (voxblox_path, output_path, sparse_graph_path) ---
    # These mirror the ROS1 arg composition pattern:
    #   <arg name="voxblox_path" default="$(arg base_path)/$(arg input_map_name)" />
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

    # --- Voxblox skeletonizer node ---
    # ROS1 node:
    #   <node name="voxblox_skeletonizer" pkg="voxblox_skeleton" type="skeletonizer"
    #         output="screen" clear_params="true" args="-v=1">
    #
    # Note: clear_params is not directly supported in ROS2; parameters are scoped
    # to the node automatically. The "-v=1" verbosity flag is preserved as an argument.
    skeletonizer_node = Node(
        package="voxblox_skeleton",
        executable="skeletonizer",
        name="voxblox_skeletonizer",
        output="screen",
        emulate_tty=True,
        arguments=["-v=1"],
        parameters=[
            {
                # File paths
                "input_filepath": voxblox_path,
                "output_filepath": output_path,
                "sparse_graph_filepath": sparse_graph_path,

                # Skeletonization parameters
                "generate_by_layer_neighbors": False,
                # If using full euclidean: 0.78 (45 degrees)
                # If using quasi-Euclidean: 1.57 (90 degrees)
                "min_separation_angle": 0.78,
                "update_esdf": False,
                "min_gvd_distance": 0.5,

                # TSDF/ESDF parameters
                "tsdf_voxel_size": 0.1,
                "esdf_max_distance_m": 5.0,
                "esdf_min_diff_m": 0.0,
                "esdf_add_occupied_crust": True,

                # Visualization parameters
                "publish_pointclouds": True,
                "publish_slices": True,
                "world_frame": LaunchConfiguration("frame_id"),
                "frame_id": LaunchConfiguration("frame_id"),

                # Verbosity
                "verbose": True,
            }
        ],
    )

    return LaunchDescription(
        [
            # Declare all arguments first
            base_path_arg,
            input_map_name_arg,
            output_map_name_arg,
            sparse_graph_name_arg,
            frame_id_arg,

            # Then launch nodes
            skeletonizer_node,
        ]
    )
