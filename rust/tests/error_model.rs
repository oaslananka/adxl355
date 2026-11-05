//! Public typed-error behavior.

use adxl355::{Error, StateRequirement};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BackendError {
    Disconnected,
}

#[test]
fn transport_and_restore_causes_remain_inspectable() {
    let transport = Error::Transport(BackendError::Disconnected);
    assert_eq!(
        transport.transport_cause(),
        Some(&BackendError::Disconnected)
    );
    assert!(!transport.is_restore_failure());

    let restore = Error::Restore(BackendError::Disconnected);
    assert_eq!(restore.transport_cause(), Some(&BackendError::Disconnected));
    assert!(restore.is_restore_failure());
}

#[test]
fn structured_failures_preserve_recovery_context() {
    let identity: Error<BackendError> = Error::InvalidIdentity {
        devid_ad: 0x00,
        devid_mst: 0x1D,
        partid: 0xED,
    };
    assert!(matches!(
        identity,
        Error::InvalidIdentity { devid_ad: 0x00, .. }
    ));

    let length: Error<BackendError> = Error::InvalidResponseLength {
        register: 0x08,
        expected: 9,
        actual: 8,
    };
    assert!(matches!(
        length,
        Error::InvalidResponseLength {
            register: 0x08,
            expected: 9,
            actual: 8
        }
    ));

    let state: Error<BackendError> = Error::InvalidState {
        required: StateRequirement::Probed,
    };
    assert!(matches!(
        state,
        Error::InvalidState {
            required: StateRequirement::Probed
        }
    ));
}

#[test]
fn every_public_error_message_retains_actionable_context() {
    let cases: [(Error<&str>, &str); 9] = [
        (
            Error::Transport("bus disconnected"),
            "transport error: bus disconnected",
        ),
        (
            Error::InvalidIdentity {
                devid_ad: 0x00,
                devid_mst: 0x1d,
                partid: 0xed,
            },
            "invalid ADXL355 identity (DEVID_AD=0x00, DEVID_MST=0x1D, PARTID=0xED)",
        ),
        (
            Error::InvalidResponseLength {
                register: 0x08,
                expected: 9,
                actual: 8,
            },
            "invalid response length at register 0x08: expected 9, received 8",
        ),
        (
            Error::InvalidState {
                required: StateRequirement::Probed,
            },
            "invalid device state; operation requires a successful probe",
        ),
        (
            Error::InvalidConfiguration {
                register: 0x2d,
                value: 0xff,
            },
            "invalid configuration value 0xFF in register 0x2D",
        ),
        (Error::NotReady, "data not ready"),
        (Error::Timeout, "operation timed out"),
        (Error::Unsupported, "unsupported operation"),
        (
            Error::Restore("write failed"),
            "failed to restore device state: write failed",
        ),
    ];
    assert_eq!(StateRequirement::Probed.to_string(), "a successful probe");
    for (error, expected) in cases {
        assert_eq!(error.to_string(), expected);
        let is_backend_error = matches!(&error, Error::Transport(_) | Error::Restore(_));
        assert_eq!(error.transport_cause().is_some(), is_backend_error);
        assert_eq!(
            error.is_restore_failure(),
            matches!(error, Error::Restore(_))
        );
    }
}

#[cfg(feature = "std")]
#[test]
fn standard_error_source_preserves_real_backend_causes() {
    use std::error::Error as StdError;

    let transport: Error<std::io::Error> =
        Error::Transport(std::io::Error::other("bus disconnected"));
    let restore: Error<std::io::Error> = Error::Restore(std::io::Error::other("failed to restore"));
    let invalid_state: Error<std::io::Error> = Error::InvalidState {
        required: StateRequirement::Probed,
    };

    assert_eq!(
        transport.source().map(ToString::to_string).as_deref(),
        Some("bus disconnected")
    );
    assert_eq!(
        restore.source().map(ToString::to_string).as_deref(),
        Some("failed to restore")
    );
    assert!(invalid_state.source().is_none());
    assert!(invalid_state.transport_cause().is_none());
}

#[cfg(feature = "hal")]
#[test]
fn embedded_hal_adapter_errors_preserve_source_and_descriptive_message() {
    use adxl355::hal::AdapterError;

    let backend = AdapterError::Backend("spi timeout");
    assert_eq!(
        backend.to_string(),
        "embedded-hal backend error: spi timeout"
    );
    assert_eq!(backend.backend_cause(), Some(&"spi timeout"));

    let oversized: AdapterError<&str> = AdapterError::PayloadTooLong {
        requested: 12,
        maximum: 11,
    };
    assert_eq!(
        oversized.to_string(),
        "adapter payload too long: requested 12 bytes, maximum 11"
    );
    assert!(oversized.backend_cause().is_none());
}

#[cfg(all(feature = "hal", feature = "std"))]
#[test]
fn embedded_hal_std_error_source_retains_backend() {
    use adxl355::hal::AdapterError;
    use std::error::Error as StdError;

    let backend: AdapterError<std::io::Error> =
        AdapterError::Backend(std::io::Error::other("spi timeout"));
    let oversized: AdapterError<std::io::Error> = AdapterError::PayloadTooLong {
        requested: 12,
        maximum: 11,
    };
    assert_eq!(
        backend.source().map(ToString::to_string).as_deref(),
        Some("spi timeout")
    );
    assert!(oversized.source().is_none());
}
