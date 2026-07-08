cmake_minimum_required(VERSION 3.14)
project(voxblox LANGUAGES CXX)

# Prefer modern standard flags over add_definitions
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()

find_package(Protobuf REQUIRED) # provides protobuf_generate_cpp + protobuf::libprotobuf

find_package(Eigen3 REQUIRED)
include_directories(
 include
  ${EIGEN3_INCLUDE_DIRS}
)

############
# PROTOBUF #
############

# Absolute paths to your .proto files
set(PROTO_DEFNS
  proto/voxblox/Block.proto
  proto/voxblox/Layer.proto
)

# Create the target first with no sources
ament_auto_add_library(${PROJECT_NAME}_proto ${PROTO_DEFNS})
protobuf_generate(
  TARGET ${PROJECT_NAME}_proto
  LANGUAGE cpp
)

include_directories(${CMAKE_CURRENT_BINARY_DIR}/proto)
include_directories(${CMAKE_CURRENT_BINARY_DIR})

# ament_auto_add_library(${PROJECT_NAME}_proto ${PROTO_SRCS}

####################
# MAIN LIB SOURCES #
####################

set(${PROJECT_NAME}_SRCS
  src/alignment/icp.cc
  src/core/block.cc
  src/core/esdf_map.cc
  src/core/tsdf_map.cc
  src/integrator/esdf_integrator.cc
  src/integrator/esdf_occ_integrator.cc
  src/integrator/integrator_utils.cc
  src/integrator/intensity_integrator.cc
  src/integrator/tsdf_integrator.cc
  src/io/mesh_ply.cc
  src/io/sdf_ply.cc
  src/mesh/marching_cubes.cc
  src/simulation/objects.cc
  src/simulation/simulation_world.cc
  src/utils/camera_model.cc
  src/utils/evaluation_utils.cc
  src/utils/layer_utils.cc
  src/utils/neighbor_tools.cc
  src/utils/protobuf_utils.cc
  src/utils/timing.cc
  src/utils/voxel_utils.cc
)

ament_auto_add_library(${PROJECT_NAME} ${${PROJECT_NAME}_SRCS})
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

find_package(glog REQUIRED)

target_link_libraries(${PROJECT_NAME}
  ${PROJECT_NAME}_proto
  glog::glog
  protobuf::libprotobuf
)

# ament_auto_add_executable(tsdf_to_esdf test/tsdf_to_esdf.cc)
# target_link_libraries(tsdf_to_esdf ${PROJECT_NAME} glog::glog ${PROTOBUF_LIBRARIES})
# ament_auto_add_executable(test_load_esdf test/test_load_esdf.cc)
# target_link_libraries(test_load_esdf ${PROJECT_NAME} glog::glog ${PROTOBUF_LIBRARIES})

# ##########
# # EXPORT #
# ##########


# Install generated protobuf headers too (so downstream projects can include *.pb.h)
install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/proto/
  DESTINATION include/
  FILES_MATCHING PATTERN "*.pb.h"
)

if(BUILD_TESTING)
  file(GLOB TEST_SRCS CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/test/*.cc)
  find_package(ament_cmake_gtest REQUIRED)
find_package(eigen_checks REQUIRED)

  foreach(TEST_SRC ${TEST_SRCS})
    get_filename_component(TEST_NAME ${TEST_SRC} NAME_WE)

    # Registers the test with CTest automatically:
    ament_add_gtest(${TEST_NAME} ${TEST_SRC})
    ament_target_dependencies(${TEST_NAME}
      eigen_checks
    )

    # Link your library + deps. Use modern imported targets when possible.
    target_link_libraries(${TEST_NAME} ${PROJECT_NAME}          
        glog::glog
        protobuf::libprotobuf
    )
  endforeach()
endif()


ament_auto_package()


