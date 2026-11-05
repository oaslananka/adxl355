# Test coverage and reproducible-build evidence

This page records **measured** evidence for the maintained ADXL355 driver family.
It is not a blanket OpenSSF Silver claim, a safety certification, or a substitute
for hardware-in-the-loop tests. The repository retains a single maintainer;
independent human approval is not a requirement.

## Coverage measurements — 4–6 November 2026

| Implementation and scope | Measured result | Measurement | Status |
| --- | ---: | --- | --- |
| Python `python/src/adxl355` | **97%** (816 / 843 statements) | `coverage.py` on all 204 Python tests | Passes 80% for measured source |
| Go core `go/adxl355` | **88.1%** statements | `go test ./adxl355 -cover` | Passes 80% for measured package |
| Go Linux SPI/I2C `go/adxl355/linuxio` | **95.5%** statements (Linux/amd64, Go 1.26.8, 5 November 2026) | `go test ./adxl355/linuxio -coverprofile=/tmp/adxl355-linuxio-coverage.out` | Above 80% on this package; error-path mocks and invalid-FD errno tests, **not** physical HIL |
| C `c/src/adxl355.c` | **85.56%** executable *lines* (545 / 637; formerly 83.83%) | GCC/gcov **13.3.0**, `--coverage -O0`, **306/306** C assertions, Linux/amd64, 6 November 2026 | Measured **line coverage**, not proven statement coverage or physical HIL |
| Go example binaries and support | 45.9–74.5% statements across example packages | `go test ./... -cover` | Not representative of core driver coverage |
| Node.js/TypeScript `node/src/**/*.ts` | **90.35%** (309 / 342 statements; 85.38% branches) | Vitest **5.0.5** + ephemeral `@vitest/coverage-v8@5.0.5` on Node **26.13.0**, all **108** tests, 5 November 2026 | Exceeds 80% for the measured source including mocked Linux SPI/I2C adapters; not physical HIL |
| Rust `rust/src` (all features, 58 unit/integration tests) | **88.20% LLVM regions** (613 / 695); **91.18% executable lines** (424 / 465); **91.18% functions** (62 / 68) | `rustc 1.99.1` / LLVM **23.1.1** source instrumentation (`-C instrument-coverage`), Windows MSVC, 6 November 2026 | LLVM *regions* and lines are **not statement counters**; no exact 80% statement claim or physical HIL |
| C++ exception-enabled header `cpp/include/adxl355/adxl355.hpp` | **97.10%** instrumented executable *lines* (134 / 138; formerly 83.56% of 73) | GCC/gcov **13.3.0**, `--coverage -O0`, 40/40 C++ assertions, Linux/amd64, 6 November 2026 | Header lines instantiated by the compiled tests, **not** full executable statement coverage or physical HIL |
| C++ exception-free header `cpp/include/adxl355/adxl355.hpp` | **98.10%** instrumented executable *lines* (103 / 105; formerly 90.16% of 61) | Same GCC/gcov, `-fno-exceptions -fno-rtti` and **28/28** assertions | Header lines instantiated by this variant, not full executable statement coverage |

The Go core gained tests for malformed frames, valid/invalid power-mode transitions,
write/read failures, acceleration conversions and invalid register range. Its
statement coverage rose from **72.7% to 88.1%**. No production behavior changed.
The Go Linux adapter improved from **64.8% to 95.5%** statements in a fresh
same-toolchain before/after measurement, using only error cases, fake
transports and invalid Linux file descriptors. Neither the source driver
nor the accepted physical SPI/I2C HIL baseline changed. The remaining
uncovered branches include real successful kernel ioctl configuration;
do not count mock coverage as a hardware acceptance result.
The C `adxl355_get_range()` readback contract now covers all three valid
range encodings, null and pre-probe guards, reserved register values, failed
and short reads, preserved output on errors, and read-only bus access using
a mock register file. On the same GCC 13.3 toolchain, C source executable
line coverage improved from **83.83% (534/637)** to **85.56% (545/637)**,
with all **306/306** assertions passing (previously 283/283); Clang strict
warnings and the same assertions also passed. No C driver behavior or
physical HIL baseline changed. These are *executable lines*, not statements.

