#!/usr/bin/env python3
# voxblox_skeletonizer.launch.py
#
# ROS2 port of the provided ROS1 launch file.
# Notes:
#  - The TF static publisher is now from tf2_ros and no "rate" argument is used (it latches).
#  - We keep the same defaults and parameter names.
#  - Paths are composed with PathJoinSubstitution. If you rely on "~" expansion,
#    consider passing absolute paths or set base_path via an env/CLI arg.

from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node

from launch import LaunchDescription


def generate_launch_description():
    # --- Arguments (equivalents to <arg> in ROS1) ---
    base_path_arg = DeclareLaunchArgument(
        "base_path",
        default_value="~",
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
        "frame_id", default_value="map", description="World / map frame"
    )
    pc_topic_arg = DeclareLaunchArgument(
        "pc_topic",
        default_value="/camera/depth/points",
        description="PointCloud2 topic to feed the skeletonizer",
    )

    # --- Derived paths (voxblox_path, output_path, sparse_graph_path) ---
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
    skeletonizer_node = Node(
        package="voxblox_skeleton",
        executable="skeletonizer_realtime",
        # name="voxblox_skeletonizer",
        output="screen",
        emulate_tty=True,
        # respawn=True,
        # arguments=["-v=1"],
        remappings=[
            ("pointcloud", LaunchConfiguration("pc_topic")),
        ],
        parameters=[
            {
                # Visualization / frames
                "verbose": True,
                "color_mode": "color",
                "frame_id": LaunchConfiguration("frame_id"),
                "world_frame": LaunchConfiguration("frame_id"),
                # Files
                "input_filepath": voxblox_path,
                "output_filepath": output_path,
                "sparse_graph_filepath": sparse_graph_path,
                # Others (kept from ROS1 launcher)
                "enable_icp": False,
                "update_esdf": True,
                "esdf_min_diff_m": 0.0,
                "tsdf_voxel_size": 0.2,
                "min_gvd_distance": 0.5,
                "esdf_max_distance_m": 5.0,
                "publish_pointclouds": True,
                "min_separation_angle": 0.78,  # 45 deg
                "icp_refine_roll_pitch": False,
                "esdf_add_occupied_crust": True,
                "vertex_distance_threshold": 0.3,
                "max_block_distance_from_body": 100.0,
                "generate_by_layer_neighbors": False,
                "slice_level": 1.0,
                "publish_slices": True,
            }
        ],
    )

    # --- Static TF (map -> map_elevated) ---
    # ROS1: <node pkg="tf" type="static_transform_publisher" ... args="0 0 0 0 0 0 map map_elevated 100" />
    # ROS2 tf2_ros syntax (RPY): x y z yaw pitch roll frame child
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
            base_path_arg,
            input_map_name_arg,
            output_map_name_arg,
            sparse_graph_name_arg,
            frame_id_arg,
            pc_topic_arg,
            skeletonizer_node,
            static_tf_node,
        ]
    )
