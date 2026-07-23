//! ADXL355 — Cross-platform accelerometer driver.
//!
//! Transport-agnostic ADXL355 driver for embedded and desktop Rust.
//! See the `Adxl355` struct for the main driver API.

#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

pub mod device;
pub mod error;
pub mod registers;
pub mod types;

#[cfg(feature = "hal")]
pub mod hal;

pub use device::decode_raw20;
pub use device::raw_to_g;
pub use device::raw_to_mps2;
pub use device::Adxl355;
pub use device::Transport;
pub use error::Error;
pub use registers::Odr;
pub use registers::PowerMode;
pub use registers::Range;
pub use types::{AccelXyz, RawXyz};
