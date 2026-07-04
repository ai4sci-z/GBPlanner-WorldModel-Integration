#include <algorithm>
#include <array>
#include <chrono>
#include <exception>
#include <cmath>
#include <iomanip>
#include <memory>
#include <optional>
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

constexpr double kPi = 3.14159265358979323846;

class NavlabExternalNavBridgeNode : public rclcpp::Node {
 public:
  NavlabExternalNavBridgeNode() : Node("navlab_external_nav_bridge_node") {
    odom_timeout_ms_ = declare_parameter("odom_timeout_ms", 500);
    imu_timeout_ms_ = declare_parameter("imu_timeout_ms", 500);
    height_timeout_ms_ = declare_parameter("height_timeout_ms", 500);
    require_imu_for_output_ = declare_parameter("require_imu_for_output", false);
    require_height_for_output_ =
        declare_parameter("require_height_for_output", true);
    output_frame_id_ =
        declare_parameter<std::string>("output_frame_id", "external_nav");
    output_child_frame_id_ =
        declare_parameter<std::string>("output_child_frame_id", "base_link");
    input_odom_topic_ =
        declare_parameter<std::string>("input_odom_topic", "/odom");
    imu_topic_ = declare_parameter<std::string>("imu_topic", "/imu/data");
    output_odom_topic_ =
        declare_parameter<std::string>("output_odom_topic", "/external_nav/odom");
    status_topic_ =
        declare_parameter<std::string>("status_topic", "/external_nav/status");
    ap_tf_topic_ = declare_parameter<std::string>("ap_tf_topic", "/ap/tf");
    ap_tf_parent_frame_ =
        declare_parameter<std::string>("ap_tf_parent_frame", "odom");
    ap_tf_child_frame_ =
        declare_parameter<std::string>("ap_tf_child_frame", "base_link");
    expected_odom_frame_id_ =
        declare_parameter<std::string>("expected_odom_frame_id", "odom");
    expected_odom_child_frame_id_ =
        declare_parameter<std::string>("expected_odom_child_frame_id", "base_link");
    min_odom_rate_hz_ = declare_parameter("min_odom_rate_hz", 4.0);
    min_imu_rate_hz_ = declare_parameter("min_imu_rate_hz", 4.0);
    min_scan_rate_hz_ = declare_parameter("min_scan_rate_hz", 2.0);
    scan_timeout_ms_ = declare_parameter("scan_timeout_ms", 1000);
    require_imu_for_quality_ =
        declare_parameter("require_imu_for_quality", false);
    require_scan_for_quality_ =
        declare_parameter("require_scan_for_quality", false);
    slam_quality_gate_enabled_ =
        declare_parameter("slam_quality_gate_enabled", true);
    low_observability_mode_ =
        declare_parameter("low_observability_mode", false);
    max_position_jump_m_ = declare_parameter("max_position_jump_m", 0.75);
    max_yaw_jump_rad_ = declare_parameter("max_yaw_jump_rad", 0.75);
    jump_hold_ms_ = declare_parameter("jump_hold_ms", 2000);
    min_observable_horizontal_span_m_ =
        declare_parameter("min_observable_horizontal_span_m", 0.10);
    min_scan_valid_ratio_for_quality_ =
        declare_parameter("min_scan_valid_ratio_for_quality", 0.50);
    min_scan_hit_ratio_for_quality_ =
        declare_parameter("min_scan_hit_ratio_for_quality", 0.25);
    min_scan_range_span_m_for_quality_ =
        declare_parameter("min_scan_range_span_m_for_quality", 1.0);
    min_scan_range_stddev_m_for_quality_ =
        declare_parameter("min_scan_range_stddev_m_for_quality", 0.20);
    min_scan_observed_quadrants_for_quality_ =
        declare_parameter("min_scan_observed_quadrants_for_quality", 3);
    scan_max_range_hit_margin_m_ =
        declare_parameter("scan_max_range_hit_margin_m", 0.05);
    max_height_covariance_ = declare_parameter("max_height_covariance", 4.0);
    height_topic_ =
        declare_parameter<std::string>("height_topic", "/height/estimate");
    scan_topic_ = declare_parameter<std::string>("scan_topic", "/scan");
    coordinate_mode_ =
        declare_parameter<std::string>("coordinate_mode", "pass_through_enu_flu");

    status_pub_ = create_publisher<std_msgs::msg::String>(
        status_topic_, 10);
    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>(
        output_odom_topic_, 10);
    ap_tf_pub_ = create_publisher<tf2_msgs::msg::TFMessage>(ap_tf_topic_, 10);

    odom_sub_ = create_subscription<nav_msgs::msg::Odometry>(
        input_odom_topic_, 10,
        std::bind(&NavlabExternalNavBridgeNode::handle_odom, this, std::placeholders::_1));

    imu_sub_ = create_subscription<sensor_msgs::msg::Imu>(
        imu_topic_, 10,
        std::bind(&NavlabExternalNavBridgeNode::handle_imu, this, std::placeholders::_1));

    scan_sub_ = create_subscription<sensor_msgs::msg::LaserScan>(
        scan_topic_, rclcpp::SensorDataQoS(),
        std::bind(&NavlabExternalNavBridgeNode::handle_scan, this, std::placeholders::_1));

    height_sub_ = create_subscription<std_msgs::msg::String>(
        height_topic_, 10,
        std::bind(&NavlabExternalNavBridgeNode::handle_height, this, std::placeholders::_1));

    timer_ = create_wall_timer(
        500ms, std::bind(&NavlabExternalNavBridgeNode::publish_status, this));

    const std::string imu_requirement =
        require_imu_for_output_ ? " and " + imu_topic_ : "";
    RCLCPP_INFO(get_logger(),
                "navlab_external_nav_bridge started; waiting for %s%s%s coordinate_mode=%s",
                input_odom_topic_.c_str(),
                imu_requirement.c_str(),
                require_height_for_output_ ? " and /height/estimate" : "",
                coordinate_mode_.c_str());
  }

