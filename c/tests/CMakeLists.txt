add_executable(test_adxl355
    test_adxl355.c
    test_mock_bus.c
)

target_include_directories(test_adxl355 PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(test_adxl355 PRIVATE adxl355)

add_test(NAME test_adxl355 COMMAND test_adxl355)

add_executable(test_linux_spi_transfer
    test_linux_spi_transfer.c
    ${CMAKE_SOURCE_DIR}/examples/linux_spi_transfer.c
)

target_include_directories(test_linux_spi_transfer PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/examples
)

target_link_libraries(test_linux_spi_transfer PRIVATE adxl355)

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(test_linux_spi_transfer PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

add_test(NAME test_linux_spi_transfer COMMAND test_linux_spi_transfer)
