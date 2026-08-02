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