 private:
  using SteadyClock = std::chrono::steady_clock;

  struct HeightEstimate {
    double z{0.0};
    double vz{0.0};
    double covariance{0.0};
    std::string source_type;
  };

  struct SlamQuality {
    std::string level{"bad"};
    std::string reason{"waiting_for_odom"};
    bool good{false};
  };

  void handle_odom(const nav_msgs::msg::Odometry::SharedPtr msg) {
    const auto stamp = SteadyClock::now();
    if (last_odom_) {
      const std::chrono::duration<double> delta = stamp - last_odom_wall_time_;
      const double delta_sec = delta.count();
      if (delta_sec > 0.0) {
        if (odom_rate_hz_ <= 0.0) {
          odom_rate_hz_ = 1.0 / delta_sec;
        } else {
          odom_rate_hz_ = 0.8 * odom_rate_hz_ + 0.2 * (1.0 / delta_sec);
        }
      }
      last_position_jump_m_ = horizontal_distance(*last_odom_, *msg);
      max_observed_position_jump_m_ =
          std::max(max_observed_position_jump_m_, last_position_jump_m_);
      last_yaw_jump_rad_ =
          std::abs(normalize_angle(yaw_from_odom(*msg) - yaw_from_odom(*last_odom_)));
      max_observed_yaw_jump_rad_ =
          std::max(max_observed_yaw_jump_rad_, last_yaw_jump_rad_);
      if (last_position_jump_m_ > max_position_jump_m_ ||
          last_yaw_jump_rad_ > max_yaw_jump_rad_) {
        last_jump_wall_time_ = stamp;
      }
    }
    update_horizontal_span(*msg);
    last_odom_ = msg;
    last_odom_wall_time_ = stamp;
  }

  void handle_imu(const sensor_msgs::msg::Imu::SharedPtr msg) {
    const auto stamp = SteadyClock::now();
    if (last_imu_) {
      const std::chrono::duration<double> delta = stamp - last_imu_wall_time_;
      const double delta_sec = delta.count();
      if (delta_sec > 0.0) {
        if (imu_rate_hz_ <= 0.0) {
          imu_rate_hz_ = 1.0 / delta_sec;
        } else {
          imu_rate_hz_ = 0.8 * imu_rate_hz_ + 0.2 * (1.0 / delta_sec);
        }
      }
    }
    last_imu_ = msg;
    last_imu_wall_time_ = stamp;
  }

  void handle_scan(const sensor_msgs::msg::LaserScan::SharedPtr msg) {
    const auto stamp = SteadyClock::now();
    if (last_scan_) {
      const std::chrono::duration<double> delta = stamp - last_scan_wall_time_;
      const double delta_sec = delta.count();
      if (delta_sec > 0.0) {
        if (scan_rate_hz_ <= 0.0) {
          scan_rate_hz_ = 1.0 / delta_sec;
        } else {
          scan_rate_hz_ = 0.8 * scan_rate_hz_ + 0.2 * (1.0 / delta_sec);
        }
      }
    }
    update_scan_geometry_metrics(*msg);
    last_scan_ = msg;
    last_scan_wall_time_ = stamp;
  }

