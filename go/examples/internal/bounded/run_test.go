package bounded

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/oaslananka/adxl355/go/adxl355"
)

type fixtureTransport struct {
	regs       [128]byte
	readCount  int
	writeCount int
}

func newFixtureTransport(ready bool) *fixtureTransport {
	fixture := &fixtureTransport{}
	fixture.regs[adxl355.RegDEVID_AD] = adxl355.DEVID_AD_VALUE
	fixture.regs[adxl355.RegDEVID_MST] = adxl355.DEVID_MST_VALUE
	fixture.regs[adxl355.RegPARTID] = adxl355.PARTID_VALUE
	fixture.regs[adxl355.RegRANGE] = byte(adxl355.Range2G)
	fixture.regs[adxl355.RegPOWER_CTL] = byte(adxl355.PowerMeasurement)
	fixture.regs[adxl355.RegTEMP2] = 0x07
	fixture.regs[adxl355.RegTEMP1] = 0x5D
	if ready {
		fixture.regs[adxl355.RegSTATUS] = 1 << adxl355.StatusDATA_RDY
	}
	fixture.setRaw(100, -200, 300)
	return fixture
}

func (f *fixtureTransport) ReadRegister(reg byte, length int) ([]byte, error) {
	f.readCount++
	if reg == adxl355.RegTEMP2 && f.regs[adxl355.RegPOWER_CTL]&0x01 != 0 {
		return make([]byte, length), nil
	}
	return append([]byte(nil), f.regs[int(reg):int(reg)+length]...), nil
}

func (f *fixtureTransport) WriteRegister(reg byte, data []byte) error {
	f.writeCount++
	copy(f.regs[int(reg):], data)
	return nil
}

func (*fixtureTransport) DelayMs(uint32) {}

func (f *fixtureTransport) setRaw(x, y, z int32) {
	encode := func(value int32, register byte) {
		unsigned := uint32(value) & 0xFFFFF
		f.regs[register] = byte(unsigned >> 12)
		f.regs[register+1] = byte(unsigned >> 4)
		f.regs[register+2] = byte(unsigned << 4)
	}
	encode(x, adxl355.RegXDATA3)
	encode(y, adxl355.RegYDATA3)
	encode(z, adxl355.RegZDATA3)
}

func TestRunIsBoundedAndRestoresStandby(t *testing.T) {
	fixture := newFixtureTransport(true)
	var output bytes.Buffer
	if err := Run(context.Background(), adxl355.New(fixture), 2, &output); err != nil {
		t.Fatalf("Run failed: %v", err)
	}
	text := output.String()
	for _, expected := range []string{
		"identity_ok=true",
		"temperature_c=25.0000",
		"sample=1 raw_x=100 raw_y=-200 raw_z=300",
		"sample=2 raw_x=100 raw_y=-200 raw_z=300",
	} {
		if !strings.Contains(text, expected) {
			t.Fatalf("output missing %q:\n%s", expected, text)
		}
	}
	if fixture.regs[adxl355.RegPOWER_CTL]&0x01 == 0 {
		t.Fatal("Run must restore standby")
	}
}

func TestRunHonorsOverallContextTimeout(t *testing.T) {
	fixture := newFixtureTransport(false)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Millisecond)
	defer cancel()
	err := Run(ctx, adxl355.New(fixture), 1, &bytes.Buffer{})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("Run error = %v, want context deadline", err)
	}
	if fixture.regs[adxl355.RegPOWER_CTL]&0x01 == 0 {
		t.Fatal("timeout path must restore standby")
	}
}

func TestRunRejectsCancelledContextBeforeTransportAccess(t *testing.T) {
	fixture := newFixtureTransport(true)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := Run(ctx, adxl355.New(fixture), 1, &bytes.Buffer{})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("Run error = %v, want context canceled", err)
	}
	if fixture.readCount != 0 || fixture.writeCount != 0 {
		t.Fatalf("cancelled run touched transport: reads=%d writes=%d", fixture.readCount, fixture.writeCount)
	}
}

type failingWriter struct {
	writes int
}

func (w *failingWriter) Write(data []byte) (int, error) {
	w.writes++
	if w.writes >= 3 {
		return 0, errors.New("output unavailable")
	}
	return len(data), nil
}

func TestRunRestoresStandbyWhenSampleOutputFails(t *testing.T) {
	fixture := newFixtureTransport(true)
	err := Run(context.Background(), adxl355.New(fixture), 1, &failingWriter{})
	if err == nil || !strings.Contains(err.Error(), "write sample 1") {
		t.Fatalf("Run error = %v, want sample output failure", err)
	}
	if fixture.regs[adxl355.RegPOWER_CTL]&0x01 == 0 {
		t.Fatal("output failure path must restore standby")
	}
}
