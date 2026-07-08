#include <rclcpp/rclcpp.hpp>
#include "voxblox_ros/tsdf_server.h"

#include <gflags/gflags.h>

int main(int argc, char** argv) {
  // Let gflags re-parse later if needed (optional)
  gflags::AllowCommandLineReparsing();

  // Init logging first (so FLAGS_* affect glog)
  google::InitGoogleLogging(argv[0]);

  // Parse only non-help flags and REMOVE recognized ones from argv
  // so the remaining argv is clean for rclcpp.
  gflags::ParseCommandLineNonHelpFlags(&argc, &argv, /*remove_flags=*/true);

  rclcpp::init(argc, argv);

  rclcpp::Node::SharedPtr node_ptr = rclcpp::Node::make_shared("voxblox_node");
  voxblox::TsdfServer node(node_ptr.get());

  rclcpp::spin(node_ptr);
  return 0;
}