  void handle_height(const std_msgs::msg::String::SharedPtr msg) {
    last_height_raw_ = msg;
    last_height_wall_time_ = SteadyClock::now();
    last_height_ = parse_height_estimate(msg->data);
  }

  void publish_status() {
    const auto stamp = SteadyClock::now();
    const double odom_age_ms = age_ms(stamp, last_odom_wall_time_, last_odom_);
    const double imu_age_ms = age_ms(stamp, last_imu_wall_time_, last_imu_);
    const double height_age_ms =
        age_ms(stamp, last_height_wall_time_, last_height_raw_);
    const double scan_age_ms = age_ms(stamp, last_scan_wall_time_, last_scan_);
    const bool odom_fresh = last_odom_ && odom_age_ms >= 0.0 &&
                            odom_age_ms < static_cast<double>(odom_timeout_ms_);
    const bool imu_ok =
        last_imu_ && imu_age_ms >= 0.0 &&
        imu_age_ms < static_cast<double>(imu_timeout_ms_);
    const bool scan_ok =
        last_scan_ && scan_age_ms >= 0.0 &&
        scan_age_ms < static_cast<double>(scan_timeout_ms_);
    const bool frame_ok = odom_frame_ok();
    const bool rate_ok = odom_rate_hz_ >= min_odom_rate_hz_;
    const bool odom_ok = odom_fresh && frame_ok && rate_ok;
    const bool height_fresh =
        last_height_raw_ && height_age_ms >= 0.0 &&
        height_age_ms < static_cast<double>(height_timeout_ms_);
    const bool height_parse_ok = last_height_.has_value();
    const bool height_covariance_ok =
        height_parse_ok && last_height_->covariance >= 0.0 &&
        last_height_->covariance <= max_height_covariance_;
    const bool height_ok =
        height_fresh && height_parse_ok && height_covariance_ok;

    const SlamQuality slam_quality =
        evaluate_slam_quality(stamp, odom_fresh, frame_ok, rate_ok, imu_ok,
                              scan_ok, odom_age_ms, imu_age_ms, scan_age_ms);
    const bool quality_ok = !slam_quality_gate_enabled_ || slam_quality.good;
    const bool ready = odom_ok && quality_ok && (!require_imu_for_output_ || imu_ok) &&
                       (!require_height_for_output_ || height_ok);

    if (ready) {
      publish_external_nav_odom();
    }

    std_msgs::msg::String status;
    status.data =
        build_status(odom_fresh, frame_ok, rate_ok, imu_ok, height_fresh,
                     height_parse_ok, height_covariance_ok, ready, odom_age_ms,
                     imu_age_ms, height_age_ms, scan_ok, scan_age_ms,
                     slam_quality);
    status_pub_->publish(status);
  }

  void publish_external_nav_odom() {
    if (!last_odom_ || !last_height_) {
      return;
    }

    nav_msgs::msg::Odometry out = *last_odom_;
    out.header.stamp = now();
    out.header.frame_id = output_frame_id_;
    out.child_frame_id = output_child_frame_id_;
    out.pose.pose.position.z = last_height_->z;
    out.twist.twist.linear.z = last_height_->vz;
    out.pose.covariance[14] = last_height_->covariance;
    out.twist.covariance[14] = last_height_->covariance;
    odom_pub_->publish(out);

    tf2_msgs::msg::TFMessage ap_tf_msg;
    geometry_msgs::msg::TransformStamped transform;
    transform.header.stamp = out.header.stamp;
    transform.header.frame_id = ap_tf_parent_frame_;
    transform.child_frame_id = ap_tf_child_frame_;
    transform.transform.translation.x = out.pose.pose.position.x;
    transform.transform.translation.y = out.pose.pose.position.y;
    transform.transform.translation.z = out.pose.pose.position.z;
    transform.transform.rotation = out.pose.pose.orientation;
    ap_tf_msg.transforms.push_back(transform);
    ap_tf_pub_->publish(ap_tf_msg);
  }

  double age_ms(const SteadyClock::time_point &now_stamp,
                const SteadyClock::time_point &last_stamp,
                const std::shared_ptr<void const> &msg) const {
    if (!msg) {
      return -1.0;
    }
    return std::chrono::duration<double, std::milli>(now_stamp - last_stamp).count();
  }

