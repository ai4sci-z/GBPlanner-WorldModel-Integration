#include <chrono>
#include <cmath>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>

#include "geometry_msgs/msg/transform_stamped.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "std_msgs/msg/string.hpp"
#include "tf2_msgs/msg/tf_message.hpp"

using namespace std::chrono_literals;

class NavlabCartographerAdapterNode : public rclcpp::Node {
 public:
  NavlabCartographerAdapterNode() : Node("navlab_cartographer_adapter_node") {
    scan_timeout_ms_ = declare_parameter("scan_timeout_ms", 500);
    imu_timeout_ms_ = declare_parameter("imu_timeout_ms", 500);
    tf_timeout_ms_ = declare_parameter("tf_timeout_ms", 500);
    max_tf_stamp_sec_ = declare_parameter("max_tf_stamp_sec", 100000000.0);
    max_tf_translation_m_ = declare_parameter("max_tf_translation_m", 100.0);
    max_tf_jump_m_ = declare_parameter("max_tf_jump_m", 2.0);
    max_tf_yaw_z_jump_ = declare_parameter("max_tf_yaw_z_jump", 1.0);
    publish_placeholder_odom_ =
        declare_parameter("publish_placeholder_odom", false);
    odom_source_mode_ =
        declare_parameter<std::string>("odom_source_mode", "slam_tf");
    map_frame_id_ = declare_parameter<std::string>("map_frame_id", "map");
    odom_frame_id_ = declare_parameter<std::string>("odom_frame_id", "odom");
    base_frame_id_ =
        declare_parameter<std::string>("base_frame_id", "base_link");
    tf_topic_ = declare_parameter<std::string>("tf_topic", "/tf");
    publish_global_tf_ = declare_parameter("publish_global_tf", false);
    cached_odom_publish_rate_hz_ =
        declare_parameter("cached_odom_publish_rate_hz", 10.0);
    global_tf_topic_ = declare_parameter<std::string>("global_tf_topic", "/tf");
    scan_topic_ = declare_parameter<std::string>("scan_topic", "/scan");
    imu_topic_ = declare_parameter<std::string>("imu_topic", "/imu/data");
    odom_topic_ = declare_parameter<std::string>("odom_topic", "/odom");
    status_topic_ =
        declare_parameter<std::string>("status_topic", "/navlab/slam/status");

    status_pub_ = create_publisher<std_msgs::msg::String>(
        status_topic_, 10);
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>(odom_topic_, 10);
    if (publish_global_tf_) {
      global_tf_pub_ =
          create_publisher<tf2_msgs::msg::TFMessage>(global_tf_topic_, 10);
    }

    scan_sub_ = create_subscription<sensor_msgs::msg::LaserScan>(
        scan_topic_, rclcpp::SensorDataQoS(),
        std::bind(&NavlabCartographerAdapterNode::handle_scan, this, std::placeholders::_1));

    imu_sub_ = create_subscription<sensor_msgs::msg::Imu>(
        imu_topic_, 10,
        std::bind(&NavlabCartographerAdapterNode::handle_imu, this, std::placeholders::_1));

    if (odom_source_mode_ == "slam_tf" || odom_source_mode_ == "tf") {
      tf_sub_ = create_subscription<tf2_msgs::msg::TFMessage>(
          tf_topic_, 10,
          std::bind(&NavlabCartographerAdapterNode::handle_tf, this, std::placeholders::_1));
    } else if (odom_source_mode_ != "placeholder") {
      RCLCPP_WARN(get_logger(),
                  "unsupported odom_source_mode '%s', using placeholder mode",
                  odom_source_mode_.c_str());
      odom_source_mode_ = "placeholder";
      publish_placeholder_odom_ = true;
    }

    timer_ = create_wall_timer(
        500ms, std::bind(&NavlabCartographerAdapterNode::publish_status, this));
    if (cached_odom_publish_rate_hz_ > 0.0) {
      const auto odom_period =
          std::chrono::duration<double>(1.0 / cached_odom_publish_rate_hz_);
      odom_timer_ = create_wall_timer(
          std::chrono::duration_cast<std::chrono::nanoseconds>(odom_period),
          std::bind(&NavlabCartographerAdapterNode::publish_cached_odom_if_fresh, this));
    }

    RCLCPP_INFO(get_logger(),
                "navlab_cartographer_adapter started; mode=%s scan_topic=%s imu_topic=%s tf_topic=%s odom_topic=%s status_topic=%s map_frame=%s odom_frame=%s base_frame=%s publish_global_tf=%s global_tf_topic=%s cached_odom_publish_rate_hz=%.3f",
                odom_source_mode_.c_str(), scan_topic_.c_str(), imu_topic_.c_str(),
                tf_topic_.c_str(), odom_topic_.c_str(), status_topic_.c_str(),
                map_frame_id_.c_str(), odom_frame_id_.c_str(), base_frame_id_.c_str(),
                publish_global_tf_ ? "true" : "false", global_tf_topic_.c_str(),
                cached_odom_publish_rate_hz_);
  }

