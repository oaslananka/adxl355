package adxl355

import (
	"math"
	"testing"
)

func TestSetPowerModePreservesUnrelatedControlBits(t *testing.T) {
	device, transport := probedStateDevice(t)
	transport.regs[RegPOWER_CTL] = 0x06 | byte(PowerStandby)
	if err := device.SetPowerMode(PowerMeasurement); err != nil {
		t.Fatalf("enter measurement: %v", err)
	}
	if got := transport.regs[RegPOWER_CTL]; got != 0x06 {
		t.Fatalf("measurement control=%#x, want 0x06", got)
	}
	if err := device.SetPowerMode(PowerStandby); err != nil {
		t.Fatalf("enter standby: %v", err)
	}
	if got := transport.regs[RegPOWER_CTL]; got != 0x07 {
		t.Fatalf("standby control=%#x, want 0x07", got)
	}
}

func TestSetPowerModeRejectsInvalidAndUninitializedStates(t *testing.T) {
	transport := newStateTransport()
	device := New(transport)
	if err := device.SetPowerMode(PowerMeasurement); err != ErrInvalidState {
		t.Fatalf("pre-probe power-mode error=%v", err)
	}
	if len(transport.calls) != 0 {
		t.Fatalf("uninitialized device accessed bus: %+v", transport.calls)
	}
	mustProbe(t, device)
	transport.calls = nil
	if err := device.SetPowerMode(PowerMode(0xFF)); err != ErrInvalidArg {
		t.Fatalf("invalid power-mode error=%v", err)
	}
	if len(transport.calls) != 0 {
		t.Fatalf("invalid mode accessed bus: %+v", transport.calls)
	}
}

func TestSetPowerModePropagatesBusErrors(t *testing.T) {
	for _, tc := range []struct {
		name  string
		read  bool
		write bool
	}{
		{name: "read control failure", read: true},
		{name: "write control failure", write: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			transport := newContractTransport()
			device := probedContractDevice(t, transport)
			if tc.read {
				transport.failReadReg = RegPOWER_CTL
			}
			if tc.write {
				transport.failWriteReg = RegPOWER_CTL
			}
			if err := device.SetPowerMode(PowerMeasurement); err != ErrBus {
				t.Fatalf("bus error = %v, want ErrBus", err)
			}
		})
	}
}

func TestReadMps2ConvertsEachAxisAndRejectsUninitialized(t *testing.T) {
	transport := newMockTransport()
	transport.setRawXYZ(1024, -2048, 4096)
	device := New(transport)
	if _, err := device.ReadMps2(); err != ErrInvalidState {
		t.Fatalf("pre-probe m/s² error=%v", err)
	}
	mustProbe(t, device)
	got, err := device.ReadMps2()
	if err != nil {
		t.Fatalf("ReadMps2: %v", err)
	}
	for _, axis := range []struct {
		name   string
		actual float32
		raw    int32
	}{
		{"X", got.X, 1024}, {"Y", got.Y, -2048}, {"Z", got.Z, 4096},
	} {
		want := RawToMps2(axis.raw, Range2G)
		if math.Abs(float64(axis.actual-want)) > 0.00001 {
			t.Errorf("%s = %v, want %v", axis.name, axis.actual, want)
		}
	}
}

func TestGetRangeRejectsInvalidRegisterAndBusFailure(t *testing.T) {
	transport := newContractTransport()
	device := probedContractDevice(t, transport)
	transport.regs[RegRANGE] = 0
	if _, err := device.GetRange(); err != ErrInvalidArg {
		t.Fatalf("reserved range error=%v", err)
	}
	transport.failReadReg = RegRANGE
	if _, err := device.GetRange(); err != ErrBus {
		t.Fatalf("read failure error=%v", err)
	}
}

func TestReadMps2RejectsMalformedFrame(t *testing.T) {
	transport := newContractTransport()
	device := probedContractDevice(t, transport)
	transport.shortReg = RegXDATA3
	transport.shortLength = 8
	if _, err := device.ReadMps2(); err != ErrBus {
		t.Fatalf("malformed frame error=%v", err)
	}
}

func TestRawScaleMatchesAllSupportedRanges(t *testing.T) {
	for _, r := range []Range{Range2G, Range4G, Range8G} {
		if got := RawToG(100, r); got <= 0 {
			t.Errorf("range %d raw scale=%g", r, got)
		}
	}
	if got := rangeToScale(Range(0)); got != Scale4GGPerLSB {
		t.Fatalf("reserved range fallback=%g", got)
	}
}