  bool odom_frame_ok() const {
    if (!last_odom_) {
      return false;
    }
    return last_odom_->header.frame_id == expected_odom_frame_id_ &&
           last_odom_->child_frame_id == expected_odom_child_frame_id_;
  }

  double yaw_from_odom(const nav_msgs::msg::Odometry &odom) const {
    const auto &q = odom.pose.pose.orientation;
    const double siny_cosp = 2.0 * ((q.w * q.z) + (q.x * q.y));
    const double cosy_cosp = 1.0 - (2.0 * ((q.y * q.y) + (q.z * q.z)));
    return std::atan2(siny_cosp, cosy_cosp);
  }

  double normalize_angle(double angle_rad) const {
    while (angle_rad > kPi) {
      angle_rad -= 2.0 * kPi;
    }
    while (angle_rad < -kPi) {
      angle_rad += 2.0 * kPi;
    }
    return angle_rad;
  }

  double horizontal_distance(const nav_msgs::msg::Odometry &a,
                             const nav_msgs::msg::Odometry &b) const {
    const double dx = a.pose.pose.position.x - b.pose.pose.position.x;
    const double dy = a.pose.pose.position.y - b.pose.pose.position.y;
    return std::hypot(dx, dy);
  }

  void update_horizontal_span(const nav_msgs::msg::Odometry &odom) {
    const double x = odom.pose.pose.position.x;
    const double y = odom.pose.pose.position.y;
    if (!horizontal_bounds_initialized_) {
      min_x_ = max_x_ = x;
      min_y_ = max_y_ = y;
      horizontal_bounds_initialized_ = true;
      return;
    }
    min_x_ = std::min(min_x_, x);
    max_x_ = std::max(max_x_, x);
    min_y_ = std::min(min_y_, y);
    max_y_ = std::max(max_y_, y);
  }

  double horizontal_span_m() const {
    if (!horizontal_bounds_initialized_) {
      return 0.0;
    }
    return std::hypot(max_x_ - min_x_, max_y_ - min_y_);
  }

  bool jump_hold_active(const SteadyClock::time_point &stamp) const {
    if (last_jump_wall_time_ == SteadyClock::time_point{}) {
      return false;
    }
    return std::chrono::duration<double, std::milli>(stamp - last_jump_wall_time_).count() <
           static_cast<double>(jump_hold_ms_);
  }

  void update_scan_geometry_metrics(const sensor_msgs::msg::LaserScan &scan) {
    const int beam_count = static_cast<int>(scan.ranges.size());
    last_scan_beam_count_ = beam_count;
    last_scan_valid_beam_count_ = 0;
    last_scan_hit_beam_count_ = 0;
    last_scan_valid_ratio_ = 0.0;
    last_scan_hit_ratio_ = 0.0;
    last_scan_range_span_m_ = 0.0;
    last_scan_range_stddev_m_ = 0.0;
    last_scan_observed_quadrants_ = 0;
    if (beam_count <= 0) {
      return;
    }

    std::array<int, 4> hit_quadrants{0, 0, 0, 0};
    double min_hit_range = 0.0;
    double max_hit_range = 0.0;
    double hit_sum = 0.0;
    double hit_sum_sq = 0.0;
    const double hit_upper =
        scan.range_max > scan_max_range_hit_margin_m_
            ? scan.range_max - scan_max_range_hit_margin_m_
            : scan.range_max;

    for (int index = 0; index < beam_count; ++index) {
      const float range = scan.ranges[static_cast<size_t>(index)];
      if (!std::isfinite(range) || range < scan.range_min || range > scan.range_max) {
        continue;
      }
      ++last_scan_valid_beam_count_;
      if (range >= hit_upper) {
        continue;
      }

      if (last_scan_hit_beam_count_ == 0) {
        min_hit_range = max_hit_range = range;
      } else {
        min_hit_range = std::min(min_hit_range, static_cast<double>(range));
        max_hit_range = std::max(max_hit_range, static_cast<double>(range));
      }
      hit_sum += range;
      hit_sum_sq += static_cast<double>(range) * static_cast<double>(range);
      ++last_scan_hit_beam_count_;

      const double angle = normalize_angle(
          scan.angle_min + static_cast<double>(index) * scan.angle_increment);
      int quadrant = 3;
      if (angle >= -kPi / 4.0 && angle < kPi / 4.0) {
        quadrant = 0;
      } else if (angle >= kPi / 4.0 && angle < 3.0 * kPi / 4.0) {
        quadrant = 1;
      } else if (angle >= 3.0 * kPi / 4.0 || angle < -3.0 * kPi / 4.0) {
        quadrant = 2;
      }
      ++hit_quadrants[static_cast<size_t>(quadrant)];
    }

    last_scan_valid_ratio_ =
        static_cast<double>(last_scan_valid_beam_count_) / static_cast<double>(beam_count);
    last_scan_hit_ratio_ =
        static_cast<double>(last_scan_hit_beam_count_) / static_cast<double>(beam_count);
    if (last_scan_hit_beam_count_ > 0) {
      last_scan_range_span_m_ = max_hit_range - min_hit_range;
      const double mean = hit_sum / static_cast<double>(last_scan_hit_beam_count_);
      const double variance =
          std::max(0.0, hit_sum_sq / static_cast<double>(last_scan_hit_beam_count_) -
                            (mean * mean));
      last_scan_range_stddev_m_ = std::sqrt(variance);
    }

    const int min_quadrant_hits =
        std::max(5, static_cast<int>(0.02 * static_cast<double>(beam_count)));
    for (const int count : hit_quadrants) {
      if (count >= min_quadrant_hits) {
        ++last_scan_observed_quadrants_;
      }
    }
  }

