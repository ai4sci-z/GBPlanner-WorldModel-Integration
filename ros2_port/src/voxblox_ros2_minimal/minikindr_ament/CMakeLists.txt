cmake_minimum_required(VERSION 3.5)
project(minkindr)

find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()
find_package(Threads REQUIRED)  # only if your headers actually require it

# Header-only library
find_package(Eigen3 REQUIRED)
include_directories(
  include
  ${EIGEN3_INCLUDE_DIRS}
)

ament_auto_add_library(${PROJECT_NAME} INTERFACE)

# target_include_directories(${PROJECT_NAME} INTERFACE
#   $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
#   $<INSTALL_INTERFACE:include>)

# # Link INTERFACE deps (remove if not needed)
target_link_libraries(${PROJECT_NAME} INTERFACE Threads::Threads)

# Export for downstream packages
# ament_export_targets(export_${PROJECT_NAME})            # no HAS_LIBRARY_TARGET
# ament_export_dependencies(Threads)                      # optional; matches find_package above
# ament_export_include_directories(include)

# # Install headers and the INTERFACE target's export
# install(TARGETS ${PROJECT_NAME}
#   EXPORT export_${PROJECT_NAME})
# install(DIRECTORY include/ DESTINATION include)

# ament_package()
ament_auto_package()