 private:
  void handle_scan(const sensor_msgs::msg::LaserScan::SharedPtr msg) {
    last_scan_ = msg;
    last_scan_time_ = now();
    ++scan_count_;
  }

  void handle_imu(const sensor_msgs::msg::Imu::SharedPtr msg) {
    last_imu_ = msg;
    last_imu_time_ = now();
    ++imu_count_;
  }

  void handle_tf(const tf2_msgs::msg::TFMessage::SharedPtr msg) {
    for (const auto &transform : msg->transforms) {
      if (transform.header.frame_id == expected_tf_parent_frame() &&
          transform.child_frame_id == base_frame_id_) {
        ++tf_received_count_;
        const double candidate_jump_m = horizontal_jump_from_last(transform);
        const double candidate_yaw_z_jump = yaw_z_jump_from_last(transform);
        if (candidate_jump_m >= 0.0 && candidate_jump_m > max_tf_observed_jump_m_) {
          max_tf_observed_jump_m_ = candidate_jump_m;
        }
        if (candidate_yaw_z_jump >= 0.0 && candidate_yaw_z_jump > max_tf_observed_yaw_z_jump_) {
          max_tf_observed_yaw_z_jump_ = candidate_yaw_z_jump;
        }
        if (!is_acceptable_odom_transform(transform)) {
          ++tf_rejected_count_;
          if (candidate_jump_m >= 0.0 && candidate_jump_m > max_tf_rejected_jump_m_) {
            max_tf_rejected_jump_m_ = candidate_jump_m;
          }
          if (candidate_yaw_z_jump >= 0.0 && candidate_yaw_z_jump > max_tf_rejected_yaw_z_jump_) {
            max_tf_rejected_yaw_z_jump_ = candidate_yaw_z_jump;
          }
          RCLCPP_WARN_THROTTLE(
              get_logger(), *get_clock(), 2000,
              "rejected odom TF stamp=%d.%09u x=%.3f y=%.3f z=%.3f rejected=%llu",
              transform.header.stamp.sec, transform.header.stamp.nanosec,
              transform.transform.translation.x, transform.transform.translation.y,
              transform.transform.translation.z,
              static_cast<unsigned long long>(tf_rejected_count_));
          continue;
        }
        if (candidate_jump_m >= 0.0 && candidate_jump_m > max_tf_accepted_jump_m_) {
          max_tf_accepted_jump_m_ = candidate_jump_m;
        }
        if (candidate_yaw_z_jump >= 0.0 && candidate_yaw_z_jump > max_tf_accepted_yaw_z_jump_) {
          max_tf_accepted_yaw_z_jump_ = candidate_yaw_z_jump;
        }
        last_odom_transform_ =
            std::make_shared<geometry_msgs::msg::TransformStamped>(transform);
        last_tf_time_ = now();
        ++tf_count_;
        publish_odom_from_transform(transform);
      }
    }
  }

  void publish_status() {
    const bool scan_ok = has_recent(last_scan_time_, scan_timeout_ms_, last_scan_);
    const bool imu_ok = has_recent(last_imu_time_, imu_timeout_ms_, last_imu_);
    const bool tf_present = static_cast<bool>(last_odom_transform_);
    const bool tf_fresh = has_recent(last_tf_time_, tf_timeout_ms_, last_odom_transform_);
    const bool publishing_placeholder =
        publish_placeholder_odom_ || odom_source_mode_ == "placeholder";
    const bool odom_ready =
        publishing_placeholder ||
        ((odom_source_mode_ == "slam_tf" || odom_source_mode_ == "tf") && tf_present);

    std_msgs::msg::String status;
    if (!scan_ok && !imu_ok) {
      status.data = build_status("waiting_for_scan_and_imu", false, scan_ok, imu_ok, tf_present, tf_fresh);
    } else if (!scan_ok) {
      status.data = build_status("waiting_for_scan", false, scan_ok, imu_ok, tf_present, tf_fresh);
    } else if (!imu_ok) {
      status.data = build_status("waiting_for_imu", false, scan_ok, imu_ok, tf_present, tf_fresh);
    } else if (publishing_placeholder) {
      publish_placeholder_odom();
      status.data = build_status("publishing_placeholder_odom", true, scan_ok, imu_ok, tf_present, tf_fresh);
    } else if (odom_source_mode_ == "slam_tf" || odom_source_mode_ == "tf") {
      status.data = build_status(tf_present ? "publishing_cached_slam_tf_odom"
                                            : "waiting_for_cartographer_tf",
                                 odom_ready, scan_ok, imu_ok, tf_present, tf_fresh);
    } else {
      status.data = build_status("waiting_for_cartographer_backend", false, scan_ok,
                                 imu_ok, tf_present, tf_fresh);
    }

    status_pub_->publish(status);
  }

