package adxl355

// Device is the ADXL355 accelerometer driver.
type Device struct {
	transport   Transport
	rangeMode   Range
	initialized bool
}

// New creates a new ADXL355 device instance.
func New(transport Transport) *Device {
	return &Device{
		transport:   transport,
		rangeMode:   Range2G,
		initialized: false,
	}
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

func (d *Device) readU8(reg byte) (byte, error) {
	data, err := d.transport.ReadRegister(reg, 1)
	if err != nil {
		return 0, err
	}
	return data[0], nil
}

func (d *Device) writeU8(reg byte, val byte) error {
	return d.transport.WriteRegister(reg, []byte{val})
}

// ---------------------------------------------------------------------------
// Core API
// ---------------------------------------------------------------------------

// Probe verifies device identity and synchronizes the cached hardware range.
func (d *Device) Probe() (bool, error) {
	idAd, err := d.readU8(RegDEVID_AD)
	if err != nil {
		return false, err
	}
	idMst, err := d.readU8(RegDEVID_MST)
	if err != nil {
		return false, err
	}
	partId, err := d.readU8(RegPARTID)
	if err != nil {
		return false, err
	}

	if idAd != DEVID_AD_VALUE || idMst != DEVID_MST_VALUE || partId != PARTID_VALUE {
		return false, ErrBadDevice
	}

	rangeValue, err := d.readU8(RegRANGE)
	if err != nil {
		return false, err
	}
	detectedRange := Range(rangeValue & RangeSEL_MASK)
	if detectedRange < Range2G || detectedRange > Range8G {
		return false, ErrInvalidArg
	}

	// Enter standby mode after probe. Commit state only after all bus operations succeed.
	if err := d.writeU8(RegPOWER_CTL, byte(PowerStandby)); err != nil {
		return false, err
	}

	d.rangeMode = detectedRange
	d.initialized = true
	return true, nil
}

// Reset performs a software reset.
func (d *Device) Reset() error {
	if err := d.writeU8(RegRESET, RESET_CODE); err != nil {
		return err
	}
	d.transport.DelayMs(10)
	d.rangeMode = Range2G
	return nil
}

// SetRange sets the acceleration range, preserving unrelated bits.
func (d *Device) SetRange(r Range) error {
	if r < Range2G || r > Range8G {
		return ErrInvalidArg
	}
	reg, err := d.readU8(RegRANGE)
	if err != nil {
		return err
	}
	reg = (reg &^ RangeSEL_MASK) | byte(r)&RangeSEL_MASK
	if err := d.writeU8(RegRANGE, reg); err != nil {
		return err
	}
	d.rangeMode = r
	return nil
}

// GetRange reads the currently configured range from hardware.
func (d *Device) GetRange() (Range, error) {
	val, err := d.readU8(RegRANGE)
	if err != nil {
		return 0, err
	}
	r := Range(val & RangeSEL_MASK)
	if r < Range2G || r > Range8G {
		return 0, ErrInvalidArg
	}
	return r, nil
}

// SetPowerMode sets the power mode (standby/measurement).
// Datasheet Rev.D, Table 43: bit 0 = 1 => standby, bit 0 = 0 => measurement.
func (d *Device) SetPowerMode(mode PowerMode) error {
	reg, err := d.readU8(RegPOWER_CTL)
	if err != nil {
		return err
	}
	if mode == PowerStandby {
		reg |= 1
	} else {
		reg &^= 1
	}
	return d.writeU8(RegPOWER_CTL, reg)
}

// ReadRaw reads raw 20-bit acceleration data for all three axes.
func (d *Device) ReadRaw() (*RawXYZ, error) {
	data, err := d.transport.ReadRegister(RegXDATA3, 9)
	if err != nil {
		return nil, err
	}
	return &RawXYZ{
		X: DecodeRaw20(data[0], data[1], data[2]),
		Y: DecodeRaw20(data[3], data[4], data[5]),
		Z: DecodeRaw20(data[6], data[7], data[8]),
	}, nil
}

// ReadG reads acceleration in g.
func (d *Device) ReadG() (*AccelXYZ, error) {
	raw, err := d.ReadRaw()
	if err != nil {
		return nil, err
	}
	scale := rangeToScale(d.rangeMode)
	return &AccelXYZ{
		X: float32(raw.X) * scale,
		Y: float32(raw.Y) * scale,
		Z: float32(raw.Z) * scale,
	}, nil
}

// ReadMps2 reads acceleration in m/s².
func (d *Device) ReadMps2() (*AccelXYZ, error) {
	accel, err := d.ReadG()
	if err != nil {
		return nil, err
	}
	return &AccelXYZ{
		X: accel.X * StandardGravityMS2,
		Y: accel.Y * StandardGravityMS2,
		Z: accel.Z * StandardGravityMS2,
	}, nil
}

// ReadTemperatureRaw reads raw temperature (16-bit).
func (d *Device) ReadTemperatureRaw() (int16, error) {
	data, err := d.transport.ReadRegister(RegTEMP2, 2)
	if err != nil {
		return 0, err
	}
	return int16(data[0])<<8 | int16(data[1]), nil
}

// ReadTemperatureC reads temperature in degrees Celsius.
// Datasheet Rev.D: T(°C) = 25.0 + (raw - 1885.0) / -9.05
func (d *Device) ReadTemperatureC() (float32, error) {
	raw, err := d.ReadTemperatureRaw()
	if err != nil {
		return 0, err
	}
	return 25.0 + (float32(raw)-1885.0)/-9.05, nil
}

// ReadStatus reads the status register.
func (d *Device) ReadStatus() (byte, error) {
	return d.readU8(RegSTATUS)
}

// ---------------------------------------------------------------------------
// Stateless conversion functions
// ---------------------------------------------------------------------------

// DecodeRaw20 decodes three bytes into a 20-bit two's complement integer.
func DecodeRaw20(b0, b1, b2 byte) int32 {
	raw := int32(b0)<<12 | int32(b1)<<4 | int32(b2)>>4
	if raw&0x80000 != 0 {
		raw -= 0x100000
	}
	return raw
}

// RawToG converts a decoded raw value to g.
func RawToG(raw int32, r Range) float32 {
	return float32(raw) * rangeToScale(r)
}

// RawToMps2 converts a decoded raw value to m/s².
func RawToMps2(raw int32, r Range) float32 {
	return float32(raw) * rangeToScale(r) * StandardGravityMS2
}

func rangeToScale(r Range) float32 {
	switch r {
	case Range2G:
		return Scale2GGPerLSB
	case Range4G:
		return Scale4GGPerLSB
	case Range8G:
		return Scale8GGPerLSB
	default:
		return Scale4GGPerLSB
	}
}
