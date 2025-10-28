cmake_minimum_required(VERSION 3.16)
project(normalizer_service CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Dependencies: Eigen (header-only) and nlohmann_json (header-only single_include)
# Expect system packages or vendored includes in /usr/include

find_path(EIGEN3_INCLUDE_DIR
    NAMES Eigen/Dense
    PATHS /usr/include /usr/local/include
    PATH_SUFFIXES eigen3
)
if (NOT EIGEN3_INCLUDE_DIR)
    # Fallback to CMake package if available
    find_package(Eigen3 QUIET)
    if (Eigen3_FOUND)
        message(STATUS "Found Eigen3 via package at: ${Eigen3_INCLUDE_DIRS}")
        set(EIGEN3_INCLUDE_DIR ${Eigen3_INCLUDE_DIRS})
    else()
        message(FATAL_ERROR "Eigen not found. Please install libeigen3-dev or provide EIGEN3_INCLUDE_DIR.")
    endif()
endif()

find_path(NLOHMANN_JSON_INCLUDE_DIR nlohmann/json.hpp)
if (NOT NLOHMANN_JSON_INCLUDE_DIR)
    message(FATAL_ERROR "nlohmann::json not found. Please install nlohmann-json3-dev or provide NLOHMANN_JSON_INCLUDE_DIR.")
endif()

include_directories(${EIGEN3_INCLUDE_DIR})
include_directories(${NLOHMANN_JSON_INCLUDE_DIR})

add_executable(normalizer_service
    main.cpp
    src/Normalizer.cpp
    src/GrpcServer.cpp
    src/RestServer.cpp
)

target_include_directories(normalizer_service PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# No external link libraries needed for stubs

install(TARGETS normalizer_service RUNTIME DESTINATION bin)


