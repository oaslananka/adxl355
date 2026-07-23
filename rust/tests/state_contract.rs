use std::cell::RefCell;
use std::rc::Rc;

use adxl355::registers;
use adxl355::{Adxl355, Error, Range, Transport};

#[derive(Debug, Clone, PartialEq, Eq)]
struct Call {
    write: bool,
    reg: u8,
}

struct State {
    regs: [u8; 128],
    calls: Vec<Call>,
    fail_write_reg: Option<u8>,
    fail_write_occurrence: usize,
    matching_writes: usize,
}

impl State {
    fn new() -> Self {
        let mut regs = [0; 128];
        regs[registers::reg::DEVID_AD as usize] = registers::id::DEVID_AD;
        regs[registers::reg::DEVID_MST as usize] = registers::id::DEVID_MST;
        regs[registers::reg::PARTID as usize] = registers::id::PARTID;
        regs[registers::reg::RANGE as usize] = Range::G2.to_register();
        regs[registers::reg::POWER_CTL as usize] = 1;
        Self {
            regs,
            calls: Vec::new(),
            fail_write_reg: None,
            fail_write_occurrence: 0,
            matching_writes: 0,
        }
    }
}

struct StateBus {
    state: Rc<RefCell<State>>,
}

impl Transport for StateBus {
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
        let mut state = self.state.borrow_mut();
        state.calls.push(Call { write: false, reg });
        let start = reg as usize;
        Ok(state.regs[start..start + len as usize].to_vec())
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
        let mut state = self.state.borrow_mut();
        if state.fail_write_reg == Some(reg) {
            state.matching_writes += 1;
            if state.fail_write_occurrence == 0
                || state.matching_writes == state.fail_write_occurrence
            {
                return Err(Error::Bus);
            }
        }
        state.calls.push(Call { write: true, reg });
        for (offset, value) in data.iter().enumerate() {
            state.regs[reg as usize + offset] = *value;
        }
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {}
}

fn probed_device() -> (Adxl355<StateBus>, Rc<RefCell<State>>) {
    let state = Rc::new(RefCell::new(State::new()));
    let mut device = Adxl355::new(StateBus {
        state: Rc::clone(&state),
    });
    device.probe().unwrap();
    (device, state)
}

#[test]
fn pre_probe_operations_fail_without_bus_access() {
    let state = Rc::new(RefCell::new(State::new()));
    let mut device = Adxl355::new(StateBus {
        state: Rc::clone(&state),
    });

    assert_eq!(device.set_range(Range::G4), Err(Error::InvalidState));
    assert_eq!(device.read_status(), Err(Error::InvalidState));
    assert_eq!(device.reset(), Err(Error::InvalidState));
    assert!(state.borrow().calls.is_empty());
}

#[test]
fn range_configuration_restores_measurement_mode() {
    let (mut device, state) = probed_device();
    {
        let mut state = state.borrow_mut();
        state.regs[registers::reg::POWER_CTL as usize] = 0;
        state.calls.clear();
    }

    device.set_range(Range::G4).unwrap();

    let state = state.borrow();
    assert_eq!(state.regs[registers::reg::POWER_CTL as usize], 0);
    assert_eq!(
        state.regs[registers::reg::RANGE as usize],
        Range::G4.to_register()
    );
    let writes: Vec<u8> = state
        .calls
        .iter()
        .filter(|call| call.write)
        .map(|call| call.reg)
        .collect();
    assert_eq!(
        writes,
        vec![
            registers::reg::POWER_CTL,
            registers::reg::RANGE,
            registers::reg::POWER_CTL
        ]
    );
}

#[test]
fn target_failure_restores_measurement_and_preserves_cached_range() {
    let (mut device, state) = probed_device();
    {
        let mut state = state.borrow_mut();
        state.regs[registers::reg::POWER_CTL as usize] = 0;
        state.fail_write_reg = Some(registers::reg::RANGE);
    }

    assert_eq!(device.set_range(Range::G4), Err(Error::Bus));
    assert_eq!(state.borrow().regs[registers::reg::POWER_CTL as usize], 0);

    state.borrow_mut().fail_write_reg = None;
    state.borrow_mut().regs[registers::reg::XDATA3 as usize] = 0x3E;
    state.borrow_mut().regs[(registers::reg::XDATA3 + 1) as usize] = 0x99;
    state.borrow_mut().regs[(registers::reg::XDATA3 + 2) as usize] = 0xA0;
    let acceleration = device.read_g().unwrap();
    assert!((acceleration.x - 1.0).abs() < 0.001);
}

#[test]
fn restore_failure_keeps_successful_range_cache_consistent() {
    let (mut device, state) = probed_device();
    {
        let mut state = state.borrow_mut();
        state.regs[registers::reg::POWER_CTL as usize] = 0;
        state.fail_write_reg = Some(registers::reg::POWER_CTL);
        state.fail_write_occurrence = 2;
    }

    assert_eq!(device.set_range(Range::G4), Err(Error::Bus));
    assert_eq!(state.borrow().regs[registers::reg::POWER_CTL as usize], 1);
    assert_eq!(
        state.borrow().regs[registers::reg::RANGE as usize],
        Range::G4.to_register()
    );

    state.borrow_mut().fail_write_reg = None;
    state.borrow_mut().regs[registers::reg::XDATA3 as usize] = 0x1F;
    state.borrow_mut().regs[(registers::reg::XDATA3 + 1) as usize] = 0x4C;
    state.borrow_mut().regs[(registers::reg::XDATA3 + 2) as usize] = 0xD0;
    let acceleration = device.read_g().unwrap();
    assert!((acceleration.x - 1.0).abs() < 0.001);
}