  bool scan_geometry_observable() const {
    return last_scan_valid_ratio_ >= min_scan_valid_ratio_for_quality_ &&
           last_scan_hit_ratio_ >= min_scan_hit_ratio_for_quality_ &&
           last_scan_range_span_m_ >= min_scan_range_span_m_for_quality_ &&
           last_scan_range_stddev_m_ >= min_scan_range_stddev_m_for_quality_ &&
           last_scan_observed_quadrants_ >= min_scan_observed_quadrants_for_quality_;
  }

  SlamQuality evaluate_slam_quality(const SteadyClock::time_point &stamp,
                                    bool odom_fresh, bool frame_ok,
                                    bool rate_ok, bool imu_ok, bool scan_ok,
                                    double odom_age_ms, double imu_age_ms,
                                    double scan_age_ms) const {
    (void)odom_age_ms;
    (void)imu_age_ms;
    (void)scan_age_ms;
    if (!last_odom_) {
      return SlamQuality{"bad", "odom_missing", false};
    }
    if (!odom_fresh) {
      return SlamQuality{"stale", "odom_stale", false};
    }
    if (!frame_ok) {
      return SlamQuality{"bad", "frame_mismatch", false};
    }
    if (!rate_ok) {
      return SlamQuality{"bad", "odom_rate_low", false};
    }
    if (jump_hold_active(stamp)) {
      return SlamQuality{"jump", "pose_or_yaw_jump", false};
    }
    if (require_imu_for_quality_) {
      if (!last_imu_) {
        return SlamQuality{"bad", "imu_missing", false};
      }
      if (!imu_ok) {
        return SlamQuality{"stale", "imu_stale", false};
      }
      if (imu_rate_hz_ < min_imu_rate_hz_) {
        return SlamQuality{"bad", "imu_rate_low", false};
      }
    }
    if (require_scan_for_quality_) {
      if (!last_scan_) {
        return SlamQuality{"bad", "scan_missing", false};
      }
      if (!scan_ok) {
        return SlamQuality{"stale", "scan_stale", false};
      }
      if (scan_rate_hz_ < min_scan_rate_hz_) {
        return SlamQuality{"bad", "scan_rate_low", false};
      }
    }
    if (low_observability_mode_ &&
        horizontal_span_m() < min_observable_horizontal_span_m_ &&
        !scan_geometry_observable()) {
      return SlamQuality{"uncertain", "low_observability_horizontal_span", false};
    }
    if (low_observability_mode_ &&
        horizontal_span_m() < min_observable_horizontal_span_m_) {
      return SlamQuality{"good", "healthy_scan_geometry", true};
    }
    return SlamQuality{"good", "healthy", true};
  }

  std::optional<double> json_number(const std::string &data,
                                    const std::string &key) const {
    const std::string quoted_key = "\"" + key + "\"";
    const auto key_pos = data.find(quoted_key);
    if (key_pos == std::string::npos) {
      return std::nullopt;
    }
    const auto colon_pos = data.find(":", key_pos + quoted_key.size());
    if (colon_pos == std::string::npos) {
      return std::nullopt;
    }
    const auto start = data.find_first_of("-0123456789.", colon_pos + 1);
    if (start == std::string::npos) {
      return std::nullopt;
    }
    const auto end =
        data.find_first_not_of("-0123456789.eE+", start);
    try {
      return std::stod(data.substr(start, end - start));
    } catch (const std::exception &) {
      return std::nullopt;
    }
  }

