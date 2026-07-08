#include <rclcpp/rclcpp.hpp>
#include "voxblox_ros/tsdf_server.h"

#include <gflags/gflags.h>

int main(int argc, char** argv) {
  // Let gflags re-parse later if needed (optional)
  gflags::AllowCommandLineReparsing();

  // Init logging first (so FLAGS_* affect glog)
  google::InitGoogleLogging(argv[0]);

  // Initialize ROS first so --ros-args/--params-file are consumed by rclcpp
  // before any gflags processing can alter argv.
  rclcpp::init(argc, argv);

  // Parse gflags without mutating argv that has already been consumed by ROS.
  int gflags_argc = argc;
  char** gflags_argv = argv;
  gflags::ParseCommandLineNonHelpFlags(&gflags_argc, &gflags_argv,
                                       /*remove_flags=*/false);

  rclcpp::NodeOptions node_options;
  node_options.automatically_declare_parameters_from_overrides(true);

  rclcpp::Node::SharedPtr node_ptr =
      rclcpp::Node::make_shared("voxblox_node", node_options);
  voxblox::TsdfServer node(node_ptr.get());

  rclcpp::spin(node_ptr);
  return 0;
}
