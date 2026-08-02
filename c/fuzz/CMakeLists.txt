if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "ADXL355_BUILD_FUZZERS requires Clang/libFuzzer")
endif()

add_executable(fuzz_adxl355 fuzz_adxl355.c)
target_include_directories(fuzz_adxl355 PRIVATE ${CMAKE_SOURCE_DIR}/include)
target_link_libraries(fuzz_adxl355 PRIVATE adxl355)
target_compile_options(fuzz_adxl355 PRIVATE
    -Wall -Wextra -Wpedantic -Werror
    -fsanitize=fuzzer,address,undefined
    -fno-omit-frame-pointer
)
target_link_options(fuzz_adxl355 PRIVATE -fsanitize=fuzzer,address,undefined)
