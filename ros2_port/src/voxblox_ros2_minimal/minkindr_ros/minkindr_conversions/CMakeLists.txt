cmake_minimum_required(VERSION 3.5)
project(minkindr_conversions)

find_package(ament_cmake_auto REQUIRED)
ament_auto_find_build_dependencies()
# catkin_simple(ALL_DEPS_REQUIRED)
find_package(glog REQUIRED)

add_definitions(-std=c++17)
include_directories(
  include
  ${EIGEN3_INCLUDE_DIRS}
)

#############
# LIBRARIES #
#############

ament_auto_add_library(${PROJECT_NAME}
  INTERFACE
)
# target_link_libraries(${PROJECT_NAME} glog::glog)

if(BUILD_TESTING)
	##########
	# GTESTS #
	##########
find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(kindr_tf_test
	  test/kindr_tf_test.cc
	)
	target_link_libraries(kindr_tf_test ${PROJECT_NAME} glog::glog)

  ament_add_gtest(kindr_msg_test
	  test/kindr_msg_test.cc
	)
target_link_libraries(kindr_msg_test ${PROJECT_NAME} glog::glog)
endif() #CATKIN_ENABLE_TESTING

##########
# EXPORT #
##########
ament_auto_package()
