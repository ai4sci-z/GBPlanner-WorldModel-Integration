cmake_minimum_required(VERSION 3.16)
project(gbplanner_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 纯算法核心库(当前为 header-only,头文件在 include/)
add_library(gbplanner_core INTERFACE)
target_include_directories(gbplanner_core
  INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)

# 离线演示程序
add_executable(gbp_demo src/demo_main.cpp)
target_link_libraries(gbp_demo PRIVATE gbplanner_core)

# 单元测试
enable_testing()
add_executable(test_gain test/test_gain.cpp)
target_link_libraries(test_gain PRIVATE gbplanner_core)
add_test(NAME test_gain COMMAND test_gain)
