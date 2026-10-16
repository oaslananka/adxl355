cmake_minimum_required(VERSION 3.14)
project(adxl355_benchmarks LANGUAGES C CXX)

# CodSpeed benchmarks for the ADXL355 C core. This project is standalone and
# is never part of the installed/exported C or C++ packages.
#
#   cmake -S benchmarks/c -B build/bench-c -DCODSPEED_MODE=simulation
#   cmake --build build/bench-c --parallel
#   ./build/bench-c/adxl355_c_bench

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    # Optimized code with debug symbols for useful flame graphs.
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "Build type" FORCE)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
set(BENCHMARK_ENABLE_GTEST_TESTS OFF CACHE BOOL "" FORCE)
set(BENCHMARK_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
set(BENCHMARK_DOWNLOAD_DEPENDENCIES ON CACHE BOOL "" FORCE)

FetchContent_Declare(
    google_benchmark
    GIT_REPOSITORY https://github.com/CodSpeedHQ/codspeed-cpp
    GIT_TAG f5a917fdd14db7293bd37acb682873fec19f8b6c # v2.4.0
    SOURCE_SUBDIR google_benchmark
)
FetchContent_MakeAvailable(google_benchmark)

# Driver core, built exactly as the shipped C library.
set(ADXL355_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../..")
add_subdirectory("${ADXL355_REPO_ROOT}/c" "${CMAKE_CURRENT_BINARY_DIR}/adxl355-c")

add_executable(adxl355_c_bench
    bench_adxl355.cpp
    "${ADXL355_REPO_ROOT}/c/tests/test_mock_bus.c"
)
target_include_directories(adxl355_c_bench PRIVATE "${ADXL355_REPO_ROOT}/c/tests")
target_link_libraries(adxl355_c_bench PRIVATE adxl355 benchmark::benchmark)
