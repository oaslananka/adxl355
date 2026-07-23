//! Integration tests for ADXL355 device with mock transport.

use adxl355::registers;
use adxl355::{Adxl355, Error, PowerMode};

struct MockBus {
    regs: [u8; 128],
}

impl MockBus {
    fn new() -> Self {
        let mut bus = MockBus { regs: [0; 128] };
        bus.regs[registers::reg::DEVID_AD as usize] = registers::id::DEVID_AD;
        bus.regs[registers::reg::DEVID_MST as usize] = registers::id::DEVID_MST;
        bus.regs[registers::reg::PARTID as usize] = registers::id::PARTID;
        bus.regs[registers::reg::RANGE as usize] = registers::Range::G2.to_register();
        bus
    }
}

impl adxl355::device::Transport for MockBus {
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
        let start = reg as usize;
        let end = start + len as usize;
        Ok(self.regs[start..end].to_vec())
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
        let start = reg as usize;
        for (i, &b) in data.iter().enumerate() {
            if start + i < self.regs.len() {
                self.regs[start + i] = b;
            }
        }
        if reg == registers::reg::RESET && data.first() == Some(&registers::RESET_CODE) {
            self.regs[registers::reg::RANGE as usize] = registers::Range::G2.to_register();
        }
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {}
}

#[test]
fn test_probe_ok() {
    let bus = MockBus::new();
    let mut dev = Adxl355::new(bus);
    assert!(dev.probe().is_ok());
}

#[test]
fn test_set_power_mode() {
    let bus = MockBus::new();
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    assert!(dev.set_power_mode(PowerMode::Measurement).is_ok());
    assert!(dev.set_power_mode(PowerMode::Standby).is_ok());
}

#[test]
fn test_reset() {
    let bus = MockBus::new();
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    assert!(dev.reset().is_ok());
}

struct TemperatureSequenceBus {
    regs: [u8; 128],
    responses: Vec<Vec<u8>>,
}

impl TemperatureSequenceBus {
    fn new(responses: Vec<Vec<u8>>) -> Self {
        let mut bus = Self {
            regs: [0; 128],
            responses,
        };
        bus.regs[registers::reg::DEVID_AD as usize] = registers::id::DEVID_AD;
        bus.regs[registers::reg::DEVID_MST as usize] = registers::id::DEVID_MST;
        bus.regs[registers::reg::PARTID as usize] = registers::id::PARTID;
        bus.regs[registers::reg::RANGE as usize] = registers::Range::G2.to_register();
        bus
    }
}

impl adxl355::device::Transport for TemperatureSequenceBus {
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
        if reg == registers::reg::TEMP2 && !self.responses.is_empty() {
            return Ok(self.responses.remove(0));
        }
        let start = reg as usize;
        let end = start + len as usize;
        Ok(self.regs[start..end].to_vec())
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
        let start = reg as usize;
        self.regs[start..start + data.len()].copy_from_slice(data);
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {}
}

#[test]
fn test_temperature_reserved_nibble_ignored() {
    let mut bus = MockBus::new();
    bus.regs[registers::reg::TEMP2 as usize] = 0xF7;
    bus.regs[registers::reg::TEMP1 as usize] = 0x5D;
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    assert_eq!(dev.read_temperature_raw().unwrap(), 1885);
    assert!((dev.read_temperature_c().unwrap() - 25.0).abs() < 0.01);
}

#[test]
fn test_temperature_short_read_returns_bus_error() {
    let mut dev = Adxl355::new(TemperatureSequenceBus::new(vec![vec![0x07]]));
    dev.probe().unwrap();
    assert_eq!(dev.read_temperature_raw(), Err(Error::Bus));
}

#[test]
fn test_temperature_rollover_is_retried() {
    let mut dev = Adxl355::new(TemperatureSequenceBus::new(vec![
        vec![0x07, 0xFF],
        vec![0x08],
        vec![0x08, 0x00],
        vec![0x08],
    ]));
    dev.probe().unwrap();
    assert_eq!(dev.read_temperature_raw().unwrap(), 2048);
}

#[test]
fn test_temperature_unstable_returns_not_ready() {
    let mut dev = Adxl355::new(TemperatureSequenceBus::new(vec![
        vec![0x07, 0xFF],
        vec![0x08],
        vec![0x08, 0xFF],
        vec![0x09],
        vec![0x09, 0xFF],
        vec![0x0A],
    ]));
    dev.probe().unwrap();
    assert_eq!(dev.read_temperature_raw(), Err(Error::NotReady));
}

