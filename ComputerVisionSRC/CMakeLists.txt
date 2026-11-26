cmake_minimum_required(VERSION 3.10)
project(pi4_balloon_interceptor CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Optimization flags for Raspberry Pi 4 (ARM Cortex-A72)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -march=armv8-a+crc -mtune=cortex-a72 -pthread")
else()
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -pthread")
endif()

find_package(OpenCV REQUIRED)
include_directories(${OpenCV_INCLUDE_DIRS})

add_executable(pi4_balloon_interceptor pi4_balloon_interceptor.cpp)
target_link_libraries(pi4_balloon_interceptor ${OpenCV_LIBS} pthread)
