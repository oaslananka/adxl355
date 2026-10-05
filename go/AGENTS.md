# Go Driver Instructions

These instructions apply to `go/**` and supplement the root instructions.

- Keep the portable driver dependent only on its `Transport` contract.
- Linux device behavior belongs under `adxl355/linuxio`; unsupported platforms/architectures return `ErrUnsupported` rather than pretending ioctl support.
- SPI/I2C adapters own descriptors until explicit idempotent `Close`.
- Preserve exact transfer counts, validated bus parameters, combined I2C transaction semantics, and inspectable `OpError` wrapping.
- I2C `BusHz` is a declaration/check of external adapter configuration, not a kernel clock setter.
- Bounded examples must probe, collect a finite count, restore standby, and close resources.
- Do not claim language-specific FIFO/self-test/DRDY support that is not implemented.

Run `go mod verify`, `go test ./...`, `go test -race ./...`, `go vet ./...`, cross-build checks, and shared vectors.
