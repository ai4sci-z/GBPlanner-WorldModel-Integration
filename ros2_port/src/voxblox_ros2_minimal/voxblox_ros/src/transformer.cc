#include "voxblox_ros/transformer.h"

#include <minkindr_conversions/kindr_msg.h>
#include <minkindr_conversions/kindr_tf.h>
#include <minkindr_conversions/kindr_xml.h>
#include <memory>
#include <rclcpp/logger.hpp>
#include <rclcpp/logging.hpp>
#include <rclcpp/rclcpp.hpp>

#include <deque>
#include <rclcpp/time.hpp>
#include <sstream>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>

namespace voxblox {

Transformer::Transformer(rclcpp::Node* node_ptr)
    : node_ptr_(node_ptr),
      world_frame_("world"),
      sensor_frame_(""),
      use_tf_transforms_(true),
      timestamp_tolerance_ns_(1000000) {
  // nh_private_.param("world_frame", world_frame_, world_frame_);
  // nh_private_.param("sensor_frame", sensor_frame_, sensor_frame_);
  if (!node_ptr_->has_parameter("world_frame")) {
    node_ptr_->declare_parameter<std::string>("world_frame", world_frame_);
  }
  // node_ptr_->declare_parameter("world_frame", world_frame_);
  // node_ptr_->declare_parameter("sensor_frame", sensor_frame_);
  if (!node_ptr_->has_parameter("sensor_frame")) {
    node_ptr_->declare_parameter<std::string>("sensor_frame", sensor_frame_);
  }

  node_ptr_->get_parameter("world_frame", world_frame_);
  node_ptr_->get_parameter("sensor_frame", sensor_frame_);

  const double kNanoSecondsInSecond = 1.0e9;
  double timestamp_tolerance_sec =
      timestamp_tolerance_ns_ / kNanoSecondsInSecond;
  // nh_private_.param("timestamp_tolerance_sec", timestamp_tolerance_sec,
  //                   timestamp_tolerance_sec);
  // node_ptr_->declare_parameter("timestamp_tolerance_sec",
  //                              timestamp_tolerance_sec);
  if (!node_ptr_->has_parameter("timestamp_tolerance_sec")) {
    node_ptr_->declare_parameter("timestamp_tolerance_sec",
                                 timestamp_tolerance_sec);
  }
  node_ptr_->get_parameter("timestamp_tolerance_sec", timestamp_tolerance_sec);

  timestamp_tolerance_ns_ =
      static_cast<int64_t>(timestamp_tolerance_sec * kNanoSecondsInSecond);

  // Transform settings.
  // nh_private_.param("use_tf_transforms", use_tf_transforms_,
  //                   use_tf_transforms_);
  // node_ptr_->declare_parameter("use_tf_transforms", use_tf_transforms_);
  if (!node_ptr_->has_parameter("use_tf_transforms")) {
    node_ptr_->declare_parameter("use_tf_transforms", use_tf_transforms_);
  }
  node_ptr_->get_parameter("use_tf_transforms", use_tf_transforms_);
  // If we use topic transforms, we have 2 parts: a dynamic transform from a
  // topic and a static transform from parameters.
  // Static transform should be T_G_D (where D is whatever sensor the
  // dynamic coordinate frame is in) and the static should be T_D_C (where
  // C is the sensor frame that produces the depth data). It is possible to
  // specify T_C_D and set invert_static_tranform to true.

  tf_buffer_ = std::make_unique<tf2_ros::Buffer>(node_ptr_->get_clock());
  tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);

  // TODO(miferco97): Re-enable when we have tf2 for ROS

  //   auto transform_sub =
  //       node_ptr_->create_subscription<geometry_msgs::msg::TransformStamped>(
  //           "transform", rclcpp::QoS(40),
  //           std::bind(&Transformer::transformCallback, this,
  //                     std::placeholders::_1));

  if (!use_tf_transforms_) {
    RCLCPP_WARN(
        node_ptr_->get_logger(),
        "Using transform topic and static transforms from parameters. This is "
        "deprecated; please use TF transforms instead.");

    transform_sub_ptr_ =
        node_ptr_->create_subscription<geometry_msgs::msg::TransformStamped>(
            "transform", rclcpp::QoS(40),
            std::bind(&Transformer::transformCallback, this,
                      std::placeholders::_1));

    //   // Retrieve T_D_C from params.
    XmlRpc::XmlRpcValue T_B_D_xml;
    // TODO(helenol): split out into a function to avoid duplication.
    if (node_ptr_->get_parameter("T_B_D", T_B_D_xml)) {
      kindr::minimal::xmlRpcToKindr(T_B_D_xml, &T_B_D_);

      // See if we need to invert it.
      bool invert_static_tranform = false;
      /* nh_private_.param("invert_T_B_D", invert_static_tranform,
                        invert_static_tranform); */
      node_ptr_->declare_parameter("invert_T_B_D", invert_static_tranform);
      node_ptr_->get_parameter("invert_T_B_D", invert_static_tranform);
      if (invert_static_tranform) {
        T_B_D_ = T_B_D_.inverse();
      }
    }

    XmlRpc::XmlRpcValue T_B_C_xml;
    if (node_ptr_->get_parameter("T_B_C", T_B_C_xml)) {
      kindr::minimal::xmlRpcToKindr(T_B_C_xml, &T_B_C_);

      // See if we need to invert it.
      bool invert_static_tranform = false;

      /* nh_private_.param("invert_T_B_C", invert_static_tranform,
                        invert_static_tranform); */
      node_ptr_->declare_parameter("invert_T_B_C", invert_static_tranform);
      node_ptr_->get_parameter("invert_T_B_C", invert_static_tranform);

      if (invert_static_tranform) {
        T_B_C_ = T_B_C_.inverse();
      }
    }
  }
}
void Transformer::transformCallback(
    const geometry_msgs::msg::TransformStamped& transform_msg) {
  // Add the new transform to the queue.
  transform_queue_.push_back(transform_msg);
}

