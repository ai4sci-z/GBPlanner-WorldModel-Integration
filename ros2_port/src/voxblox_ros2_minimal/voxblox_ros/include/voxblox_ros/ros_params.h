#ifndef VOXBLOX_ROS_ROS_PARAMS_H_
#define VOXBLOX_ROS_ROS_PARAMS_H_

#include <rclcpp/rclcpp.hpp>

#include <voxblox/alignment/icp.h>
#include <voxblox/core/esdf_map.h>
#include <voxblox/core/tsdf_map.h>
#include <voxblox/integrator/esdf_integrator.h>
#include <voxblox/integrator/tsdf_integrator.h>
#include <voxblox/mesh/mesh_integrator.h>

namespace voxblox {

inline TsdfMap::Config getTsdfMapConfigFromRosParam(rclcpp::Node* node_ptr) {
  TsdfMap::Config tsdf_config;

  /**
   * Workaround for OS X on mac mini not having specializations for float
   * for some reason.
   */
  double voxel_size = tsdf_config.tsdf_voxel_size;
  int voxels_per_side = tsdf_config.tsdf_voxels_per_side;

  if (!node_ptr->has_parameter("tsdf_voxel_size")) {
    node_ptr->declare_parameter("tsdf_voxel_size", voxel_size);
  }

  if (!node_ptr->has_parameter("tsdf_voxels_per_side")) {
    node_ptr->declare_parameter("tsdf_voxels_per_side", voxels_per_side);
  }

  node_ptr->get_parameter("tsdf_voxel_size", voxel_size);
  node_ptr->get_parameter("tsdf_voxels_per_side", voxels_per_side);

  if (!isPowerOfTwo(voxels_per_side)) {
    RCLCPP_ERROR(
        node_ptr->get_logger(),
        "voxels_per_side must be a power of 2, setting to default value");
    voxels_per_side = tsdf_config.tsdf_voxels_per_side;
  }

  tsdf_config.tsdf_voxel_size = static_cast<FloatingPoint>(voxel_size);
  tsdf_config.tsdf_voxels_per_side = voxels_per_side;

  return tsdf_config;
}

inline ICP::Config getICPConfigFromRosParam(rclcpp::Node* node_ptr) {
  ICP::Config icp_config;

  // nh_private.param("icp_min_match_ratio", icp_config.min_match_ratio,
  //                  icp_config.min_match_ratio);
  // nh_private.param("icp_subsample_keep_ratio",
  // icp_config.subsample_keep_ratio,
  //                  icp_config.subsample_keep_ratio);
  // nh_private.param("icp_mini_batch_size", icp_config.mini_batch_size,
  //                  icp_config.mini_batch_size);
  // nh_private.param("icp_refine_roll_pitch", icp_config.refine_roll_pitch,
  //                  icp_config.refine_roll_pitch);
  // nh_private.param("icp_inital_translation_weighting",
  //                  icp_config.inital_translation_weighting,
  //                  icp_config.inital_translation_weighting);
  // nh_private.param("icp_inital_rotation_weighting",
  //                  icp_config.inital_rotation_weighting,
  //                  icp_config.inital_rotation_weighting);
  if (!node_ptr->has_parameter("icp_min_match_ratio")) {
    node_ptr->declare_parameter("icp_min_match_ratio",
                                icp_config.min_match_ratio);
  }
  if (!node_ptr->has_parameter("icp_subsample_keep_ratio")) {
    node_ptr->declare_parameter("icp_subsample_keep_ratio",
                                icp_config.subsample_keep_ratio);
  }
  if (!node_ptr->has_parameter("icp_mini_batch_size")) {
    node_ptr->declare_parameter("icp_mini_batch_size",
                                icp_config.mini_batch_size);
  }
  if (!node_ptr->has_parameter("icp_refine_roll_pitch")) {
    node_ptr->declare_parameter("icp_refine_roll_pitch",
                                icp_config.refine_roll_pitch);
  }
  if (!node_ptr->has_parameter("icp_inital_translation_weighting")) {
    node_ptr->declare_parameter("icp_inital_translation_weighting",
                                icp_config.inital_translation_weighting);
  }
  if (!node_ptr->has_parameter("icp_inital_rotation_weighting")) {
    node_ptr->declare_parameter("icp_inital_rotation_weighting",
                                icp_config.inital_rotation_weighting);
  }

  node_ptr->get_parameter("icp_min_match_ratio", icp_config.min_match_ratio);
  node_ptr->get_parameter("icp_subsample_keep_ratio",
                          icp_config.subsample_keep_ratio);
  node_ptr->get_parameter("icp_mini_batch_size", icp_config.mini_batch_size);
  node_ptr->get_parameter("icp_refine_roll_pitch",
                          icp_config.refine_roll_pitch);
  node_ptr->get_parameter("icp_inital_translation_weighting",
                          icp_config.inital_translation_weighting);
  node_ptr->get_parameter("icp_inital_rotation_weighting",
                          icp_config.inital_rotation_weighting);

  return icp_config;
}

inline TsdfIntegratorBase::Config getTsdfIntegratorConfigFromRosParam(
    rclcpp::Node* node_ptr) {
  TsdfIntegratorBase::Config integrator_config;

  integrator_config.voxel_carving_enabled = true;

  const TsdfMap::Config tsdf_config = getTsdfMapConfigFromRosParam(node_ptr);
  integrator_config.default_truncation_distance =
      tsdf_config.tsdf_voxel_size * 4;

  double truncation_distance = integrator_config.default_truncation_distance;
  double max_weight = integrator_config.max_weight;
  // nh_private.param("voxel_carving_enabled",
  //                  integrator_config.voxel_carving_enabled,
  //                  integrator_config.voxel_carving_enabled);
  // nh_private.param("truncation_distance", truncation_distance,
  //                  truncation_distance);
  // nh_private.param("max_ray_length_m", integrator_config.max_ray_length_m,
  //                  integrator_config.max_ray_length_m);
  // nh_private.param("min_ray_length_m", integrator_config.min_ray_length_m,
  //                  integrator_config.min_ray_length_m);
  // nh_private.param("max_weight", max_weight, max_weight);
  // nh_private.param("use_const_weight", integrator_config.use_const_weight,
  //                  integrator_config.use_const_weight);
  // nh_private.param("use_weight_dropoff",
  // integrator_config.use_weight_dropoff,
  //                  integrator_config.use_weight_dropoff);
  // nh_private.param("allow_clear", integrator_config.allow_clear,
  //                  integrator_config.allow_clear);
  // nh_private.param("start_voxel_subsampling_factor",
  //                  integrator_config.start_voxel_subsampling_factor,
  //                  integrator_config.start_voxel_subsampling_factor);
  // nh_private.param("max_consecutive_ray_collisions",
  //                  integrator_config.max_consecutive_ray_collisions,
  //                  integrator_config.max_consecutive_ray_collisions);
  // nh_private.param("clear_checks_every_n_frames",
  //                  integrator_config.clear_checks_every_n_frames,
  //                  integrator_config.clear_checks_every_n_frames);
  // nh_private.param("max_integration_time_s",
  //                  integrator_config.max_integration_time_s,
  //                  integrator_config.max_integration_time_s);
  // nh_private.param("anti_grazing", integrator_config.enable_anti_grazing,
  //                  integrator_config.enable_anti_grazing);
  // nh_private.param("use_sparsity_compensation_factor",
  //                  integrator_config.use_sparsity_compensation_factor,
  //                  integrator_config.use_sparsity_compensation_factor);
  // nh_private.param("sparsity_compensation_factor",
  //                  integrator_config.sparsity_compensation_factor,
  //                  integrator_config.sparsity_compensation_factor);
  // nh_private.param("integration_order_mode",
  //                  integrator_config.integration_order_mode,
  //                  integrator_config.integration_order_mode);

  if (!node_ptr->has_parameter("voxel_carving_enabled")) {
    node_ptr->declare_parameter("voxel_carving_enabled",
                                integrator_config.voxel_carving_enabled);
  }
  if (!node_ptr->has_parameter("truncation_distance")) {
    node_ptr->declare_parameter("truncation_distance", truncation_distance);
  }
  if (!node_ptr->has_parameter("max_ray_length_m")) {
    node_ptr->declare_parameter("max_ray_length_m",
                                integrator_config.max_ray_length_m);
  }
  if (!node_ptr->has_parameter("min_ray_length_m")) {
    node_ptr->declare_parameter("min_ray_length_m",
                                integrator_config.min_ray_length_m);
  }
  if (!node_ptr->has_parameter("max_weight")) {
    node_ptr->declare_parameter("max_weight", max_weight);
  }
  if (!node_ptr->has_parameter("use_const_weight")) {
    node_ptr->declare_parameter("use_const_weight",
                                integrator_config.use_const_weight);
  }
  if (!node_ptr->has_parameter("use_weight_dropoff")) {
    node_ptr->declare_parameter("use_weight_dropoff",
                                integrator_config.use_weight_dropoff);
  }
  if (!node_ptr->has_parameter("allow_clear")) {
    node_ptr->declare_parameter("allow_clear", integrator_config.allow_clear);
  }
  if (!node_ptr->has_parameter("start_voxel_subsampling_factor")) {
    node_ptr->declare_parameter(
        "start_voxel_subsampling_factor",
        integrator_config.start_voxel_subsampling_factor);
  }
  if (!node_ptr->has_parameter("max_consecutive_ray_collisions")) {
    node_ptr->declare_parameter(
        "max_consecutive_ray_collisions",
        integrator_config.max_consecutive_ray_collisions);
  }
  if (!node_ptr->has_parameter("clear_checks_every_n_frames")) {
    node_ptr->declare_parameter("clear_checks_every_n_frames",
                                integrator_config.clear_checks_every_n_frames);
  }
  if (!node_ptr->has_parameter("max_integration_time_s")) {
    node_ptr->declare_parameter("max_integration_time_s",
                                integrator_config.max_integration_time_s);
  }
  if (!node_ptr->has_parameter("anti_grazing")) {
    node_ptr->declare_parameter("anti_grazing",
                                integrator_config.enable_anti_grazing);
  }
  if (!node_ptr->has_parameter("use_sparsity_compensation_factor")) {
    node_ptr->declare_parameter(
        "use_sparsity_compensation_factor",
        integrator_config.use_sparsity_compensation_factor);
  }
  if (!node_ptr->has_parameter("sparsity_compensation_factor")) {
    node_ptr->declare_parameter("sparsity_compensation_factor",
                                integrator_config.sparsity_compensation_factor);
  }
  if (!node_ptr->has_parameter("integration_order_mode")) {
    node_ptr->declare_parameter("integration_order_mode",
                                integrator_config.integration_order_mode);
  }

  node_ptr->get_parameter("voxel_carving_enabled",
                          integrator_config.voxel_carving_enabled);
  node_ptr->get_parameter("truncation_distance", truncation_distance);
  node_ptr->get_parameter("max_ray_length_m",
                          integrator_config.max_ray_length_m);
  node_ptr->get_parameter("min_ray_length_m",
                          integrator_config.min_ray_length_m);
  node_ptr->get_parameter("max_weight", max_weight);
  node_ptr->get_parameter("use_const_weight",
                          integrator_config.use_const_weight);
  node_ptr->get_parameter("use_weight_dropoff",
                          integrator_config.use_weight_dropoff);
  node_ptr->get_parameter("allow_clear", integrator_config.allow_clear);
  node_ptr->get_parameter("start_voxel_subsampling_factor",
                          integrator_config.start_voxel_subsampling_factor);
  node_ptr->get_parameter("max_consecutive_ray_collisions",
                          integrator_config.max_consecutive_ray_collisions);
  node_ptr->get_parameter("clear_checks_every_n_frames",
                          integrator_config.clear_checks_every_n_frames);
  node_ptr->get_parameter("max_integration_time_s",
                          integrator_config.max_integration_time_s);
  node_ptr->get_parameter("anti_grazing",
                          integrator_config.enable_anti_grazing);
  node_ptr->get_parameter("use_sparsity_compensation_factor",
                          integrator_config.use_sparsity_compensation_factor);
  node_ptr->get_parameter("sparsity_compensation_factor",
                          integrator_config.sparsity_compensation_factor);
  node_ptr->get_parameter("integration_order_mode",
                          integrator_config.integration_order_mode);

  integrator_config.default_truncation_distance =
      static_cast<float>(truncation_distance);
  integrator_config.max_weight = static_cast<float>(max_weight);

  return integrator_config;
}

inline EsdfMap::Config getEsdfMapConfigFromRosParam(rclcpp::Node* node_ptr) {
  EsdfMap::Config esdf_config;

  const TsdfMap::Config tsdf_config = getTsdfMapConfigFromRosParam(node_ptr);
  esdf_config.esdf_voxel_size = tsdf_config.tsdf_voxel_size;
  esdf_config.esdf_voxels_per_side = tsdf_config.tsdf_voxels_per_side;

  return esdf_config;
}

inline EsdfIntegrator::Config getEsdfIntegratorConfigFromRosParam(
    rclcpp::Node* node_ptr) {
  EsdfIntegrator::Config esdf_integrator_config;

  TsdfIntegratorBase::Config tsdf_integrator_config =
      getTsdfIntegratorConfigFromRosParam(node_ptr);

  esdf_integrator_config.min_distance_m =
      tsdf_integrator_config.default_truncation_distance / 2.0;

  // nh_private.param("esdf_euclidean_distance",
  //                  esdf_integrator_config.full_euclidean_distance,
  //                  esdf_integrator_config.full_euclidean_distance);
  // nh_private.param("esdf_max_distance_m",
  // esdf_integrator_config.max_distance_m,
  //                  esdf_integrator_config.max_distance_m);
  // nh_private.param("esdf_min_distance_m",
  // esdf_integrator_config.min_distance_m,
  //                  esdf_integrator_config.min_distance_m);
  // nh_private.param("esdf_default_distance_m",
  //                  esdf_integrator_config.default_distance_m,
  //                  esdf_integrator_config.default_distance_m);
  // nh_private.param("esdf_min_diff_m", esdf_integrator_config.min_diff_m,
  //                  esdf_integrator_config.min_diff_m);
  // nh_private.param("clear_sphere_radius",
  //                  esdf_integrator_config.clear_sphere_radius,
  //                  esdf_integrator_config.clear_sphere_radius);
  // nh_private.param("occupied_sphere_radius",
  //                  esdf_integrator_config.occupied_sphere_radius,
  //                  esdf_integrator_config.occupied_sphere_radius);
  // nh_private.param("esdf_add_occupied_crust",
  //                  esdf_integrator_config.add_occupied_crust,
  //                  esdf_integrator_config.add_occupied_crust);

  if (!node_ptr->has_parameter("esdf_euclidean_distance")) {
    node_ptr->declare_parameter("esdf_euclidean_distance",
                                esdf_integrator_config.full_euclidean_distance);
  }
  if (!node_ptr->has_parameter("esdf_max_distance_m")) {
    node_ptr->declare_parameter("esdf_max_distance_m",
                                esdf_integrator_config.max_distance_m);
  }
  if (!node_ptr->has_parameter("esdf_min_distance_m")) {
    node_ptr->declare_parameter("esdf_min_distance_m",
                                esdf_integrator_config.min_distance_m);
  }
  if (!node_ptr->has_parameter("esdf_default_distance_m")) {
    node_ptr->declare_parameter("esdf_default_distance_m",
                                esdf_integrator_config.default_distance_m);
  }
  if (!node_ptr->has_parameter("esdf_min_diff_m")) {
    node_ptr->declare_parameter("esdf_min_diff_m",
                                esdf_integrator_config.min_diff_m);
  }
  if (!node_ptr->has_parameter("clear_sphere_radius")) {
    node_ptr->declare_parameter("clear_sphere_radius",
                                esdf_integrator_config.clear_sphere_radius);
  }
  if (!node_ptr->has_parameter("occupied_sphere_radius")) {
    node_ptr->declare_parameter("occupied_sphere_radius",
                                esdf_integrator_config.occupied_sphere_radius);
  }
  if (!node_ptr->has_parameter("esdf_add_occupied_crust")) {
    node_ptr->declare_parameter("esdf_add_occupied_crust",
                                esdf_integrator_config.add_occupied_crust);
  }

  node_ptr->get_parameter("esdf_euclidean_distance",
                          esdf_integrator_config.full_euclidean_distance);
  node_ptr->get_parameter("esdf_max_distance_m",
                          esdf_integrator_config.max_distance_m);
  node_ptr->get_parameter("esdf_min_distance_m",
                          esdf_integrator_config.min_distance_m);
  node_ptr->get_parameter("esdf_default_distance_m",
                          esdf_integrator_config.default_distance_m);
  node_ptr->get_parameter("esdf_min_diff_m", esdf_integrator_config.min_diff_m);
  node_ptr->get_parameter("clear_sphere_radius",
                          esdf_integrator_config.clear_sphere_radius);
  node_ptr->get_parameter("occupied_sphere_radius",
                          esdf_integrator_config.occupied_sphere_radius);
  node_ptr->get_parameter("esdf_add_occupied_crust",
                          esdf_integrator_config.add_occupied_crust);

  if (esdf_integrator_config.default_distance_m <
      esdf_integrator_config.max_distance_m) {
    esdf_integrator_config.default_distance_m =
        esdf_integrator_config.max_distance_m;
  }

  return esdf_integrator_config;
}

inline MeshIntegratorConfig getMeshIntegratorConfigFromRosParam(
    rclcpp::Node* node_ptr) {
  MeshIntegratorConfig mesh_integrator_config;

  // nh_private.param("mesh_min_weight", mesh_integrator_config.min_weight,
  //                  mesh_integrator_config.min_weight);
  // nh_private.param("mesh_use_color", mesh_integrator_config.use_color,
  //                  mesh_integrator_config.use_color);
  // node_ptr->declare_parameter("mesh_min_weight",
  //                             mesh_integrator_config.min_weight);
  // node_ptr->declare_parameter("mesh_use_color",
  //                             mesh_integrator_config.use_color);
  if (!node_ptr->has_parameter("mesh_min_weight")) {
    node_ptr->declare_parameter("mesh_min_weight",
                                mesh_integrator_config.min_weight);
  }
  if (!node_ptr->has_parameter("mesh_use_color")) {
    node_ptr->declare_parameter("mesh_use_color",
                                mesh_integrator_config.use_color);
  }
  node_ptr->get_parameter("mesh_min_weight", mesh_integrator_config.min_weight);
  node_ptr->get_parameter("mesh_use_color", mesh_integrator_config.use_color);

  return mesh_integrator_config;
}

}  // namespace voxblox

#endif  // VOXBLOX_ROS_ROS_PARAMS_H_