  std::optional<std::string> json_string(const std::string &data,
                                         const std::string &key) const {
    const std::string quoted_key = "\"" + key + "\"";
    const auto key_pos = data.find(quoted_key);
    if (key_pos == std::string::npos) {
      return std::nullopt;
    }
    const auto colon_pos = data.find(":", key_pos + quoted_key.size());
    if (colon_pos == std::string::npos) {
      return std::nullopt;
    }
    const auto first_quote = data.find("\"", colon_pos + 1);
    if (first_quote == std::string::npos) {
      return std::nullopt;
    }
    const auto second_quote = data.find("\"", first_quote + 1);
    if (second_quote == std::string::npos) {
      return std::nullopt;
    }
    return data.substr(first_quote + 1, second_quote - first_quote - 1);
  }

  std::optional<HeightEstimate> parse_height_estimate(
      const std::string &data) const {
    const auto z = json_number(data, "z");
    const auto vz = json_number(data, "vz");
    const auto covariance = json_number(data, "covariance");
    const auto source_type = json_string(data, "source_type");
    if (!z || !vz || !covariance || !source_type || source_type->empty()) {
      return std::nullopt;
    }
    return HeightEstimate{*z, *vz, *covariance, *source_type};
  }

  std::string state_for(bool odom_fresh, bool frame_ok, bool rate_ok, bool imu_ok,
                        bool height_fresh, bool height_parse_ok,
                        bool height_covariance_ok, bool ready,
                        const SlamQuality &slam_quality) const {
    if (ready) {
      return "healthy";
    }
    if (slam_quality_gate_enabled_ && !slam_quality.good) {
      return "slam_quality_" + slam_quality.level;
    }
    if (!last_odom_) {
      return "waiting_for_odom";
    }
    if (!odom_fresh) {
      return "timeout";
    }
    if (!frame_ok) {
      return "invalid_frame";
    }
    if (!rate_ok) {
      return "low_rate";
    }
    if (require_imu_for_output_ && !imu_ok) {
      return "waiting_for_imu";
    }
    if (require_height_for_output_ && !last_height_raw_) {
      return "waiting_for_height";
    }
    if (require_height_for_output_ && !height_fresh) {
      return "height_timeout";
    }
    if (require_height_for_output_ && !height_parse_ok) {
      return "invalid_height";
    }
    if (require_height_for_output_ && !height_covariance_ok) {
      return "height_covariance_high";
    }
    return "not_ready";
  }

