#pragma once
// tf1-style msg<->tf2 conversion helpers for the vendored core (M3).
// Deliberately declared in namespace tf so the vendored call sites
// (tf::pointMsgToTF etc.) compile unchanged -- same shim philosophy as the
// ROS_* logging macros in port/log.h.
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/pose.hpp>
#include <tf2/LinearMath/Transform.h>

namespace tf {

inline void pointMsgToTF(const geometry_msgs::msg::Point& m, tf2::Vector3& v) {
  v.setValue(m.x, m.y, m.z);
}

inline void pointTFToMsg(const tf2::Vector3& v, geometry_msgs::msg::Point& m) {
  m.x = v.x();
  m.y = v.y();
  m.z = v.z();
}

inline void poseTFToMsg(const tf2::Transform& t, geometry_msgs::msg::Pose& m) {
  m.position.x = t.getOrigin().x();
  m.position.y = t.getOrigin().y();
  m.position.z = t.getOrigin().z();
  const tf2::Quaternion q = t.getRotation();
  m.orientation.x = q.x();
  m.orientation.y = q.y();
  m.orientation.z = q.z();
  m.orientation.w = q.w();
}

inline void poseMsgToTF(const geometry_msgs::msg::Pose& m, tf2::Transform& t) {
  t.setOrigin(tf2::Vector3(m.position.x, m.position.y, m.position.z));
  t.setRotation(tf2::Quaternion(m.orientation.x, m.orientation.y,
                                m.orientation.z, m.orientation.w));
}

}  // namespace tf
