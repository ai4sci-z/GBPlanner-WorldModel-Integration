#include <gflags/gflags.h>
#include <glog/logging.h>
// #include <ros/ros.h>
#include <rclcpp/rclcpp.hpp>

#include "voxblox_ros/simulation_server.h"

namespace voxblox {
class SimulationServerImpl : public voxblox::SimulationServer {
 public:
  SimulationServerImpl(rclcpp::Node* node_ptr)

      : SimulationServer(node_ptr) {}

  void prepareWorld() {
    CHECK_NOTNULL(world_);
    world_->addObject(std::unique_ptr<Object>(
        new Sphere(Point(0.0, 0.0, 2.0), 2.0, Color::Red())));

    world_->addObject(std::unique_ptr<Object>(new PlaneObject(
        Point(-2.0, -4.0, 2.0), Point(0, 1, 0), Color::White())));

    world_->addObject(std::unique_ptr<Object>(
        new PlaneObject(Point(4.0, 0.0, 0.0), Point(-1, 0, 0), Color::Pink())));

    world_->addObject(std::unique_ptr<Object>(
        new Cube(Point(-4.0, 4.0, 2.0), Point(4, 4, 4), Color::Green())));

    world_->addGroundLevel(0.03);

    world_->generateSdfFromWorld(truncation_distance_, tsdf_gt_.get());
    world_->generateSdfFromWorld(esdf_max_distance_, esdf_gt_.get());
  }
};

}  // namespace voxblox

int main(int argc, char** argv) {
  // ros::init(argc, argv, "voxblox_sim");
  // Let gflags re-parse later if needed (optional)
  gflags::AllowCommandLineReparsing();

  // Init logging first (so FLAGS_* affect glog)
  google::InitGoogleLogging(argv[0]);

  // Parse only non-help flags and REMOVE recognized ones from argv
  // so the remaining argv is clean for rclcpp.
  gflags::ParseCommandLineNonHelpFlags(&argc, &argv, /*remove_flags=*/true);

  rclcpp::init(argc, argv);
  // ros::NodeHandle nh;
  // ros::NodeHandle nh_private("~");
  auto node = rclcpp::Node::make_shared("voxblox_sim");

  voxblox::SimulationServerImpl sim_eval(node.get());

  sim_eval.run();

  /* ROS_INFO("Done.");
   */
  RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "Done.");
  rclcpp::spin(node);
  return 0;
}
