cmake_minimum_required(VERSION 3.8)
project(planner_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# M1 minimal interface set. Order: leaf enums first, then messages/services
# that reference them. rosidl resolves same-package refs regardless of order,
# but keeping leaves first documents the dependency structure.
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/BoundMode.msg"
  "msg/PlanningMode.msg"
  "msg/TriggerMode.msg"
  "msg/ExecutionPathMode.msg"
  "msg/PlannerStatus.msg"
  "msg/Vertex.msg"
  "msg/Edge.msg"
  "msg/Graph.msg"
  "msg/PlanningBound.msg"
  "srv/PlannerSrv.srv"
  "srv/PlannerSetPlanningMode.srv"
  "srv/PlannerHoming.srv"
  "srv/PlannerDynamicGlobalBound.srv"
  DEPENDENCIES std_msgs geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
