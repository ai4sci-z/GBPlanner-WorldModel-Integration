#pragma once
// No-op visualization interface for the ROS-free gbplanner core (M3).
// Signatures are lifted verbatim from gbplanner_rviz.h for exactly the 24
// methods rrg.cpp calls; the ROS2 node shell (M4) subclasses this with the
// real marker-publishing implementation. The core links only this header.
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <Eigen/Dense>
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <geometry_msgs/msg/pose.hpp>

#include "planner_common/geofence_manager.h"
#include "planner_common/graph_manager.h"
#include "planner_common/map_manager.h"
#include "planner_common/params.h"
#include "planner_common/random_sampler.h"

class Visualization {
 public:
  Visualization() = default;
  virtual ~Visualization() = default;

  virtual void setGlobalFrame(std::string /*frame_id*/) {}
  virtual void visualizeBestPaths(
      const std::shared_ptr<GraphManager> /*graph_manager*/,
      const ShortestPathsReport& /*graph_rep*/, int /*n*/,
      int /*best_vertex_id*/) {}
  virtual void visualizeClusteredPaths(
      const std::shared_ptr<GraphManager> /*graph_manager*/,
      const ShortestPathsReport& /*graph_rep*/,
      const std::vector<Vertex*>& /*vertices*/,
      const std::vector<int>& /*cluster_ids*/) {}
  virtual void visualizeFailedEdges(std::shared_ptr<SampleStatistic> /*ss*/) {}
  virtual void visualizeGeofence(
      const std::shared_ptr<GeofenceManager> /*geofence_manager*/) {}
  virtual void visualizeGlobalGraph(
      const std::shared_ptr<GraphManager> /*graph_manager*/) {}
  virtual void visualizeGlobalPaths(
      const std::shared_ptr<GraphManager> /*graph_manager*/,
      std::vector<int>& /*to_frontier_ids*/, std::vector<int>& /*to_home_ids*/) {}
  virtual void visualizeGraph(
      const std::shared_ptr<GraphManager> /*graph_manager*/) {}
  virtual void visualizeHomingPath(
      const std::shared_ptr<GraphManager> /*graph_manager*/,
      const ShortestPathsReport& /*graph_rep*/, int /*current_id*/) {}
  virtual void visualizeHyperplanes(
      Eigen::Vector3d& /*center*/,
      std::vector<Eigen::Vector3d>& /*hyperplane_list*/,
      std::vector<Eigen::Vector3d>& /*tangent_point_list*/) {}
  virtual void visualizeModPath(
      const std::vector<geometry_msgs::msg::Pose>& /*path*/) {}
  virtual void visualizeNegativePaths(
      const std::vector<int>& /*ids*/,
      const std::shared_ptr<GraphManager> /*graph_manager*/,
      const ShortestPathsReport& /*graph_rep*/) {}
  virtual void visualizeNegativePaths(
      const std::vector<Eigen::Vector3d>& /*edge_vertices*/,
      const std::shared_ptr<GraphManager> /*graph_manager*/,
      const ShortestPathsReport& /*graph_rep*/) {}
  virtual void visualizeNoGainZones(
      std::vector<BoundedSpaceParams>& /*no_gain_zones*/) {}
  virtual void visualizePCL(const pcl::PointCloud<pcl::PointXYZ>* /*pcl*/) {}
  virtual void visualizeProjectedGraph(
      const std::shared_ptr<GraphManager> /*graph_manager*/) {}
  virtual void visualizeRays(
      const StateVec /*state*/,
      const std::vector<Eigen::Vector3d> /*ray_endpoints*/) {}
  virtual void visualizeRefPath(
      const std::vector<geometry_msgs::msg::Pose>& /*path*/) {}
  virtual void visualizeRobotState(StateVec& /*state*/,
                                   RobotParams& /*robot_params*/) {}
  virtual void visualizeRobotStateHistory(
      const std::vector<StateVec*> /*state_hist*/) {}
  virtual void visualizeSampler(RandomSampler& /*random_sampler*/) {}
  virtual void visualizeSensorFOV(StateVec& /*state*/,
                                  SensorParams& /*sensor_params*/) {}
  virtual void visualizeShortestPaths(
      const std::shared_ptr<GraphManager> /*graph_manager*/,
      const ShortestPathsReport& /*graph_rep*/) {}
  virtual void visualizeVolumetricGain(
      Eigen::Vector3d& /*bound_min*/, Eigen::Vector3d& /*bound_max*/,
      std::vector<std::pair<Eigen::Vector3d, MapManager::VoxelStatus>>&
      /*voxels*/,
      double /*voxel_size*/) {}
  virtual void visualizeWorkspace(StateVec& /*state*/,
                                  BoundedSpaceParams& /*global_ws*/,
                                  BoundedSpaceParams& /*local_ws*/) {}
};
