#include "voxblox_ros/esdf_server.h"

#include <gflags/gflags.h>
#include <rclcpp/rclcpp.hpp>

int main(int argc, char** argv) {
  // ros::init(argc, argv, "voxblox");
  // Let gflags re-parse later if needed (optional)
  gflags::AllowCommandLineReparsing();

  // Init logging first (so FLAGS_* affect glog)
  google::InitGoogleLogging(argv[0]);

  // Parse only non-help flags and REMOVE recognized ones from argv
  // so the remaining argv is clean for rclcpp.
  gflags::ParseCommandLineNonHelpFlags(&argc, &argv, /*remove_flags=*/true);

  rclcpp::init(argc, argv);

  auto nh = rclcpp::Node::make_shared("voxblox");

  voxblox::EsdfServer node(nh.get());

  rclcpp::spin(nh);
  return 0;
}
