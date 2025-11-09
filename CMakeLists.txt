cmake_minimum_required(VERSION 3.16)
project(normalizer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Eigen3
find_path(EIGEN3_INCLUDE_DIR
    NAMES Eigen/Dense
    PATHS /usr/include /usr/local/include
    PATH_SUFFIXES eigen3
)
if (NOT EIGEN3_INCLUDE_DIR)
    find_package(Eigen3 QUIET)
    if (Eigen3_FOUND)
        message(STATUS "Found Eigen3 via package at: ${Eigen3_INCLUDE_DIRS}")
        set(EIGEN3_INCLUDE_DIR ${Eigen3_INCLUDE_DIRS})
    else()
        message(FATAL_ERROR "Eigen not found. Please install libeigen3-dev")
    endif()
endif()

# Find nlohmann/json
find_path(NLOHMANN_JSON_INCLUDE_DIR nlohmann/json.hpp)
if (NOT NLOHMANN_JSON_INCLUDE_DIR)
    message(FATAL_ERROR "nlohmann::json not found. Please install nlohmann-json3-dev")
endif()

# Find gRPC and Protobuf using pkg-config
include(FindPkgConfig)
pkg_check_modules(GRPC REQUIRED grpc++)
pkg_check_modules(PROTOBUF REQUIRED protobuf)

include_directories(${EIGEN3_INCLUDE_DIR})
include_directories(${NLOHMANN_JSON_INCLUDE_DIR})
include_directories(${GRPC_INCLUDE_DIRS})
include_directories(${PROTOBUF_INCLUDE_DIRS})
include_directories(${CMAKE_CURRENT_BINARY_DIR}/generated/cpp)

# Generate protobuf and gRPC code
find_program(PROTOC protoc REQUIRED)
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin REQUIRED)

set(PROTO_DIR ${CMAKE_CURRENT_SOURCE_DIR}/protos)
set(PROTO_FILE ${PROTO_DIR}/pipeline.proto)
set(GENERATED_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated/cpp)

file(MAKE_DIRECTORY ${GENERATED_DIR})

add_custom_command(
    OUTPUT
        ${GENERATED_DIR}/pipeline.pb.cc
        ${GENERATED_DIR}/pipeline.pb.h
        ${GENERATED_DIR}/pipeline.grpc.pb.cc
        ${GENERATED_DIR}/pipeline.grpc.pb.h
    COMMAND ${PROTOC}
        --proto_path=${PROTO_DIR}
        --cpp_out=${GENERATED_DIR}
        --grpc_out=${GENERATED_DIR}
        --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
        ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
    COMMENT "Generating protobuf and gRPC C++ code"
)

# CLI executable (stdin/stdout) - keep for backward compatibility
add_executable(normalizer_cli
    main.cpp
    src/Normalizer.cpp
)
target_include_directories(normalizer_cli PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# gRPC Server executable - pure C++ server
add_executable(normalizer_server
    src/NormalizerServer.cpp
    src/Normalizer.cpp
    ${GENERATED_DIR}/pipeline.pb.cc
    ${GENERATED_DIR}/pipeline.grpc.pb.cc
)
target_include_directories(normalizer_server PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${GENERATED_DIR}
)
target_link_libraries(normalizer_server
    ${GRPC_LDFLAGS}
    ${PROTOBUF_LDFLAGS}
    pthread
)

install(TARGETS normalizer_cli normalizer_server RUNTIME DESTINATION bin)