  template <typename SharedPtrT>
  bool has_recent(const rclcpp::Time &stamp, int timeout_ms,
                  const SharedPtrT &msg) const {
    if (!msg) {
      return false;
    }

    return (now() - stamp).nanoseconds() <
           static_cast<int64_t>(timeout_ms) * 1000000LL;
  }

  double age_ms(const rclcpp::Time &stamp, const std::shared_ptr<void const> &msg) const {
    if (!msg) {
      return -1.0;
    }
    return static_cast<double>((now() - stamp).nanoseconds()) / 1000000.0;
  }

  static std::string json_escape(const std::string &value) {
    std::ostringstream escaped;
    for (const char ch : value) {
      switch (ch) {
        case '"':
          escaped << "\\\"";
          break;
        case '\\':
          escaped << "\\\\";
          break;
        case '\n':
          escaped << "\\n";
          break;
        default:
          escaped << ch;
          break;
      }
    }
    return escaped.str();
  }

  std::string build_status(const std::string &state, bool ready, bool scan_ok,
                           bool imu_ok, bool tf_present, bool tf_fresh) const {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(3);
    oss << "{";
    oss << "\"state\":\"" << json_escape(state) << "\",";
    oss << "\"ready\":" << (ready ? "true" : "false") << ",";
    oss << "\"mode\":\"" << json_escape(odom_source_mode_) << "\",";
    oss << "\"scan\":{";
    oss << "\"present\":" << (last_scan_ ? "true" : "false") << ",";
    oss << "\"fresh\":" << (scan_ok ? "true" : "false") << ",";
    oss << "\"age_ms\":" << age_ms(last_scan_time_, last_scan_) << ",";
    oss << "\"count\":" << scan_count_ << "},";
    oss << "\"imu\":{";
    oss << "\"present\":" << (last_imu_ ? "true" : "false") << ",";
    oss << "\"fresh\":" << (imu_ok ? "true" : "false") << ",";
    oss << "\"age_ms\":" << age_ms(last_imu_time_, last_imu_) << ",";
    oss << "\"count\":" << imu_count_ << "},";
    oss << "\"tf\":{";
    oss << "\"present\":" << (tf_present ? "true" : "false") << ",";
    oss << "\"fresh\":" << (tf_fresh ? "true" : "false") << ",";
    oss << "\"age_ms\":" << age_ms(last_tf_time_, last_odom_transform_) << ",";
    oss << "\"count\":" << tf_count_ << ",";
    oss << "\"received_count\":" << tf_received_count_ << ",";
    oss << "\"rejected_count\":" << tf_rejected_count_ << ",";
    oss << "\"rejection_ratio\":" << rejection_ratio() << ",";
    oss << "\"max_observed_jump_m\":" << max_tf_observed_jump_m_ << ",";
    oss << "\"max_accepted_jump_m\":" << max_tf_accepted_jump_m_ << ",";
    oss << "\"max_rejected_jump_m\":" << max_tf_rejected_jump_m_ << ",";
    oss << "\"max_allowed_jump_m\":" << max_tf_jump_m_ << ",";
    oss << "\"max_observed_yaw_z_jump\":" << max_tf_observed_yaw_z_jump_ << ",";
    oss << "\"max_accepted_yaw_z_jump\":" << max_tf_accepted_yaw_z_jump_ << ",";
    oss << "\"max_rejected_yaw_z_jump\":" << max_tf_rejected_yaw_z_jump_ << ",";
    oss << "\"max_allowed_yaw_z_jump\":" << max_tf_yaw_z_jump_ << ",";
    oss << "\"topic\":\"" << json_escape(tf_topic_) << "\",";
    oss << "\"frame_id\":\"" << json_escape(expected_tf_parent_frame()) << "\",";
    oss << "\"child_frame_id\":\"" << json_escape(base_frame_id_) << "\"},";
    oss << "\"output\":{";
    oss << "\"odom_topic\":\"" << json_escape(odom_topic_) << "\",";
    oss << "\"status_topic\":\"" << json_escape(status_topic_) << "\",";
    oss << "\"publish_global_tf\":" << (publish_global_tf_ ? "true" : "false") << ",";
    oss << "\"global_tf_topic\":\"" << json_escape(global_tf_topic_) << "\",";
    oss << "\"odom_count\":" << odom_count_ << ",";
    oss << "\"last_x\":" << last_odom_x_ << ",";
    oss << "\"last_y\":" << last_odom_y_ << ",";
    oss << "\"last_yaw_z\":" << last_odom_yaw_z_ << "}";
    oss << "}";
    return oss.str();
  }

