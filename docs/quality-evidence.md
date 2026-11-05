# Test coverage and reproducible-build evidence

This page records **measured** evidence for the maintained ADXL355 driver family.
It is not a blanket OpenSSF Silver claim, a safety certification, or a substitute
for hardware-in-the-loop tests. The repository retains a single maintainer;
independent human approval is not a requirement.

## Coverage measurements — 4–5 November 2026

| Implementation and scope | Measured result | Measurement | Status |
| --- | ---: | --- | --- |
| Python `python/src/adxl355` | **97%** (816 / 843 statements) | `coverage.py` on all 204 Python tests | Passes 80% for measured source |
| Go core `go/adxl355` | **88.1%** statements | `go test ./adxl355 -cover` | Passes 80% for measured package |
| Go Linux SPI/I2C `go/adxl355/linuxio` | **95.5%** statements (Linux/amd64, Go 1.26.8, 5 November 2026) | `go test ./adxl355/linuxio -coverprofile=/tmp/adxl355-linuxio-coverage.out` | Above 80% on this package; error-path mocks and invalid-FD errno tests, **not** physical HIL |
| C `c/src/adxl355.c` | **83.83%** executable *lines* (of 637) | GCC `--coverage` + `gcov` after `ctest` | This is **line coverage**, not proven statement coverage |
| Go example binaries and support | 45.9–74.5% statements across example packages | `go test ./... -cover` | Not representative of core driver coverage |
| C++ public wrapper, Rust, Node.js | **Not yet independently measured** as complete statement coverage | Tests and CI pass; statement coverage evidence is incomplete | No 80% assertion |

The Go core gained tests for malformed frames, valid/invalid power-mode transitions,
write/read failures, acceleration conversions and invalid register range. Its
statement coverage rose from **72.7% to 88.1%**. No production behavior changed.
The Go Linux adapter improved from **64.8% to 95.5%** statements in a fresh
same-toolchain before/after measurement, using only error cases, fake
transports and invalid Linux file descriptors. Neither the source driver
nor the accepted physical SPI/I2C HIL baseline changed. The remaining
uncovered branches include real successful kernel ioctl configuration;
do not count mock coverage as a hardware acceptance result.
Python coverage includes simulated adapters and the public library. C's percentage
comes from `gcov` executable lines and must not be relabeled as statements.
The Silver `test_statement_coverage80` item remains **unverified for the complete
multi-language product** pending accurate statement counters for remaining source
and permitted hardware-specific exclusions grounded in real evidence.

### Reproduce the measurements locally

Run from a working tree with supported toolchains (Go >=1.25, CMake/GCC,
Python and a free isolated `uvx` environment):

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

# C: build instrumentation in an isolated directory; gcov reports lines.
cmake -S c -B /tmp/adxl355-c-cover \
  -DADXL355_BUILD_TESTS=ON -DADXL355_BUILD_EXAMPLES=OFF \
  -DCMAKE_C_FLAGS='--coverage -O0' -DCMAKE_EXE_LINKER_FLAGS='--coverage'
cmake --build /tmp/adxl355-c-cover --parallel 2
ctest --test-dir /tmp/adxl355-c-cover --output-on-failure
gcov -o /tmp/adxl355-c-cover/CMakeFiles/adxl355.dir/src/adxl355.c.gcno \
  c/src/adxl355.c
```

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
