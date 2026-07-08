#!/usr/bin/env python3
"""
skeletonize_map_multirobot_realtime.launch.py

ROS2 Jazzy port of the ROS1 XML launch file for realtime skeletonization in multi-robot scenarios.

This launch file provides:
- Namespace support for multi-robot deployments
- Realtime skeletonization with pointcloud input
- Configurable frame IDs that adapt to robot namespaces
- Static TF publisher for map elevation
- Full parameter configuration from the original ROS1 launch file
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node, PushRosNamespace


def generate_launch_description():
    """Generate launch description for multi-robot realtime skeletonization."""

    # --- Launch Arguments (equivalent to <arg> in ROS1) ---
    base_path_arg = DeclareLaunchArgument(
        "base_path",
        default_value="/home/hriday",
        description="Base directory where maps are located"
    )

    input_map_name_arg = DeclareLaunchArgument(
        "input_map_name",
        default_value="rs_esdf_0.10.voxblox",
        description="Input ESDF/TSDF Voxblox map filename"
    )

    output_map_name_arg = DeclareLaunchArgument(
        "output_map_name",
        default_value="rs_skeleton_0.10.voxblox",
        description="Output skeletonized map filename"
    )

    sparse_graph_name_arg = DeclareLaunchArgument(
        "sparse_graph_name",
        default_value="rs_sparse_graph_0.10.voxblox",
        description="Output sparse graph filename"
    )

    namespace_arg = DeclareLaunchArgument(
        "namespace",
        default_value="",
        description="Robot namespace for multi-robot scenarios (empty for single robot)"
    )

    frame_id_arg = DeclareLaunchArgument(
        "frame_id",
        default_value="map",
        description="Base frame ID for the map"
    )

    # --- Derived paths (voxblox_path, output_path, sparse_graph_path) ---
    # These use PathJoinSubstitution to build full paths from base_path + filename
    voxblox_path = PathJoinSubstitution([
        LaunchConfiguration("base_path"),
        LaunchConfiguration("input_map_name")
    ])

    output_path = PathJoinSubstitution([
        LaunchConfiguration("base_path"),
        LaunchConfiguration("output_map_name")
    ])

    sparse_graph_path = PathJoinSubstitution([
        LaunchConfiguration("base_path"),
        LaunchConfiguration("sparse_graph_name")
    ])

    # --- Compute final_frame_id ---
    # ROS1: $(eval namespace + '/' + frame_id if len(namespace) else frame_id)
    # ROS2: Use PythonExpression for the conditional logic
    final_frame_id = PythonExpression([
        "'", LaunchConfiguration("namespace"), "' + '/' + '",
        LaunchConfiguration("frame_id"), "' if len('",
        LaunchConfiguration("namespace"), "') > 0 else '",
        LaunchConfiguration("frame_id"), "'"
    ])

    # --- Voxblox Skeletonizer Node (realtime version) ---
    skeletonizer_node = Node(
        package="voxblox_skeleton",
        executable="skeletonizer_realtime",
        name="voxblox_skeletonizer",
        output="screen",
        emulate_tty=True,
        respawn=True,  # respawn="true" from ROS1
        arguments=["-v=1"],  # Verbosity argument from ROS1
        remappings=[
            ("pointcloud", "filtered_points"),
        ],
        parameters=[{
            # Visualization and frames
            "color_mode": "lambert",
            "frame_id": final_frame_id,
            "world_frame": final_frame_id,
            "verbose": False,

            # File paths
            "input_filepath": voxblox_path,
            "output_filepath": output_path,
            "sparse_graph_filepath": sparse_graph_path,

            # Skeletonization parameters
            "max_block_distance_from_body": 10.0,
            "generate_by_layer_neighbors": False,
            "min_separation_angle": 0.78,  # 45 degrees for full euclidean
            "min_gvd_distance": 0.5,

            # ICP parameters
            "enable_icp": False,
            "icp_refine_roll_pitch": False,

            # ESDF parameters
            "update_esdf": True,
            "esdf_max_distance_m": 5.0,
            "esdf_min_diff_m": 0.0,
            "esdf_add_occupied_crust": True,

            # TSDF parameters
            "tsdf_voxel_size": 0.2,

            # Publishing options
            "publish_pointclouds": True,
            # Uncommented from ROS1 launch file:
            # "publish_slices": True,
            # "slice_level": 1.0,
        }]
    )

    # --- Static TF Publisher (map to map_elevated) ---
    # ROS1: <node pkg="tf" type="static_transform_publisher" ... args="0 0 0.0 0 0 0 $(arg final_frame_id) map_elevated 100" />
    # ROS2: Use tf2_ros static_transform_publisher with arguments: x y z qx qy qz qw frame_id child_frame_id
    # Note: ROS1 format was x y z yaw pitch roll, but for zero rotation both are equivalent
    static_tf_node = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="map_to_map_elevated",
        arguments=["0", "0", "0.0", "0", "0", "0", final_frame_id, "map_elevated"],
        output="screen",
        emulate_tty=True,
    )

    # --- Group with namespace (equivalent to <group ns="...">) ---
    # ROS1: <group ns="$(eval namespace if len(namespace) else '/')">
    # ROS2: Use PushRosNamespace with conditional logic, but ROS2 handles empty namespace differently
    # We'll compute the effective namespace
    namespace_value = PythonExpression([
        "'", LaunchConfiguration("namespace"), "' if len('",
        LaunchConfiguration("namespace"), "') > 0 else '/'"
    ])

    # Create a group action to apply the namespace to all nodes
    namespaced_group = GroupAction(
        actions=[
            PushRosNamespace(namespace_value),
            skeletonizer_node,
            static_tf_node,
        ]
    )

    # --- Return Launch Description ---
    return LaunchDescription([
        # Declare all arguments first
        base_path_arg,
        input_map_name_arg,
        output_map_name_arg,
        sparse_graph_name_arg,
        namespace_arg,
        frame_id_arg,

        # Launch nodes in namespaced group
        namespaced_group,
    ])
