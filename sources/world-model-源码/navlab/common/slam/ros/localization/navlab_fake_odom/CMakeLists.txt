cmake_minimum_required(VERSION 3.8)
project(navlab_fake_odom)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(navlab_fake_odom_node
  src/navlab_fake_odom_node.cpp
)

ament_target_dependencies(navlab_fake_odom_node
  nav_msgs
  rclcpp
  std_msgs
)

install(TARGETS
  navlab_fake_odom_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)

ament_package()
