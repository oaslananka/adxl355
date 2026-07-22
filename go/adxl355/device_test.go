package adxl355

import (
	"testing"
)

// mockTransport implements Transport for testing.
type mockTransport struct {
	regs [128]byte
}

func newMockTransport() *mockTransport {
	m := &mockTransport{}
	m.regs[RegDEVID_AD] = DEVID_AD_VALUE
	m.regs[RegDEVID_MST] = DEVID_MST_VALUE
	m.regs[RegPARTID] = PARTID_VALUE
	m.regs[RegRANGE] = byte(Range2G)
	return m
}

func (m *mockTransport) ReadRegister(reg byte, length int) ([]byte, error) {
	return m.regs[reg : reg+byte(length)], nil
}

func (m *mockTransport) WriteRegister(reg byte, data []byte) error {
	copy(m.regs[reg:], data)
	if reg == RegRESET && len(data) > 0 && data[0] == RESET_CODE {
		m.regs[RegRANGE] = byte(Range2G)
	}
	return nil
}

func (m *mockTransport) DelayMs(ms uint32) {}

func (m *mockTransport) setRawXYZ(x, y, z int32) {
	encode := func(v int32, base byte) {
		uv := uint32(v) & 0xFFFFF
		m.regs[base] = byte((uv >> 12) & 0xFF)
		m.regs[base+1] = byte((uv >> 4) & 0xFF)
		m.regs[base+2] = byte((uv & 0x0F) << 4)
	}
	encode(x, RegXDATA3)
	encode(y, RegYDATA3)
	encode(z, RegZDATA3)
}

func TestDecodeRaw20(t *testing.T) {
	tests := []struct {
		b0, b1, b2 byte
		expected   int32
	}{
		{0, 0, 0, 0},
		{0, 0, 16, 1},
		{127, 255, 240, 524287},
		{128, 0, 0, -524288},
		{255, 255, 240, -1},
	}

	for _, tt := range tests {
		result := DecodeRaw20(tt.b0, tt.b1, tt.b2)
		if result != tt.expected {
			t.Errorf("DecodeRaw20(%d,%d,%d) = %d, want %d",
				tt.b0, tt.b1, tt.b2, result, tt.expected)
		}
	}
}

func TestRawToG(t *testing.T) {
	g := RawToG(524287, Range2G)
	expected := float32(524287) * Scale2GGPerLSB
	if g != expected {
		t.Errorf("RawToG = %f, want %f", g, expected)
	}
}

func TestRawToMps2(t *testing.T) {
	v := RawToMps2(100000, Range2G)
	expected := float32(100000) * Scale2GGPerLSB * StandardGravityMS2
	if v != expected {
		t.Errorf("RawToMps2 = %f, want %f", v, expected)
	}
}

func TestProbe(t *testing.T) {
	mock := newMockTransport()
	dev := New(mock)
	ok, err := dev.Probe()
	if err != nil {
		t.Fatalf("Probe failed: %v", err)
	}
	if !ok {
		t.Fatal("Probe returned false")
	}
}

func TestNewDefaultsTo2G(t *testing.T) {
	dev := New(newMockTransport())
	if dev.rangeMode != Range2G {
		t.Fatalf("rangeMode = %d, want %d", dev.rangeMode, Range2G)
	}
}

func TestProbeSynchronizesHardwareRange(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegRANGE] = byte(Range8G)
	dev := New(mock)

	ok, err := dev.Probe()
	if err != nil || !ok {
		t.Fatalf("Probe failed: ok=%v err=%v", ok, err)
	}
	if dev.rangeMode != Range8G {
		t.Fatalf("rangeMode = %d, want %d", dev.rangeMode, Range8G)
	}
}

func TestProbeRejectsReservedRange(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegRANGE] = 0
	dev := New(mock)

	ok, err := dev.Probe()
	if ok || err != ErrInvalidArg {
		t.Fatalf("Probe = (%v, %v), want (false, ErrInvalidArg)", ok, err)
	}
	if dev.initialized {
		t.Fatal("failed probe should remain uninitialized")
	}
	if dev.rangeMode != Range2G {
		t.Fatalf("rangeMode = %d, want %d", dev.rangeMode, Range2G)
	}
}

