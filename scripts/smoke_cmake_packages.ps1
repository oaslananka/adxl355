param(
    [Parameter(Mandatory = $false)]
    [string]$BuildRoot = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($BuildRoot)) {
    $BuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("adxl355-cmake-smoke-" + [guid]::NewGuid())
}
$BuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
$Prefix = Join-Path $BuildRoot "prefix"

cmake -S (Join-Path $RepoRoot "c") -B (Join-Path $BuildRoot "c-build") -A x64 `
    -DADXL355_WARNINGS_AS_ERRORS=ON
cmake --build (Join-Path $BuildRoot "c-build") --config Release --parallel
cmake --install (Join-Path $BuildRoot "c-build") --config Release --prefix $Prefix

cmake -S (Join-Path $RepoRoot "cmake/smoke/c") -B (Join-Path $BuildRoot "c-consumer") -A x64 `
    "-DCMAKE_PREFIX_PATH=$Prefix"
cmake --build (Join-Path $BuildRoot "c-consumer") --config Release --parallel
& (Join-Path $BuildRoot "c-consumer/Release/adxl355_c_consumer.exe")

cmake -S (Join-Path $RepoRoot "cpp") -B (Join-Path $BuildRoot "cpp-build") -A x64 `
    "-DCMAKE_PREFIX_PATH=$Prefix"
cmake --build (Join-Path $BuildRoot "cpp-build") --config Release --parallel
cmake --install (Join-Path $BuildRoot "cpp-build") --config Release --prefix $Prefix

$InstalledTargets = Get-ChildItem -Path (Join-Path $Prefix "lib/cmake/adxl355-cpp") -Recurse -File |
    Select-String -Pattern "-Werror|-Wall|-fsanitize"
if ($InstalledTargets) {
    throw "Build-only warning or sanitizer flags leaked into the installed C++ target"
}

cmake -S (Join-Path $RepoRoot "cmake/smoke/cpp") -B (Join-Path $BuildRoot "cpp-consumer") -A x64 `
    "-DCMAKE_PREFIX_PATH=$Prefix"
cmake --build (Join-Path $BuildRoot "cpp-consumer") --config Release --parallel
& (Join-Path $BuildRoot "cpp-consumer/Release/adxl355_cpp_consumer.exe")
& (Join-Path $BuildRoot "cpp-consumer/Release/adxl355_cpp_noexcept_consumer.exe")

Write-Host "C and C++ install/export smoke tests passed"
