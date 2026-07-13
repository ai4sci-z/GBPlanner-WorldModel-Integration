#pragma once
// Injected I/O for the ROS-free gbplanner core (M3). The core produces
// data and asks questions; the ROS2 node shell (M4) wires these callbacks
// to real publishers / tf2. Unset callbacks are silently skipped, so the
// core runs headless (unit tests) with a default-constructed RrgIO.
#include <functional>
#include <string>

#include <sensor_msgs/msg/point_cloud2.hpp>
#include <std_msgs/msg/bool.hpp>
#include <tf2/LinearMath/Transform.h>

namespace pshim {

struct RrgIO {
  // ROS1: nh_.advertise<sensor_msgs::PointCloud2>("freespace_pointcloud", 10)
  std::function<void(const sensor_msgs::msg::PointCloud2&)> publish_free_cloud;
  // ROS1: nh_.advertise<std_msgs::Bool>("planner_control_interface/msg/reset")
  std::function<void(const std_msgs::msg::Bool&)> publish_pci_reset;
  // ROS1: landing_srv_client_.call(std_srvs::Empty) — the landing sequence.
  std::function<void()> call_landing;
  // ROS1: tf::TransformListener::lookupTransform(target, source, t, out).
  // Returns false when the transform is unavailable (matches the try/catch
  // semantics at the three rrg.cpp call sites).
  std::function<bool(const std::string& target, const std::string& source,
                     tf2::Transform* out)>
      lookup_transform;

  void publishFreeCloud(const sensor_msgs::msg::PointCloud2& msg) const {
    if (publish_free_cloud) publish_free_cloud(msg);
  }
  void publishPciReset(const std_msgs::msg::Bool& msg) const {
    if (publish_pci_reset) publish_pci_reset(msg);
  }
  void callLanding() const {
    if (call_landing) call_landing();
  }
  bool lookupTransform(const std::string& target, const std::string& source,
                       tf2::Transform* out) const {
    return lookup_transform ? lookup_transform(target, source, out) : false;
  }
};

}  // namespace pshim
