cmake_minimum_required(VERSION 3.5)
project(voxblox_rviz_plugin)

# Default to C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies using ament_auto
find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()

# Do find_package(rviz_ogre_vendor) first to make sure the custom OGRE is found
find_package(rviz_ogre_vendor REQUIRED)

# OGRE includes must be set before AUTOMOC for Qt MOC to find headers
# Note: Official rviz plugins use different build system that handles this automatically
# With ament_cmake_auto, we need explicit include_directories for AUTOMOC stage
set(OGRE_INCLUDE_DIRS "${rviz_ogre_vendor_DIR}/../../../opt/rviz_ogre_vendor/include")
include_directories(SYSTEM ${OGRE_INCLUDE_DIRS})

# Qt5 is required for RViz2 plugins (not handled by ament_auto)
find_package(Qt5 REQUIRED COMPONENTS Core Widgets)
set(QT_LIBRARIES Qt5::Widgets Qt5::Core)

# This setting causes Qt's "MOC" generation to happen automatically
set(CMAKE_AUTOMOC ON)

# Avoid Qt signals and slots defining "emit", "slots", etc.
add_definitions(-DQT_NO_KEYWORDS)

set(HEADER_FILES
  include/voxblox_rviz_plugin/voxblox_mesh_display.h
  include/voxblox_rviz_plugin/voxblox_mesh_visual.h
)

set(SRC_FILES
  src/voxblox_mesh_display.cc
  src/voxblox_mesh_visual.cc
)

# Build the plugin library using ament_auto
ament_auto_add_library(${PROJECT_NAME} SHARED
  ${SRC_FILES}
  ${HEADER_FILES}
)

target_link_libraries(${PROJECT_NAME}
  ${QT_LIBRARIES}
  rviz_ogre_vendor::OgreMain
)

# Prevent pluginlib from using boost
target_compile_definitions(${PROJECT_NAME} PUBLIC "PLUGINLIB__DISABLE_BOOST_FUNCTIONS")

# Install plugin description and icons
install(FILES plugin_description.xml
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY icons/
  DESTINATION share/${PROJECT_NAME}/icons
)

# Export plugin
pluginlib_export_plugin_description_file(rviz_common plugin_description.xml)

ament_auto_package()
