# Versioning and package names

## Canonical version

The repository root `VERSION` file is the only manually edited version source.
For the current release candidate it contains:

```text
0.1.0-alpha.2
```

Run the synchronizer after changing it:

```bash
python scripts/versioning.py --write
python scripts/versioning.py
```

The second command is the non-mutating CI check. It fails when any maintained
declaration differs from `VERSION`.

## Ecosystem mapping

| Target | Current value | Rule |
|---|---|---|
| Root Git tag | `v0.1.0-alpha.2` | `v` + canonical SemVer |
| Python distribution/runtime | `0.1.0a2` | PEP 440 mapping of `alpha.2` |
| Rust and npm | `0.1.0-alpha.2` | canonical SemVer |
| C/C++ CMake projects | `0.1.0` | numeric core; prerelease remains in the C version string and artifact metadata |
| Go submodule tag | `go/v0.1.0-alpha.2` | module-directory prefix + canonical SemVer tag |

The Go module path remains:

```text
module github.com/oaslananka/adxl355/go
```

A root tag alone does not publish that nested module. The `go/` prefix is
required by Go module version discovery.

## Registry package names

Availability was checked on **2026-07-23** without reserving or publishing any
name:

- PyPI: `adxl355` returned not found.
- npm: the owned scope name `@oaslananka/adxl355` returned not found.
- crates.io: `adxl355` is owned by another project, so this repository uses the
  distribution name `adxl355-driver` while preserving `use adxl355::...` through
  `[lib] name = "adxl355"`.

Registry state can change. Maintainers must **re-check** every selected name and
account ownership immediately before enabling publication. A dry-run artifact is
not proof that a registry name has been reserved.

## Release update sequence

1. Update `VERSION` to a supported stable, `alpha.N`, `beta.N`, or `rc.N` value.
2. Run `python scripts/versioning.py --write`.
3. Update the Unreleased changelog heading and release notes.
4. Run the complete CI and package smoke matrix.
5. Create the root tag on the verified commit.
6. Create the matching `go/v...` tag on the same commit when the Go module is
   intentionally released.
7. Run the release gate and inspect checksums and package contents before any
   explicit registry publication step.
