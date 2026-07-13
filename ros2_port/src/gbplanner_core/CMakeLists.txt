cmake_minimum_required(VERSION 3.8)
project(gbplanner_core)

set(CMAKE_CXX_STANDARD 17)
add_compile_options(-Wno-deprecated-declarations)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_auto REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(PCL REQUIRED)
find_package(OpenCV REQUIRED)
find_package(Boost REQUIRED COMPONENTS graph)
ament_auto_find_build_dependencies()

include_directories(include ${EIGEN3_INCLUDE_DIRS} ${PCL_INCLUDE_DIRS} ${OpenCV_INCLUDE_DIRS})

ament_auto_add_library(${PROJECT_NAME} STATIC
  src/kdtree.c
  src/adaptive_obb.cpp
  src/geofence_manager.cpp
  src/graph.cpp
  src/graph_manager.cpp
  src/params.cpp
  src/random_sampler.cpp
  src/trajectory.cpp
  src/voxblox/voxblox_common_impl.cpp
  src/voxblox/voxblox_alt_impl.cpp
  src/rrg.cpp
)
# voxblox installs static archives; spell out the closure in link order so
# consumers (the gtest) resolve core symbols behind libvoxblox_ros.a.
find_library(VOXBLOX_LIB voxblox)
find_library(VOXBLOX_ROS_LIB voxblox_ros)
find_library(VOXBLOX_PROTO_LIB voxblox_proto)
find_package(Protobuf REQUIRED)
# Typesupport shared libs must appear AFTER the static voxblox archives on
# the link line, or --as-needed discards them before the archive members
# reference them.
target_link_libraries(${PROJECT_NAME}
  "$<LINK_GROUP:RESCAN,${VOXBLOX_ROS_LIB},${VOXBLOX_LIB},${VOXBLOX_PROTO_LIB}>"
  protobuf::libprotobuf
  ${sensor_msgs_TARGETS} ${visualization_msgs_TARGETS} ${std_srvs_TARGETS}
  ${voxblox_msgs_TARGETS} ${geometry_msgs_TARGETS} ${std_msgs_TARGETS}
  ${nav_msgs_TARGETS} ${planner_msgs_TARGETS} ${planner_semantic_msgs_TARGETS}
  rclcpp::rclcpp
  ${PCL_LIBRARIES} ${OpenCV_LIBS} Boost::graph glog gflags)
# CMake dedup reorders the typesupport .so's ahead of the static voxblox
# archives on consumer link lines; defeat --as-needed instead of fighting
# the ordering.
target_link_options(${PROJECT_NAME} PUBLIC "LINKER:--no-as-needed")

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_auto_add_gtest(test_core_callable test/test_core_callable.cpp)
endif()

ament_auto_package()
