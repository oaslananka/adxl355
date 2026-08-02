# Contributing to ADXL355

Thank you for your interest in contributing!

## Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). Please be respectful and inclusive.

## How to Contribute

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-feature`).
3. Make your changes.
4. Run the relevant tests.
5. Commit using conventional commit messages.
6. Push and open a Pull Request.

## Development Setup

### Prerequisites

- CMake >= 3.14 (C/C++ builds)
- Python >= 3.10 (Python package)
- Rust toolchain (Rust crate)
- Node.js 22 or >= 24 (npm package; CI covers 22, 24, and 26)
- Go >= 1.21 (Go module)

### Testing

See [docs/testing.md](docs/testing.md) for full testing instructions.

## Coding Standards

- C: C99, no dynamic allocation in core, no global mutable state
- C++: C++17, RAII, thin wrapper over C core
- Python: Python 3.10+, type hints, Ruff linting, strict mypy
- Rust: no_std compatible, embedded-hal friendly
- TypeScript: strict mode, ES modules
- Go: gofmt, standard Go conventions
- All languages: same register constants, same decode logic, shared test vectors

## Commit Messages

Use conventional commits:

```
feat: add range configuration API
fix: correct sign extension in raw decode
docs: update register map table
test: add mock bus test for probe
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
