#include "voxblox_ros/esdf_server.h"

#include <gflags/gflags.h>
#include <rclcpp/rclcpp.hpp>

int main(int argc, char** argv) {
  // ros::init(argc, argv, "voxblox");
  // Let gflags re-parse later if needed (optional)
  gflags::AllowCommandLineReparsing();

  // Init logging first (so FLAGS_* affect glog)
  google::InitGoogleLogging(argv[0]);

  // Initialize ROS first so --ros-args/--params-file are consumed by rclcpp
  // before any gflags processing can alter argv (same fix as tsdf_server_node;
  // upstream Gabriele b5c3911 patched only the tsdf node).
  rclcpp::init(argc, argv);

  // Parse gflags without mutating argv that has already been consumed by ROS.
  int gflags_argc = argc;
  char** gflags_argv = argv;
  gflags::ParseCommandLineNonHelpFlags(&gflags_argc, &gflags_argv,
                                       /*remove_flags=*/false);

  rclcpp::NodeOptions node_options;
  node_options.automatically_declare_parameters_from_overrides(true);

  auto nh = rclcpp::Node::make_shared("voxblox", node_options);

  voxblox::EsdfServer node(nh.get());

  rclcpp::spin(nh);
  return 0;
}
