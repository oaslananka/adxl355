cmake_minimum_required(VERSION 3.14)
project(adxl355-cpp VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(ADXL355_BUILD_TESTS "Build tests" OFF)
option(ADXL355_BUILD_EXAMPLES "Build examples" OFF)
option(ADXL355_ENABLE_SANITIZERS "Enable Address/Undefined sanitizers" OFF)
option(ADXL355_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" OFF)
set(ADXL355_C_LIB "" CACHE FILEPATH "Path to a prebuilt ADXL355 C library")
set(
    ADXL355_C_INCLUDE_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/../c/include"
    CACHE PATH
    "Path to ADXL355 C headers when ADXL355_C_LIB is used"
)

if(ADXL355_ENABLE_SANITIZERS)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
        add_link_options(-fsanitize=address,undefined)
    else()
        message(FATAL_ERROR "ADXL355_ENABLE_SANITIZERS requires GCC or Clang")
    endif()
endif()

find_package(adxl355 CONFIG QUIET)
if(NOT TARGET adxl355::adxl355)
    if(NOT ADXL355_C_LIB)
        find_library(ADXL355_C_LIB adxl355 PATHS "${CMAKE_CURRENT_SOURCE_DIR}/../c/build")
    endif()
    if(NOT ADXL355_C_LIB)
        message(FATAL_ERROR
            "ADXL355 C core not found. Install the C package, set CMAKE_PREFIX_PATH, "
            "or pass ADXL355_C_LIB and ADXL355_C_INCLUDE_DIR."
        )
    endif()
    add_library(adxl355_c_core UNKNOWN IMPORTED)
    set_target_properties(adxl355_c_core PROPERTIES
        IMPORTED_LOCATION "${ADXL355_C_LIB}"
        INTERFACE_INCLUDE_DIRECTORIES "${ADXL355_C_INCLUDE_DIR}"
    )
    add_library(adxl355::adxl355 ALIAS adxl355_c_core)
endif()

add_library(adxl355_cpp INTERFACE)
add_library(adxl355::cpp ALIAS adxl355_cpp)
set_target_properties(adxl355_cpp PROPERTIES EXPORT_NAME cpp)
target_include_directories(adxl355_cpp INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(adxl355_cpp INTERFACE adxl355::adxl355)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(
        -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Wsign-conversion
    )
    if(ADXL355_WARNINGS_AS_ERRORS)
        add_compile_options(-Werror)
    endif()
elseif(MSVC)
    add_compile_options(/W4)
    if(ADXL355_WARNINGS_AS_ERRORS)
        add_compile_options(/WX)
    endif()
endif()

if(ADXL355_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

if(ADXL355_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
set(ADXL355_CPP_INSTALL_CMAKEDIR "${CMAKE_INSTALL_LIBDIR}/cmake/adxl355-cpp")

configure_package_config_file(
    cmake/adxl355-cpp-config.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/adxl355-cpp-config.cmake"
    INSTALL_DESTINATION "${ADXL355_CPP_INSTALL_CMAKEDIR}"
)
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/adxl355-cpp-config-version.cmake"
    VERSION "${PROJECT_VERSION}"
    COMPATIBILITY SameMajorVersion
)

install(TARGETS adxl355_cpp EXPORT adxl355-cpp-targets)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT adxl355-cpp-targets
    FILE adxl355-cpp-targets.cmake
    NAMESPACE adxl355::
    DESTINATION "${ADXL355_CPP_INSTALL_CMAKEDIR}"
)
install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/adxl355-cpp-config.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/adxl355-cpp-config-version.cmake"
    DESTINATION "${ADXL355_CPP_INSTALL_CMAKEDIR}"
)
