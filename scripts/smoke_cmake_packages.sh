#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build_root=${1:-}
cleanup=0

if [[ -z "$build_root" ]]; then
    build_root=$(mktemp -d -t adxl355-cmake-smoke-XXXXXX)
    cleanup=1
fi
if [[ $cleanup -eq 1 ]]; then
    trap 'rm -rf "$build_root"' EXIT
fi

prefix="$build_root/prefix"

cmake -S "$repo_root/c" -B "$build_root/c-build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DADXL355_WARNINGS_AS_ERRORS=ON
cmake --build "$build_root/c-build" --parallel
cmake --install "$build_root/c-build" --prefix "$prefix"

cmake -S "$repo_root/cmake/smoke/c" -B "$build_root/c-consumer" \
    -DCMAKE_PREFIX_PATH="$prefix"
cmake --build "$build_root/c-consumer" --parallel
"$build_root/c-consumer/adxl355_c_consumer"

cmake -S "$repo_root/cpp" -B "$build_root/cpp-build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$prefix"
cmake --build "$build_root/cpp-build" --parallel
cmake --install "$build_root/cpp-build" --prefix "$prefix"

if grep -R -E -- '-Werror|-Wall|-fsanitize' "$prefix/lib/cmake/adxl355-cpp"; then
    printf 'Build-only warning or sanitizer flags leaked into the installed C++ target\n' >&2
    exit 1
fi

cmake -S "$repo_root/cmake/smoke/cpp" -B "$build_root/cpp-consumer" \
    -DCMAKE_PREFIX_PATH="$prefix"
cmake --build "$build_root/cpp-consumer" --parallel
"$build_root/cpp-consumer/adxl355_cpp_consumer"

printf 'C and C++ install/export smoke tests passed\n'
