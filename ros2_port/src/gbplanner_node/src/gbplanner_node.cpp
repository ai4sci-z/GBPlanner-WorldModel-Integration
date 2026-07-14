// M4: minimal ROS2 shell for the ROS-free gbplanner core.
//
// Mirrors the thin logic of the ROS1 wrapper (gbplanner.cpp) but only the
// surface the world-model integration needs: odometry in, the planner and
// homing services out, voxblox fed by the map manager's own subscriptions,
// and the four core ticks driven by wall timers. Everything else the ROS1
// node offered (13 more services, rviz markers) is deliberately absent per
// the task book ("最小壳, 勿复刻全家桶").
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_srvs/srv/empty.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <tf2/utils.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <tf2_ros/buffer.h>
#include <tf2_ros/transform_listener.h>

#include <planner_msgs/srv/planner_srv.hpp>
#include <planner_msgs/srv/planner_homing.hpp>

#include "gbplanner_core/rrg.h"
#include "planner_common/port/param.h"

namespace {

// ROS2 parameters use '.' separators; the vendored loaders expect
// '/gbplanner_node/<Group>/<name>' keys (ROS1 node-namespace layout).
std::string toRegistryKey(const std::string& param_name) {
  std::string key = "/gbplanner_node/" + param_name;
  for (auto& c : key) {
    if (c == '.') c = '/';
  }
  return key;
}

void bridgeParamsToRegistry(rclcpp::Node* node) {
  const auto result = node->list_parameters({}, 0);
  int n = 0;
  for (const auto& name : result.names) {
    const rclcpp::Parameter p = node->get_parameter(name);
    const std::string key = toRegistryKey(name);
    switch (p.get_type()) {
      case rclcpp::ParameterType::PARAMETER_BOOL:
        pshim::param::set<bool>(key, p.as_bool());
        break;
      case rclcpp::ParameterType::PARAMETER_INTEGER:
        pshim::param::set<int64_t>(key, p.as_int());
        break;
      case rclcpp::ParameterType::PARAMETER_DOUBLE:
        pshim::param::set<double>(key, p.as_double());
        break;
      case rclcpp::ParameterType::PARAMETER_STRING:
        pshim::param::set<std::string>(key, p.as_string());
        break;
      case rclcpp::ParameterType::PARAMETER_DOUBLE_ARRAY:
        pshim::param::set<std::vector<double>>(key, p.as_double_array());
        break;
      case rclcpp::ParameterType::PARAMETER_INTEGER_ARRAY:
        pshim::param::set<std::vector<int64_t>>(key, p.as_integer_array());
        break;
      case rclcpp::ParameterType::PARAMETER_STRING_ARRAY:
        pshim::param::set<std::vector<std::string>>(key, p.as_string_array());
        break;
      default:
        continue;
    }
    ++n;
  }
  RCLCPP_INFO(node->get_logger(),
              "param bridge: %d parameters -> pshim registry", n);
}

}  // namespace

class GbplannerNode : public rclcpp::Node {
 public:
  GbplannerNode()
      : rclcpp::Node(
            "gbplanner_node",
            rclcpp::NodeOptions()
                .automatically_declare_parameters_from_overrides(true)) {}

