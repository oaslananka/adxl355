#![cfg(feature = "hal")]

use std::cell::RefCell;
use std::rc::Rc;

use adxl355::hal::SpiTransport;
use adxl355::Transport;
use embedded_hal::delay::DelayNs;
use embedded_hal::spi::{ErrorKind, ErrorType, Operation, SpiDevice};

#[derive(Debug, Clone, PartialEq, Eq)]
enum RecordedOperation {
    Read(usize),
    Write(Vec<u8>),
    Transfer { read_len: usize, write: Vec<u8> },
    TransferInPlace(Vec<u8>),
    DelayNs(u32),
}

#[derive(Debug, Default)]
struct Trace {
    transactions: Vec<Vec<RecordedOperation>>,
    read_payload: Vec<u8>,
}

struct FakeSpi {
    trace: Rc<RefCell<Trace>>,
}

impl ErrorType for FakeSpi {
    type Error = ErrorKind;
}

impl SpiDevice for FakeSpi {
    fn transaction(&mut self, operations: &mut [Operation<'_, u8>]) -> Result<(), Self::Error> {
        let read_payload = self.trace.borrow().read_payload.clone();
        let mut recorded = Vec::with_capacity(operations.len());

        for operation in operations {
            match operation {
                Operation::Read(words) => {
                    for (destination, source) in words.iter_mut().zip(read_payload.iter()) {
                        *destination = *source;
                    }
                    recorded.push(RecordedOperation::Read(words.len()));
                }
                Operation::Write(words) => {
                    recorded.push(RecordedOperation::Write(words.to_vec()));
                }
                Operation::Transfer(read, write) => {
                    recorded.push(RecordedOperation::Transfer {
                        read_len: read.len(),
                        write: write.to_vec(),
                    });
                }
                Operation::TransferInPlace(words) => {
                    recorded.push(RecordedOperation::TransferInPlace(words.to_vec()));
                }
                Operation::DelayNs(ns) => recorded.push(RecordedOperation::DelayNs(*ns)),
            }
        }

        self.trace.borrow_mut().transactions.push(recorded);
        Ok(())
    }
}

struct FakeDelay;

impl DelayNs for FakeDelay {
    fn delay_ns(&mut self, _ns: u32) {}
}

#[test]
fn read_register_uses_adxl355_command_and_single_transaction() {
    let trace = Rc::new(RefCell::new(Trace {
        read_payload: vec![0xAA, 0xBB, 0xCC],
        ..Trace::default()
    }));
    let spi = FakeSpi {
        trace: Rc::clone(&trace),
    };
    let mut transport = SpiTransport::new(spi, FakeDelay);

    let payload = transport.read_register(0x08, 3).unwrap();

    assert_eq!(payload, vec![0xAA, 0xBB, 0xCC]);
    assert_eq!(
        trace.borrow().transactions,
        vec![vec![
            RecordedOperation::Write(vec![0x11]),
            RecordedOperation::Read(3),
        ]]
    );
}

#[test]
fn write_register_uses_adxl355_command_and_single_transaction() {
    let trace = Rc::new(RefCell::new(Trace::default()));
    let spi = FakeSpi {
        trace: Rc::clone(&trace),
    };
    let mut transport = SpiTransport::new(spi, FakeDelay);

    transport.write_register(0x2D, &[0x12, 0x34]).unwrap();

    assert_eq!(
        trace.borrow().transactions,
        vec![vec![RecordedOperation::Write(vec![0x5A, 0x12, 0x34])]]
    );
}