Python coverage includes simulated adapters and the public library. C's percentage
comes from `gcov` executable lines and must not be relabeled as statements.
The Node.js/TypeScript V8 source statement coverage improved from **88.88% (304/342)** to **90.35% (309/342)** on the same local toolchain, by adding 27 focused Linux validation/error tests. The shared `linux/common.ts` helper now has **100% statements and branches** under Vitest; Node source overall has **85.38% branch coverage**. This includes mocked optional Linux adapters; no native physical sensor access was tested. This is opt-in, locally measured evidence, not an enforced CI coverage threshold.
Rust LLVM source coverage improved from **78.42% (545/695) to 88.20% (613/695)**
regions, with **91.18% (424/465)** executable lines and **91.18% (62/68)**
functions on the exact same MSVC toolchain. Four additional Rust tests
assert stable error messages, preserved backend causes and `embedded-hal`
error behavior, including standard-library error chaining. `rust/src/error.rs`
reached 100% of LLVM regions and lines. The instrumented tests use
fake transports only; no physical device was accessed. LLVM regions
are more granular than lines but are **not** the same metric as executable
statements; this does not certify the project-wide Silver criterion.
The C++ header is tested in **both** exception-enabled and exception-free builds. GCC/gcov now reports **97.10% (134/138)** and **98.10% (103/105)** instrumented executable source lines respectively; the earlier same-toolchain measurements were 83.56% (61/73) and 90.16% (55/61). Tests exercise public read/control/conversion methods, range and bad-ID errors, moved-device callback rebinding and exception containment in the `NoexceptDevice` bus callbacks. These are **separate compilation variants**, not additive coverage values. Because uninstantiated inline/template methods may not enter gcov's denominator, the percentages are neither complete statement coverage nor device HIL.
The Silver `test_statement_coverage80` item remains **unverified for the complete
multi-language product** pending accurate statement counters for remaining source
and permitted hardware-specific exclusions grounded in real evidence.

### Reproduce the measurements locally

Run from a working tree with supported toolchains (Go >=1.25, CMake/GCC,
Python, Node.js 22/24/26, and a free isolated `uvx` environment):

```bash
# Python: reports actual executable statements, no repository dependency change.
export PYTHONPATH="$PWD/python/src"
uvx --from 'coverage==7.10.7' --with 'pytest>=8,<10' coverage run \
  --source=python/src/adxl355 -m pytest -q python/tests
uvx --from 'coverage==7.10.7' coverage report -m

# Go: use the exact Go package and full suite, not just one selected test.
(cd go && go test ./adxl355 -cover && \
  go test ./adxl355/linuxio -coverprofile=/tmp/adxl355-linuxio-coverage.out && \
  go tool cover -func=/tmp/adxl355-linuxio-coverage.out | tail -1)
(cd go && go test ./... -coverprofile=/tmp/adxl355-go-cover.out)

# Node.js: install V8 coverage provider ephemerally (no manifest/lock write).
# Run from repository root; the provider version must match Vitest 5.0.5.
(cd node && npm ci --ignore-scripts --no-audit --no-fund && \
  npm install --no-save --package-lock=false --ignore-scripts --no-audit --no-fund \
    @vitest/coverage-v8@5.0.5 && \
  npx --no-install vitest run --coverage --coverage.provider=v8 \
    --coverage.include='src/**/*.ts' --coverage.reporter=text \
    --coverage.reporter=json-summary \
    --coverage.reportsDirectory=/tmp/adxl355-node-cover)
# The transient provider can be cleared by rerunning npm ci afterwards.

# C: build instrumentation in an isolated directory; gcov reports lines.
cmake -S c -B /tmp/adxl355-c-cover \
  -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=OFF \
  -DCMAKE_C_FLAGS='--coverage -O0' -DCMAKE_EXE_LINKER_FLAGS='--coverage'
cmake --build /tmp/adxl355-c-cover --parallel 2
ctest --test-dir /tmp/adxl355-c-cover --output-on-failure
gcov -o /tmp/adxl355-c-cover/CMakeFiles/adxl355.dir/src/adxl355.c.gcno \
  c/src/adxl355.c
```

#### C++ header coverage (Linux GCC, no repository dependency change)

From the repository root on Linux with GCC/gcov 13.3, build both C++ tests
against the C core using disposable objects. **Only** inspect the gcov record
for `cpp/include/adxl355/adxl355.hpp`; excluding C, test code and system
headers avoids inflating the driver wrapper's reported coverage.

```bash
repo=$PWD
work=$(mktemp -d)
mkdir -p "$work"/{except,noexcept}
gcc --coverage -O0 -g -std=c99 -I"$repo/c/include" -c "$repo/c/src/adxl355.c" -o "$work/c-core.o"
g++ --coverage -O0 -g -std=c++17 -I"$repo/cpp/include" -I"$repo/c/include" \
  "$repo/cpp/tests/test_adxl355_cpp.cpp" "$work/c-core.o" -o "$work/except/test_cpp"
g++ --coverage -O0 -g -std=c++17 -fno-exceptions -fno-rtti \
  -DADXL355_CPP_NO_EXCEPTIONS=1 -I"$repo/cpp/include" -I"$repo/c/include" \
  "$repo/cpp/tests/test_adxl355_cpp_noexcept.cpp" "$work/c-core.o" \
  -o "$work/noexcept/test_cpp_noexcept"
"$work/except/test_cpp"
"$work/noexcept/test_cpp_noexcept"
(cd "$work/except" && gcov -b -c -o test_cpp-test_adxl355_cpp.gcda \
  "$repo/cpp/tests/test_adxl355_cpp.cpp")
(cd "$work/noexcept" && gcov -b -c -o \
  test_cpp_noexcept-test_adxl355_cpp_noexcept.gcda \
  "$repo/cpp/tests/test_adxl355_cpp_noexcept.cpp")
# Compare each of the two 'adxl355.hpp' file sections above.
rm -rf -- "$work" # Only the fresh disposable coverage directory
```