#[test]
fn test_temperature_raw() {
    let mut bus = MockBus::new();
    // TEMP2 = 0x07, TEMP1 = 0x5D → 0x075D = 1885 (nominal)
    bus.regs[registers::reg::TEMP2 as usize] = 0x07;
    bus.regs[registers::reg::TEMP1 as usize] = 0x5D;
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    let raw = dev.read_temperature_raw().unwrap();
    assert_eq!(raw, 1885);
}

#[test]
fn test_temperature_boundaries() {
    let mut bus = MockBus::new();
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    assert_eq!(dev.read_temperature_raw().unwrap(), 0);

    bus = dev.into_inner();
    bus.regs[registers::reg::TEMP2 as usize] = 0x0F;
    bus.regs[registers::reg::TEMP1 as usize] = 0xFF;
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    assert_eq!(dev.read_temperature_raw().unwrap(), 4095);
    let temp = dev.read_temperature_c().unwrap();
    assert!((temp - -219.1989).abs() < 0.01);
}

#[test]
fn test_temperature_celsius_nominal() {
    let mut bus = MockBus::new();
    // Raw = 1885 → 25°C
    bus.regs[registers::reg::TEMP2 as usize] = 0x07;
    bus.regs[registers::reg::TEMP1 as usize] = 0x5D;
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    let temp = dev.read_temperature_c().unwrap();
    assert!((temp - 25.0).abs() < 0.1);
}

#[test]
fn test_temperature_celsius_fifty() {
    let mut bus = MockBus::new();
    // 50°C → raw = 1885 - 25 * 9.05 ≈ 1659 = 0x067B
    bus.regs[registers::reg::TEMP2 as usize] = 0x06;
    bus.regs[registers::reg::TEMP1 as usize] = 0x7B;
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    let temp = dev.read_temperature_c().unwrap();
    assert!((temp - 50.0).abs() < 0.5);
}

#[test]
fn test_read_status_all_clear() {
    let mut bus = MockBus::new();
    bus.regs[registers::reg::STATUS as usize] = 0x00;
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    let status = dev.read_status().unwrap();
    assert_eq!(status, 0x00);
}

#[test]
fn test_read_status_data_ready() {
    let mut bus = MockBus::new();
    bus.regs[registers::reg::STATUS as usize] = 0x01; // DATA_RDY bit
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    let status = dev.read_status().unwrap();
    assert_eq!(status, 0x01);
}

#[test]
fn test_read_status_fifo_full() {
    let mut bus = MockBus::new();
    bus.regs[registers::reg::STATUS as usize] = 0x02; // FIFO_FULL bit
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    let status = dev.read_status().unwrap();
    assert_eq!(status, 0x02);
}

#[test]
fn test_filter_default_odr() {
    let bus = MockBus::new();
    let dev = Adxl355::new(bus);
    let inner = dev.into_inner();
    assert_eq!(
        inner.regs[registers::reg::FILTER as usize] & registers::filter::ODR_MASK,
        0x00
    );
    assert_eq!(
        inner.regs[registers::reg::FILTER as usize] & registers::filter::HPF_MASK,
        0x00
    );
}

#[test]
fn test_filter_hpf_preserved() {
    let mut bus = MockBus::new();
    bus.regs[registers::reg::FILTER as usize] = 0x10;
    let dev = Adxl355::new(bus);
    let inner = dev.into_inner();
    assert_eq!(
        inner.regs[registers::reg::FILTER as usize] & registers::filter::HPF_MASK,
        0x10
    );
}

#[test]
fn test_half_scale_decode() {
    let mut bus = MockBus::new();
    bus.regs[registers::reg::XDATA3 as usize] = 0x40;
    bus.regs[registers::reg::XDATA2 as usize] = 0x00;
    bus.regs[registers::reg::XDATA1 as usize] = 0x00;
    bus.regs[registers::reg::DEVID_AD as usize] = registers::id::DEVID_AD;
    bus.regs[registers::reg::DEVID_MST as usize] = registers::id::DEVID_MST;
    bus.regs[registers::reg::PARTID as usize] = registers::id::PARTID;
    let mut dev = Adxl355::new(bus);
    dev.probe().unwrap();
    let raw = dev.read_raw().unwrap();
    assert_eq!(raw.x, 262144);
}