  std::string expected_tf_parent_frame() const {
    if (odom_source_mode_ == "tf") {
      return odom_frame_id_;
    }
    return map_frame_id_;
  }

  double horizontal_jump_from_last(
      const geometry_msgs::msg::TransformStamped &transform) const {
    if (!has_published_odom_) {
      return -1.0;
    }
    const auto &translation = transform.transform.translation;
    return std::hypot(translation.x - last_odom_x_, translation.y - last_odom_y_);
  }

  double yaw_z_jump_from_last(
      const geometry_msgs::msg::TransformStamped &transform) const {
    if (!has_published_odom_) {
      return -1.0;
    }
    return std::abs(transform.transform.rotation.z - last_odom_yaw_z_);
  }

  double rejection_ratio() const {
    if (tf_received_count_ == 0) {
      return 0.0;
    }
    return static_cast<double>(tf_rejected_count_) /
           static_cast<double>(tf_received_count_);
  }

  bool is_acceptable_odom_transform(
      const geometry_msgs::msg::TransformStamped &transform) const {
    const double stamp_sec =
        static_cast<double>(transform.header.stamp.sec) +
        static_cast<double>(transform.header.stamp.nanosec) * 1e-9;
    const auto &translation = transform.transform.translation;
    const auto &rotation = transform.transform.rotation;
    if (stamp_sec > max_tf_stamp_sec_) {
      return false;
    }
    if (!std::isfinite(translation.x) || !std::isfinite(translation.y) ||
        !std::isfinite(translation.z) || !std::isfinite(rotation.x) ||
        !std::isfinite(rotation.y) || !std::isfinite(rotation.z) ||
        !std::isfinite(rotation.w)) {
      return false;
    }
    if (std::hypot(translation.x, translation.y) > max_tf_translation_m_) {
      return false;
    }
    if (has_published_odom_) {
      if (std::hypot(translation.x - last_odom_x_,
                     translation.y - last_odom_y_) > max_tf_jump_m_) {
        return false;
      }
      if (std::abs(rotation.z - last_odom_yaw_z_) > max_tf_yaw_z_jump_) {
        return false;
      }
    }
    return true;
  }

  void publish_odom_from_transform(
      const geometry_msgs::msg::TransformStamped &transform) {
    nav_msgs::msg::Odometry odom;
    odom.header = transform.header;
    odom.child_frame_id = transform.child_frame_id;
    odom.pose.pose.position.x = transform.transform.translation.x;
    odom.pose.pose.position.y = transform.transform.translation.y;
    odom.pose.pose.position.z = transform.transform.translation.z;
    odom.pose.pose.orientation = transform.transform.rotation;

    // Cartographer 2D only estimates planar pose. Keep z/roll/pitch covariance
    // large so downstream ExternalNav consumers do not treat zero altitude as a
    // measured height and fight the FCU rangefinder/baro vertical estimator.
    odom.pose.covariance[0] = 0.05;
    odom.pose.covariance[7] = 0.05;
    odom.pose.covariance[14] = 9999.0;
    odom.pose.covariance[21] = 9999.0;
    odom.pose.covariance[28] = 9999.0;
    odom.pose.covariance[35] = 0.1;
    odom.twist.covariance[0] = 0.5;
    odom.twist.covariance[7] = 0.5;
    odom.twist.covariance[14] = 9999.0;
    odom.twist.covariance[21] = 9999.0;
    odom.twist.covariance[28] = 9999.0;
    odom.twist.covariance[35] = 1.0;

    if (last_imu_) {
      odom.twist.twist.angular = last_imu_->angular_velocity;
    }

    publish_global_tf_from_transform(transform);
    last_odom_x_ = odom.pose.pose.position.x;
    last_odom_y_ = odom.pose.pose.position.y;
    last_odom_yaw_z_ = odom.pose.pose.orientation.z;
    has_published_odom_ = true;
    ++odom_count_;
    odom_pub_->publish(odom);
  }