  std::string build_status(bool odom_fresh, bool frame_ok, bool rate_ok,
                           bool imu_ok, bool height_fresh, bool height_parse_ok,
                           bool height_covariance_ok, bool ready,
                           double odom_age_ms, double imu_age_ms,
                           double height_age_ms, bool scan_ok,
                           double scan_age_ms,
                           const SlamQuality &slam_quality) const {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(3);
    oss << "{";
    oss << "\"state\":\""
        << state_for(odom_fresh, frame_ok, rate_ok, imu_ok, height_fresh,
                     height_parse_ok, height_covariance_ok, ready, slam_quality)
        << "\",";
    oss << "\"ready\":" << (ready ? "true" : "false") << ",";
    oss << "\"slam_quality\":\"" << slam_quality.level << "\",";
    oss << "\"slam_quality_reason\":\"" << slam_quality.reason << "\",";
    oss << "\"slam_quality_good\":" << (slam_quality.good ? "true" : "false")
        << ",";
    oss << "\"odom\":{";
    oss << "\"input_topic\":\"" << input_odom_topic_ << "\",";
    oss << "\"present\":" << (last_odom_ ? "true" : "false") << ",";
    oss << "\"fresh\":" << (odom_fresh ? "true" : "false") << ",";
    oss << "\"frame_ok\":" << (frame_ok ? "true" : "false") << ",";
    oss << "\"rate_ok\":" << (rate_ok ? "true" : "false") << ",";
    oss << "\"age_ms\":" << odom_age_ms << ",";
    oss << "\"rate_hz\":" << odom_rate_hz_ << ",";
    oss << "\"frame_id\":\"" << (last_odom_ ? last_odom_->header.frame_id : "") << "\",";
    oss << "\"child_frame_id\":\"" << (last_odom_ ? last_odom_->child_frame_id : "")
        << "\"},";
    oss << "\"imu\":{";
    oss << "\"required\":" << (require_imu_for_output_ ? "true" : "false") << ",";
    oss << "\"present\":" << (last_imu_ ? "true" : "false") << ",";
    oss << "\"fresh\":" << (imu_ok ? "true" : "false") << ",";
    oss << "\"age_ms\":" << imu_age_ms << "},";
    oss << "\"scan\":{";
    oss << "\"required_for_quality\":" << (require_scan_for_quality_ ? "true" : "false") << ",";
    oss << "\"present\":" << (last_scan_ ? "true" : "false") << ",";
    oss << "\"fresh\":" << (scan_ok ? "true" : "false") << ",";
    oss << "\"age_ms\":" << scan_age_ms << ",";
    oss << "\"rate_hz\":" << scan_rate_hz_ << ",";
    oss << "\"rate_ok\":" << (scan_rate_hz_ >= min_scan_rate_hz_ ? "true" : "false") << ",";
    oss << "\"beam_count\":" << last_scan_beam_count_ << ",";
    oss << "\"valid_beam_count\":" << last_scan_valid_beam_count_ << ",";
    oss << "\"hit_beam_count\":" << last_scan_hit_beam_count_ << ",";
    oss << "\"valid_ratio\":" << last_scan_valid_ratio_ << ",";
    oss << "\"hit_ratio\":" << last_scan_hit_ratio_ << ",";
    oss << "\"range_span_m\":" << last_scan_range_span_m_ << ",";
    oss << "\"range_stddev_m\":" << last_scan_range_stddev_m_ << ",";
    oss << "\"observed_quadrants\":" << last_scan_observed_quadrants_ << ",";
    oss << "\"geometry_observable\":" << (scan_geometry_observable() ? "true" : "false") << ",";
    oss << "\"topic\":\"" << scan_topic_ << "\"},";
    oss << "\"slam_quality_report\":{";
    oss << "\"gate_enabled\":" << (slam_quality_gate_enabled_ ? "true" : "false") << ",";
    oss << "\"quality\":\"" << slam_quality.level << "\",";
    oss << "\"reason\":\"" << slam_quality.reason << "\",";
    oss << "\"good\":" << (slam_quality.good ? "true" : "false") << ",";
    oss << "\"low_observability_mode\":" << (low_observability_mode_ ? "true" : "false") << ",";
    oss << "\"horizontal_span_m\":" << horizontal_span_m() << ",";
    oss << "\"min_observable_horizontal_span_m\":" << min_observable_horizontal_span_m_ << ",";
    oss << "\"scan_geometry_observable\":" << (scan_geometry_observable() ? "true" : "false") << ",";
    oss << "\"min_scan_valid_ratio_for_quality\":" << min_scan_valid_ratio_for_quality_ << ",";
    oss << "\"min_scan_hit_ratio_for_quality\":" << min_scan_hit_ratio_for_quality_ << ",";
    oss << "\"min_scan_range_span_m_for_quality\":" << min_scan_range_span_m_for_quality_ << ",";
    oss << "\"min_scan_range_stddev_m_for_quality\":" << min_scan_range_stddev_m_for_quality_ << ",";
    oss << "\"min_scan_observed_quadrants_for_quality\":" << min_scan_observed_quadrants_for_quality_ << ",";
    oss << "\"last_position_jump_m\":" << last_position_jump_m_ << ",";
    oss << "\"max_position_jump_m\":" << max_position_jump_m_ << ",";
    oss << "\"max_observed_position_jump_m\":" << max_observed_position_jump_m_ << ",";
    oss << "\"last_yaw_jump_rad\":" << last_yaw_jump_rad_ << ",";
    oss << "\"max_yaw_jump_rad\":" << max_yaw_jump_rad_ << ",";
    oss << "\"max_observed_yaw_jump_rad\":" << max_observed_yaw_jump_rad_ << ",";
    oss << "\"require_imu_for_quality\":" << (require_imu_for_quality_ ? "true" : "false") << ",";
    oss << "\"require_scan_for_quality\":" << (require_scan_for_quality_ ? "true" : "false")
        << "},";
    oss << "\"height\":{";
    oss << "\"required\":" << (require_height_for_output_ ? "true" : "false")
        << ",";
    oss << "\"present\":" << (last_height_raw_ ? "true" : "false") << ",";
    oss << "\"fresh\":" << (height_fresh ? "true" : "false") << ",";
    oss << "\"parse_ok\":" << (height_parse_ok ? "true" : "false") << ",";
    oss << "\"covariance_ok\":"
        << (height_covariance_ok ? "true" : "false") << ",";
    oss << "\"age_ms\":" << height_age_ms << ",";
    oss << "\"topic\":\"" << height_topic_ << "\",";
    oss << "\"max_covariance\":" << max_height_covariance_ << ",";
    oss << "\"source_type\":\""
        << (last_height_ ? last_height_->source_type : "") << "\",";
    oss << "\"z\":" << (last_height_ ? last_height_->z : 0.0) << ",";
    oss << "\"vz\":" << (last_height_ ? last_height_->vz : 0.0) << ",";
    oss << "\"covariance\":"
        << (last_height_ ? last_height_->covariance : 0.0) << "},";
    oss << "\"output\":{";
    oss << "\"odom_topic\":\"" << output_odom_topic_ << "\",";
    oss << "\"status_topic\":\"" << status_topic_ << "\",";
    oss << "\"ap_tf_topic\":\"" << ap_tf_topic_ << "\",";
    oss << "\"coordinate_mode\":\"" << coordinate_mode_ << "\",";
    oss << "\"xy_yaw_source\":\"" << input_odom_topic_ << "\",";
    oss << "\"z_source\":\"" << (last_height_ ? last_height_->source_type : "") << "\",";
    oss << "\"vz_source\":\"" << (last_height_ ? last_height_->source_type : "") << "\"}";
    oss << "}";
    return oss.str();
  }

