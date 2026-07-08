#include "voxblox_ros/tsdf_server.h"

#include <minkindr_conversions/kindr_msg.h>
#include <minkindr_conversions/kindr_tf.h>
#include <rclcpp/logging.hpp>
#include <tf2/transform_datatypes.hpp>

#include "voxblox_ros/conversions.h"
#include "voxblox_ros/ptcloud_vis.h"
#include "voxblox_ros/ros_params.h"

namespace voxblox
{

static std::string generate_private_name(
  const rclcpp::Node *node_ptr,
  const std::string & name)
{
  if (name.empty() || name.front() == '/' || name.front() == '~') {
    return name;
  }
  return std::string(node_ptr->get_name()) + "/" + name;
}


TsdfServer::TsdfServer(rclcpp::Node * node_ptr)

: TsdfServer(node_ptr, getTsdfMapConfigFromRosParam(node_ptr),
    getTsdfIntegratorConfigFromRosParam(node_ptr),
    getMeshIntegratorConfigFromRosParam(node_ptr)) {}

TsdfServer::TsdfServer(
  rclcpp::Node * node_ptr, const TsdfMap::Config & config,
  const TsdfIntegratorBase::Config & integrator_config,
  const MeshIntegratorConfig & mesh_config)
: node_ptr_(node_ptr),
  verbose_(true),
  world_frame_("world"),
  icp_corrected_frame_("icp_corrected"),
  pose_corrected_frame_("pose_corrected"),
  max_block_distance_from_body_(std::numeric_limits<FloatingPoint>::max()),
  slice_level_(0.5),
  use_freespace_pointcloud_(false),
  color_map_(new RainbowColorMap()),
  publish_pointclouds_on_update_(false),
  publish_slices_(false),
  publish_pointclouds_(false),
  publish_tsdf_map_(false),
  cache_mesh_(false),
  enable_icp_(false),
  accumulate_icp_corrections_(true),
  pointcloud_queue_size_(1),
  num_subscribers_tsdf_map_(0),
  transformer_(node_ptr),
  min_time_between_msgs_(rclcpp::Duration::from_seconds(1))
{
  last_msg_time_freespace_ptcloud_ =
    rclcpp::Time(0, 0, node_ptr_->get_clock()->get_clock_type());
  tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(node_ptr_);

  getServerConfigFromRosParam(node_ptr);

  // Advertise topics.
  // surface_pointcloud_pub_ =
  //     nh_private_.advertise<pcl::PointCloud<pcl::PointXYZRGB>>(
  //         "surface_pointcloud", 1, true);
  // tsdf_pointcloud_pub_ =
  // nh_private_.advertise<pcl::PointCloud<pcl::PointXYZI>>(
  //     "tsdf_pointcloud", 1, true);
  // occupancy_marker_pub_ =
  //     nh_private_.advertise<visualization_msgs::msg::MarkerArray>(
  //         "occupied_nodes", 1, true);
  // tsdf_slice_pub_ = nh_private_.advertise<pcl::PointCloud<pcl::PointXYZI>>(
  //     "tsdf_slice", 1, true);
  surface_pointcloud_pub_ =
    node_ptr_->create_publisher<sensor_msgs::msg::PointCloud2>(
          // "surface_pointcloud", 1);
          generate_private_name(node_ptr_, "surface_pointcloud"), 1);
  tsdf_pointcloud_pub_ =
    node_ptr_->create_publisher<sensor_msgs::msg::PointCloud2>(
          // "tsdf_pointcloud", 1);
          generate_private_name(node_ptr_, "tsdf_pointcloud"), 1);
  occupancy_marker_pub_ =
    node_ptr_->create_publisher<visualization_msgs::msg::MarkerArray>(
          // "occupied_nodes", 1);
          generate_private_name(node_ptr_, "occupied_nodes"), 1);
  tsdf_slice_pub_ = node_ptr_->create_publisher<sensor_msgs::msg::PointCloud2>(
      // "tsdf_slice", 1);
      generate_private_name(node_ptr_, "tsdf_slice"), 1);

  // nh_private_.param("pointcloud_queue_size", pointcloud_queue_size_,
  //                   pointcloud_queue_size_);
  // pointcloud_sub_ = nh_.subscribe("pointcloud", pointcloud_queue_size_,
  //                                 &TsdfServer::insertPointcloud, this);

  // mesh_pub_ = nh_private_.advertise<voxblox_msgs::msg::Mesh>("mesh", 1,
  // true);
  // mesh_pub_ = node_ptr_->create_publisher<voxblox_msgs::msg::Mesh>("mesh", 1);
  mesh_pub_ = node_ptr_->create_publisher<voxblox_msgs::msg::Mesh>(
      generate_private_name(node_ptr_, "mesh"), 1);

  if (!node_ptr_->has_parameter("pointcloud_queue_size")) {
    node_ptr_->declare_parameter("pointcloud_queue_size",
                                 pointcloud_queue_size_);
  }
  node_ptr_->get_parameter("pointcloud_queue_size", pointcloud_queue_size_);

  pointcloud_sub_ =
    node_ptr_->create_subscription<sensor_msgs::msg::PointCloud2>(
          // "pointcloud", pointcloud_queue_size_,
          generate_private_name(node_ptr_, "pointcloud"), pointcloud_queue_size_,
          std::bind(&TsdfServer::insertPointcloud, this,
                    std::placeholders::_1));

  // Publishing/subscribing to a layer from another node (when using this as
  // a library, for example within a planner).
  // tsdf_map_pub_ =
  //     nh_private_.advertise<voxblox_msgs::msg::Layer>("tsdf_map_out", 1,
  //     false);
  // tsdf_map_sub_ = nh_private_.subscribe("tsdf_map_in", 1,
  //                                       &TsdfServer::tsdfMapCallback, this);
  // nh_private_.param("publish_tsdf_map", publish_tsdf_map_,
  // publish_tsdf_map_);

  tsdf_map_pub_ =
      // node_ptr_->create_publisher<voxblox_msgs::msg::Layer>("tsdf_map_out", 1);
    node_ptr_->create_publisher<voxblox_msgs::msg::Layer>(
          generate_private_name(node_ptr_, "tsdf_map_out"), 1);
  tsdf_map_sub_ = node_ptr_->create_subscription<voxblox_msgs::msg::Layer>(
      // "tsdf_map_in", 1,
      generate_private_name(node_ptr_, "tsdf_map_in"), 1,
      std::bind(&TsdfServer::tsdfMapCallback, this, std::placeholders::_1));
  if (!node_ptr_->has_parameter("publish_tsdf_map")) {
    node_ptr_->declare_parameter("publish_tsdf_map", publish_tsdf_map_);
  }
  node_ptr_->get_parameter("publish_tsdf_map", publish_tsdf_map_);

  if (use_freespace_pointcloud_) {
    // points that are not inside an object, but may also not be on a surface.
    // These will only be used to mark freespace beyond the truncation distance.
    // freespace_pointcloud_sub_ =
    //     nh_.subscribe("freespace_pointcloud", pointcloud_queue_size_,
    //                   &TsdfServer::insertFreespacePointcloud, this);
    freespace_pointcloud_sub_ =
      node_ptr_->create_subscription<sensor_msgs::msg::PointCloud2>(
            // "freespace_pointcloud", pointcloud_queue_size_,
            generate_private_name(node_ptr_, "freespace_pointcloud"), pointcloud_queue_size_,
            std::bind(&TsdfServer::insertFreespacePointcloud, this,
                      std::placeholders::_1));
  }

  if (enable_icp_) {
    // icp_transform_pub_ =
    //     nh_private_.advertise<geometry_msgs::msg::TransformStamped>(
    //         "icp_transform", 1, true);
    // nh_private_.param("icp_corrected_frame", icp_corrected_frame_,
    //                   icp_corrected_frame_);
    // nh_private_.param("pose_corrected_frame", pose_corrected_frame_,
    //                   pose_corrected_frame_);
    icp_transform_pub_ =
      node_ptr_->create_publisher<geometry_msgs::msg::TransformStamped>(
            // "icp_transform", 1);
            generate_private_name(node_ptr_, "icp_transform"), 1);
    if (!node_ptr_->has_parameter("icp_corrected_frame")) {
      node_ptr_->declare_parameter("icp_corrected_frame", icp_corrected_frame_);
    }
    if (!node_ptr_->has_parameter("pose_corrected_frame")) {
      node_ptr_->declare_parameter("pose_corrected_frame",
                                   pose_corrected_frame_);
    }
    node_ptr_->get_parameter("icp_corrected_frame", icp_corrected_frame_);
    node_ptr_->get_parameter("pose_corrected_frame", pose_corrected_frame_);
  }

  // Initialize TSDF Map and integrator.
  tsdf_map_.reset(new TsdfMap(config));

  std::string method("merged");
  // nh_private_.param("method", method, method);
  // node_ptr_->declare_parameter("method", method);
  if (!node_ptr_->has_parameter("method")) {
    node_ptr_->declare_parameter("method", method);
  }
  node_ptr_->get_parameter("method", method);

  if (method.compare("simple") == 0) {
    tsdf_integrator_.reset(new SimpleTsdfIntegrator(
        integrator_config, tsdf_map_->getTsdfLayerPtr()));
  } else if (method.compare("merged") == 0) {
    tsdf_integrator_.reset(new MergedTsdfIntegrator(
        integrator_config, tsdf_map_->getTsdfLayerPtr()));
  } else if (method.compare("fast") == 0) {
    tsdf_integrator_.reset(new FastTsdfIntegrator(
        integrator_config, tsdf_map_->getTsdfLayerPtr()));
  } else {
    tsdf_integrator_.reset(new SimpleTsdfIntegrator(
        integrator_config, tsdf_map_->getTsdfLayerPtr()));
  }

  mesh_layer_.reset(new MeshLayer(tsdf_map_->block_size()));

  mesh_integrator_.reset(new MeshIntegrator<TsdfVoxel>(
      mesh_config, tsdf_map_->getTsdfLayerPtr(), mesh_layer_.get()));

  icp_.reset(new ICP(getICPConfigFromRosParam(node_ptr_)));

  // Advertise services.
  // generate_mesh_srv_ = nh_private_.advertiseService(
  //     "generate_mesh", &TsdfServer::generateMeshCallback, this);
  // clear_map_srv_ = nh_private_.advertiseService(
  //     "clear_map", &TsdfServer::clearMapCallback, this);
  // save_map_srv_ = nh_private_.advertiseService(
  //     "save_map", &TsdfServer::saveMapCallback, this);
  // load_map_srv_ = nh_private_.advertiseService(
  //     "load_map", &TsdfServer::loadMapCallback, this);
  // publish_pointclouds_srv_ = nh_private_.advertiseService(
  //     "publish_pointclouds", &TsdfServer::publishPointcloudsCallback, this);
  // publish_tsdf_map_srv_ = nh_private_.advertiseService(
  //     "publish_map", &TsdfServer::publishTsdfMapCallback, this);
  generate_mesh_srv_ = node_ptr_->create_service<std_srvs::srv::Empty>(
      // "generate_mesh",
    generate_private_name(node_ptr_, "generate_mesh"),
    std::bind(&TsdfServer::generateMeshCallback, this,
                                 std::placeholders::_1, std::placeholders::_2));
  clear_map_srv_ = node_ptr_->create_service<std_srvs::srv::Empty>(
      // "clear_map",
    generate_private_name(node_ptr_, "clear_map"),
    std::bind(&TsdfServer::clearMapCallback, this,
                             std::placeholders::_1, std::placeholders::_2));
  save_map_srv_ = node_ptr_->create_service<voxblox_msgs::srv::FilePath>(
      // "save_map",
    generate_private_name(node_ptr_, "save_map"),
    std::bind(&TsdfServer::saveMapCallback, this,
                            std::placeholders::_1, std::placeholders::_2));
  load_map_srv_ = node_ptr_->create_service<voxblox_msgs::srv::FilePath>(
      // "load_map",
    generate_private_name(node_ptr_, "load_map"),
    std::bind(&TsdfServer::loadMapCallback, this,
                            std::placeholders::_1, std::placeholders::_2));
  publish_pointclouds_srv_ = node_ptr_->create_service<std_srvs::srv::Empty>(
      // "publish_pointclouds",
    generate_private_name(node_ptr_, "publish_pointclouds"),
      std::bind(&TsdfServer::publishPointcloudsCallback, this,
                std::placeholders::_1, std::placeholders::_2));
  publish_tsdf_map_srv_ = node_ptr_->create_service<std_srvs::srv::Empty>(
      // "publish_map",
    generate_private_name(node_ptr_, "publish_map"),
    std::bind(&TsdfServer::publishTsdfMapCallback, this,
                               std::placeholders::_1, std::placeholders::_2));

  // If set, use a timer to progressively integrate the mesh.
  double update_mesh_every_n_sec = 1.0;
  // nh_private_.param("update_mesh_every_n_sec", update_mesh_every_n_sec,
  //                   update_mesh_every_n_sec);
  /* node_ptr_->declare_parameter("update_mesh_every_n_sec",
                               update_mesh_every_n_sec); */
  if (!node_ptr_->has_parameter("update_mesh_every_n_sec")) {
    node_ptr_->declare_parameter("update_mesh_every_n_sec",
                                 update_mesh_every_n_sec);
  }
  node_ptr_->get_parameter("update_mesh_every_n_sec", update_mesh_every_n_sec);

  if (update_mesh_every_n_sec > 0.0) {
    // update_mesh_timer_ =
    // nh_private_.createTimer(ros::Duration(update_mesh_every_n_sec),
    //                         &TsdfServer::updateMeshEvent, this);
    update_mesh_timer_ = node_ptr_->create_wall_timer(
        std::chrono::duration<double>(update_mesh_every_n_sec),
        std::bind(&TsdfServer::updateMeshEvent, this));
  }

  double publish_map_every_n_sec = 1.0;
  // nh_private_.param("publish_map_every_n_sec", publish_map_every_n_sec,
  //                   publish_map_every_n_sec);
  if (!node_ptr_->has_parameter("publish_map_every_n_sec")) {
    node_ptr_->declare_parameter("publish_map_every_n_sec",
                                 publish_map_every_n_sec);
  }
  node_ptr_->get_parameter("publish_map_every_n_sec", publish_map_every_n_sec);

  if (publish_map_every_n_sec > 0.0) {
    // publish_map_timer_ =
    //     nh_private_.createTimer(ros::Duration(publish_map_every_n_sec),
    //                             &TsdfServer::publishMapEvent, this);
    publish_map_timer_ = node_ptr_->create_wall_timer(
        std::chrono::duration<double>(publish_map_every_n_sec),
        std::bind(&TsdfServer::publishMapEvent, this));
  }
}

void TsdfServer::getServerConfigFromRosParam(rclcpp::Node * node_ptr)
{
  // Before subscribing, determine minimum time between messages.
  // 0 by default.
  double min_time_between_msgs_sec = 0.0;
  // nh_private.param("min_time_between_msgs_sec", min_time_between_msgs_sec,
  //                  min_time_between_msgs_sec);
  // min_time_between_msgs_.fromSec(min_time_between_msgs_sec);

  // nh_private.param("max_block_distance_from_body",
  //                  max_block_distance_from_body_,
  //                  max_block_distance_from_body_);
  // nh_private.param("slice_level", slice_level_, slice_level_);
  // nh_private.param("world_frame", world_frame_, world_frame_);
  // nh_private.param("publish_pointclouds_on_update",
  //                  publish_pointclouds_on_update_,
  //                  publish_pointclouds_on_update_);
  // nh_private.param("publish_slices", publish_slices_, publish_slices_);
  // nh_private.param("publish_pointclouds", publish_pointclouds_,
  //                  publish_pointclouds_);

  // nh_private.param("use_freespace_pointcloud", use_freespace_pointcloud_,
  //                  use_freespace_pointcloud_);
  // nh_private.param("pointcloud_queue_size", pointcloud_queue_size_,
  //                  pointcloud_queue_size_);
  // nh_private.param("enable_icp", enable_icp_, enable_icp_);
  // nh_private.param("accumulate_icp_corrections", accumulate_icp_corrections_,
  //                  accumulate_icp_corrections_);

  // nh_private.param("verbose", verbose_, verbose_);

  // // Mesh settings.
  // nh_private.param("mesh_filename", mesh_filename_, mesh_filename_);
  // std::string color_mode("");
  // nh_private.param("color_mode", color_mode, color_mode);
  // color_mode_ = getColorModeFromString(color_mode);

  // // Color map for intensity pointclouds.
  // std::string intensity_colormap("rainbow");
  // float intensity_max_value = kDefaultMaxIntensity;
  // nh_private.param("intensity_colormap", intensity_colormap,
  //                  intensity_colormap);
  // nh_private.param("intensity_max_value", intensity_max_value,
  //                  intensity_max_value);
  if (!node_ptr->has_parameter("min_time_between_msgs_sec")) {
    node_ptr->declare_parameter("min_time_between_msgs_sec",
                                min_time_between_msgs_sec);
  }
  if (!node_ptr->has_parameter("max_block_distance_from_body")) {
    node_ptr->declare_parameter("max_block_distance_from_body",
                                max_block_distance_from_body_);
  }
  if (!node_ptr->has_parameter("slice_level")) {
    node_ptr->declare_parameter("slice_level", slice_level_);
  }
  if (!node_ptr->has_parameter("world_frame")) {
    node_ptr->declare_parameter("world_frame", world_frame_);
  }
  if (!node_ptr->has_parameter("publish_pointclouds_on_update")) {
    node_ptr->declare_parameter("publish_pointclouds_on_update",
                                publish_pointclouds_on_update_);
  }
  if (!node_ptr->has_parameter("publish_slices")) {
    node_ptr->declare_parameter("publish_slices", publish_slices_);
  }
  if (!node_ptr->has_parameter("publish_pointclouds")) {
    node_ptr->declare_parameter("publish_pointclouds", publish_pointclouds_);
  }
  if (!node_ptr->has_parameter("use_freespace_pointcloud")) {
    node_ptr->declare_parameter("use_freespace_pointcloud",
                                use_freespace_pointcloud_);
  }
  if (!node_ptr->has_parameter("pointcloud_queue_size")) {
    node_ptr->declare_parameter("pointcloud_queue_size",
                                pointcloud_queue_size_);
  }
  if (!node_ptr->has_parameter("enable_icp")) {
    node_ptr->declare_parameter("enable_icp", enable_icp_);
  }
  if (!node_ptr->has_parameter("accumulate_icp_corrections")) {
    node_ptr->declare_parameter("accumulate_icp_corrections",
                                accumulate_icp_corrections_);
  }
  if (!node_ptr->has_parameter("verbose")) {
    node_ptr->declare_parameter("verbose", verbose_);
  }
  if (!node_ptr->has_parameter("mesh_filename")) {
    node_ptr->declare_parameter("mesh_filename", mesh_filename_);
  }
  std::string color_mode = "color";
  if (!node_ptr->has_parameter("color_mode")) {
    node_ptr->declare_parameter("color_mode", color_mode);
  }
  if (!node_ptr->has_parameter("intensity_colormap")) {
    node_ptr->declare_parameter("intensity_colormap", std::string("rainbow"));
  }
  if (!node_ptr->has_parameter("intensity_max_value")) {
    node_ptr->declare_parameter("intensity_max_value", kDefaultMaxIntensity);
  }

  node_ptr->get_parameter("min_time_between_msgs_sec",
                          min_time_between_msgs_sec);
  min_time_between_msgs_.from_seconds(min_time_between_msgs_sec);
  node_ptr->get_parameter("max_block_distance_from_body",
                          max_block_distance_from_body_);
  node_ptr->get_parameter("slice_level", slice_level_);
  node_ptr->get_parameter("world_frame", world_frame_);
  node_ptr->get_parameter("publish_pointclouds_on_update",
                          publish_pointclouds_on_update_);
  node_ptr->get_parameter("publish_slices", publish_slices_);
  node_ptr->get_parameter("publish_pointclouds", publish_pointclouds_);
  node_ptr->get_parameter("use_freespace_pointcloud",
                          use_freespace_pointcloud_);
  node_ptr->get_parameter("pointcloud_queue_size", pointcloud_queue_size_);
  node_ptr->get_parameter("enable_icp", enable_icp_);
  node_ptr->get_parameter("accumulate_icp_corrections",
                          accumulate_icp_corrections_);
  node_ptr->get_parameter("verbose", verbose_);
  RCLCPP_ERROR(node_ptr_->get_logger(), "Verbose mode is %s",
               verbose_ ? "on" : "off");
  node_ptr->get_parameter("mesh_filename", mesh_filename_);

  // node_ptr->get_parameter("color_mode", color_mode_);
  node_ptr->get_parameter("color_mode", color_mode);
  color_mode_ = getColorModeFromString(color_mode);

  std::string intensity_colormap("rainbow");
  float intensity_max_value = kDefaultMaxIntensity;
  node_ptr->get_parameter("intensity_colormap", intensity_colormap);
  node_ptr->get_parameter("intensity_max_value", intensity_max_value);

  // Default set in constructor.
  if (intensity_colormap == "rainbow") {
    color_map_.reset(new RainbowColorMap());
  } else if (intensity_colormap == "inverse_rainbow") {
    color_map_.reset(new InverseRainbowColorMap());
  } else if (intensity_colormap == "grayscale") {
    color_map_.reset(new GrayscaleColorMap());
  } else if (intensity_colormap == "inverse_grayscale") {
    color_map_.reset(new InverseGrayscaleColorMap());
  } else if (intensity_colormap == "ironbow") {
    color_map_.reset(new IronbowColorMap());
  } else {
    // ROS_ERROR_STREAM("Invalid color map: " << intensity_colormap);
    RCLCPP_ERROR(node_ptr_->get_logger(), "Invalid color map: %s",
                 intensity_colormap.c_str());
  }
  color_map_->setMaxValue(intensity_max_value);
}

void TsdfServer::processPointCloudMessageAndInsert(
  const sensor_msgs::msg::PointCloud2::SharedPtr & pointcloud_msg,
  const Transformation & T_G_C, const bool is_freespace_pointcloud)
{
  // Convert the PCL pointcloud into our awesome format.

  // Horrible hack fix to fix color parsing colors in PCL.
  bool color_pointcloud = false;
  bool has_intensity = false;
  for (size_t d = 0; d < pointcloud_msg->fields.size(); ++d) {
    if (pointcloud_msg->fields[d].name == std::string("rgb")) {
      pointcloud_msg->fields[d].datatype =
        sensor_msgs::msg::PointField::FLOAT32;
      color_pointcloud = true;
    } else if (pointcloud_msg->fields[d].name == std::string("intensity")) {
      has_intensity = true;
    }
  }

  Pointcloud points_C;
  Colors colors;
  timing::Timer ptcloud_timer("ptcloud_preprocess");

  // Convert differently depending on RGB or I type.
  if (color_pointcloud) {
    pcl::PointCloud<pcl::PointXYZRGB> pointcloud_pcl;
    // pointcloud_pcl is modified below:
    pcl::fromROSMsg(*pointcloud_msg, pointcloud_pcl);
    convertPointcloud(pointcloud_pcl, color_map_, &points_C, &colors);
  } else if (has_intensity) {
    pcl::PointCloud<pcl::PointXYZI> pointcloud_pcl;
    // pointcloud_pcl is modified below:
    pcl::fromROSMsg(*pointcloud_msg, pointcloud_pcl);
    convertPointcloud(pointcloud_pcl, color_map_, &points_C, &colors);
  } else {
    pcl::PointCloud<pcl::PointXYZ> pointcloud_pcl;
    // pointcloud_pcl is modified below:
    pcl::fromROSMsg(*pointcloud_msg, pointcloud_pcl);
    convertPointcloud(pointcloud_pcl, color_map_, &points_C, &colors);
  }
  ptcloud_timer.Stop();

  Transformation T_G_C_refined = T_G_C;
  if (enable_icp_) {
    timing::Timer icp_timer("icp");
    if (!accumulate_icp_corrections_) {
      icp_corrected_transform_.setIdentity();
    }
    static Transformation T_offset;
    const size_t num_icp_updates =
      icp_->runICP(tsdf_map_->getTsdfLayer(), points_C,
                     icp_corrected_transform_ * T_G_C, &T_G_C_refined);
    if (verbose_) {
      // ROS_INFO("ICP refinement performed %zu successful update steps",
      // num_icp_updates);
      RCLCPP_INFO(node_ptr_->get_logger(),
                  "ICP refinement performed %zu successful update steps",
                  num_icp_updates);
    }
    icp_corrected_transform_ = T_G_C_refined * T_G_C.inverse();

    if (!icp_->refiningRollPitch()) {
      // its already removed internally but small floating point errors can
      // build up if accumulating transforms
      Transformation::Vector6 T_vec = icp_corrected_transform_.log();
      T_vec[3] = 0.0;
      T_vec[4] = 0.0;
      icp_corrected_transform_ = Transformation::exp(T_vec);
    }

    // Publish transforms as both TF and message.
    tf2::Transform icp_tf_msg, pose_tf_msg;
    geometry_msgs::msg::TransformStamped transform_msg;

    tf::transformKindrToTF(icp_corrected_transform_.cast<double>(),
                           &icp_tf_msg);
    tf::transformKindrToTF(T_G_C.cast<double>(), &pose_tf_msg);
    tf::transformKindrToMsg(icp_corrected_transform_.cast<double>(),
                            &transform_msg.transform);

    // tf_broadcaster_->sendTransform(
    //     tf::StampedTransform(icp_tf_msg, pointcloud_msg->header.stamp,
    //                          world_frame_, icp_corrected_frame_));
    auto stamp = rclcpp::Time(pointcloud_msg->header.stamp,
                              node_ptr_->get_clock()->get_clock_type());
    auto msg_transform_stamped = geometry_msgs::msg::TransformStamped();
    msg_transform_stamped.header.stamp = stamp;
    msg_transform_stamped.header.frame_id = world_frame_;
    msg_transform_stamped.child_frame_id = icp_corrected_frame_;
    msg_transform_stamped.transform = tf2::toMsg(icp_tf_msg);

    tf_broadcaster_->sendTransform(msg_transform_stamped);

    // tf_broadcaster_.sendTransform(
    //     tf::StampedTransform(pose_tf_msg, pointcloud_msg->header.stamp,
    //                          icp_corrected_frame_, pose_corrected_frame_));
    auto msg_transform_stamped2 = geometry_msgs::msg::TransformStamped();
    msg_transform_stamped2.header.stamp = stamp;
    msg_transform_stamped2.header.frame_id = icp_corrected_frame_;
    msg_transform_stamped2.child_frame_id = pose_corrected_frame_;
    msg_transform_stamped2.transform = tf2::toMsg(pose_tf_msg);
    tf_broadcaster_->sendTransform(msg_transform_stamped2);

    transform_msg.header.frame_id = world_frame_;
    transform_msg.child_frame_id = icp_corrected_frame_;
    // icp_transform_pub_.publish(transform_msg);
    icp_transform_pub_->publish(transform_msg);

    icp_timer.Stop();
  }

  if (verbose_) {
    // ROS_INFO("Integrating a pointcloud with %lu points.", points_C.size());
    RCLCPP_INFO(node_ptr_->get_logger(),
                "Integrating a pointcloud with %lu points.", points_C.size());
  }

  // ros::WallTime start = ros::WallTime::now();
  rclcpp::Time start = node_ptr_->now();

  integratePointcloud(T_G_C_refined, points_C, colors, is_freespace_pointcloud);
  // ros::WallTime end = ros::WallTime::now();
  rclcpp::Time end = node_ptr_->now();
  if (verbose_) {
    // ROS_INFO("Finished integrating in %f seconds, have %lu blocks.",
    // (end - start).toSec(),
    // tsdf_map_->getTsdfLayer().getNumberOfAllocatedBlocks());
    RCLCPP_INFO(node_ptr_->get_logger(),
                "Finished integrating in %f seconds, have %lu blocks.",
      (end - start).seconds(),
                tsdf_map_->getTsdfLayer().getNumberOfAllocatedBlocks());
  }

  timing::Timer block_remove_timer("remove_distant_blocks");
  tsdf_map_->getTsdfLayerPtr()->removeDistantBlocks(
      T_G_C.getPosition(), max_block_distance_from_body_);
  mesh_layer_->clearDistantMesh(T_G_C.getPosition(),
                                max_block_distance_from_body_);
  block_remove_timer.Stop();

  // Callback for inheriting classes.
  newPoseCallback(T_G_C);
}

// Checks if we can get the next message from queue.
bool TsdfServer::getNextPointcloudFromQueue(
  std::queue<sensor_msgs::msg::PointCloud2::SharedPtr> * queue,
  sensor_msgs::msg::PointCloud2::SharedPtr * pointcloud_msg,
  Transformation * T_G_C)
{
  const size_t kMaxQueueSize = 10;
  if (queue->empty()) {
    return false;
  }

  *pointcloud_msg = queue->front();
  auto origin_frame = (*pointcloud_msg)->header.frame_id;
  if (transformer_.lookupTransform((*pointcloud_msg)->header.frame_id,
                                   world_frame_,
    (*pointcloud_msg)->header.stamp, T_G_C))
  {
    queue->pop();
    // RCLCPP_WARN(node_ptr_->get_logger(),
    //             "Got transform for pointcloud at time %.3f sec.",
    //             rclcpp::Time((*pointcloud_msg)->header.stamp,
    //                          node_ptr_->get_clock()->get_clock_type())
    //                 .seconds());
    return true;
  } else {
    RCLCPP_WARN(node_ptr_->get_logger(),
                "Could not get transform for pointcloud at time %.3f sec. , "
                "from %s to %s. "
                "Waiting for the transform to become available.",
                rclcpp::Time((*pointcloud_msg)->header.stamp,
                             node_ptr_->get_clock()->get_clock_type())
      .seconds(),
                origin_frame.c_str(), world_frame_.c_str());
  }

  if (queue->size() >= kMaxQueueSize) {
    // ROS_ERROR_THROTTLE(60,
    //                    "Input pointcloud queue getting too long! Dropping "
    //                    "some pointclouds. Either unable to look up
    //                    transform " "timestamps or the processing is taking
    //                    too long.");
    RCLCPP_ERROR_THROTTLE(
        node_ptr_->get_logger(), *node_ptr_->get_clock(), 1000,
        "Input pointcloud queue getting too long! Dropping "
        "some pointclouds. Either unable to look up transform "
        "timestamps or the processing is taking too long.");

    while (queue->size() >= kMaxQueueSize) {
      queue->pop();
    }
  }

  return false;
}

// void TsdfServer::insertPointcloud(
//     const sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg_in) {
//   const auto clk_type = node_ptr_->get_clock()->get_clock_type();
//   if (rclcpp::Time(pointcloud_msg_in->header.stamp, clk_type) -
//           last_msg_time_ptcloud_ >
//       min_time_between_msgs_) {
//     last_msg_time_ptcloud_ = pointcloud_msg_in->header.stamp;
//     // So we have to process the queue anyway... Push this back.
//     pointcloud_queue_.push(pointcloud_msg_in);
//   }

//   Transformation T_G_C;
//   sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg;
//   bool processed_any = false;
//   while (
//       getNextPointcloudFromQueue(&pointcloud_queue_, &pointcloud_msg,
//       &T_G_C)) {
//     constexpr bool is_freespace_pointcloud = false;
//     processPointCloudMessageAndInsert(pointcloud_msg, T_G_C,
//                                       is_freespace_pointcloud);
//     processed_any = true;
//   }

//   if (!processed_any) {
//     return;
//   }

//   if (publish_pointclouds_on_update_) {
//     publishPointclouds();
//   }

//   if (verbose_) {
//     // ROS_INFO_STREAM("Timings: " << std::endl << timing::Timing::Print());
//     // ROS_INFO_STREAM(
//     //     "Layer memory: " << tsdf_map_->getTsdfLayer().getMemorySize());
//     RCLCPP_INFO_STREAM(node_ptr_->get_logger(),
//                        "Timings: " << std::endl
//                                    << timing::Timing::Print());
//     RCLCPP_INFO_STREAM(
//         node_ptr_->get_logger(),
//         "Layer memory: " << tsdf_map_->getTsdfLayer().getMemorySize());
//   }
// }

void TsdfServer::insertPointcloud(
  const sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg_in)
{
  // RCLCPP_INFO(node_ptr_->get_logger(),
  //             "TSDF Server received pointcloud message with %d points at time
  //             "
  //             "%.3f sec.",
  //             pointcloud_msg_in->width * pointcloud_msg_in->height,
  //             rclcpp::Time(pointcloud_msg_in->header.stamp,
  //                          node_ptr_->get_clock()->get_clock_type())
  //                 .seconds());

  const auto clk_type = node_ptr_->get_clock()->get_clock_type();
  const rclcpp::Time t_msg(pointcloud_msg_in->header.stamp, clk_type);

  // First message or clock-type mismatch: seed and enqueue
  if (last_msg_time_ptcloud_.nanoseconds() == 0 ||
    last_msg_time_ptcloud_.get_clock_type() != clk_type)
  {
    RCLCPP_WARN(
        node_ptr_->get_logger(),
        "TSDF Server pointcloud clock type changed or first message. Resetting "
        "last message time.");
    last_msg_time_ptcloud_ = t_msg;  // <-- use t_msg (same clock)
    pointcloud_queue_.push(pointcloud_msg_in);
  } else if ((t_msg - last_msg_time_ptcloud_) > min_time_between_msgs_) {
    last_msg_time_ptcloud_ = t_msg;  // <-- use t_msg (same clock)
    pointcloud_queue_.push(pointcloud_msg_in);
  }

  Transformation T_G_C;
  sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg;
  bool processed_any = false;
  while (
    getNextPointcloudFromQueue(&pointcloud_queue_, &pointcloud_msg, &T_G_C))
  {
    constexpr bool is_freespace_pointcloud = false;
    processPointCloudMessageAndInsert(pointcloud_msg, T_G_C,
                                      is_freespace_pointcloud);
    processed_any = true;
  }

  if (!processed_any) {return;}

  if (publish_pointclouds_on_update_) {publishPointclouds();}

  if (verbose_) {
    RCLCPP_INFO_STREAM(node_ptr_->get_logger(), "Timings:\n"
                                                    << timing::Timing::Print());
    RCLCPP_INFO_STREAM(
        node_ptr_->get_logger(),
        "Layer memory: " << tsdf_map_->getTsdfLayer().getMemorySize());
  }
}

void TsdfServer::insertFreespacePointcloud(
  const sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg_in)
{
  const auto clk_type = node_ptr_->get_clock()->get_clock_type();
  if (rclcpp::Time(pointcloud_msg_in->header.stamp, clk_type) -
    last_msg_time_freespace_ptcloud_ >
    min_time_between_msgs_)
  {
    last_msg_time_freespace_ptcloud_ = pointcloud_msg_in->header.stamp;
    // So we have to process the queue anyway... Push this back.
    freespace_pointcloud_queue_.push(pointcloud_msg_in);
  }

  Transformation T_G_C;
  sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg;
  while (getNextPointcloudFromQueue(&freespace_pointcloud_queue_,
                                    &pointcloud_msg, &T_G_C))
  {
    constexpr bool is_freespace_pointcloud = true;
    processPointCloudMessageAndInsert(pointcloud_msg, T_G_C,
                                      is_freespace_pointcloud);
  }
}

void TsdfServer::integratePointcloud(
  const Transformation & T_G_C,
  const Pointcloud & ptcloud_C,
  const Colors & colors,
  const bool is_freespace_pointcloud)
{
  CHECK_EQ(ptcloud_C.size(), colors.size());
  tsdf_integrator_->integratePointCloud(T_G_C, ptcloud_C, colors,
                                        is_freespace_pointcloud);
}

void TsdfServer::publishAllUpdatedTsdfVoxels()
{
  // Create a pointcloud with distance = intensity.
  pcl::PointCloud<pcl::PointXYZI> pointcloud;

  createDistancePointcloudFromTsdfLayer(tsdf_map_->getTsdfLayer(), &pointcloud);

  pointcloud.header.frame_id = world_frame_;
  sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg(
    new sensor_msgs::msg::PointCloud2);
  pcl::toROSMsg(pointcloud, *pointcloud_msg);
  tsdf_pointcloud_pub_->publish(*pointcloud_msg);
}

void TsdfServer::publishTsdfSurfacePoints()
{
  // Create a pointcloud with distance = intensity.
  pcl::PointCloud<pcl::PointXYZRGB> pointcloud;
  const float surface_distance_thresh =
    tsdf_map_->getTsdfLayer().voxel_size() * 0.75;
  createSurfacePointcloudFromTsdfLayer(tsdf_map_->getTsdfLayer(),
                                       surface_distance_thresh, &pointcloud);

  pointcloud.header.frame_id = world_frame_;
  sensor_msgs::msg::PointCloud2 pointcloud_msg;
  pcl::toROSMsg(pointcloud, pointcloud_msg);
  surface_pointcloud_pub_->publish(pointcloud_msg);
}

void TsdfServer::publishTsdfOccupiedNodes()
{
  // Create a pointcloud with distance = intensity.
  visualization_msgs::msg::MarkerArray marker_array;
  createOccupancyBlocksFromTsdfLayer(tsdf_map_->getTsdfLayer(), world_frame_,
                                     &marker_array);
  occupancy_marker_pub_->publish(marker_array);  //
}

void TsdfServer::publishSlices()
{
  pcl::PointCloud<pcl::PointXYZI> pointcloud;

  createDistancePointcloudFromTsdfLayerSlice(tsdf_map_->getTsdfLayer(), 2,
                                             slice_level_, &pointcloud);

  pointcloud.header.frame_id = world_frame_;
  sensor_msgs::msg::PointCloud2::SharedPtr pointcloud_msg(
    new sensor_msgs::msg::PointCloud2);
  pcl::toROSMsg(pointcloud, *pointcloud_msg);
  tsdf_slice_pub_->publish(*pointcloud_msg);
}

void TsdfServer::publishMap(bool reset_remote_map)
{
  if (!publish_tsdf_map_) {
    return;
  }
  int subscribers = this->tsdf_map_pub_->get_subscription_count();
  if (subscribers > 0) {
    if (num_subscribers_tsdf_map_ < subscribers) {
      // Always reset the remote map and send all when a new subscriber
      // subscribes. A bit of overhead for other subscribers, but better than
      // inconsistent map states.
      reset_remote_map = true;
    }
    const bool only_updated = !reset_remote_map;
    timing::Timer publish_map_timer("map/publish_tsdf");
    voxblox_msgs::msg::Layer layer_msg;
    serializeLayerAsMsg<TsdfVoxel>(this->tsdf_map_->getTsdfLayer(),
                                   only_updated, &layer_msg);
    if (reset_remote_map) {
      layer_msg.action = static_cast<uint8_t>(MapDerializationAction::kReset);
    }
    this->tsdf_map_pub_->publish(layer_msg);
    publish_map_timer.Stop();
  }
  num_subscribers_tsdf_map_ = subscribers;
}

void TsdfServer::publishPointclouds()
{
  // Combined function to publish all possible pointcloud messages -- surface
  // pointclouds, updated points, and occupied points.
  publishAllUpdatedTsdfVoxels();
  publishTsdfSurfacePoints();
  publishTsdfOccupiedNodes();
  if (publish_slices_) {
    publishSlices();
  }
}

void TsdfServer::updateMesh()
{
  if (verbose_) {
    // ROS_INFO("Updating mesh.");
    RCLCPP_INFO(node_ptr_->get_logger(), "Updating mesh.");
  }

  timing::Timer generate_mesh_timer("mesh/update");
  constexpr bool only_mesh_updated_blocks = true;
  constexpr bool clear_updated_flag = true;
  mesh_integrator_->generateMesh(only_mesh_updated_blocks, clear_updated_flag);
  generate_mesh_timer.Stop();

  timing::Timer publish_mesh_timer("mesh/publish");

  voxblox_msgs::msg::Mesh mesh_msg;
  generateVoxbloxMeshMsg(mesh_layer_, color_mode_, &mesh_msg);
  mesh_msg.header.frame_id = world_frame_;
  mesh_pub_->publish(mesh_msg);

  if (cache_mesh_) {
    cached_mesh_msg_ = mesh_msg;
  }

  publish_mesh_timer.Stop();

  if (publish_pointclouds_ && !publish_pointclouds_on_update_) {
    publishPointclouds();
  }
}

bool TsdfServer::generateMesh()
{
  timing::Timer generate_mesh_timer("mesh/generate");
  const bool clear_mesh = true;
  if (clear_mesh) {
    constexpr bool only_mesh_updated_blocks = false;
    constexpr bool clear_updated_flag = true;
    mesh_integrator_->generateMesh(only_mesh_updated_blocks,
                                   clear_updated_flag);
  } else {
    constexpr bool only_mesh_updated_blocks = true;
    constexpr bool clear_updated_flag = true;
    mesh_integrator_->generateMesh(only_mesh_updated_blocks,
                                   clear_updated_flag);
  }
  generate_mesh_timer.Stop();

  timing::Timer publish_mesh_timer("mesh/publish");
  voxblox_msgs::msg::Mesh mesh_msg;
  generateVoxbloxMeshMsg(mesh_layer_, color_mode_, &mesh_msg);
  mesh_msg.header.frame_id = world_frame_;
  // mesh_pub_.publish(mesh_msg);
  mesh_pub_->publish(mesh_msg);

  publish_mesh_timer.Stop();

  if (!mesh_filename_.empty()) {
    timing::Timer output_mesh_timer("mesh/output");
    const bool success = outputMeshLayerAsPly(mesh_filename_, *mesh_layer_);
    output_mesh_timer.Stop();
    if (success) {
      // ROS_INFO("Output file as PLY: %s", mesh_filename_.c_str());
      RCLCPP_INFO(node_ptr_->get_logger(), "Output file as PLY: %s",
                  mesh_filename_.c_str());

    } else {
      // ROS_INFO("Failed to output mesh as PLY: %s", mesh_filename_.c_str());
      RCLCPP_INFO(node_ptr_->get_logger(), "Failed to output mesh as PLY: %s",
                  mesh_filename_.c_str());
    }
  }

  // ROS_INFO_STREAM("Mesh Timings: " << std::endl << timing::Timing::Print());
  RCLCPP_INFO_STREAM(node_ptr_->get_logger(),
                     "Mesh Timings: " << std::endl
                                      << timing::Timing::Print());
  return true;
}

bool TsdfServer::saveMap(const std::string & file_path)
{
  // Inheriting classes should add saving other layers to this function.
  return io::SaveLayer(tsdf_map_->getTsdfLayer(), file_path);
}

bool TsdfServer::loadMap(const std::string & file_path)
{
  // Inheriting classes should add other layers to load, as this will only
  // load
  // the TSDF layer.
  constexpr bool kMulitpleLayerSupport = true;
  bool success = io::LoadBlocksFromFile(
      file_path, Layer<TsdfVoxel>::BlockMergingStrategy::kReplace,
      kMulitpleLayerSupport, tsdf_map_->getTsdfLayerPtr());
  if (success) {
    LOG(INFO) << "Successfully loaded TSDF layer.";
  }
  return success;
}

void TsdfServer::clearMapCallback(
  const std_srvs::srv::Empty::Request::SharedPtr /*request*/,
  std_srvs::srv::Empty::Response::SharedPtr
    /*response*/)  // NOLINT
{
  clear();
  // return true;
}

void TsdfServer::generateMeshCallback(
  const std_srvs::srv::Empty::Request::SharedPtr /*request*/,
  std_srvs::srv::Empty::Response::SharedPtr
    /*response*/)  // NOLINT
{
  generateMesh();
}

void TsdfServer::saveMapCallback(
  const voxblox_msgs::srv::FilePath::Request::SharedPtr request,
  voxblox_msgs::srv::FilePath::Response::SharedPtr
    /*response*/)  // NOLINT
{
  saveMap(request->file_path);
}

void TsdfServer::loadMapCallback(
  const voxblox_msgs::srv::FilePath::Request::SharedPtr request,
  voxblox_msgs::srv::FilePath::Response::SharedPtr
    /*response*/)  // NOLINT
{
  bool success = loadMap(request->file_path);
}

void TsdfServer::publishPointcloudsCallback(
  const std_srvs::srv::Empty::Request::SharedPtr /*request*/,
  std_srvs::srv::Empty::Response::SharedPtr
    /*response*/)  // NOLINT
{
  publishPointclouds();
}

void TsdfServer::publishTsdfMapCallback(
  const std_srvs::srv::Empty::Request::SharedPtr /*request*/,
  std_srvs::srv::Empty::Response::SharedPtr
    /*response*/)  // NOLINT
{
  publishMap();
}

void TsdfServer::updateMeshEvent() {updateMesh();}

void TsdfServer::publishMapEvent() {publishMap();}

void TsdfServer::clear()
{
  tsdf_map_->getTsdfLayerPtr()->removeAllBlocks();
  mesh_layer_->clear();

  // Publish a message to reset the map to all subscribers.
  if (publish_tsdf_map_) {
    constexpr bool kResetRemoteMap = true;
    publishMap(kResetRemoteMap);
  }
}

void TsdfServer::tsdfMapCallback(const voxblox_msgs::msg::Layer & layer_msg)
{
  timing::Timer receive_map_timer("map/receive_tsdf");

  bool success =
    deserializeMsgToLayer<TsdfVoxel>(layer_msg, tsdf_map_->getTsdfLayerPtr());

  if (!success) {
    // ROS_ERROR_THROTTLE(10, "Got an invalid TSDF map message!");
    RCLCPP_ERROR_THROTTLE(node_ptr_->get_logger(), *node_ptr_->get_clock(),
                          10000, "Got an invalid TSDF map message!");

  } else {
    // ROS_INFO_ONCE("Got an TSDF map from ROS topic!");
    RCLCPP_INFO_ONCE(node_ptr_->get_logger(),
                     "Got an TSDF map from ROS topic!");
    if (publish_pointclouds_on_update_) {
      publishPointclouds();
    }
  }
}

}  // namespace voxblox