func TestResetRestores2GCache(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegRANGE] = byte(Range8G)
	dev := New(mock)
	if _, err := dev.Probe(); err != nil {
		t.Fatalf("Probe failed: %v", err)
	}

	if err := dev.Reset(); err != nil {
		t.Fatalf("Reset failed: %v", err)
	}
	if dev.rangeMode != Range2G {
		t.Fatalf("rangeMode = %d, want %d", dev.rangeMode, Range2G)
	}
}

func TestResetRangeConvertsRawValueToOneG(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegRANGE] = byte(Range2G)
	mock.setRawXYZ(256410, 0, 0)
	dev := New(mock)
	if _, err := dev.Probe(); err != nil {
		t.Fatalf("Probe failed: %v", err)
	}

	accel, err := dev.ReadG()
	if err != nil {
		t.Fatalf("ReadG failed: %v", err)
	}
	if accel.X < 0.999 || accel.X > 1.001 {
		t.Fatalf("X = %f, want approximately 1g", accel.X)
	}
}

func TestSetRange(t *testing.T) {
	mock := newMockTransport()
	dev := New(mock)
	dev.Probe()

	if err := dev.SetRange(Range8G); err != nil {
		t.Fatalf("SetRange failed: %v", err)
	}

	r, err := dev.GetRange()
	if err != nil {
		t.Fatalf("GetRange failed: %v", err)
	}
	if r != Range8G {
		t.Fatalf("Range = %d, want %d", r, Range8G)
	}
}

func TestReadRaw(t *testing.T) {
	mock := newMockTransport()
	mock.setRawXYZ(100, -200, 300)
	dev := New(mock)
	dev.Probe()

	raw, err := dev.ReadRaw()
	if err != nil {
		t.Fatalf("ReadRaw failed: %v", err)
	}
	if raw.X != 100 || raw.Y != -200 || raw.Z != 300 {
		t.Fatalf("Raw = %+v, want {X:100 Y:-200 Z:300}", raw)
	}
}

type temperatureSequenceTransport struct {
	*mockTransport
	responses [][]byte
}

func (m *temperatureSequenceTransport) ReadRegister(reg byte, length int) ([]byte, error) {
	if reg == RegTEMP2 && len(m.responses) > 0 {
		response := m.responses[0]
		m.responses = m.responses[1:]
		return response, nil
	}
	return m.mockTransport.ReadRegister(reg, length)
}

func TestTemperatureReservedNibbleIgnored(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegTEMP2] = 0xF7
	mock.regs[RegTEMP1] = 0x5D
	raw, err := New(mock).ReadTemperatureRaw()
	if err != nil || raw != 1885 {
		t.Fatalf("ReadTemperatureRaw = (%d, %v), want (1885, nil)", raw, err)
	}
}

func TestTemperatureShortReadReturnsBusError(t *testing.T) {
	transport := &temperatureSequenceTransport{mockTransport: newMockTransport(), responses: [][]byte{{0x07}}}
	_, err := New(transport).ReadTemperatureRaw()
	if err != ErrBus {
		t.Fatalf("short read error = %v, want ErrBus", err)
	}
}

func TestTemperatureRolloverRetry(t *testing.T) {
	transport := &temperatureSequenceTransport{
		mockTransport: newMockTransport(),
		responses:     [][]byte{{0x07, 0xFF}, {0x08}, {0x08, 0x00}, {0x08}},
	}
	raw, err := New(transport).ReadTemperatureRaw()
	if err != nil || raw != 2048 {
		t.Fatalf("rollover read = (%d, %v), want (2048, nil)", raw, err)
	}
}

func TestTemperatureUnstableReturnsNotReady(t *testing.T) {
	transport := &temperatureSequenceTransport{
		mockTransport: newMockTransport(),
		responses:     [][]byte{{0x07, 0xFF}, {0x08}, {0x08, 0xFF}, {0x09}, {0x09, 0xFF}, {0x0A}},
	}
	_, err := New(transport).ReadTemperatureRaw()
	if err != ErrNotReady {
		t.Fatalf("unstable read error = %v, want ErrNotReady", err)
	}
}