  int odom_timeout_ms_;
  int imu_timeout_ms_;
  int scan_timeout_ms_;
  int height_timeout_ms_;
  bool require_imu_for_output_;
  bool require_height_for_output_;
  bool require_imu_for_quality_;
  bool require_scan_for_quality_;
  bool slam_quality_gate_enabled_;
  bool low_observability_mode_;
  std::string output_frame_id_;
  std::string output_child_frame_id_;
  std::string input_odom_topic_;
  std::string imu_topic_;
  std::string scan_topic_;
  std::string output_odom_topic_;
  std::string status_topic_;
  std::string ap_tf_topic_;
  std::string ap_tf_parent_frame_;
  std::string ap_tf_child_frame_;
  std::string expected_odom_frame_id_;
  std::string expected_odom_child_frame_id_;
  double min_odom_rate_hz_;
  double min_imu_rate_hz_;
  double min_scan_rate_hz_;
  double odom_rate_hz_{0.0};
  double imu_rate_hz_{0.0};
  double scan_rate_hz_{0.0};
  double max_position_jump_m_;
  double max_yaw_jump_rad_;
  int jump_hold_ms_;
  double min_observable_horizontal_span_m_;
  double min_scan_valid_ratio_for_quality_;
  double min_scan_hit_ratio_for_quality_;
  double min_scan_range_span_m_for_quality_;
  double min_scan_range_stddev_m_for_quality_;
  int min_scan_observed_quadrants_for_quality_;
  double scan_max_range_hit_margin_m_;
  double last_position_jump_m_{0.0};
  double last_yaw_jump_rad_{0.0};
  double max_observed_position_jump_m_{0.0};
  double max_observed_yaw_jump_rad_{0.0};
  bool horizontal_bounds_initialized_{false};
  double min_x_{0.0};
  double max_x_{0.0};
  double min_y_{0.0};
  double max_y_{0.0};
  int last_scan_beam_count_{0};
  int last_scan_valid_beam_count_{0};
  int last_scan_hit_beam_count_{0};
  double last_scan_valid_ratio_{0.0};
  double last_scan_hit_ratio_{0.0};
  double last_scan_range_span_m_{0.0};
  double last_scan_range_stddev_m_{0.0};
  int last_scan_observed_quadrants_{0};
  double max_height_covariance_;
  std::string height_topic_;
  std::string coordinate_mode_;

  nav_msgs::msg::Odometry::SharedPtr last_odom_;
  sensor_msgs::msg::Imu::SharedPtr last_imu_;
  sensor_msgs::msg::LaserScan::SharedPtr last_scan_;
  std_msgs::msg::String::SharedPtr last_height_raw_;
  std::optional<HeightEstimate> last_height_;
  SteadyClock::time_point last_odom_wall_time_{};
  SteadyClock::time_point last_imu_wall_time_{};
  SteadyClock::time_point last_scan_wall_time_{};
  SteadyClock::time_point last_height_wall_time_{};
  SteadyClock::time_point last_jump_wall_time_{};

  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr scan_sub_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr height_sub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
  rclcpp::Publisher<tf2_msgs::msg::TFMessage>::SharedPtr ap_tf_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<NavlabExternalNavBridgeNode>());
  rclcpp::shutdown();
  return 0;
}
