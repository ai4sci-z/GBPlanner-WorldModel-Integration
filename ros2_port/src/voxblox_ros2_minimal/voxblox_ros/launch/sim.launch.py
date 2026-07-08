#!/usr/bin/env python3
# sim.launch.py
#
# ROS2 Jazzy port of sim.launch from ROS1
# Launches the simulation_eval node from voxblox_ros package with all parameters
# originally defined in the XML launch file.

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """
    Generate launch description for voxblox simulation evaluation.

    This launch file starts the simulation_eval node which evaluates voxblox
    performance with configurable TSDF/ESDF parameters and viewpoint generation.
    """

    # Define the simulation_eval node with all parameters
    simulation_eval_node = Node(
        package="voxblox_ros",
        executable="simulation_eval",
        name="simulation_eval",
        output="screen",
        emulate_tty=True,
        arguments=["-alsologtostderr", "-v=3"],
        parameters=[
            {
                # TSDF configuration
                "tsdf_voxel_size": 0.1,
                "tsdf_voxels_per_side": 16,
                "truncation_distance": 0.4,

                # ESDF configuration
                "esdf_min_distance_m": 0.2,

                # Simulation settings
                "incremental": False,
                "add_robot_pose": False,
                "generate_mesh": True,
                "num_viewpoints": 50,
                "max_attempts_to_generate_viewpoint": 50,

                # General settings
                "verbose": True,
                "world_frame": "map",
            }
        ],
    )

    return LaunchDescription([
        simulation_eval_node,
    ])
