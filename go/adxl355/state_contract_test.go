package adxl355

import "testing"

type stateCall struct {
	write bool
	reg   byte
}

type stateTransport struct {
	regs                [128]byte
	calls               []stateCall
	failWriteReg        byte
	failWriteEnabled    bool
	failWriteOccurrence int
	matchingWrites      int
}

func newStateTransport() *stateTransport {
	transport := &stateTransport{}
	transport.regs[RegDEVID_AD] = DEVID_AD_VALUE
	transport.regs[RegDEVID_MST] = DEVID_MST_VALUE
	transport.regs[RegPARTID] = PARTID_VALUE
	transport.regs[RegRANGE] = byte(Range2G)
	transport.regs[RegPOWER_CTL] = byte(PowerStandby)
	return transport
}

func (m *stateTransport) ReadRegister(reg byte, length int) ([]byte, error) {
	m.calls = append(m.calls, stateCall{reg: reg})
	result := make([]byte, length)
	copy(result, m.regs[int(reg):int(reg)+length])
	return result, nil
}

func (m *stateTransport) WriteRegister(reg byte, data []byte) error {
	if m.failWriteEnabled && reg == m.failWriteReg {
		m.matchingWrites++
		if m.failWriteOccurrence == 0 || m.matchingWrites == m.failWriteOccurrence {
			return ErrBus
		}
	}
	m.calls = append(m.calls, stateCall{write: true, reg: reg})
	copy(m.regs[reg:], data)
	return nil
}

func (m *stateTransport) DelayMs(_ uint32) {}

func probedStateDevice(t *testing.T) (*Device, *stateTransport) {
	t.Helper()
	transport := newStateTransport()
	device := New(transport)
	if _, err := device.Probe(); err != nil {
		t.Fatalf("Probe failed: %v", err)
	}
	return device, transport
}

func TestPreProbeOperationsFailWithoutBusAccess(t *testing.T) {
	transport := newStateTransport()
	device := New(transport)

	if err := device.SetRange(Range4G); err != ErrInvalidState {
		t.Fatalf("SetRange error = %v, want ErrInvalidState", err)
	}
	if _, err := device.ReadStatus(); err != ErrInvalidState {
		t.Fatalf("ReadStatus error = %v, want ErrInvalidState", err)
	}
	if err := device.Reset(); err != ErrInvalidState {
		t.Fatalf("Reset error = %v, want ErrInvalidState", err)
	}
	if len(transport.calls) != 0 {
		t.Fatalf("pre-probe operations accessed bus: %+v", transport.calls)
	}
}

func TestRangeConfigurationRestoresMeasurementMode(t *testing.T) {
	device, transport := probedStateDevice(t)
	transport.regs[RegPOWER_CTL] = byte(PowerMeasurement)
	transport.calls = nil

	if err := device.SetRange(Range4G); err != nil {
		t.Fatalf("SetRange failed: %v", err)
	}
	if transport.regs[RegPOWER_CTL] != byte(PowerMeasurement) {
		t.Fatal("measurement mode was not restored")
	}
	writes := make([]byte, 0)
	for _, call := range transport.calls {
		if call.write {
			writes = append(writes, call.reg)
		}
	}
	want := []byte{RegPOWER_CTL, RegRANGE, RegPOWER_CTL}
	if len(writes) != len(want) {
		t.Fatalf("writes = %v, want %v", writes, want)
	}
	for i := range want {
		if writes[i] != want[i] {
			t.Fatalf("writes = %v, want %v", writes, want)
		}
	}
}

func TestRangeTargetFailureRestoresMeasurementAndCache(t *testing.T) {
	device, transport := probedStateDevice(t)
	transport.regs[RegPOWER_CTL] = byte(PowerMeasurement)
	transport.failWriteEnabled = true
	transport.failWriteReg = RegRANGE

	if err := device.SetRange(Range4G); err != ErrBus {
		t.Fatalf("SetRange error = %v, want ErrBus", err)
	}
	if transport.regs[RegPOWER_CTL] != byte(PowerMeasurement) {
		t.Fatal("measurement mode was not restored")
	}
	if device.rangeMode != Range2G || transport.regs[RegRANGE] != byte(Range2G) {
		t.Fatalf("range cache/hardware changed: cache=%v hardware=%v", device.rangeMode, transport.regs[RegRANGE])
	}
}

func TestRangeRestoreFailureKeepsCacheConsistent(t *testing.T) {
	device, transport := probedStateDevice(t)
	transport.regs[RegPOWER_CTL] = byte(PowerMeasurement)
	transport.failWriteEnabled = true
	transport.failWriteReg = RegPOWER_CTL
	transport.failWriteOccurrence = 2

	if err := device.SetRange(Range4G); err != ErrBus {
		t.Fatalf("SetRange error = %v, want ErrBus", err)
	}
	if transport.regs[RegPOWER_CTL] != byte(PowerStandby) {
		t.Fatal("failed restore should leave hardware in standby")
	}
	if device.rangeMode != Range4G || transport.regs[RegRANGE] != byte(Range4G) {
		t.Fatalf("range cache/hardware mismatch: cache=%v hardware=%v", device.rangeMode, transport.regs[RegRANGE])
	}
}
