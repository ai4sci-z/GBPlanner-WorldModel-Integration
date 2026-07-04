#include <chrono>
#include <iomanip>
#include <memory>
#include <optional>
#include <sstream>
#include <string>

#include "navlab_slam_imu_bridge/timestamp.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class NavlabSlamImuBridgeNode : public rclcpp::Node {
 public:
  NavlabSlamImuBridgeNode() : Node("navlab_slam_imu_bridge_node") {
    source_mode_ = declare_parameter<std::string>("source_mode", "topic");
    source_topic_ =
        declare_parameter<std::string>("source_topic", "/ap/imu/experimental/data");
    source_label_ =
        declare_parameter<std::string>("source_label", "ardupilot_dds");
    output_topic_ =
        declare_parameter<std::string>("output_topic", "/imu");
    status_topic_ =
        declare_parameter<std::string>("status_topic", "/imu/status");
    output_frame_id_ =
        declare_parameter<std::string>("output_frame_id", "imu_link");
    use_input_frame_id_ = declare_parameter("use_input_frame_id", true);
    replace_zero_timestamp_ = declare_parameter("replace_zero_timestamp", true);
    publish_placeholder_imu_ = declare_parameter("publish_placeholder_imu", false);
    input_timeout_ms_ = declare_parameter("input_timeout_ms", 500);
    status_period_ms_ = declare_parameter("status_period_ms", 500);
    min_input_rate_hz_ = declare_parameter("min_input_rate_hz", 4.0);

    if (publish_placeholder_imu_) {
      source_mode_ = "placeholder";
    }

    imu_pub_ = create_publisher<sensor_msgs::msg::Imu>(output_topic_, 10);
    status_pub_ = create_publisher<std_msgs::msg::String>(status_topic_, 10);

    if (source_mode_ == "topic") {
      imu_sub_ = create_subscription<sensor_msgs::msg::Imu>(
          source_topic_, rclcpp::SensorDataQoS(),
          std::bind(&NavlabSlamImuBridgeNode::handle_input_imu, this, std::placeholders::_1));
    } else if (source_mode_ != "placeholder") {
      RCLCPP_WARN(get_logger(),
                  "unsupported source_mode '%s', falling back to placeholder mode",
                  source_mode_.c_str());
      source_mode_ = "placeholder";
    }

    timer_ = create_wall_timer(
        std::chrono::milliseconds(status_period_ms_),
        std::bind(&NavlabSlamImuBridgeNode::tick, this));

    RCLCPP_INFO(get_logger(),
                "navlab_slam_imu_bridge started; mode=%s source_label=%s source_topic=%s output_topic=%s status_topic=%s",
                source_mode_.c_str(), source_label_.c_str(), source_topic_.c_str(),
                output_topic_.c_str(), status_topic_.c_str());
  }

 private:
  void handle_input_imu(const sensor_msgs::msg::Imu::SharedPtr msg) {
    const auto received_at = now();
    const auto received_wall_at = std::chrono::steady_clock::now();
    auto normalized = *msg;
    bool timestamp_replaced = false;
    bool timestamp_adjusted = false;

    if (last_output_msg_) {
      const double delta_sec =
          std::chrono::duration<double>(received_wall_at - last_source_wall_time_).count();
      if (delta_sec > 0.0) {
        if (input_rate_hz_ <= 0.0) {
          input_rate_hz_ = 1.0 / delta_sec;
        } else {
          input_rate_hz_ = 0.8 * input_rate_hz_ + 0.2 * (1.0 / delta_sec);
        }
      }
    }

    if (!use_input_frame_id_ || normalized.header.frame_id.empty()) {
      normalized.header.frame_id = output_frame_id_;
    }

    if (replace_zero_timestamp_ && normalized.header.stamp.sec == 0 &&
        normalized.header.stamp.nanosec == 0) {
      normalized.header.stamp = received_at;
      timestamp_replaced = true;
    }
    timestamp_adjusted = ensure_monotonic_output_stamp(normalized);

    last_source_msg_time_ = received_at;
    last_source_wall_time_ = received_wall_at;
    last_output_msg_ = std::make_shared<sensor_msgs::msg::Imu>(normalized);
    last_input_frame_id_ = msg->header.frame_id;
    last_output_frame_id_ = normalized.header.frame_id;
    last_timestamp_replaced_ = timestamp_replaced;
    last_timestamp_adjusted_ = timestamp_adjusted;
    if (timestamp_replaced) {
      ++timestamp_replaced_count_;
    }
    if (timestamp_adjusted) {
      ++timestamp_adjusted_count_;
    }
    ++forwarded_count_;

    imu_pub_->publish(normalized);
  }

  void publish_placeholder_imu() {
    sensor_msgs::msg::Imu imu;
    imu.header.stamp = now();
    imu.header.frame_id = output_frame_id_;
    imu.orientation.w = 1.0;
    const bool timestamp_adjusted = ensure_monotonic_output_stamp(imu);

    imu_pub_->publish(imu);
    last_source_msg_time_ = now();
    last_source_wall_time_ = std::chrono::steady_clock::now();
    last_output_msg_ = std::make_shared<sensor_msgs::msg::Imu>(imu);
    last_input_frame_id_.clear();
    last_output_frame_id_ = output_frame_id_;
    last_timestamp_replaced_ = false;
    last_timestamp_adjusted_ = timestamp_adjusted;
    if (timestamp_adjusted) {
      ++timestamp_adjusted_count_;
    }
    input_rate_hz_ = status_period_ms_ > 0 ? 1000.0 / status_period_ms_ : 0.0;
    ++forwarded_count_;
  }

  bool input_is_recent() const {
    if (!last_output_msg_) {
      return false;
    }

    return std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::steady_clock::now() - last_source_wall_time_)
               .count() < input_timeout_ms_;
  }

  double input_age_ms() const {
    if (!last_output_msg_) {
      return -1.0;
    }

    return std::chrono::duration<double, std::milli>(
               std::chrono::steady_clock::now() - last_source_wall_time_)
        .count();
  }

  bool input_rate_ok() const {
    if (source_mode_ == "placeholder") {
      return true;
    }
    if (!last_output_msg_) {
      return false;
    }

    return input_rate_hz_ >= min_input_rate_hz_;
  }

  bool ensure_monotonic_output_stamp(sensor_msgs::msg::Imu &msg) {
    const auto candidate_ns = rclcpp::Time(msg.header.stamp).nanoseconds();
    const auto adjusted_ns =
        navlab_slam_imu_bridge::monotonic_output_stamp_nanoseconds(
            candidate_ns, last_output_stamp_ns_);
    last_output_stamp_ns_ = adjusted_ns;
    if (adjusted_ns == candidate_ns) {
      return false;
    }
    msg.header.stamp.sec = static_cast<int32_t>(adjusted_ns / 1000000000LL);
    msg.header.stamp.nanosec = static_cast<uint32_t>(adjusted_ns % 1000000000LL);
    return true;
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

  std::string state_for(bool fresh, bool rate_ok) const {
    if (source_mode_ == "placeholder") {
      return "publishing_placeholder_fcu_imu";
    }
    if (!last_output_msg_) {
      return "waiting_for_fcu_imu_source";
    }
    if (!fresh) {
      return "stale_fcu_imu_source";
    }
    if (!rate_ok) {
      return "low_rate_fcu_imu_source";
    }
    return "streaming_fcu_imu";
  }

  std::string build_status() const {
    std::ostringstream oss;
    const bool fresh = input_is_recent();
    const bool rate_ok = input_rate_ok();
    const bool ready = last_output_msg_ && fresh && rate_ok;

    oss << std::fixed << std::setprecision(3);
    oss << "{";
    oss << "\"state\":\"" << state_for(fresh, rate_ok) << "\",";
    oss << "\"ready\":" << (ready ? "true" : "false") << ",";
    oss << "\"source\":{";
    oss << "\"mode\":\"" << json_escape(source_mode_) << "\",";
    oss << "\"label\":\"" << json_escape(source_label_) << "\",";
    oss << "\"topic\":\"" << json_escape(source_topic_) << "\"},";
    oss << "\"input\":{";
    oss << "\"present\":" << (last_output_msg_ ? "true" : "false") << ",";
    oss << "\"fresh\":" << (fresh ? "true" : "false") << ",";
    oss << "\"age_ms\":" << input_age_ms() << ",";
    oss << "\"rate_hz\":" << input_rate_hz_ << ",";
    oss << "\"rate_ok\":" << (rate_ok ? "true" : "false") << ",";
    oss << "\"min_rate_hz\":" << min_input_rate_hz_ << ",";
    oss << "\"frame_id\":\"" << json_escape(last_input_frame_id_) << "\",";
    oss << "\"count\":" << forwarded_count_ << "},";
    oss << "\"output\":{";
    oss << "\"topic\":\"" << json_escape(output_topic_) << "\",";
    oss << "\"status_topic\":\"" << json_escape(status_topic_) << "\",";
    oss << "\"frame_id\":\"" << json_escape(last_output_frame_id_) << "\",";
    oss << "\"fallback_frame_id\":\"" << json_escape(output_frame_id_) << "\",";
    oss << "\"use_input_frame_id\":" << (use_input_frame_id_ ? "true" : "false")
        << ",";
    oss << "\"replace_zero_timestamp\":"
        << (replace_zero_timestamp_ ? "true" : "false") << ",";
    oss << "\"last_timestamp_replaced\":"
        << (last_timestamp_replaced_ ? "true" : "false") << ",";
    oss << "\"timestamp_replaced_count\":" << timestamp_replaced_count_ << ",";
    oss << "\"last_timestamp_adjusted\":"
        << (last_timestamp_adjusted_ ? "true" : "false") << ",";
    oss << "\"timestamp_adjusted_count\":" << timestamp_adjusted_count_ << "}";
    oss << "}";
    return oss.str();
  }

  void tick() {
    if (source_mode_ == "placeholder") {
      publish_placeholder_imu();
    }

    std_msgs::msg::String status;
    status.data = build_status();
    status_pub_->publish(status);
  }

  std::string source_mode_;
  std::string source_topic_;
  std::string source_label_;
  std::string output_topic_;
  std::string status_topic_;
  std::string output_frame_id_;
  bool use_input_frame_id_;
  bool replace_zero_timestamp_;
  bool publish_placeholder_imu_;
  int input_timeout_ms_;
  int status_period_ms_;
  double min_input_rate_hz_;
  double input_rate_hz_{0.0};
  uint64_t forwarded_count_{0};
  uint64_t timestamp_replaced_count_{0};
  uint64_t timestamp_adjusted_count_{0};
  bool last_timestamp_replaced_{false};
  bool last_timestamp_adjusted_{false};
  std::string last_input_frame_id_;
  std::string last_output_frame_id_;
  std::optional<int64_t> last_output_stamp_ns_;

  sensor_msgs::msg::Imu::SharedPtr last_output_msg_;
  rclcpp::Time last_source_msg_time_{0, 0, RCL_ROS_TIME};
  std::chrono::steady_clock::time_point last_source_wall_time_;

  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_sub_;
  rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr status_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<NavlabSlamImuBridgeNode>());
  rclcpp::shutdown();
  return 0;
}
