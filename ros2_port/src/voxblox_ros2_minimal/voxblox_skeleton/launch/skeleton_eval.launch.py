#!/usr/bin/env python3
# skeleton_eval.launch.py
#
# ROS2 port of skeleton_eval.launch
# This launch file provides skeleton evaluation capabilities.
#
# Notes:
#  - Converted from ROS1 XML launch file
#  - Preserves all parameters from the original configuration
#  - Uses ROS2 Jazzy conventions following skeletonize_map_vsgraphs.launch.py style

from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from launch import LaunchDescription


def generate_launch_description():
    # --- Arguments (equivalent to <arg> in ROS1) ---
    frame_id_arg = DeclareLaunchArgument(
        "frame_id",
        default_value="map",
        description="World / map frame ID",
    )

    # --- Voxblox skeletonizer node (skeleton_eval) ---
    # ROS1: <node name="voxblox_skeletonizer" pkg="voxblox_skeleton" type="skeleton_eval" ...>
    # ROS2: Node with executable="skeleton_eval"
    voxblox_skeletonizer_node = Node(
        package="voxblox_skeleton",
        executable="skeleton_eval",
        name="voxblox_skeletonizer",
        output="screen",
        emulate_tty=True,
        arguments=["-v=1"],
        parameters=[
            {
                # Skeleton generation parameters
                "generate_by_layer_neighbors": False,
                "full_euclidean_distance": True,
                "min_separation_angle": 0.7,
                "min_gvd_distance": 0.5,
                # Noise parameters
                "apply_noise": True,
                "noise_sigma": 0.01,
                # Robot pose generation
                "generate_from_robot_poses": False,
                # TSDF/ESDF parameters
                "tsdf_voxel_size": 0.1,
                "esdf_max_distance_m": 5.0,
                "esdf_min_diff_m": 0.0,
                "esdf_add_occupied_crust": True,
                # Publishing options
                "publish_pointclouds": True,
                "publish_slices": True,
                # Frame configuration
                "world_frame": LaunchConfiguration("frame_id"),
                "frame_id": LaunchConfiguration("frame_id"),
                # Verbosity
                "verbose": True,
            }
        ],
    )

    return LaunchDescription(
        [
            frame_id_arg,
            voxblox_skeletonizer_node,
        ]
    )