gcov reports *instrumented executable lines*, not precise statement
coverage. Never add results from the two builds together or count the
test/source-C lines as C++ wrapper coverage.

#### Rust source coverage (Windows MSVC, no repository dependency change)

The run used the official `llvm-tools-preview` component matched to
`rustc 1.99.1` (LLVM 23.1.1), with an isolated target and profile directory.
From the repository root in PowerShell:

```powershell
rustup component add llvm-tools-preview
$work = Join-Path $env:TEMP "adxl355-rust-coverage"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$env:CARGO_TARGET_DIR = Join-Path $work "target"
$env:RUSTFLAGS = "-Cinstrument-coverage"
$env:LLVM_PROFILE_FILE = Join-Path $work "rust-%p-%m.profraw"
Push-Location rust
$artifacts = @(cargo test --locked --all-features --tests --no-run --message-format=json)
cargo test --locked --all-features --tests
Pop-Location
$bins = @($artifacts | Where-Object { $_ -match '^\{' } | ForEach-Object {
  $artifact = $_ | ConvertFrom-Json
  if ($artifact.reason -eq "compiler-artifact" -and
      $artifact.profile.test -and $artifact.executable) { $artifact.executable }
} | Sort-Object -Unique)
$llvm = Join-Path (rustc --print sysroot) "lib\rustlib\x86_64-pc-windows-msvc\bin"
$profdata = Join-Path $work "rust.profdata"
$raw = @(Get-ChildItem $work -Filter "rust-*.profraw" | Select-Object -ExpandProperty FullName)
& (Join-Path $llvm "llvm-profdata.exe") merge -sparse @raw -o $profdata
$covArgs = @("export", "-instr-profile=$profdata", $bins[0])
foreach ($bin in $bins | Select-Object -Skip 1) { $covArgs += "-object=$bin" }
$coverage = (& (Join-Path $llvm "llvm-cov.exe") @covArgs) | ConvertFrom-Json
$source = @($coverage.data[0].files | Where-Object {
  $_.filename -match '[\\/]rust[\\/]src[\\/].+\.rs$'
})
$covered = 0; $total = 0
foreach ($file in $source) {
  $covered += [int]$file.summary.regions.covered
  $total += [int]$file.summary.regions.count
}
"$covered/$total LLVM source regions"
```

Include **all seven** test executables and count only `rust/src` files, not
test implementations or dependencies. LLVM's regions, executable lines,
and functions are different counters; do not call them statements.
Delete disposable coverage artifacts after use.

Use a disposable directory and remove temporary coverage data when finished.
Do not run optional hardware suites on machines without an authorized fixture.
See [testing](testing.md) and [hardware validation](hardware-testing.md).

## Independent, byte-for-byte package builds

An **opt-in local** acceptance script compiles/packages twice in separate scratch
build directories under the same controlled Linux toolchain, then compares
SHA-256 hashes and fails if any artifact set or byte stream differs:

```bash
# npm development dependencies must first be installed (no optional scripts):
(cd node && npm ci --ignore-scripts --no-audit --no-fund)
bash scripts/check_reproducible_builds.sh --components c python rust npm
```

The script sets `SOURCE_DATE_EPOCH` from the Git commit, `TZ=UTC` and `LC_ALL=C`.
It uses GCC/CMake Release for the C static library, pinned Python `build==1.5.0`
and `setuptools==84.1.0` for the wheel/sdist, Cargo's locked Rust manifest,
and the pinned npm lockfile/TypeScript toolchain. Python sdist's generated tar/gzip
metadata is normalized with `scripts/normalize_sdist.py` before checksum or
attestation, preserving the original source bytes. The release workflow also
calls this normalizer before computing signed package checksums.

| Output | Repeated on 4 November 2026 | Result |
| --- | --- | --- |
| C `libadxl355.a` | Two Release builds | Byte-identical |
| Python wheel and normalized sdist | Two independent builds each | Both byte-identical |
| Rust `adxl355-driver` crate | Two Cargo package invocations | Byte-identical |
| npm `@oaslananka/adxl355` tarball | Two isolated TypeScript builds/package runs | Byte-identical |

The script does **not** certify cross-host toolchain reproducibility, all historical
release packages, installed C/C++ consumer binaries, embedded targets, hardware
behavior, or a Go executable (the published Go module is source-based). The
repository has not yet earned Silver; its separate sole-maintainer continuity
requirement is not resolved. These tests are valuable package integrity
checks regardless of badge level.
