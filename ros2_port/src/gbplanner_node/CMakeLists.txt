cmake_minimum_required(VERSION 3.8)
project(gbplanner_node)

set(CMAKE_CXX_STANDARD 17)
add_compile_options(-Wno-deprecated-declarations)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()

# gbplanner_core is a static archive whose voxblox closure needs group
# rescan; the $<LINK_GROUP> in its interface does not survive ament's
# cross-package export, so repeat it here for the executable.
find_library(VOXBLOX_LIB voxblox)
find_library(VOXBLOX_ROS_LIB voxblox_ros)
find_library(VOXBLOX_PROTO_LIB voxblox_proto)
find_package(Protobuf REQUIRED)

ament_auto_add_executable(gbplanner_node src/gbplanner_node.cpp)
target_link_libraries(gbplanner_node
  "$<LINK_GROUP:RESCAN,${VOXBLOX_ROS_LIB},${VOXBLOX_LIB},${VOXBLOX_PROTO_LIB}>"
  protobuf::libprotobuf glog gflags)

ament_auto_add_executable(pci_trigger_node src/pci_trigger_node.cpp)

ament_auto_package()
