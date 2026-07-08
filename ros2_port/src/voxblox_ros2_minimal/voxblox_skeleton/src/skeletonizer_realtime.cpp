// #include <ros/wall_timer_options.h>
#include <voxblox/core/esdf_map.h>
#include <voxblox/core/tsdf_map.h>
#include <voxblox/integrator/merge_integration.h>
#include <voxblox_ros/conversions.h>
#include <voxblox_ros/esdf_server.h>
#include <voxblox_ros/mesh_pcl.h>
#include <voxblox_ros/mesh_vis.h>
#include <voxblox_ros/ptcloud_vis.h>
#include <rclcpp/rclcpp.hpp>
#include <string>

#include "voxblox_skeleton/io/skeleton_io.h"
#include "voxblox_skeleton/ros/skeleton_vis.h"
#include "voxblox_skeleton/skeleton_generator.h"

namespace voxblox {

class SkeletonizerNode {
 public:
  SkeletonizerNode(rclcpp::Node::SharedPtr node_ptr)
      : node_ptr_(node_ptr), frame_id_("world"), esdf_server_(node_ptr.get()) {
    // skeleton_pub_ = nh_private_.advertise<pcl::PointCloud<pcl::PointXYZ> >(
    //     "skeleton", 1, true);
    // sparse_graph_pub_ =
    // nh_private_.advertise<visualization_msgs::MarkerArray>(
    //     "sparse_graph", 1, true);
    skeleton_pub_ = node_ptr_->create_publisher<sensor_msgs::msg::PointCloud2>(
        std::string(node_ptr_->get_name()) + "/skeleton",
        rclcpp::QoS(1).transient_local());
    sparse_graph_pub_ =
        node_ptr_->create_publisher<visualization_msgs::msg::MarkerArray>(
            std::string(node_ptr_->get_name()) + "/sparse_graph",
            rclcpp::QoS(1).transient_local());
  }

  // Initialize the node.
  // void read_params(rclcpp::Node::SharedPtr node_ptr);

  void init();
  // Update ESDF
  void updateEsdf();
  // Start skeleton generation
  void generateSkeleton();

  // Make a skeletor!!!
  void skeletonize(Layer<EsdfVoxel>* esdf_layer, voxblox::Pointcloud* skeleton,
                   std::vector<float>* distances);

 private:
  // ros::NodeHandle nh_;
  // ros::NodeHandle nh_private_;
  rclcpp::Node::SharedPtr node_ptr_;

  std::string frame_id_;

  // ros::Publisher skeleton_pub_;
  // ros::Publisher sparse_graph_pub_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr skeleton_pub_;
  rclcpp::Publisher<visualization_msgs::msg::MarkerArray>::SharedPtr
      sparse_graph_pub_;

  EsdfServer esdf_server_;

  // ros params
  FloatingPoint min_separation_angle_;
  bool generate_by_layer_neighbors_;
  int num_neighbors_for_edge_;
  FloatingPoint min_gvd_distance_;
  bool update_esdf_;
  std::string input_filepath_, output_filepath_, sparse_graph_filepath_;
  float vertex_distance_threshold_;

