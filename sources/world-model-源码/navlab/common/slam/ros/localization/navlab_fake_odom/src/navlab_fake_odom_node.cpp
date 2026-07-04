#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>
#include <sstream>
#include <string>

#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

namespace {

geometry_msgs::msg::Quaternion yaw_to_quaternion(double yaw) {
  geometry_msgs::msg::Quaternion q;
  q.x = 0.0;
  q.y = 0.0;
  q.z = std::sin(yaw * 0.5);
  q.w = std::cos(yaw * 0.5);
  return q;
}

}  // namespace

class NavlabFakeOdomNode : public rclcpp::Node {
 public:
  NavlabFakeOdomNode() : Node("navlab_fake_odom_node") {
    mode_ = declare_parameter<std::string>("mode", "static");
    publish_rate_hz_ = declare_parameter("publish_rate_hz", 20.0);
    frame_id_ = declare_parameter<std::string>("frame_id", "odom");
    child_frame_id_ = declare_parameter<std::string>("child_frame_id", "base_link");
    odom_topic_ = declare_parameter<std::string>("odom_topic", "/odom");
    status_topic_ = declare_parameter<std::string>("status_topic", "/navlab/fake_odom/status");
    start_x_ = declare_parameter("start_x", 0.0);
    start_y_ = declare_parameter("start_y", 0.0);
    start_z_ = declare_parameter("start_z", 0.0);
    start_yaw_ = declare_parameter("start_yaw", 0.0);
    linear_velocity_x_ = declare_parameter("linear_velocity_x", 0.05);
    yaw_rate_ = declare_parameter("yaw_rate", 0.05);
    pose_covariance_xy_ = declare_parameter("pose_covariance_xy", 0.01);
    pose_covariance_yaw_ = declare_parameter("pose_covariance_yaw", 0.02);
    twist_covariance_xy_ = declare_parameter("twist_covariance_xy", 0.02);
    twist_covariance_yaw_ = declare_parameter("twist_covariance_yaw", 0.02);

    if (mode_ != "static" && mode_ != "line" && mode_ != "yaw") {
      RCLCPP_WARN(get_logger(), "unsupported mode '%s', falling back to static", mode_.c_str());
      mode_ = "static";
    }

    if (publish_rate_hz_ <= 0.0) {
      RCLCPP_WARN(get_logger(), "publish_rate_hz must be positive, falling back to 20.0");
      publish_rate_hz_ = 20.0;
    }

    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>(odom_topic_, 10);
    status_pub_ = create_publisher<std_msgs::msg::String>(status_topic_, 10);
    started_at_ = now();

    const auto period = std::chrono::duration<double>(1.0 / publish_rate_hz_);
    timer_ = create_wall_timer(
        std::chrono::duration_cast<std::chrono::nanoseconds>(period),
        std::bind(&NavlabFakeOdomNode::publish_tick, this));

    RCLCPP_INFO(get_logger(),
                "navlab_fake_odom started; mode=%s rate=%.3f odom_topic=%s frame=%s child=%s",
                mode_.c_str(), publish_rate_hz_, odom_topic_.c_str(), frame_id_.c_str(),
                child_frame_id_.c_str());
  }

 private:
  void publish_tick() {
    const auto stamp = now();
    const double elapsed_sec = std::max(0.0, (stamp - started_at_).seconds());

    nav_msgs::msg::Odometry odom;
    odom.header.stamp = stamp;
    odom.header.frame_id = frame_id_;
    odom.child_frame_id = child_frame_id_;
    odom.pose.pose.position.x = start_x_;
    odom.pose.pose.position.y = start_y_;
    odom.pose.pose.position.z = start_z_;

    double yaw = start_yaw_;
    if (mode_ == "line") {
      odom.pose.pose.position.x += linear_velocity_x_ * elapsed_sec;
      odom.twist.twist.linear.x = linear_velocity_x_;
    } else if (mode_ == "yaw") {
      yaw += yaw_rate_ * elapsed_sec;
      odom.twist.twist.angular.z = yaw_rate_;
    }

    odom.pose.pose.orientation = yaw_to_quaternion(yaw);
    odom.pose.covariance[0] = pose_covariance_xy_;
    odom.pose.covariance[7] = pose_covariance_xy_;
    odom.pose.covariance[35] = pose_covariance_yaw_;
    odom.twist.covariance[0] = twist_covariance_xy_;
    odom.twist.covariance[7] = twist_covariance_xy_;
    odom.twist.covariance[35] = twist_covariance_yaw_;
    odom_pub_->publish(odom);

    std_msgs::msg::String status;
    status.data = build_status(elapsed_sec, odom.pose.pose.position.x, yaw);
    status_pub_->publish(status);
  }

  std::string build_status(double elapsed_sec, double x, double yaw) const {
    std::ostringstream oss;
    oss << "mode=" << mode_;
    oss << " elapsed_sec=" << elapsed_sec;
    oss << " frame_id=" << frame_id_;
    oss << " child_frame_id=" << child_frame_id_;
    oss << " odom_topic=" << odom_topic_;
    oss << " rate_hz=" << publish_rate_hz_;
    oss << " x=" << x;
    oss << " yaw=" << yaw;
    return oss.str();
  }

  std::string mode_;
  double publish_rate_hz_;
  std::string frame_id_;
  std::string child_frame_id_;
  std::string odom_topic_;
  std::string status_topic_;
  double start_x_;
  double start_y_;
  double start_z_;
  double start_yaw_;
  double linear_velocity_x_;
  double yaw_rate_;
  double pose_covariance_xy_;
  double pose_covariance_yaw_;
  double twist_covariance_xy_;
  double twist_covariance_yaw_;

  rclcpp::Time started_at_{0, 0, RCL_ROS_TIME};
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<NavlabFakeOdomNode>());
  rclcpp::shutdown();
  return 0;
}