  // Two-phase init: Rrg/voxblox need the fully-constructed node pointer.
  bool init() {
    bridgeParamsToRegistry(this);

    map_manager_ = new MapManagerVoxblox<MapManagerVoxbloxServer,
                                         MapManagerVoxbloxVoxel>(this);
    rrg_ = std::make_unique<explorer::Rrg>(map_manager_);

    if (!rrg_->loadParams(false)) {
      RCLCPP_ERROR(get_logger(),
                   "Could not load all required gbplanner parameters.");
      return false;
    }

    // --- injected I/O (the core's former publishers/clients/tf) ---
    free_cloud_pub_ = create_publisher<sensor_msgs::msg::PointCloud2>(
        "freespace_pointcloud", 10);
    pci_reset_pub_ = create_publisher<std_msgs::msg::Bool>(
        "planner_control_interface/msg/reset", 10);
    landing_client_ = create_client<std_srvs::srv::Empty>("land_srv");
    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(get_clock());
    tf_listener_ = std::make_unique<tf2_ros::TransformListener>(*tf_buffer_);

    pshim::RrgIO io;
    io.publish_free_cloud =
        [this](const sensor_msgs::msg::PointCloud2& msg) {
          free_cloud_pub_->publish(msg);
        };
    io.publish_pci_reset = [this](const std_msgs::msg::Bool& msg) {
      pci_reset_pub_->publish(msg);
    };
    io.call_landing = [this]() {
      landing_client_->async_send_request(
          std::make_shared<std_srvs::srv::Empty::Request>());
    };
    io.lookup_transform = [this](const std::string& target,
                                 const std::string& source,
                                 tf2::Transform* out) {
      try {
        const auto t =
            tf_buffer_->lookupTransform(target, source, rclcpp::Time(0));
        tf2::fromMsg(t.transform, *out);
        return true;
      } catch (const tf2::TransformException&) {
        return false;
      }
    };
    rrg_->setIO(io);

    // --- inputs ---
    // /slam/odom publishes with sensor-data (BEST_EFFORT) QoS; a RELIABLE
    // subscription would silently receive nothing (bug-ledger B9 pattern).
    odometry_sub_ = create_subscription<nav_msgs::msg::Odometry>(
        "odometry", rclcpp::SensorDataQoS(),
        [this](const nav_msgs::msg::Odometry& odo) {
          StateVec state;
          state[0] = odo.pose.pose.position.x;
          state[1] = odo.pose.pose.position.y;
          state[2] = odo.pose.pose.position.z;
          state[3] = tf2::getYaw(odo.pose.pose.orientation);
          rrg_->setState(state);
        });

    // --- services (the world-model contract surface) ---
    planner_srv_ = create_service<planner_msgs::srv::PlannerSrv>(
        "gbplanner",
        [this](const planner_msgs::srv::PlannerSrv::Request::SharedPtr req,
               planner_msgs::srv::PlannerSrv::Response::SharedPtr res) {
          plannerService(*req, res.get());
        });
    homing_srv_ = create_service<planner_msgs::srv::PlannerHoming>(
        "gbplanner/homing",
        [this](const planner_msgs::srv::PlannerHoming::Request::SharedPtr req,
               planner_msgs::srv::PlannerHoming::Response::SharedPtr res) {
          res->path = rrg_->getHomingPath(req->header.frame_id);
        });

    // --- the four core ticks (ROS1's self-owned timers, M3) ---
    tick_planner_ = create_wall_timer(
        std::chrono::duration<double>(explorer::Rrg::kTickPlannerPeriod),
        [this] { rrg_->tickPlanner(); });
    tick_free_cloud_ = create_wall_timer(
        std::chrono::duration<double>(
            explorer::Rrg::kTickFreePointCloudPeriod),
        [this] { rrg_->tickFreePointCloud(); });
    tick_global_graph_ = create_wall_timer(
        std::chrono::duration<double>(
            explorer::Rrg::kTickGlobalGraphUpdatePeriod),
        [this] { rrg_->tickGlobalGraphUpdate(); });
    tick_frontier_add_ = create_wall_timer(
        std::chrono::duration<double>(
            explorer::Rrg::kTickGlobalGraphFrontierAdditionPeriod),
        [this] { rrg_->tickGlobalGraphFrontierAddition(); });

    // One-shot map probe 15s after start — kept for M5 bring-up diagnostics.
    debug_timer_ = create_wall_timer(std::chrono::seconds(15), [this] {
      debug_timer_->cancel();
      const double res = map_manager_->getResolution();
      auto q = [this](double x, double y, double z) {
        return static_cast<int>(
            map_manager_->getVoxelStatus(Eigen::Vector3d(x, y, z)));
      };
      RCLCPP_INFO(get_logger(),
                  "[MAPPROBE] res=%.2f ready=%d  (0,0,1)=%d (1,0,1)=%d "
                  "(2,0,1)=%d (0,0,0.2)=%d (0,0,-0.4)=%d (3.9,0,1)=%d "
                  "[0=unk 1=occ 2=free]",
                  res, map_manager_->getStatus(), q(0, 0, 1), q(1, 0, 1),
                  q(2, 0, 1), q(0, 0, 0.2), q(0, 0, -0.4), q(3.9, 0, 1));
      auto qb = [this](double x, double y, double z, double s) {
        return static_cast<int>(map_manager_->getBoxStatus(
            Eigen::Vector3d(x, y, z), Eigen::Vector3d(s, s, s), true));
      };
      RCLCPP_INFO(get_logger(),
                  "[BOXPROBE] box0.6@(0,0,1)=%d box0.6@(1,0,1)=%d "
                  "box0.6@(2,0,1.5)=%d box1.0@(0,0,1)=%d "
                  "path(0,0,1)->(1.5,0,1)=%d",
                  qb(0, 0, 1, 0.6), qb(1, 0, 1, 0.6), qb(2, 0, 1.5, 0.6),
                  qb(0, 0, 1, 1.0),
                  static_cast<int>(map_manager_->getPathStatus(
                      Eigen::Vector3d(0, 0, 1), Eigen::Vector3d(1.5, 0, 1),
                      Eigen::Vector3d(0.6, 0.6, 0.6), true)));
    });

    RCLCPP_INFO(get_logger(), "gbplanner_node ready (M4 minimal shell).");
    return true;
  }