  void publish_global_tf_from_transform(
      const geometry_msgs::msg::TransformStamped &transform) {
    if (!publish_global_tf_ || !global_tf_pub_) {
      return;
    }
    tf2_msgs::msg::TFMessage message;
    message.transforms.push_back(transform);
    global_tf_pub_->publish(message);
  }

  void publish_odom_from_cached_transform() {
    if (!last_odom_transform_) {
      return;
    }

    auto transform = *last_odom_transform_;
    transform.header.stamp = now();
    publish_odom_from_transform(transform);
  }

  void publish_cached_odom_if_fresh() {
    if (!(odom_source_mode_ == "slam_tf" || odom_source_mode_ == "tf")) {
      return;
    }
    if (!has_recent(last_tf_time_, tf_timeout_ms_, last_odom_transform_)) {
      return;
    }
    publish_odom_from_cached_transform();
  }

  void publish_placeholder_odom() {
    nav_msgs::msg::Odometry odom;
    odom.header.stamp = now();
    odom.header.frame_id = odom_frame_id_;
    odom.child_frame_id = base_frame_id_;

    if (last_imu_) {
      odom.pose.pose.orientation = last_imu_->orientation;
      odom.twist.twist.angular = last_imu_->angular_velocity;
    } else {
      odom.pose.pose.orientation.w = 1.0;
    }

    odom.pose.covariance[0] = 0.25;
    odom.pose.covariance[7] = 0.25;
    odom.pose.covariance[14] = 9999.0;
    odom.pose.covariance[21] = 9999.0;
    odom.pose.covariance[28] = 9999.0;
    odom.pose.covariance[35] = 0.5;
    odom.twist.covariance[0] = 0.5;
    odom.twist.covariance[7] = 0.5;
    odom.twist.covariance[14] = 9999.0;
    odom.twist.covariance[21] = 9999.0;
    odom.twist.covariance[28] = 9999.0;
    odom.twist.covariance[35] = 1.0;

    last_odom_x_ = odom.pose.pose.position.x;
    last_odom_y_ = odom.pose.pose.position.y;
    last_odom_yaw_z_ = odom.pose.pose.orientation.z;
    has_published_odom_ = true;
    ++odom_count_;
    odom_pub_->publish(odom);
  }

  int scan_timeout_ms_;
  int imu_timeout_ms_;
  int tf_timeout_ms_;
  double max_tf_stamp_sec_;
  double max_tf_translation_m_;
  double max_tf_jump_m_;
  double max_tf_yaw_z_jump_;
  bool publish_placeholder_odom_;
  bool publish_global_tf_;
  double cached_odom_publish_rate_hz_;
  bool has_published_odom_{false};
  std::string odom_source_mode_;
  std::string map_frame_id_;
  std::string odom_frame_id_;
  std::string base_frame_id_;
  std::string tf_topic_;
  std::string global_tf_topic_;
  std::string scan_topic_;
  std::string imu_topic_;
  std::string odom_topic_;
  std::string status_topic_;
  uint64_t scan_count_{0};
  uint64_t imu_count_{0};
  uint64_t tf_received_count_{0};
  uint64_t tf_rejected_count_{0};
  uint64_t tf_count_{0};
  uint64_t odom_count_{0};
  double max_tf_observed_jump_m_{0.0};
  double max_tf_accepted_jump_m_{0.0};
  double max_tf_rejected_jump_m_{0.0};
  double max_tf_observed_yaw_z_jump_{0.0};
  double max_tf_accepted_yaw_z_jump_{0.0};
  double max_tf_rejected_yaw_z_jump_{0.0};
  double last_odom_x_{0.0};
  double last_odom_y_{0.0};
  double last_odom_yaw_z_{0.0};

  sensor_msgs::msg::LaserScan::SharedPtr last_scan_;
  sensor_msgs::msg::Imu::SharedPtr last_imu_;
  geometry_msgs::msg::TransformStamped::SharedPtr last_odom_transform_;
  rclcpp::Time last_scan_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_imu_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time last_tf_time_{0, 0, RCL_ROS_TIME};

  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr scan_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<tf2_msgs::msg::TFMessage>::SharedPtr tf_sub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<tf2_msgs::msg::TFMessage>::SharedPtr global_tf_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::TimerBase::SharedPtr odom_timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<NavlabCartographerAdapterNode>());
  rclcpp::shutdown();
  return 0;
}
