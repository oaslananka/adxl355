//! ADXL355 error types.

use core::fmt;

/// Driver error codes.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Error {
    /// Bus communication error.
    Bus,
    /// Device probe failed (ID mismatch).
    BadDevice,
    /// Invalid argument.
    InvalidArgument,
    /// Operation requires a successful probe or a different device state.
    InvalidState,
    /// Data not ready.
    NotReady,
    /// Operation timed out.
    Timeout,
    /// Feature not supported.
    Unsupported,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Bus => write!(f, "bus communication error"),
            Error::BadDevice => write!(f, "bad device (ID mismatch)"),
            Error::InvalidArgument => write!(f, "invalid argument"),
            Error::InvalidState => write!(f, "invalid device state (call probe first)"),
            Error::NotReady => write!(f, "data not ready"),
            Error::Timeout => write!(f, "timeout"),
            Error::Unsupported => write!(f, "unsupported operation"),
        }
    }
}

#[cfg(feature = "std")]
impl std::error::Error for Error {}