 private:
  // Mirrors ROS1 Gbplanner::plannerServiceCallback verbatim.
  void plannerService(const planner_msgs::srv::PlannerSrv::Request& req,
                      planner_msgs::srv::PlannerSrv::Response* res) {
    rrg_->setGlobalFrame(req.header.frame_id);
    rrg_->setBoundMode(static_cast<BoundModeType>(req.bound_mode));
    rrg_->setRootStateForPlanning(req.root_pose);

    res->path.clear();
    rrg_->reset();
    explorer::Rrg::GraphStatus status = rrg_->buildGraph();
    switch (status) {
      case explorer::Rrg::GraphStatus::OK:
        break;
      case explorer::Rrg::GraphStatus::ERR_KDTREE:
        RCLCPP_WARN(get_logger(), "[PLANNER_ERROR] kdtree issue.");
        break;
      case explorer::Rrg::GraphStatus::ERR_NO_FEASIBLE_PATH:
        RCLCPP_WARN(get_logger(), "[PLANNER_ERROR] no feasible path.");
        break;
      case explorer::Rrg::GraphStatus::NOT_OK:
        RCLCPP_WARN(get_logger(), "[GBPLANNER] resending global path.");
        res->path = rrg_->reRunGlobalPlanner();
        break;
      default:
        RCLCPP_WARN(get_logger(), "[PLANNER_ERROR] graph build error.");
        break;
    }
    if (status == explorer::Rrg::GraphStatus::OK) {
      status = rrg_->evaluateGraph();
      switch (status) {
        case explorer::Rrg::GraphStatus::OK:
          break;
        case explorer::Rrg::GraphStatus::NO_GAIN:
          RCLCPP_WARN(get_logger(), "[PLANNER_ERROR] no positive gain.");
          break;
        case explorer::Rrg::GraphStatus::NOT_OK:
          RCLCPP_WARN(get_logger(),
                      "[GBPLANNER] low local gain -> global planner.");
          res->path = rrg_->runGlobalPlanner(0, false, false);
          res->status =
              planner_msgs::srv::PlannerSrv::Response::K_REPOSITIONING;
          break;
        default:
          RCLCPP_WARN(get_logger(), "[PLANNER_ERROR] gain calc error.");
          break;
      }
    }
    if (status == explorer::Rrg::GraphStatus::OK) {
      res->path = rrg_->getBestPath(req.header.frame_id, res->status);
    }
  }

  MapManagerVoxblox<MapManagerVoxbloxServer, MapManagerVoxbloxVoxel>*
      map_manager_ = nullptr;
  std::unique_ptr<explorer::Rrg> rrg_;

  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr free_cloud_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr pci_reset_pub_;
  rclcpp::Client<std_srvs::srv::Empty>::SharedPtr landing_client_;
  std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
  std::unique_ptr<tf2_ros::TransformListener> tf_listener_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odometry_sub_;
  rclcpp::Service<planner_msgs::srv::PlannerSrv>::SharedPtr planner_srv_;
  rclcpp::Service<planner_msgs::srv::PlannerHoming>::SharedPtr homing_srv_;
  rclcpp::TimerBase::SharedPtr tick_planner_, tick_free_cloud_,
      tick_global_graph_, tick_frontier_add_, debug_timer_;
};

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<GbplannerNode>();
  if (!node->init()) {
    rclcpp::shutdown();
    return 1;
  }
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