func TestTemperatureBoundaries(t *testing.T) {
	mock := newMockTransport()
	dev := New(mock)
	raw, err := dev.ReadTemperatureRaw()
	if err != nil || raw != 0 {
		t.Fatalf("minimum raw = (%d, %v), want (0, nil)", raw, err)
	}

	mock.regs[RegTEMP2] = 0x0F
	mock.regs[RegTEMP1] = 0xFF
	raw, err = dev.ReadTemperatureRaw()
	if err != nil || raw != 4095 {
		t.Fatalf("maximum raw = (%d, %v), want (4095, nil)", raw, err)
	}
	temp, err := dev.ReadTemperatureC()
	if err != nil || temp < -219.21 || temp > -219.19 {
		t.Fatalf("maximum temperature = (%f, %v), want ~-219.1989", temp, err)
	}
}

func TestTemperatureRaw(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegTEMP2] = 0x07
	mock.regs[RegTEMP1] = 0x5D
	dev := New(mock)
	raw, err := dev.ReadTemperatureRaw()
	if err != nil {
		t.Fatalf("ReadTemperatureRaw failed: %v", err)
	}
	if raw != 1885 {
		t.Fatalf("Raw temperature = %d, want 1885", raw)
	}
}

func TestTemperatureCelsiusNominal(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegTEMP2] = 0x07
	mock.regs[RegTEMP1] = 0x5D
	dev := New(mock)
	temp, err := dev.ReadTemperatureC()
	if err != nil {
		t.Fatalf("ReadTemperatureC failed: %v", err)
	}
	if temp < 24.5 || temp > 25.5 {
		t.Fatalf("Temperature = %f, want ~25.0", temp)
	}
}

func TestTemperatureCelsius50C(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegTEMP2] = 0x06
	mock.regs[RegTEMP1] = 0x7B
	dev := New(mock)
	temp, err := dev.ReadTemperatureC()
	if err != nil {
		t.Fatalf("ReadTemperatureC failed: %v", err)
	}
	if temp < 49.5 || temp > 50.5 {
		t.Fatalf("Temperature = %f, want ~50.0", temp)
	}
}

func TestReadStatusAllClear(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegSTATUS] = 0x00
	dev := New(mock)
	status, err := dev.ReadStatus()
	if err != nil {
		t.Fatalf("ReadStatus failed: %v", err)
	}
	if status != 0x00 {
		t.Fatalf("Status = 0x%02X, want 0x00", status)
	}
}

func TestReadStatusDataReady(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegSTATUS] = 0x01
	dev := New(mock)
	status, err := dev.ReadStatus()
	if err != nil {
		t.Fatalf("ReadStatus failed: %v", err)
	}
	if status != 0x01 {
		t.Fatalf("Status = 0x%02X, want 0x01", status)
	}
}

func TestReadStatusFifoFull(t *testing.T) {
	mock := newMockTransport()
	mock.regs[RegSTATUS] = 0x02
	dev := New(mock)
	status, err := dev.ReadStatus()
	if err != nil {
		t.Fatalf("ReadStatus failed: %v", err)
	}
	if status != 0x02 {
		t.Fatalf("Status = 0x%02X, want 0x02", status)
	}
}

func TestFilterDefaultODR(t *testing.T) {
	mock := newMockTransport()
	// Default: FILTER = 0x00
	if mock.regs[RegFILTER]&FilterODR_MASK != 0x00 {
		t.Fatal("Default ODR mask not zero")
	}
	if mock.regs[RegFILTER]&FilterHPF_MASK != 0x00 {
		t.Fatal("Default HPF mask not zero")
	}
}

func TestReset(t *testing.T) {
	mock := newMockTransport()
	dev := New(mock)
	if err := dev.Reset(); err != nil {
		t.Fatalf("Reset failed: %v", err)
	}
	// Verify reset code was written to the register
	if mock.regs[RegRESET] != RESET_CODE {
		t.Fatalf("Reset register = 0x%02X, want 0x%02X", mock.regs[RegRESET], RESET_CODE)
	}
}

func TestHalfScaleDecode(t *testing.T) {
	mock := newMockTransport()
	mock.setRawXYZ(262144, 0, 0)
	dev := New(mock)
	dev.Probe()
	raw, err := dev.ReadRaw()
	if err != nil {
		t.Fatalf("ReadRaw failed: %v", err)
	}
	if raw.X != 262144 {
		t.Fatalf("X = %d, want 262144", raw.X)
	}
}
