//! Shared transport contract scenarios from spec/transport_contract.json.

use adxl355::registers;
use adxl355::{Adxl355, Error, Range};

struct ContractBus {
    regs: [u8; 128],
    short_reg: Option<u8>,
    short_len: usize,
    fail_read_reg: Option<u8>,
    fail_write_reg: Option<u8>,
}

impl ContractBus {
    fn new() -> Self {
        let mut bus = Self {
            regs: [0; 128],
            short_reg: None,
            short_len: 0,
            fail_read_reg: None,
            fail_write_reg: None,
        };
        bus.regs[registers::reg::DEVID_AD as usize] = registers::id::DEVID_AD;
        bus.regs[registers::reg::DEVID_MST as usize] = registers::id::DEVID_MST;
        bus.regs[registers::reg::PARTID as usize] = registers::id::PARTID;
        bus.regs[registers::reg::RANGE as usize] = Range::G2.to_register();
        bus.regs[registers::reg::POWER_CTL as usize] = 1;
        bus
    }
}

impl adxl355::device::Transport for ContractBus {
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
        if self.fail_read_reg == Some(reg) {
            return Err(Error::InvalidArgument);
        }
        let actual_len = if self.short_reg == Some(reg) {
            self.short_len
        } else {
            len as usize
        };
        let start = reg as usize;
        Ok(self.regs[start..start + actual_len].to_vec())
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
        if self.fail_write_reg == Some(reg) {
            return Err(Error::InvalidArgument);
        }
        let start = reg as usize;
        self.regs[start..start + data.len()].copy_from_slice(data);
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {}
}

#[test]
fn tr_1_zero_is_bus_error() {
    let mut bus = ContractBus::new();
    bus.short_reg = Some(registers::reg::DEVID_AD);
    bus.short_len = 0;
    assert_eq!(Adxl355::new(bus).probe(), Err(Error::Bus));
}

#[test]
fn tr_1_overlong_is_bus_error() {
    let mut bus = ContractBus::new();
    bus.short_reg = Some(registers::reg::DEVID_AD);
    bus.short_len = 2;
    assert_eq!(Adxl355::new(bus).probe(), Err(Error::Bus));
}

#[test]
fn tr_2_zero_and_truncated_are_bus_errors() {
    for returned in [0, 1] {
        let mut bus = ContractBus::new();
        bus.short_reg = Some(registers::reg::TEMP2);
        bus.short_len = returned;
        let mut device = Adxl355::new(bus);
        device.probe().unwrap();
        assert_eq!(device.read_temperature_raw(), Err(Error::Bus));
    }
}

#[test]
fn tr_9_zero_and_truncated_are_bus_errors() {
    for returned in [0, 8] {
        let mut bus = ContractBus::new();
        bus.short_reg = Some(registers::reg::XDATA3);
        bus.short_len = returned;
        let mut device = Adxl355::new(bus);
        device.probe().unwrap();
        assert_eq!(device.read_raw(), Err(Error::Bus));
    }
}

#[test]
fn transport_errors_are_normalized_to_bus() {
    let mut bus = ContractBus::new();
    bus.fail_read_reg = Some(registers::reg::DEVID_AD);
    assert_eq!(Adxl355::new(bus).probe(), Err(Error::Bus));

    let mut bus = ContractBus::new();
    bus.fail_write_reg = Some(registers::reg::RANGE);
    let mut device = Adxl355::new(bus);
    device.probe().unwrap();
    assert_eq!(device.set_range(Range::G4), Err(Error::Bus));
}
