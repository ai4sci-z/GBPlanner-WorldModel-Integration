cmake_minimum_required(VERSION 3.5)
project(voxblox_ros)

find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies(REQUIRED)

add_definitions(-std=c++17 -Wall -Wextra)
set(CMAKE_BUILD_TYPE RelWithDebInfo)

find_package(backward_ros REQUIRED)
find_package(PCL REQUIRED)
include_directories(
  include
  ${EIGEN3_INCLUDE_DIRS}
  ${PCL_INCLUDE_DIRS}
)


#############
# LIBRARIES #
#############

ament_auto_add_library(${PROJECT_NAME}
  src/esdf_server.cc
  src/interactive_slider.cc
  src/simulation_server.cc
  src/intensity_server.cc
  src/transformer.cc
  src/tsdf_server.cc
)

find_package(glog REQUIRED)
find_package(Protobuf REQUIRED)
find_package(voxblox REQUIRED)
find_package(xmlrpcpp REQUIRED)

ament_target_dependencies(${PROJECT_NAME}
  voxblox_msgs
)

target_link_libraries(${PROJECT_NAME}
  ${PCL_LIBRARIES}
  ${voxblox_LIBRARIES}
  ${xmlrpcpp_LIBRARIES}
  glog::glog
  protobuf::libprotobuf
)

set(ADITIONAL_LIBS 
  ${PCL_LIBRARIES}
  glog::glog
  protobuf::libprotobuf
)

# find_package(xmlrpc++ REQUIRED)
############
# BINARIES #
############

ament_auto_add_executable(voxblox_eval
  src/voxblox_eval.cc
)
target_link_libraries(voxblox_eval ${PROJECT_NAME} ${ADITIONAL_LIBS})

ament_auto_add_executable(tsdf_server
  src/tsdf_server_node.cc
)
target_link_libraries(tsdf_server ${PROJECT_NAME} ${ADITIONAL_LIBS})

ament_auto_add_executable(esdf_server
  src/esdf_server_node.cc
)
target_link_libraries(esdf_server ${PROJECT_NAME} ${ADITIONAL_LIBS})

ament_auto_add_executable(intensity_server
  src/intensity_server_node.cc
)
target_link_libraries(intensity_server ${PROJECT_NAME} ${ADITIONAL_LIBS})

ament_auto_add_executable(simulation_eval
  src/simulation_eval.cc
)
target_link_libraries(simulation_eval ${PROJECT_NAME} ${ADITIONAL_LIBS})

ament_auto_add_executable(visualize_tsdf
  src/visualize_tsdf.cc
)
target_link_libraries(visualize_tsdf ${PROJECT_NAME} ${ADITIONAL_LIBS})

##########
# EXPORT #
##########
ament_auto_package()
