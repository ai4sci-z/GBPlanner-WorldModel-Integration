cmake_minimum_required(VERSION 3.5)
project(voxblox_skeleton)

# find_package(catkin_simple REQUIRED)
find_package(ament_cmake_auto REQUIRED)
# catkin_simple(ALL_DEPS_REQUIRED)
ament_auto_find_build_dependencies()

add_definitions(-std=c++17)
find_package(glog REQUIRED)
find_package(backward_ros REQUIRED)

############
# PROTOBUF #
############
# General idea: first check if we have protobuf catkin, then use that.
# Otherwise use system protobuf.
set(PROTO_DEFNS proto/voxblox_skeleton/skeleton.proto)
set(ADDITIONAL_LIBRARIES "")

  message(STATUS "Using system protobuf")
  find_package(Protobuf REQUIRED)
  include_directories(${PROTOBUF_INCLUDE_DIRS})
  include_directories(${CMAKE_CURRENT_BINARY_DIR})

  PROTOBUF_GENERATE_CPP(PROTO_SRCS PROTO_HDRS ${PROTO_DEFNS})
  set(ADDITIONAL_LIBRARIES ${PROTOBUF_LIBRARY})
# endif()

#############
# LIBRARIES #
#############
ament_auto_add_library(${PROJECT_NAME}_proto
  ${PROTO_SRCS}
)
target_link_libraries(${PROJECT_NAME}_proto ${PROTOBUF_LIBRARIES} glog::glog)

ament_auto_add_library(${PROJECT_NAME}
  src/io/skeleton_io.cpp
  src/skeleton.cpp
  src/skeleton_generator.cpp
  src/skeleton_planner.cpp
  src/skeleton_serialization.cpp
  src/sparse_graph_planner.cpp
  src/voxel_template_matcher.cpp
)
target_link_libraries(${PROJECT_NAME} ${PROJECT_NAME}_proto glog::glog)

############
# BINARIES #
############
ament_auto_add_executable(skeletonizer_realtime
  src/skeletonizer_realtime.cpp
)
target_link_libraries(skeletonizer_realtime ${PROJECT_NAME} glog::glog)

ament_auto_add_executable(skeletonizer
  src/skeletonizer.cpp
)
target_link_libraries(skeletonizer ${PROJECT_NAME} glog::glog)

ament_auto_add_executable(skeleton_eval
  src/skeleton_eval.cpp
)
target_link_libraries(skeleton_eval ${PROJECT_NAME} glog::glog)

##########
# EXPORT #
##########

# export launch folder into install directory
ament_auto_package(INSTALL_TO_SHARE
  launch
)
