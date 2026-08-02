//! Typed ADXL355 driver and adapter errors.

use core::fmt;

/// Device state required by an operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StateRequirement {
    /// The caller must complete a successful device probe first.
    Probed,
}

impl fmt::Display for StateRequirement {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Probed => write!(f, "a successful probe"),
        }
    }
}

/// Driver error with the underlying transport error preserved as `E`.
///
/// This type is allocation-free and remains usable in `no_std` builds. Match on
/// [`Error::Transport`] or [`Error::Restore`] to inspect and recover the original
/// bus/backend cause.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error<E> {
    /// A read or write failed in the configured transport.
    Transport(E),
    /// Probe returned identity bytes that do not identify an ADXL355.
    InvalidIdentity {
        /// Analog Devices identifier byte read from `DEVID_AD`.
        devid_ad: u8,
        /// MEMS identifier byte read from `DEVID_MST`.
        devid_mst: u8,
        /// Part identifier byte read from `PARTID`.
        partid: u8,
    },
    /// A transport returned a payload whose length violated the exact-length contract.
    InvalidResponseLength {
        /// First register requested by the driver.
        register: u8,
        /// Required payload length.
        expected: usize,
        /// Payload length returned by the transport.
        actual: usize,
    },
    /// The device lifecycle does not permit the requested operation.
    InvalidState {
        /// State that must be established before retrying.
        required: StateRequirement,
    },
    /// A register value does not represent a supported configuration.
    InvalidConfiguration {
        /// Register containing the unsupported value.
        register: u8,
        /// Unsupported raw register value.
        value: u8,
    },
    /// Coherent data was not available within the driver's bounded retry sequence.
    NotReady,
    /// A bounded operation timed out.
    Timeout,
    /// The requested feature is not supported by this implementation.
    Unsupported,
    /// Restoring a previously active hardware state failed.
    Restore(E),
}

impl<E> Error<E> {
    /// Return the preserved transport cause when the error came from bus access.
    pub fn transport_cause(&self) -> Option<&E> {
        match self {
            Self::Transport(source) | Self::Restore(source) => Some(source),
            _ => None,
        }
    }

    /// Return `true` when the failure happened while restoring device state.
    pub const fn is_restore_failure(&self) -> bool {
        matches!(self, Self::Restore(_))
    }
}

impl<E: fmt::Display> fmt::Display for Error<E> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(source) => write!(f, "transport error: {source}"),
            Self::InvalidIdentity {
                devid_ad,
                devid_mst,
                partid,
            } => write!(
                f,
                "invalid ADXL355 identity (DEVID_AD=0x{devid_ad:02X}, DEVID_MST=0x{devid_mst:02X}, PARTID=0x{partid:02X})"
            ),
            Self::InvalidResponseLength {
                register,
                expected,
                actual,
            } => write!(
                f,
                "invalid response length at register 0x{register:02X}: expected {expected}, received {actual}"
            ),
            Self::InvalidState { required } => {
                write!(f, "invalid device state; operation requires {required}")
            }
            Self::InvalidConfiguration { register, value } => write!(
                f,
                "invalid configuration value 0x{value:02X} in register 0x{register:02X}"
            ),
            Self::NotReady => write!(f, "data not ready"),
            Self::Timeout => write!(f, "operation timed out"),
            Self::Unsupported => write!(f, "unsupported operation"),
            Self::Restore(source) => write!(f, "failed to restore device state: {source}"),
        }
    }
}

#[cfg(feature = "std")]
impl<E> std::error::Error for Error<E>
where
    E: std::error::Error + 'static,
{
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Transport(source) | Self::Restore(source) => Some(source),
            _ => None,
        }
    }
}
