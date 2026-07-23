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

func (d *Device) readExact(reg byte, length int) ([]byte, error) {
	data, err := d.transport.ReadRegister(reg, length)
	if err != nil || len(data) != length {
		return nil, ErrBus
	}
	return data, nil
}

func (d *Device) readU8(reg byte) (byte, error) {
	data, err := d.readExact(reg, 1)
	if err != nil {
		return 0, err
	}
	return data[0], nil
}

func (d *Device) writeU8(reg byte, val byte) error {
	if err := d.transport.WriteRegister(reg, []byte{val}); err != nil {
		return ErrBus
	}
	return nil
}

func (d *Device) ensureInitialized() error {
	if !d.initialized {
		return ErrInvalidState
	}
	return nil
}

func (d *Device) enterConfigurationStandby() (byte, bool, error) {
	original, err := d.readU8(RegPOWER_CTL)
	if err != nil {
		return 0, false, err
	}
	if original&0x01 != 0 {
		return original, false, nil
	}
	if err := d.writeU8(RegPOWER_CTL, original|0x01); err != nil {
		return 0, false, err
	}
	return original, true, nil
}

func (d *Device) finishConfiguration(original byte, restore bool, operationErr error) error {
	if restore {
		if err := d.writeU8(RegPOWER_CTL, original); err != nil {
			return err
		}
	}
	return operationErr
}

// ---------------------------------------------------------------------------
// Core API
// ---------------------------------------------------------------------------

// Probe verifies device identity and synchronizes the cached hardware range.
func (d *Device) Probe() (bool, error) {
	d.initialized = false
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

	powerCtl, err := d.readU8(RegPOWER_CTL)
	if err != nil {
		return false, err
	}
	if powerCtl&0x01 == 0 {
		if err := d.writeU8(RegPOWER_CTL, powerCtl|0x01); err != nil {
			return false, err
		}
	}

	d.rangeMode = detectedRange
	d.initialized = true
	return true, nil
}

// Reset performs a software reset.
func (d *Device) Reset() error {
	if err := d.ensureInitialized(); err != nil {
		return err
	}
	if err := d.writeU8(RegRESET, RESET_CODE); err != nil {
		return err
	}
	d.transport.DelayMs(10)
	d.rangeMode = Range2G
	return nil
}

// SetRange sets the acceleration range, preserving unrelated bits.
func (d *Device) SetRange(r Range) error {
	if err := d.ensureInitialized(); err != nil {
		return err
	}
	if r < Range2G || r > Range8G {
		return ErrInvalidArg
	}
	original, restore, err := d.enterConfigurationStandby()
	if err != nil {
		return err
	}

	reg, operationErr := d.readU8(RegRANGE)
	if operationErr == nil {
		reg = (reg &^ RangeSEL_MASK) | byte(r)&RangeSEL_MASK
		operationErr = d.writeU8(RegRANGE, reg)
		if operationErr == nil {
			d.rangeMode = r
		}
	}
	return d.finishConfiguration(original, restore, operationErr)
}

// GetRange reads the currently configured range from hardware.
func (d *Device) GetRange() (Range, error) {
	if err := d.ensureInitialized(); err != nil {
		return 0, err
	}
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
	if err := d.ensureInitialized(); err != nil {
		return err
	}
	if mode != PowerStandby && mode != PowerMeasurement {
		return ErrInvalidArg
	}
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
	if err := d.ensureInitialized(); err != nil {
		return nil, err
	}
	data, err := d.readExact(RegXDATA3, 9)
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

// ReadTemperatureRaw reads a coherent 12-bit unsigned temperature sample.
// TEMP2/TEMP1 are read together, then TEMP2 is re-read to detect high-byte rollover.
func (d *Device) ReadTemperatureRaw() (int16, error) {
	if err := d.ensureInitialized(); err != nil {
		return 0, err
	}
	for attempt := 0; attempt < TempReadAttempts; attempt++ {
		data, err := d.readExact(RegTEMP2, 2)
		if err != nil {
			return 0, err
		}
		confirm, err := d.readExact(RegTEMP2, 1)
		if err != nil {
			return 0, err
		}

		temp2 := data[0] & Temp2DataMask
		if temp2 == confirm[0]&Temp2DataMask {
			return int16(temp2)<<8 | int16(data[1]), nil
		}
	}
	return 0, ErrNotReady
}

// ReadTemperatureC reads temperature in degrees Celsius.
// Datasheet Rev.D: T(°C) = 25.0 + (raw - 1885.0) / -9.05
func (d *Device) ReadTemperatureC() (float32, error) {
	raw, err := d.ReadTemperatureRaw()
	if err != nil {
		return 0, err
	}
	return TempInterceptC + (float32(raw)-TempInterceptLSB)/TempSlopeLSBPerC, nil
}

// ReadStatus reads the status register.
func (d *Device) ReadStatus() (byte, error) {
	if err := d.ensureInitialized(); err != nil {
		return 0, err
	}
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
