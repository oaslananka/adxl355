# adxl355

Rust driver for the Analog Devices ADXL355 accelerometer. The crate supports
`std`, `no_std`, and optional `embedded-hal` transports while sharing the same
register and conversion behavior as the other maintained implementations in
this repository.

See the repository root documentation for API status, hardware wiring, and
cross-language verification details.

The crates.io distribution name is `adxl355-driver`; the Rust import remains
`adxl355` (`use adxl355::...`).


## Typed error handling

The transport trait exposes an associated backend error type. Driver methods
return `Error<T::Error>`, preserving the original transport cause without heap
allocation and distinguishing identity, exact-length, lifecycle, configuration,
not-ready, timeout, unsupported, and restore failures.

```rust
match device.read_raw() {
    Ok(sample) => use_sample(sample),
    Err(Error::Transport(source)) => recover_bus(source),
    Err(Error::InvalidResponseLength { expected, actual, .. }) => {
        report_framing_error(expected, actual)
    }
    Err(Error::InvalidState { required }) => report_state_requirement(required),
    Err(Error::Restore(source)) => report_restore_failure(source),
    Err(other) => report_driver_error(other),
}
```

This associated-error API is an alpha-stage breaking change from the earlier
string-like/coarse `Error::Bus` model. Custom transports implement
`type Error = MyBackendError` and return that cause directly.
