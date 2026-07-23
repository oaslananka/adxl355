use adxl355::registers::id;
use adxl355::registers::reg;
/// Basic ADXL355 readout example using mock transport.
///
/// Run: cargo run --example basic
use adxl355::{Adxl355, Error, PowerMode, Range};

struct MockBus {
    regs: [u8; 128],
}

impl adxl355::Transport for MockBus {
    fn read_register(&mut self, reg: u8, len: u8) -> Result<Vec<u8>, Error> {
        Ok(self.regs[reg as usize..(reg + len) as usize].to_vec())
    }

    fn write_register(&mut self, reg: u8, data: &[u8]) -> Result<(), Error> {
        for (i, &b) in data.iter().enumerate() {
            self.regs[(reg as usize) + i] = b;
        }
        Ok(())
    }

    fn delay_ms(&mut self, _ms: u32) {}
}

fn main() -> Result<(), Error> {
    let mut bus = MockBus { regs: [0u8; 128] };
    // Set expected ID values for probe to pass
    bus.regs[reg::DEVID_AD as usize] = id::DEVID_AD;
    bus.regs[reg::DEVID_MST as usize] = id::DEVID_MST;
    bus.regs[reg::PARTID as usize] = id::PARTID;

    let mut dev = Adxl355::new(bus);

    if !dev.probe()? {
        eprintln!("Device not found");
        return Ok(());
    }

    dev.set_range(Range::G4)?;
    dev.set_power_mode(PowerMode::Measurement)?;

    let raw = dev.read_raw()?;
    let accel = dev.read_g()?;
    let temp = dev.read_temperature_c()?;

    println!("Raw:   x={:7}  y={:7}  z={:7}", raw.x, raw.y, raw.z);
    println!(
        "Accel: x={:10.6}  y={:10.6}  z={:10.6} g",
        accel.x, accel.y, accel.z
    );
    println!("Temp:  {:.2} °C", temp);

    Ok(())
}
