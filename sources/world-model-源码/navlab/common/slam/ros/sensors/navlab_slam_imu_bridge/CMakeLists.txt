cmake_minimum_required(VERSION 3.8)
project(navlab_slam_imu_bridge)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

include_directories(include)

add_executable(navlab_slam_imu_bridge_node
  src/navlab_slam_imu_bridge_node.cpp
)

ament_target_dependencies(navlab_slam_imu_bridge_node
  rclcpp
  sensor_msgs
  std_msgs
)

install(TARGETS
  navlab_slam_imu_bridge_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)

  ament_add_gtest(imu_timestamp_test
    test/imu_timestamp_test.cpp
  )
  target_include_directories(imu_timestamp_test PRIVATE include)
endif()

ament_package()
