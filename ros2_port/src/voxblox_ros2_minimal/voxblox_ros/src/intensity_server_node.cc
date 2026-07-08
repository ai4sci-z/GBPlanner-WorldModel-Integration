#include <rclcpp/rclcpp.hpp>
#include "voxblox_ros/intensity_server.h"

#include <gflags/gflags.h>

int main(int argc, char** argv) {
  // ros::init(argc, argv, "voxblox");
  rclcpp::init(argc, argv);
  google::InitGoogleLogging(argv[0]);
  google::ParseCommandLineFlags(&argc, &argv, false);
  google::InstallFailureSignalHandler();

  rclcpp::NodeOptions node_options;
  node_options.automatically_declare_parameters_from_overrides(true);

  auto nh = rclcpp::Node::make_shared("voxblox_intensity_server", node_options);

  voxblox::IntensityServer node(nh.get());

  // ros::spin();
  rclcpp::spin(nh);
  return 0;
}