bool Transformer::lookupTransform(const std::string& from_frame,
                                  const std::string& to_frame,
                                  const rclcpp::Time& timestamp,
                                  Transformation* transform) {
  CHECK_NOTNULL(transform);
  if (use_tf_transforms_) {
    return lookupTransformTf(from_frame, to_frame, timestamp, transform);
  } else {
    return lookupTransformQueue(timestamp, transform);
  }
}

// Stolen from octomap_manager
bool Transformer::lookupTransformTf(const std::string& from_frame,
                                    const std::string& to_frame,
                                    const rclcpp::Time& timestamp,
                                    Transformation* transform) {
  CHECK_NOTNULL(transform);
  geometry_msgs::msg::TransformStamped tf_transform;
  rclcpp::Time time_to_lookup = timestamp;

  // Allow overwriting the TF frame for the sensor.
  std::string from_frame_modified = from_frame;
  if (!sensor_frame_.empty()) {
    from_frame_modified = sensor_frame_;
  }

  // Previous behavior was just to use the latest transform if the time is in
  // the future. Now we will just wait.
  if (!tf_buffer_->canTransform(to_frame, from_frame_modified, time_to_lookup,
                                rclcpp::Duration::from_seconds(0.1))) {
    return false;
  }

  try {
    tf_transform = tf_buffer_->lookupTransform(to_frame, from_frame_modified,
                                               time_to_lookup);
  } catch (tf2::TransformException& ex) {  // NOLINT

    RCLCPP_ERROR(node_ptr_->get_logger(),
                 "Error getting TF transform from sensor data: %s", ex.what());
    return false;
  }

  tf2::Transform transform_tf;
  tf2::fromMsg(tf_transform.transform, transform_tf);
  tf::transformTFToKindr(transform_tf, transform);

  return true;
}

bool Transformer::lookupTransformQueue(const rclcpp::Time& timestamp,
                                       Transformation* transform) {
  CHECK_NOTNULL(transform);
  if (transform_queue_.empty()) {
    auto& clock = *node_ptr_->get_clock();
    RCLCPP_WARN_THROTTLE(node_ptr_->get_logger(), clock, 30,
                         "No match found for transform timestamp: %ld  as "
                         "transform queue is empty.",
                         timestamp.nanoseconds());
    return false;
  }
  // Try to match the transforms in the queue.
  bool match_found = false;
  std::deque<geometry_msgs::msg::TransformStamped>::iterator it =
      transform_queue_.begin();
  for (; it != transform_queue_.end(); ++it) {
    // If the current transform is newer than the requested timestamp, we need
    // to break.
    if (rclcpp::Time(it->header.stamp) > timestamp) {
      if ((rclcpp::Time(it->header.stamp) - timestamp).nanoseconds() <
          timestamp_tolerance_ns_) {
        match_found = true;
      }
      break;
    }

    if ((timestamp - it->header.stamp).nanoseconds() <
        timestamp_tolerance_ns_) {
      match_found = true;
      break;
    }
  }

  // Match found basically means an exact match.
  Transformation T_G_D;
  if (match_found) {
    tf::transformMsgToKindr(it->transform, &T_G_D);
  } else {
    // If we think we have an inexact match, have to check that we're still
    // within bounds and interpolate.
    std::stringstream ss;
    ss << "No match found for transform timestamp: " << timestamp.seconds()
       << " Queue front: "
       << rclcpp::Time(transform_queue_.front().header.stamp).seconds()
       << " back: "
       << rclcpp::Time(transform_queue_.back().header.stamp).seconds();

    if (it == transform_queue_.begin() || it == transform_queue_.end()) {
      RCLCPP_WARN_THROTTLE(node_ptr_->get_logger(), *node_ptr_->get_clock(), 30,
                           "%s. Not enough data to interpolate.",
                           ss.str().c_str());
      return false;
    }
    // Newest should be 1 past the requested timestamp, oldest should be one
    // before the requested timestamp.
    Transformation T_G_D_newest;
    tf::transformMsgToKindr(it->transform, &T_G_D_newest);
    int64_t offset_newest_ns =
        (rclcpp::Time(it->header.stamp) - timestamp).nanoseconds();
    // We already checked that this is not the beginning.
    it--;
    Transformation T_G_D_oldest;
    tf::transformMsgToKindr(it->transform, &T_G_D_oldest);
    int64_t offset_oldest_ns = (timestamp - it->header.stamp).nanoseconds();

    // Interpolate between the two transformations using the exponential map.
    FloatingPoint t_diff_ratio =
        static_cast<FloatingPoint>(offset_oldest_ns) /
        static_cast<FloatingPoint>(offset_newest_ns + offset_oldest_ns);

    Transformation::Vector6 diff_vector =
        (T_G_D_oldest.inverse() * T_G_D_newest).log();
    T_G_D = T_G_D_oldest * Transformation::exp(t_diff_ratio * diff_vector);
  }

  // If we have a static transform, apply it too.
  // Transform should actually be T_G_C. So need to take it through the full
  // chain.
  *transform = T_G_D * T_B_D_.inverse() * T_B_C_;

  // And also clear the queue up to this point. This leaves the current
  // message in place.
  transform_queue_.erase(transform_queue_.begin(), it);
  return true;
}

}  // namespace voxblox
