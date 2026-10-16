//! CodSpeed benchmarks for the ADXL355 Rust driver.
//!
//! All benchmarks run against an in-memory register-file transport, so they
//! measure driver CPU cost (framing, validation, decode, and conversion) and
//! never touch real hardware.

use adxl355::registers::{self, Range};
use adxl355::{decode_raw20, raw_to_g, raw_to_mps2, Adxl355, PowerMode, Transport};
use core::convert::Infallible;
use divan::{black_box, Bencher};

fn main() {
    divan::main();
}

/// Number of samples used by the batch decode/conversion benchmarks.
const BATCH_SAMPLES: usize = 1024;

/// In-memory register file emulating a healthy ADXL355.
struct MockBus {
    regs: [u8; 128],
}

impl MockBus {
    fn new() -> Self {
        let mut bus = MockBus { regs: [0; 128] };
        bus.regs[registers::reg::DEVID_AD as usize] = registers::id::DEVID_AD;
        bus.regs[registers::reg::DEVID_MST as usize] = registers::id::DEVID_MST;
        bus.regs[registers::reg::PARTID as usize] = registers::id::PARTID;
        bus.regs[registers::reg::RANGE as usize] = Range::G2.to_register();
        // Nominal 25 degC temperature sample (1885 LSB).
        bus.regs[registers::reg::TEMP2 as usize] = 0x07;
        bus.regs[registers::reg::TEMP1 as usize] = 0x5D;
        bus.set_xyz_raw(123_456, -98_765, 256_000);
        bus
    }

    fn set_xyz_raw(&mut self, x: i32, y: i32, z: i32) {
        for (value, base) in [
            (x, registers::reg::XDATA3),
            (y, registers::reg::YDATA3),
            (z, registers::reg::ZDATA3),
        ] {
            let bytes = encode_raw20(value);
            let base = base as usize;
            self.regs[base..base + 3].copy_from_slice(&bytes);
        }
    }
}

impl Transport for MockBus {
    type Error = Infallible;

    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Self::Error> {
        let start = reg as usize;
        Ok(self.regs[start..start + len as usize].to_vec())
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Self::Error> {
        let start = reg as usize;
        for (i, &b) in data.iter().enumerate() {
            if start + i < self.regs.len() {
                self.regs[start + i] = b;
            }
        }
        if reg == registers::reg::RESET && data.first() == Some(&registers::RESET_CODE) {
            self.regs[registers::reg::RANGE as usize] = Range::G2.to_register();
        }
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {}
}

fn encode_raw20(value: i32) -> [u8; 3] {
    let v = (value as u32) & 0xF_FFFF;
    [
        ((v >> 12) & 0xFF) as u8,
        ((v >> 4) & 0xFF) as u8,
        ((v & 0x0F) << 4) as u8,
    ]
}

/// Deterministic spread of raw samples covering the full signed 20-bit range.
fn raw_samples() -> Vec<i32> {
    (0..BATCH_SAMPLES)
        .map(|i| {
            let step = (1 << 20) / BATCH_SAMPLES as i32;
            -524_288 + i as i32 * step + (i as i32 % 7)
        })
        .collect()
}

fn probed_device() -> Adxl355<MockBus> {
    let mut dev = Adxl355::new(MockBus::new());
    dev.probe().expect("mock probe must succeed");
    dev
}

// ---------------------------------------------------------------------------
// Stateless decode / conversion helpers
// ---------------------------------------------------------------------------

mod stateless {
    use super::*;

    #[divan::bench]
    fn decode_raw20_batch(bencher: Bencher) {
        let frames: Vec<[u8; 3]> = raw_samples().into_iter().map(encode_raw20).collect();
        bencher.bench_local(|| {
            let mut acc = 0i64;
            for frame in black_box(&frames) {
                acc += decode_raw20(frame[0], frame[1], frame[2]) as i64;
            }
            acc
        });
    }

    #[divan::bench(args = [Range::G2, Range::G4, Range::G8])]
    fn raw_to_g_batch(bencher: Bencher, range: Range) {
        let samples = raw_samples();
        bencher.bench_local(|| {
            let mut acc = 0f32;
            for &raw in black_box(&samples) {
                acc += raw_to_g(raw, black_box(range));
            }
            acc
        });
    }

    #[divan::bench(args = [Range::G2, Range::G4, Range::G8])]
    fn raw_to_mps2_batch(bencher: Bencher, range: Range) {
        let samples = raw_samples();
        bencher.bench_local(|| {
            let mut acc = 0f32;
            for &raw in black_box(&samples) {
                acc += raw_to_mps2(raw, black_box(range));
            }
            acc
        });
    }
}

// ---------------------------------------------------------------------------
// Device lifecycle and configuration
// ---------------------------------------------------------------------------

mod lifecycle {
    use super::*;

    #[divan::bench]
    fn probe(bencher: Bencher) {
        bencher
            .with_inputs(|| Adxl355::new(MockBus::new()))
            .bench_local_refs(|dev| dev.probe().unwrap());
    }

    /// Software reset followed by the mandatory re-probe.
    #[divan::bench]
    fn reset_and_reprobe(bencher: Bencher) {
        bencher.with_inputs(probed_device).bench_local_refs(|dev| {
            dev.reset().unwrap();
            dev.probe().unwrap()
        });
    }

    #[divan::bench]
    fn set_range_cycle(bencher: Bencher) {
        bencher.with_inputs(probed_device).bench_local_refs(|dev| {
            for range in [Range::G4, Range::G8, Range::G2] {
                dev.set_range(black_box(range)).unwrap();
            }
        });
    }

    #[divan::bench]
    fn get_range(bencher: Bencher) {
        bencher
            .with_inputs(probed_device)
            .bench_local_refs(|dev| dev.get_range().unwrap());
    }

    #[divan::bench]
    fn set_power_mode_cycle(bencher: Bencher) {
        bencher.with_inputs(probed_device).bench_local_refs(|dev| {
            dev.set_power_mode(PowerMode::Measurement).unwrap();
            dev.set_power_mode(PowerMode::Standby).unwrap();
        });
    }
}

// ---------------------------------------------------------------------------
// Data readout through the transport
// ---------------------------------------------------------------------------

mod readout {
    use super::*;

    #[divan::bench]
    fn read_raw(bencher: Bencher) {
        bencher
            .with_inputs(probed_device)
            .bench_local_refs(|dev| dev.read_raw().unwrap());
    }

    #[divan::bench]
    fn read_g(bencher: Bencher) {
        bencher
            .with_inputs(probed_device)
            .bench_local_refs(|dev| dev.read_g().unwrap());
    }

    #[divan::bench]
    fn read_mps2(bencher: Bencher) {
        bencher
            .with_inputs(probed_device)
            .bench_local_refs(|dev| dev.read_mps2().unwrap());
    }

    #[divan::bench]
    fn read_temperature_c(bencher: Bencher) {
        bencher
            .with_inputs(probed_device)
            .bench_local_refs(|dev| dev.read_temperature_c().unwrap());
    }

    #[divan::bench]
    fn read_status(bencher: Bencher) {
        bencher
            .with_inputs(probed_device)
            .bench_local_refs(|dev| dev.read_status().unwrap());
    }

    /// Acquire a burst of samples, as a polling loop would.
    #[divan::bench(args = [64, 1024])]
    fn read_g_burst(bencher: Bencher, samples: usize) {
        bencher.with_inputs(probed_device).bench_local_refs(|dev| {
            let mut acc = 0f32;
            for _ in 0..samples {
                let sample = dev.read_g().unwrap();
                acc += sample.x + sample.y + sample.z;
            }
            acc
        });
    }
}
