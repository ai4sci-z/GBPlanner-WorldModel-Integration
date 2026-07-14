// M4: minimal PCI replacement (task book: "PCI 先用最小定时 trigger 替代,
// 勿复刻全家桶"). A wall timer calls the gbplanner service and republishes
// the returned pose path as MultiDOFJointTrajectory on /gbp/trajectory —
// the exact ingress the world-model adapter consumed in the bridge era
// (docs/ros2迁移_直连架构契约: adapter zero-change condition).
#include <chrono>
#include <memory>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/path.hpp>
#include <trajectory_msgs/msg/multi_dof_joint_trajectory.hpp>
#include <planner_msgs/srv/planner_srv.hpp>

using namespace std::chrono_literals;

class PciTriggerNode : public rclcpp::Node {
 public:
  PciTriggerNode() : rclcpp::Node("pci_trigger_node") {
    period_sec_ = declare_parameter<double>("trigger_period_sec", 2.0);
    frame_id_ = declare_parameter<std::string>("frame_id", "map");
    bound_mode_ =
        static_cast<int>(declare_parameter<int64_t>("bound_mode", 0));

    client_ = create_client<planner_msgs::srv::PlannerSrv>("gbplanner");
    traj_pub_ = create_publisher<trajectory_msgs::msg::MultiDOFJointTrajectory>(
        "/gbp/trajectory", 10);
    path_pub_ = create_publisher<nav_msgs::msg::Path>("/gbp/path", 10);

    timer_ = create_wall_timer(std::chrono::duration<double>(period_sec_),
                               [this] { trigger(); });
    RCLCPP_INFO(get_logger(), "pci_trigger: every %.1fs -> gbplanner srv",
                period_sec_);
  }

 private:
  void trigger() {
    if (busy_) return;  // one outstanding request at a time
    if (!client_->service_is_ready()) {
      RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 10000,
                           "gbplanner service not ready yet");
      return;
    }
    auto req = std::make_shared<planner_msgs::srv::PlannerSrv::Request>();
    req->header.frame_id = frame_id_;
    req->header.stamp = now();
    req->bound_mode = bound_mode_;
    busy_ = true;
    client_->async_send_request(
        req, [this](rclcpp::Client<planner_msgs::srv::PlannerSrv>::SharedFuture
                        future) {
          busy_ = false;
          const auto res = future.get();
          if (!res || res->path.empty()) {
            RCLCPP_WARN(get_logger(), "planner returned empty path");
            return;
          }
          publishPath(*res);
        });
  }

  void publishPath(const planner_msgs::srv::PlannerSrv::Response& res) {
    const auto stamp = now();

    trajectory_msgs::msg::MultiDOFJointTrajectory traj;
    traj.header.stamp = stamp;
    traj.header.frame_id = frame_id_;
    for (const auto& pose : res.path) {
      trajectory_msgs::msg::MultiDOFJointTrajectoryPoint pt;
      geometry_msgs::msg::Transform t;
      t.translation.x = pose.position.x;
      t.translation.y = pose.position.y;
      t.translation.z = pose.position.z;
      t.rotation = pose.orientation;
      pt.transforms.push_back(t);
      traj.points.push_back(pt);
    }
    traj_pub_->publish(traj);

    nav_msgs::msg::Path path;
    path.header = traj.header;
    for (const auto& pose : res.path) {
      geometry_msgs::msg::PoseStamped ps;
      ps.header = traj.header;
      ps.pose = pose;
      path.poses.push_back(ps);
    }
    path_pub_->publish(path);

    RCLCPP_INFO(get_logger(), "published %zu waypoints (status=%d)",
                res.path.size(), res.status);
  }

  double period_sec_ = 2.0;
  std::string frame_id_ = "map";
  int bound_mode_ = 0;
  bool busy_ = false;
  rclcpp::Client<planner_msgs::srv::PlannerSrv>::SharedPtr client_;
  rclcpp::Publisher<trajectory_msgs::msg::MultiDOFJointTrajectory>::SharedPtr
      traj_pub_;
  rclcpp::Publisher<nav_msgs::msg::Path>::SharedPtr path_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<PciTriggerNode>());
  rclcpp::shutdown();
  return 0;
}