  // ros::Timer esdf_update_timer_, skeleton_generator_timer_;
  rclcpp::TimerBase::SharedPtr esdf_update_timer_;
  rclcpp::TimerBase::SharedPtr skeleton_generator_timer_;
};

void SkeletonizerNode::init() {
  // skeleton_generator_timer_ = nh_.createTimer(
  //     ros::Duration(5.0), &SkeletonizerNode::generateSkeleton, this);
  skeleton_generator_timer_ = node_ptr_->create_wall_timer(
      std::chrono::duration<double>(5.0),
      std::bind(&SkeletonizerNode::generateSkeleton, this));
}

void SkeletonizerNode::generateSkeleton() {
  // Skeletonize????
  voxblox::Pointcloud pointcloud;
  std::vector<float> distances;
  skeletonize(esdf_server_.getEsdfMapPtr()->getEsdfLayerPtr(), &pointcloud,
              &distances);

  // Publish the skeleton.
  pcl::PointCloud<pcl::PointXYZI> ptcloud_pcl;
  pointcloudToPclXYZI(pointcloud, distances, &ptcloud_pcl);
  ptcloud_pcl.header.frame_id = frame_id_;
  sensor_msgs::msg::PointCloud2 ptcloud_msg;
  pcl::toROSMsg(ptcloud_pcl, ptcloud_msg);
  skeleton_pub_->publish(ptcloud_msg);
}

void SkeletonizerNode::skeletonize(Layer<EsdfVoxel>* esdf_layer,
                                   voxblox::Pointcloud* pointcloud,
                                   std::vector<float>* distances) {
  SkeletonGenerator skeleton_generator;
  // Load a file from the params.
  // nh_private_.param("input_filepath", input_filepath_, input_filepath_);
  // nh_private_.param("output_filepath", output_filepath_, output_filepath_);
  // nh_private_.param("sparse_graph_filepath", sparse_graph_filepath_,
  //                   sparse_graph_filepath_);
  // nh_private_.param("frame_id", frame_id_, frame_id_);
  if (!node_ptr_->has_parameter("input_filepath")) {
    node_ptr_->declare_parameter("input_filepath", input_filepath_);
  }

  if (!node_ptr_->has_parameter("output_filepath")) {
    node_ptr_->declare_parameter("output_filepath", output_filepath_);
  }
  if (!node_ptr_->has_parameter("sparse_graph_filepath")) {
    node_ptr_->declare_parameter("sparse_graph_filepath",
                                 sparse_graph_filepath_);
  }
  if (!node_ptr_->has_parameter("frame_id")) {
    node_ptr_->declare_parameter("frame_id", frame_id_);
  }

  node_ptr_->get_parameter("input_filepath", input_filepath_);
  node_ptr_->get_parameter("output_filepath", output_filepath_);
  node_ptr_->get_parameter("sparse_graph_filepath", sparse_graph_filepath_);
  node_ptr_->get_parameter("frame_id", frame_id_);

  RCLCPP_WARN_STREAM(node_ptr_->get_logger(),
                     "Input filepath: " << input_filepath_);
  RCLCPP_WARN_STREAM(node_ptr_->get_logger(),
                     "Output filepath: " << output_filepath_);
  RCLCPP_WARN_STREAM(node_ptr_->get_logger(),
                     "Sparse graph filepath: " << sparse_graph_filepath_);
  RCLCPP_WARN_STREAM(node_ptr_->get_logger(), "Frame ID: " << frame_id_);

  update_esdf_ = false;
  // nh_private_.param("update_esdf", update_esdf_, update_esdf_);
  // nh_private_.param("vertex_distance_threshold", vertex_distance_threshold_,
  //                   vertex_distance_threshold_);

  if (!node_ptr_->has_parameter("update_esdf")) {
    node_ptr_->declare_parameter("update_esdf", update_esdf_);
  }
  if (!node_ptr_->has_parameter("vertex_distance_threshold")) {
    node_ptr_->declare_parameter("vertex_distance_threshold",
                                 vertex_distance_threshold_);
  }
  node_ptr_->get_parameter("update_esdf", update_esdf_);
  node_ptr_->get_parameter("vertex_distance_threshold",
                           vertex_distance_threshold_);
  min_separation_angle_ = skeleton_generator.getMinSeparationAngle();
  // nh_private_.param("min_separation_angle", min_separation_angle_,
  //                   min_separation_angle_);
  if (!node_ptr_->has_parameter("min_separation_angle")) {
    node_ptr_->declare_parameter("min_separation_angle", min_separation_angle_);
  }
  node_ptr_->get_parameter("min_separation_angle", min_separation_angle_);
  skeleton_generator.setMinSeparationAngle(min_separation_angle_);

  generate_by_layer_neighbors_ =
      skeleton_generator.getGenerateByLayerNeighbors();
  // nh_private_.param("generate_by_layer_neighbors",
  // generate_by_layer_neighbors_,
  //                   generate_by_layer_neighbors_);
  if (!node_ptr_->has_parameter("generate_by_layer_neighbors")) {
    node_ptr_->declare_parameter("generate_by_layer_neighbors",
                                 generate_by_layer_neighbors_);
  }
  node_ptr_->get_parameter("generate_by_layer_neighbors",
                           generate_by_layer_neighbors_);
  skeleton_generator.setGenerateByLayerNeighbors(generate_by_layer_neighbors_);

  num_neighbors_for_edge_ = skeleton_generator.getNumNeighborsForEdge();
  // nh_private_.param("num_neighbors_for_edge", num_neighbors_for_edge_,
  //                   num_neighbors_for_edge_);
  if (!node_ptr_->has_parameter("num_neighbors_for_edge")) {
    node_ptr_->declare_parameter("num_neighbors_for_edge",
                                 num_neighbors_for_edge_);
  }
  node_ptr_->get_parameter("num_neighbors_for_edge", num_neighbors_for_edge_);
  skeleton_generator.setNumNeighborsForEdge(num_neighbors_for_edge_);

  min_gvd_distance_ = skeleton_generator.getMinGvdDistance();
  // nh_private_.param("min_gvd_distance", min_gvd_distance_,
  // min_gvd_distance_);
  if (!node_ptr_->has_parameter("min_gvd_distance")) {
    node_ptr_->declare_parameter("min_gvd_distance", min_gvd_distance_);
  }
  node_ptr_->get_parameter("min_gvd_distance", min_gvd_distance_);
  skeleton_generator.setMinGvdDistance(min_gvd_distance_);

  skeleton_generator.setEsdfLayer(esdf_layer);
  skeleton_generator.generateSkeleton();
  skeleton_generator.getSkeleton().getEdgePointcloudWithDistances(pointcloud,
                                                                  distances);
  // ROS_INFO("Finished generating skeleton.");
  RCLCPP_INFO(node_ptr_->get_logger(), "Finished generating skeleton.");

  skeleton_generator.generateSparseGraph();
  /* ROS_INFO("Finished generating sparse graph.");
  ROS_INFO_STREAM("Total Timings: " << std::endl << timing::Timing::Print()); */
  RCLCPP_INFO(node_ptr_->get_logger(), "Finished generating sparse graph.");
  RCLCPP_INFO_STREAM(node_ptr_->get_logger(),
                     "Total Timings: " << std::endl
                                       << timing::Timing::Print());

  // Now visualize the graph.
  const SparseSkeletonGraph& graph = skeleton_generator.getSparseGraph();
  visualization_msgs::msg::MarkerArray marker_array;
  visualizeSkeletonGraph(graph, "map_elevated", &marker_array,
                         vertex_distance_threshold_);
  sparse_graph_pub_->publish(marker_array);
}

}  // namespace voxblox

int main(int argc, char** argv) {
  // Let gflags re-parse later if needed (optional)
  // gflags::AllowCommandLineReparsing();

  // Init logging first (so FLAGS_* affect glog)
  google::InitGoogleLogging("-v=1");

  // Parse only non-help flags and REMOVE recognized ones from argv
  // so the remaining argv is clean for rclcpp.
  // gflags::ParseCommandLineNonHelpFlags(&argc, &argv, /*remove_flags=*/true);

  // Now ROS 2 sees only its own args (e.g., --ros-args --params-file …)
  rclcpp::init(argc, argv);

  FLAGS_alsologtostderr = true;

  auto nh = std::make_shared<rclcpp::Node>("voxblox_skeletonizer");
  voxblox::SkeletonizerNode node(nh);
  node.init();
  rclcpp::spin(nh);
  rclcpp::shutdown();
  return 0;
}
