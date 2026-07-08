#ifndef VOXBLOX_SKELETON_ROS_SKELETON_VIS_H_
#define VOXBLOX_SKELETON_ROS_SKELETON_VIS_H_

// #include <eigen_conversions/
#include <voxblox/core/color.h>
#include <voxblox/core/common.h>
#include <voxblox_ros/conversions.h>
#include <visualization_msgs/msg/marker_array.hpp>

#include "voxblox_skeleton/skeleton.h"

namespace voxblox {

inline void pointEigenToMsg(const Eigen::Vector3d& point_eigen,
                            geometry_msgs::msg::Point& point_msg) {
  point_msg.x = point_eigen.x();
  point_msg.y = point_eigen.y();
  point_msg.z = point_eigen.z();
}

struct connected_vertices_struct {
 public:
  int64_t id;
  bool visited;
  SkeletonVertex vertex;
  int64_t subgraph_id;
};

inline void connected_components(
    int64_t subgraph_id, const SparseSkeletonGraph& graph,
    connected_vertices_struct& connected_vertex,
    std::vector<connected_vertices_struct>& connected_vertices_struct_vec,
    std::vector<int64_t> closed_space_edge_ids) {
  std::vector<int64_t> edge_list = connected_vertex.vertex.edge_list;
  // std::cout << "connected_vertex.vertex.vertex_id " <<
  // connected_vertex.vertex.vertex_id << std::endl;
  for (int64_t edge_id : edge_list) {
    auto it_edge = std::find(closed_space_edge_ids.begin(),
                             closed_space_edge_ids.end(), edge_id);
    // edge exists
    if (it_edge != closed_space_edge_ids.end()) {
      const SkeletonEdge& connected_edge = graph.getEdge(edge_id);

      if (connected_edge.start_vertex != connected_vertex.vertex.vertex_id) {
        // this is the vertex neighbour
        auto start_vertex =
            std::find_if(connected_vertices_struct_vec.begin(),
                         connected_vertices_struct_vec.end(),
                         // boost::bind(&connected_vertices_struct::id, _1) ==
                         //     connected_edge.start_vertex);
                         [&](const connected_vertices_struct& cvs) {
                           return cvs.id == connected_edge.start_vertex;
                         });

        if (start_vertex != connected_vertices_struct_vec.end() &&
            (*start_vertex).visited == false) {
          (*start_vertex).visited = true;
          (*start_vertex).subgraph_id = subgraph_id;
          connected_components(subgraph_id, graph, (*start_vertex),
                               connected_vertices_struct_vec,
                               closed_space_edge_ids);
        } else
          continue;
      } else if (connected_edge.end_vertex !=
                 connected_vertex.vertex.vertex_id) {
        // this is the vertex neighbour
        auto end_vertex =
            std::find_if(connected_vertices_struct_vec.begin(),
                         connected_vertices_struct_vec.end(),
                         // boost::bind(&connected_vertices_struct::id, _1) ==
                         //     connected_edge.end_vertex);
                         [&](const connected_vertices_struct& cvs) {
                           return cvs.id == connected_edge.end_vertex;
                         });

        if (end_vertex != connected_vertices_struct_vec.end() &&
            (*end_vertex).visited == false) {
          (*end_vertex).visited = true;
          (*end_vertex).subgraph_id = subgraph_id;
          connected_components(subgraph_id, graph, (*end_vertex),
                               connected_vertices_struct_vec,
                               closed_space_edge_ids);
        } else
          continue;
      }
    }
  }
  return;
}

inline void visualizeSkeletonGraph(
    const SparseSkeletonGraph& graph, const std::string& frame_id,
    visualization_msgs::msg::MarkerArray* marker_array,
    const float vertex_distance_threshold = 0.8) {
  bool visualize_subgraphs = true;
  bool visualize_freespace = false;
  CHECK_NOTNULL(marker_array);
  // Get a list of all vertices and visualize them as spheres.
  std::vector<int64_t> vertex_ids;
  graph.getAllVertexIds(&vertex_ids);
  std::vector<int64_t> deleted_vertex_ids;
  std::vector<connected_vertices_struct> connected_vertices_struct_vec;

  visualization_msgs::msg::Marker closed_space_marker;
  visualization_msgs::msg::Marker vertex_marker;
  vertex_marker.points.reserve(vertex_ids.size());
  // Also create the free-space marker.
  visualization_msgs::msg::Marker vertex_free_space_marker;

  vertex_marker.header.frame_id = frame_id;
  vertex_marker.ns = "vertices";
  closed_space_marker.header.frame_id = frame_id;
  closed_space_marker.ns = "closed_spaces";

  if (!visualize_subgraphs) {
    vertex_marker.type = visualization_msgs::msg::Marker::SPHERE_LIST;
    closed_space_marker.type = visualization_msgs::msg::Marker::SPHERE_LIST;
  } else {
    vertex_marker.type = visualization_msgs::msg::Marker::CUBE_LIST;
    closed_space_marker.type = visualization_msgs::msg::Marker::CUBE_LIST;
  }

  vertex_marker.pose.orientation.w = 1.0;
  vertex_marker.scale.x = 0.05;
  vertex_marker.scale.y = vertex_marker.scale.x;
  vertex_marker.scale.z = vertex_marker.scale.x;
  vertex_marker.color.r = 1.0;
  vertex_marker.color.a = 1.0;

  closed_space_marker.pose.orientation.w = 1.0;
  closed_space_marker.scale.x = 0.05;
  closed_space_marker.scale.y = closed_space_marker.scale.x;
  closed_space_marker.scale.z = closed_space_marker.scale.x;
  closed_space_marker.color.r = 1.0;
  closed_space_marker.color.a = 1.0;

  vertex_free_space_marker.header.frame_id = frame_id;
  vertex_free_space_marker.type = visualization_msgs::msg::Marker::SPHERE;
  vertex_free_space_marker.ns = "vertex_space";
  vertex_free_space_marker.color.a = 0.2;
  vertex_free_space_marker.color.r = 1.0;
  vertex_free_space_marker.color.g = 1.0;

  for (int64_t vertex_id : vertex_ids) {
    geometry_msgs::msg::Point point_msg;
    const SkeletonVertex& vertex = graph.getVertex(vertex_id);
    pointEigenToMsg(vertex.point.cast<double>(), point_msg);
    vertex_marker.points.push_back(point_msg);

    connected_vertices_struct connected_vertex;
    if (vertex.distance > vertex_distance_threshold) {
      closed_space_marker.points.push_back(point_msg);
      connected_vertex.id = vertex_id;
      connected_vertex.visited = false;
      connected_vertex.vertex = vertex;
      connected_vertices_struct_vec.push_back(connected_vertex);
    }

    if (visualize_subgraphs) {
      std_msgs::msg::ColorRGBA color_msg;
      Color color = rainbowColorMap(vertex.subgraph_id % 100 / 10.0);
      colorVoxbloxToMsg(color, &color_msg);
      if (vertex.distance > vertex_distance_threshold) {
        vertex_marker.colors.push_back(color_msg);
        closed_space_marker.colors.push_back(color_msg);
      } else {
        color_msg.b = 0;
        color_msg.r = 0;
        color_msg.g = 0;
        vertex_marker.colors.push_back(color_msg);
        deleted_vertex_ids.push_back(vertex_id);
      }
    }

    if (visualize_freespace) {
      // std::cout << "vertex distance: " << vertex.distance << std::endl;
      if (vertex.distance > vertex_distance_threshold) {
        vertex_free_space_marker.pose.orientation.w = 1.0;
        vertex_free_space_marker.pose.position = point_msg;
        vertex_free_space_marker.scale.x = vertex.distance;
        vertex_free_space_marker.scale.y = vertex.distance;
        vertex_free_space_marker.scale.z = vertex.distance;
        marker_array->markers.push_back(vertex_free_space_marker);
        vertex_free_space_marker.id++;
      }
    }
  }
  marker_array->markers.push_back(closed_space_marker);
  marker_array->markers.push_back(vertex_marker);

  // Get all edges and visualize as lines.
  std::vector<int64_t> edge_ids;
  std::vector<int64_t> deleted_edge_ids;
  std::vector<int64_t> closed_space_edge_ids;
  graph.getAllEdgeIds(&edge_ids);

  visualization_msgs::msg::Marker edge_marker;
  edge_marker.points.reserve(edge_ids.size() * 2);

  edge_marker.header.frame_id = frame_id;
  edge_marker.ns = "edges";
  edge_marker.type = visualization_msgs::msg::Marker::LINE_LIST;
  edge_marker.pose.orientation.w = 1.0;
  edge_marker.scale.x = 0.005;

  edge_marker.scale.y = edge_marker.scale.x;
  edge_marker.scale.z = edge_marker.scale.x;
  edge_marker.color.b = 1.0;
  edge_marker.color.a = 0.3;

  for (int64_t edge_id : edge_ids) {
    geometry_msgs::msg::Point point_msg;
    const SkeletonEdge& edge = graph.getEdge(edge_id);
    int64_t start_vertex_id = edge.start_vertex;
    int64_t end_vertex_id = edge.end_vertex;

    auto it_start = std::find(deleted_vertex_ids.begin(),
                              deleted_vertex_ids.end(), start_vertex_id);
    auto it_end = std::find(deleted_vertex_ids.begin(),
                            deleted_vertex_ids.end(), end_vertex_id);

    pointEigenToMsg(edge.start_point.cast<double>(), point_msg);
    edge_marker.points.push_back(point_msg);
    pointEigenToMsg(edge.end_point.cast<double>(), point_msg);
    edge_marker.points.push_back(point_msg);
    // vertex is found
    if (it_start != deleted_vertex_ids.end() ||
        it_end != deleted_vertex_ids.end()) {
      // std_msgs::ColorRGBA color_msg;
      // color_msg.r = 0; color_msg.g = 0; color_msg.b = 0; color_msg.a =1;
      // edge_marker.colors.push_back(color_msg);
      deleted_edge_ids.push_back(edge_id);
      continue;
    }
    closed_space_edge_ids.push_back(edge_id);
  }
  marker_array->markers.push_back(edge_marker);

  int64_t subgraph_id = 0;
  for (connected_vertices_struct& connected_vertex :
       connected_vertices_struct_vec) {
    if (connected_vertex.visited == false) {
      connected_vertex.visited = true;
      connected_vertex.subgraph_id = subgraph_id;
      connected_components(subgraph_id, graph, connected_vertex,
                           connected_vertices_struct_vec,
                           closed_space_edge_ids);
      subgraph_id++;
    }
  }

  std::vector<std::vector<SkeletonVertex> > connected_vertex_vec;
  connected_vertex_vec.resize(subgraph_id + 1);
  for (int64_t current_subgraph_id = 0; current_subgraph_id < subgraph_id;
       ++current_subgraph_id) {
    for (connected_vertices_struct connected_vertex :
         connected_vertices_struct_vec) {
      if (connected_vertex.subgraph_id == current_subgraph_id) {
        SkeletonVertex current_vertex = connected_vertex.vertex;
        connected_vertex_vec[current_subgraph_id].push_back(current_vertex);
      }
    }
  }

  // merge the deleted components to the appropriate subgraphs
  for (int64_t deleted_vertex_id : deleted_vertex_ids) {
    // get the vertex object given its id
    const SkeletonVertex& deleted_vertex = graph.getVertex(deleted_vertex_id);
    std::vector<int64_t> deleted_vertex_edge_list = deleted_vertex.edge_list;

    for (int64_t deleted_vertex_edge_id : deleted_vertex_edge_list) {
      const SkeletonEdge& connected_edge =
          graph.getEdge(deleted_vertex_edge_id);
      connected_vertices_struct connected_vertex_struct;

      if (connected_edge.start_vertex != deleted_vertex.vertex_id) {
        // this is the neighbour vertex and now check to which subgraph it
        // belongs to
        // and then assign this poor vertex to the subgraph
        auto connected_vertex =
            std::find_if(connected_vertices_struct_vec.begin(),
                         connected_vertices_struct_vec.end(),
                         // boost::bind(&connected_vertices_struct::id, _1) ==
                         //     connected_edge.start_vertex);
                         [&](const connected_vertices_struct& v) {
                           return v.id == connected_edge.start_vertex;
                         });
        // if vertex exist then find its subgraph id and assign the deleted
        // vertex to the subgraph
        if (connected_vertex != connected_vertices_struct_vec.end()) {
          SkeletonVertex current_deleted_vertex = deleted_vertex;
          connected_vertex_vec[(*connected_vertex).subgraph_id].push_back(
              current_deleted_vertex);
          connected_vertex_struct.id = current_deleted_vertex.vertex_id;
          connected_vertex_struct.subgraph_id = (*connected_vertex).subgraph_id;
          connected_vertex_struct.visited = true;
          connected_vertex_struct.vertex = current_deleted_vertex;
          connected_vertices_struct_vec.push_back(connected_vertex_struct);
          break;
        } else
          continue;
      } else if (connected_edge.end_vertex != deleted_vertex.vertex_id) {
        auto connected_vertex =
            std::find_if(connected_vertices_struct_vec.begin(),
                         connected_vertices_struct_vec.end(),
                         // boost::bind(&connected_vertices_struct::id, _1) ==
                         //     connected_edge.end_vertex);
                         [&](const connected_vertices_struct& v) {
                           return v.id == connected_edge.end_vertex;
                         });
        if (connected_vertex != connected_vertices_struct_vec.end()) {
          SkeletonVertex current_deleted_vertex = deleted_vertex;
          connected_vertex_vec[(*connected_vertex).subgraph_id].push_back(
              current_deleted_vertex);
          connected_vertex_struct.id = current_deleted_vertex.vertex_id;
          connected_vertex_struct.subgraph_id = (*connected_vertex).subgraph_id;
          connected_vertex_struct.visited = true;
          connected_vertex_struct.vertex = current_deleted_vertex;
          connected_vertices_struct_vec.push_back(connected_vertex_struct);
          break;
        } else
          continue;
      }
    }
  }

  for (int i = 0; i < connected_vertex_vec.size(); ++i) {
    visualization_msgs::msg::Marker connected_vertex_marker;
    connected_vertex_marker.header.frame_id = frame_id;
    connected_vertex_marker.ns = "connected_vertices_" + std::to_string(i);
    connected_vertex_marker.pose.orientation.w = 1.0;
    connected_vertex_marker.scale.x = 0.05;
    connected_vertex_marker.scale.y = connected_vertex_marker.scale.x;
    connected_vertex_marker.scale.z = connected_vertex_marker.scale.x;
    connected_vertex_marker.color.r = 1.0;
    connected_vertex_marker.color.a = 1.0;
    connected_vertex_marker.type = visualization_msgs::msg::Marker::CUBE_LIST;

    visualization_msgs::msg::Marker connected_edge_marker;
    connected_edge_marker.header.frame_id = frame_id;
    connected_edge_marker.ns = "connected_edges_" + std::to_string(i);
    connected_edge_marker.pose.orientation.w = 1.0;
    connected_edge_marker.scale.x = 0.005;
    connected_edge_marker.scale.y = connected_vertex_marker.scale.x;
    connected_edge_marker.scale.z = connected_vertex_marker.scale.x;
    connected_edge_marker.color.b = 1.0;
    connected_edge_marker.color.a = 1.0;
    connected_edge_marker.type = visualization_msgs::msg::Marker::LINE_LIST;

    for (int j = 0; j < connected_vertex_vec[i].size(); ++j) {
      geometry_msgs::msg::Point point_msg;
      pointEigenToMsg(connected_vertex_vec[i][j].point.cast<double>(),
                      point_msg);
      connected_vertex_marker.points.push_back(point_msg);
      std_msgs::msg::ColorRGBA color_msg;
      Color color = rainbowColorMap(i % 100 / 10.0);
      colorVoxbloxToMsg(color, &color_msg);
      connected_vertex_marker.colors.push_back(color_msg);

      for (int64_t edge_id : connected_vertex_vec[i][j].edge_list) {
        geometry_msgs::msg::Point point_msg;
        const SkeletonEdge& edge = graph.getEdge(edge_id);
        int64_t start_vertex_id = edge.start_vertex;
        int64_t end_vertex_id = edge.end_vertex;
        pointEigenToMsg(edge.start_point.cast<double>(), point_msg);
        connected_edge_marker.points.push_back(point_msg);
        pointEigenToMsg(edge.end_point.cast<double>(), point_msg);
        connected_edge_marker.points.push_back(point_msg);
      }
    }
    marker_array->markers.push_back(connected_vertex_marker);
    marker_array->markers.push_back(connected_edge_marker);
  }

  // // find connections between subgraphs to find doors/openings to connect
  // // adjacent rooms
  // for (int i = 0; i < connected_vertex_vec.size(); ++i) {
  //   for (int j = 0; j < connected_vertex_vec[i].size(); ++j) {
  //     visualization_msgs::Marker subgraph_edge_marker;
  //     subgraph_edge_marker.header.frame_id = frame_id;
  //     subgraph_edge_marker.pose.orientation.w = 1.0;
  //     subgraph_edge_marker.scale.x = 0.02;
  //     subgraph_edge_marker.scale.y = subgraph_edge_marker.scale.x;
  //     subgraph_edge_marker.scale.z = subgraph_edge_marker.scale.x;
  //     subgraph_edge_marker.color.r = 1.0;
  //     subgraph_edge_marker.color.g = 0.0;
  //     subgraph_edge_marker.color.b = 0.0;
  //     subgraph_edge_marker.color.a = 1.0;
  //     subgraph_edge_marker.type = visualization_msgs::Marker::LINE_STRIP;
  //     int neigbouring_subgraph_id = -1;
  //     // get the vertex and its edges
  //     for (int64_t edge_id : connected_vertex_vec[i][j].edge_list) {
  //       const SkeletonEdge& connected_edge = graph.getEdge(edge_id);
  //       if (connected_edge.start_vertex !=
  //           connected_vertex_vec[i][j].vertex_id) {
  //         auto connected_vertex =
  //             std::find_if(connected_vertices_struct_vec.begin(),
  //                          connected_vertices_struct_vec.end(),
  //                          boost::bind(&connected_vertices_struct::id, _1) ==
  //                              connected_edge.start_vertex);
  //         // if the vertex subgraph id is not equal to the current subgraph
  //         id,
  //         // then its a connecting edge between subgraphs
  //         if (connected_vertex != connected_vertices_struct_vec.end() &&
  //             (*connected_vertex).subgraph_id != i) {
  //           // add the edge between subgraphs here
  //           neigbouring_subgraph_id = (*connected_vertex).subgraph_id;
  //           geometry_msgs::Point point_msg;
  //           tf::pointEigenToMsg(connected_edge.start_point.cast<double>(),
  //                               point_msg);
  //           subgraph_edge_marker.points.push_back(point_msg);
  //           tf::pointEigenToMsg(connected_edge.end_point.cast<double>(),
  //                               point_msg);
  //           subgraph_edge_marker.points.push_back(point_msg);
  //         }
  //       } else if (connected_edge.end_vertex !=
  //                  connected_vertex_vec[i][j].vertex_id) {
  //         auto connected_vertex =
  //             std::find_if(connected_vertices_struct_vec.begin(),
  //                          connected_vertices_struct_vec.end(),
  //                          boost::bind(&connected_vertices_struct::id, _1) ==
  //                              connected_edge.end_vertex);
  //         if (connected_vertex != connected_vertices_struct_vec.end() &&
  //             (*connected_vertex).subgraph_id != i) {
  //           // add the edge between subgraphs here
  //           neigbouring_subgraph_id = (*connected_vertex).subgraph_id;
  //           geometry_msgs::Point point_msg;
  //           tf::pointEigenToMsg(connected_edge.start_point.cast<double>(),
  //                               point_msg);
  //           subgraph_edge_marker.points.push_back(point_msg);
  //           tf::pointEigenToMsg(connected_edge.end_point.cast<double>(),
  //                               point_msg);
  //           subgraph_edge_marker.points.push_back(point_msg);
  //         }
  //       }
  //       if (neigbouring_subgraph_id != -1) {
  //         subgraph_edge_marker.ns = "subgraph_edges_" + std::to_string(i) +
  //                                   "_" +
  //                                   std::to_string(neigbouring_subgraph_id);
  //         int id1 = i;
  //         int id2 = neigbouring_subgraph_id;
  //         int combined_ids = id1 << 8 | id2;
  //         subgraph_edge_marker.id = combined_ids;
  //         marker_array->markers.push_back(subgraph_edge_marker);
  //       }
  //     }
  //   }
  // }
}

}  // namespace voxblox

#endif  // VOXBLOX_SKELETON_ROS_SKELETON_VIS_H_
